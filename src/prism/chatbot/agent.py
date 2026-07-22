"""Chatbot agent — LLM-powered tool-use loop over Prism's MCP tools.

The agent:

1. Starts an in-memory Prism MCP server (same as ``prism serve`` but
   without the HTTP transport).
2. Connects a FastMCP client to it (in-memory, no network).
3. Discovers all registered tools via ``client.list_tools()``.
4. Converts the MCP tool schemas to OpenAI function-calling format.
5. Sends the user's message to the LLM API (OpenAI-compatible
   ``/chat/completions`` endpoint).
6. If the LLM responds with tool calls, executes them via the MCP client
   and feeds the results back.
7. Repeats until the LLM produces a final text response (no tool calls).

The agent uses ``httpx`` directly — no ``openai`` Python SDK dependency
needed. Any OpenAI-compatible API works (OpenAI, Azure OpenAI, vLLM,
Ollama with ``/v1/``, LM Studio, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from fastmcp import Client

from prism.chatbot.skills import load_skills
from prism.mcp.server import create_mcp
from prism.settings import settings

logger = logging.getLogger("prism.chatbot")

# -- ANSI colour helpers for terminal output ---------------------------------

_ANSI_RESET = "\x1b[0m"
_ANSI_BOLD = "\x1b[1m"
_ANSI_DIM = "\x1b[2m"
_ANSI_CYAN = "\x1b[36m"
_ANSI_YELLOW = "\x1b[33m"
_ANSI_GREEN = "\x1b[32m"
_ANSI_RED = "\x1b[31m"

# Hard limit on the number of tool-call rounds to prevent infinite loops.
_MAX_ITERATIONS = 25


def _build_system_prompt(tools_summary: str, skills_text: str) -> str:
    """Build the system prompt for the LLM.

    Includes:
    - Prism's base instructions (from the MCP server)
    - A summary of available tools
    - Optional skill files content
    """
    parts: list[str] = [
        "You are Prism Chatbot, an AI assistant with access to InterSystems IRIS",
        "development tools. You help users query databases, manage documents,",
        "run ObjectScript, execute tests, and inspect server state by calling",
        "the available tools.\n",
        "## Available tools\n",
        tools_summary,
        "\n## How to use tools\n",
        "- Call tools when you need data or need to perform an action on IRIS.",
        "- You may call multiple tools in a single response if the calls are independent.",
        "- After receiving tool results, analyse them and decide whether more calls are needed.",
        "- When you have the final answer, respond with a clear, concise summary in natural language.",
        "- If a tool returns an error, explain the issue and suggest a fix.\n",
    ]

    if skills_text:
        parts.append(skills_text)
        parts.append("")

    return "\n".join(parts)


def _tools_to_openai_format(tools: list[Any]) -> list[dict[str, Any]]:
    """Convert MCP ``Tool`` objects to OpenAI function-calling format.

    Each tool becomes::

        {
            "type": "function",
            "function": {
                "name": "<tool_name>",
                "description": "<tool_description>",
                "parameters": {<JSON schema>}
            }
        }
    """
    result: list[dict[str, Any]] = []
    for tool in tools:
        schema = (
            tool.inputSchema
            if tool.inputSchema
            else {"type": "object", "properties": {}}
        )
        # Ensure the schema has the required OpenAI fields
        if "type" not in schema:
            schema["type"] = "object"
        if "properties" not in schema:
            schema["properties"] = {}
        entry = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": schema,
            },
        }
        result.append(entry)
    return result


def _tools_summary(tools: list[Any]) -> str:
    """Build a compact text summary of tools for the system prompt."""
    lines: list[str] = []
    for tool in tools:
        desc = tool.description or ""
        # First sentence only for brevity
        first_sentence = desc.split("\n")[0] if desc else ""
        if len(first_sentence) > 100:
            first_sentence = first_sentence[:97] + "..."
        lines.append(f"- **{tool.name}**: {first_sentence}")
    return "\n".join(lines)


def _extract_tool_result_text(result: Any) -> str:
    """Extract a text representation from a CallToolResult.

    Handles structured content, text content blocks, and raw data.
    """
    # CallToolResult has .data, .content, .structured_content, .is_error
    if result.is_error:
        # Return error content
        texts: list[str] = []
        for block in result.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return f"Error: {', '.join(texts)}" if texts else "Error: tool execution failed"

    # Prefer structured content if available (dict)
    if result.structured_content:
        return json.dumps(result.structured_content, indent=2, default=str)

    # Fall back to text content blocks
    texts = []
    for block in result.content:
        if hasattr(block, "text"):
            texts.append(block.text)
    if texts:
        return "\n".join(texts)

    # Last resort: data attribute
    if result.data is not None:
        return json.dumps(result.data, indent=2, default=str)

    return "(no output)"


class ChatbotAgent:
    """An LLM-powered agent that orchestrates Prism MCP tools.

    Parameters are resolved from settings (which already incorporates
    env vars, ``.env``, and ``config.json``) but can be overridden via
    the constructor for CLI flag overrides.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        skills_path: str | None = None,
    ) -> None:
        self.api_url = (api_url or settings.chatbot_api_url or "").rstrip("/")
        self.api_key = api_key or settings.chatbot_api_key or ""
        self.model = model or settings.chatbot_model or "gpt-4o"
        self.skills_path = skills_path or settings.chatbot_skills_path or ""

        if not self.api_url:
            raise ValueError(
                "No chatbot API URL configured. Set it with:\n"
                "  prism config --chatbot-api-url <url>\n"
                "  CHATBOT_API_URL=<url> prism chatbot\n"
                "  prism chatbot --api-url <url>"
            )
        if not self.api_key:
            raise ValueError(
                "No chatbot API key configured. Set it with:\n"
                "  prism config --chatbot-api-key <key>\n"
                "  CHATBOT_API_KEY=<key> prism chatbot\n"
                "  prism chatbot --api-key <key>"
            )

    async def run(self, user_message: str) -> str:
        """Send *user_message* to the LLM and run the tool-use loop.

        Returns the final assistant text response.
        """
        # Build the MCP server and connect in-memory
        mcp_server = create_mcp()
        client = Client(mcp_server)

        async with client:
            # Discover available tools
            mcp_tools = await client.list_tools()
            openai_tools = _tools_to_openai_format(mcp_tools)
            tools_summary = _tools_summary(mcp_tools)

            # Load skill files (if configured)
            skills_text = load_skills(self.skills_path)

            # Build system prompt
            system_prompt = _build_system_prompt(tools_summary, skills_text)

            # Message history for the conversation
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            http_client = httpx.AsyncClient(timeout=120.0)

            try:
                for iteration in range(_MAX_ITERATIONS):
                    # Call the LLM
                    response = await self._call_llm(http_client, messages, openai_tools)

                    assistant_msg = response["choices"][0]["message"]

                    # Check if the LLM wants to call tools
                    tool_calls = assistant_msg.get("tool_calls")

                    if not tool_calls:
                        # No tool calls — final answer
                        content = assistant_msg.get("content", "")
                        return content or "(no response)"

                    # Add the assistant's message (with tool calls) to history
                    messages.append(assistant_msg)

                    # Execute each tool call
                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        try:
                            arguments = json.loads(tc["function"]["arguments"])
                        except (json.JSONDecodeError, KeyError):
                            arguments = {}

                        print(
                            f"{_ANSI_DIM}  → calling {tool_name}"
                            f"({_ANSI_RESET}{_ANSI_YELLOW}{json.dumps(arguments, default=str)}{_ANSI_DIM})..."
                            f"{_ANSI_RESET}",
                            flush=True,
                        )

                        try:
                            result = await client.call_tool(tool_name, arguments)
                            result_text = _extract_tool_result_text(result)

                            # Truncate very long results to avoid blowing the context
                            if len(result_text) > 10_000:
                                result_text = result_text[:9_900] + "\n... (truncated)"

                        except Exception as exc:
                            result_text = f"Error calling {tool_name}: {exc}"

                        print(
                            f"{_ANSI_DIM}  ← {tool_name} returned: "
                            f"{len(result_text)} chars{_ANSI_RESET}",
                            flush=True,
                        )

                        # Add the tool result to the conversation
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": tool_name,
                                "content": result_text,
                            }
                        )

                # Exceeded max iterations
                logger.warning(
                    "Agent reached max iterations (%d) without a final response",
                    _MAX_ITERATIONS,
                )
                return (
                    "I reached the maximum number of tool-call iterations "
                    f"({_MAX_ITERATIONS}) without producing a final answer. "
                    "Please refine your request."
                )
            finally:
                await http_client.aclose()

    async def _call_llm(
        self,
        http_client: httpx.AsyncClient,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Send a chat completion request to the OpenAI-compatible API.

        Returns the parsed JSON response.
        """
        endpoint = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await http_client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
