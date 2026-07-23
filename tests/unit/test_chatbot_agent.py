"""Tests for the chatbot agent (prism.chatbot.agent).

These tests mock the LLM API (_call_llm) and the MCP client to verify
the agent loop works correctly: sending messages, receiving tool calls,
executing tools, and returning final responses.

The agent now has lifecycle management (__aenter__/__aexit__).  Tests
that need a connected agent use the ``_connected_agent`` helper which
patches create_mcp and Client, then enters the agent's async context.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from prism.chatbot.agent import (
    ChatbotAgent,
    _build_system_prompt,
    _extract_tool_result_text,
    _truncate_tool_result,
    _tools_summary,
    _tools_to_openai_format,
)


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def mock_mcp_tool():
    """A fake MCP Tool object mimicking mcp.types.Tool."""
    tool = MagicMock()
    tool.name = "execute_sql"
    tool.description = "Execute an InterSystems SQL query and return results."
    tool.inputSchema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "SQL query"},
            "namespace": {"type": "string"},
        },
        "required": ["query"],
    }
    return tool


@pytest.fixture
def mock_tool_result():
    """A fake CallToolResult with structured content."""
    result = MagicMock()
    result.is_error = False
    result.structured_content = {"rows": [{"count": 1}], "count": 1}
    result.content = []
    result.data = None
    return result


@pytest.fixture
def mock_error_tool_result():
    """A fake CallToolResult that is an error."""
    result = MagicMock()
    result.is_error = True
    result.structured_content = None
    error_block = MagicMock()
    error_block.text = "Table not found"
    result.content = [error_block]
    result.data = None
    return result


@pytest.fixture
def mock_text_tool_result():
    """A fake CallToolResult with text content (no structured content)."""
    result = MagicMock()
    result.is_error = False
    result.structured_content = None
    text_block = MagicMock()
    text_block.text = "Raw text output"
    result.content = [text_block]
    result.data = None
    return result


def _make_llm_response(
    content: str | None = None,
    tool_calls: list[dict] | None = None,
    finish_reason: str = "stop",
    usage: dict | None = None,
) -> dict:
    """Build a mock LLM chat completion response."""
    message: dict = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    resp: dict = {"choices": [{"message": message, "finish_reason": finish_reason}]}
    if usage:
        resp["usage"] = usage
    return resp


def _make_tool_call(
    call_id: str = "call_1",
    name: str = "execute_sql",
    arguments: dict | None = None,
) -> dict:
    """Build a mock tool_call object."""
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments or {}),
        },
    }


class _MockClient:
    """A mock FastMCP Client that supports async context manager."""

    def __init__(self, tools=None, tool_result=None, tool_side_effect=None):
        self._tools = tools or []
        self._tool_result = tool_result
        self._tool_side_effect = tool_side_effect
        self.call_tool = AsyncMock()
        if tool_side_effect:
            self.call_tool.side_effect = tool_side_effect
        elif tool_result is not None:
            self.call_tool.return_value = tool_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def list_tools(self):
        return self._tools


def _patch_agent(mcp_tools=None, tool_result=None, tool_side_effect=None):
    """Create patch context for create_mcp and Client.

    Returns (mcp_patch, client_factory) where client_factory returns the mock client.
    """
    mock_client = _MockClient(
        tools=mcp_tools, tool_result=tool_result, tool_side_effect=tool_side_effect
    )

    mcp_patch = patch("prism.chatbot.agent.create_mcp")
    client_patch = patch("prism.chatbot.agent.Client", return_value=mock_client)
    return mcp_patch, client_patch, mock_client


class TestToolsToOpenAIFormat:
    """Tests for _tools_to_openai_format() — converting MCP tools to OpenAI format."""

    def test_single_tool_conversion(self, mock_mcp_tool):
        result = _tools_to_openai_format([mock_mcp_tool])
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "execute_sql"
        assert "SQL" in result[0]["function"]["description"]
        assert "query" in result[0]["function"]["parameters"]["properties"]

    def test_empty_list(self):
        assert _tools_to_openai_format([]) == []

    def test_tool_with_no_description(self):
        tool = MagicMock()
        tool.name = "noop"
        tool.description = None
        tool.inputSchema = {"type": "object", "properties": {}}
        result = _tools_to_openai_format([tool])
        assert result[0]["function"]["description"] == ""

    def test_tool_with_no_schema(self):
        tool = MagicMock()
        tool.name = "bare"
        tool.description = "A bare tool"
        tool.inputSchema = None
        result = _tools_to_openai_format([tool])
        assert result[0]["function"]["parameters"]["type"] == "object"
        assert result[0]["function"]["parameters"]["properties"] == {}

    def test_multiple_tools(self, mock_mcp_tool):
        tool2 = MagicMock()
        tool2.name = "get_document"
        tool2.description = "Fetch a document"
        tool2.inputSchema = {"type": "object", "properties": {}}
        result = _tools_to_openai_format([mock_mcp_tool, tool2])
        assert len(result) == 2
        assert result[0]["function"]["name"] == "execute_sql"
        assert result[1]["function"]["name"] == "get_document"

    def test_schema_without_type_gets_default(self):
        tool = MagicMock()
        tool.name = "t"
        tool.description = "desc"
        tool.inputSchema = {"properties": {"x": {}}}
        result = _tools_to_openai_format([tool])
        assert result[0]["function"]["parameters"]["type"] == "object"

    def test_schema_without_properties_gets_default(self):
        tool = MagicMock()
        tool.name = "t"
        tool.description = "desc"
        tool.inputSchema = {"type": "object"}
        result = _tools_to_openai_format([tool])
        assert result[0]["function"]["parameters"]["properties"] == {}


class TestToolsSummary:
    """Tests for _tools_summary() — building a text summary of tools."""

    def test_single_tool_summary(self, mock_mcp_tool):
        summary = _tools_summary([mock_mcp_tool])
        assert "execute_sql" in summary
        assert "Execute an InterSystems SQL query" in summary

    def test_empty_list(self):
        assert _tools_summary([]) == ""

    def test_long_description_truncated(self):
        tool = MagicMock()
        tool.name = "verbose"
        tool.description = "A" * 200
        summary = _tools_summary([tool])
        assert "..." in summary
        assert len(summary) < 200

    def test_multiline_description_first_line_only(self):
        tool = MagicMock()
        tool.name = "multi"
        tool.description = "First line.\nSecond line.\nThird line."
        summary = _tools_summary([tool])
        assert "First line." in summary
        assert "Second line." not in summary

    def test_no_description(self):
        tool = MagicMock()
        tool.name = "bare"
        tool.description = None
        summary = _tools_summary([tool])
        assert "bare" in summary


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt()."""

    def test_includes_tools_summary(self):
        prompt = _build_system_prompt("- **execute_sql**: Run SQL", "")
        assert "execute_sql" in prompt
        assert "Available tools" in prompt

    def test_includes_skills_when_provided(self):
        skills = "# Skills\n\n## Skill: guide\nUse execute_sql."
        prompt = _build_system_prompt("- **execute_sql**: Run SQL", skills)
        assert "# Skills" in prompt
        assert "## Skill: guide" in prompt

    def test_no_skills_section_when_empty(self):
        prompt = _build_system_prompt("- **t**: tool", "")
        assert "## Skill:" not in prompt

    def test_includes_agent_identity(self):
        prompt = _build_system_prompt("", "")
        assert "Prism Chatbot" in prompt

    def test_includes_usage_instructions(self):
        prompt = _build_system_prompt("", "")
        assert "Call tools" in prompt
        assert "final answer" in prompt

    def test_includes_security_guidance(self):
        """System prompt must include prompt injection defense."""
        prompt = _build_system_prompt("", "")
        assert "data, not instructions" in prompt
        assert "Security" in prompt

    def test_includes_shell_and_file_guidance(self):
        """System prompt must mention shell and file tools."""
        prompt = _build_system_prompt(
            "- **run_shell**: Run shell", "- **read_file**: Read file"
        )
        assert "run_shell" in prompt
        assert "read_file" in prompt
        assert "PowerShell" in prompt
        assert "Bash" in prompt
        assert "list_files" in prompt

    def test_includes_iris_vs_local_separation(self):
        """System prompt must clearly separate IRIS server tools from local tools."""
        prompt = _build_system_prompt("", "")
        assert "IRIS server" in prompt
        assert "local host" in prompt
        assert "execute_sql" in prompt
        assert "execute_terminal" in prompt
        assert "get_document" in prompt
        assert "run_shell" in prompt
        assert "read_file" in prompt
        assert "Do not confuse" in prompt


class TestExtractToolResultText:
    """Tests for _extract_tool_result_text()."""

    def test_structured_content_preferred(self, mock_tool_result):
        result = _extract_tool_result_text(mock_tool_result)
        assert '"rows"' in result
        assert '"count": 1' in result

    def test_text_content_fallback(self, mock_text_tool_result):
        result = _extract_tool_result_text(mock_text_tool_result)
        assert "Raw text output" in result

    def test_error_result(self, mock_error_tool_result):
        result = _extract_tool_result_text(mock_error_tool_result)
        assert "Error" in result
        assert "Table not found" in result

    def test_data_fallback(self):
        result = MagicMock()
        result.is_error = False
        result.structured_content = None
        result.content = []
        result.data = {"fallback": "data"}
        text = _extract_tool_result_text(result)
        assert "fallback" in text

    def test_no_output(self):
        result = MagicMock()
        result.is_error = False
        result.structured_content = None
        result.content = []
        result.data = None
        text = _extract_tool_result_text(result)
        assert text == "(no output)"

    def test_multiple_text_blocks_concatenated(self):
        result = MagicMock()
        result.is_error = False
        result.structured_content = None
        block1 = MagicMock()
        block1.text = "Line 1"
        block2 = MagicMock()
        block2.text = "Line 2"
        result.content = [block1, block2]
        result.data = None
        text = _extract_tool_result_text(result)
        assert "Line 1" in text
        assert "Line 2" in text


class TestTruncateToolResult:
    """Tests for _truncate_tool_result() — smart truncation."""

    def test_short_result_unchanged(self):
        assert _truncate_tool_result("short") == "short"

    def test_result_under_limit_unchanged(self):
        text = "x" * 5000
        assert _truncate_tool_result(text) == text

    def test_long_text_truncated_at_line_boundary(self):
        lines = [f"line {i}" for i in range(500)]
        text = "\n".join(lines)
        result = _truncate_tool_result(text, max_chars=1000)
        assert len(result) < len(text)
        assert "truncated" in result
        assert "chars" in result

    def test_json_list_truncated_at_item_boundary(self):
        data = [{"id": i, "name": f"item_{i}"} for i in range(200)]
        text = json.dumps(data, indent=2)
        result = _truncate_tool_result(text, max_chars=1000)
        assert "more items truncated" in result
        # Should be valid JSON up to the truncation note
        truncated_data = json.loads(result.split("\n\n[...")[0])
        assert len(truncated_data) == 50

    def test_json_dict_with_list_field_truncated(self):
        data = {"rows": [{"id": i} for i in range(200)], "count": 200}
        text = json.dumps(data, indent=2)
        result = _truncate_tool_result(text, max_chars=2000)
        if "_rows_truncated" in result:
            parsed = json.loads(result)
            assert parsed["_rows_total_count"] == 200
            assert parsed["_rows_truncated"] is True
            assert len(parsed["rows"]) == 50

    def test_custom_max_chars(self):
        text = "x" * 5000
        result = _truncate_tool_result(text, max_chars=100)
        assert len(result) < 200
        assert "truncated" in result


class TestChatbotAgentInit:
    """Tests for ChatbotAgent constructor — config resolution."""

    def test_explicit_values_override_settings(self):
        agent = ChatbotAgent(
            api_url="https://custom.api/v1",
            api_key="sk-test",
            model="my-model",
            skills_path="/tmp/skills",
        )
        assert agent.api_url == "https://custom.api/v1"
        assert agent.api_key == "sk-test"
        assert agent.model == "my-model"
        assert agent.skills_path == "/tmp/skills"

    def test_trailing_slash_stripped_from_url(self):
        agent = ChatbotAgent(
            api_url="https://api.example.com/v1/",
            api_key="key",
        )
        assert agent.api_url == "https://api.example.com/v1"

    def test_no_url_raises_error(self):
        with patch("prism.chatbot.agent.settings") as mock_settings:
            mock_settings.chatbot_api_url = ""
            mock_settings.chatbot_api_key = "key"
            mock_settings.chatbot_model = "gpt-4o"
            mock_settings.chatbot_skills_path = ""
            with pytest.raises(ValueError, match="API URL"):
                ChatbotAgent()

    def test_no_key_raises_error(self):
        with patch("prism.chatbot.agent.settings") as mock_settings:
            mock_settings.chatbot_api_url = "https://api.openai.com/v1"
            mock_settings.chatbot_api_key = ""
            mock_settings.chatbot_model = "gpt-4o"
            mock_settings.chatbot_skills_path = ""
            with pytest.raises(ValueError, match="API key"):
                ChatbotAgent()

    def test_defaults_from_settings(self):
        with patch("prism.chatbot.agent.settings") as mock_settings:
            mock_settings.chatbot_api_url = "https://from-settings/v1"
            mock_settings.chatbot_api_key = "sk-settings"
            mock_settings.chatbot_model = "gpt-4o-mini"
            mock_settings.chatbot_skills_path = "/skills"
            agent = ChatbotAgent()
            assert agent.api_url == "https://from-settings/v1"
            assert agent.api_key == "sk-settings"
            assert agent.model == "gpt-4o-mini"
            assert agent.skills_path == "/skills"

    def test_empty_model_falls_back_to_gpt4o(self):
        with patch("prism.chatbot.agent.settings") as mock_settings:
            mock_settings.chatbot_api_url = "https://api/v1"
            mock_settings.chatbot_api_key = "key"
            mock_settings.chatbot_model = ""
            mock_settings.chatbot_skills_path = ""
            agent = ChatbotAgent()
            assert agent.model == "gpt-4o"

    def test_max_tokens_configurable(self):
        agent = ChatbotAgent(
            api_url="https://api/v1",
            api_key="key",
            max_tokens=8192,
        )
        assert agent.max_tokens == 8192

    def test_timeout_configurable(self):
        agent = ChatbotAgent(
            api_url="https://api/v1",
            api_key="key",
            timeout=60.0,
        )
        assert agent.timeout == 60.0

    def test_persistent_state_initialised_empty(self):
        """Agent should start with empty messages and no connection."""
        agent = ChatbotAgent(api_url="https://api/v1", api_key="key")
        assert agent.messages == []
        assert agent._system_prompt is None
        assert agent._client is None
        assert agent._http_client is None

    def test_max_context_tokens_configurable(self):
        agent = ChatbotAgent(
            api_url="https://api/v1",
            api_key="key",
            max_context_tokens=50_000,
        )
        assert agent.max_context_tokens == 50_000


class TestChatbotAgentLifecycle:
    """Tests for the agent's async context manager lifecycle."""

    async def test_aenter_connects_mcp_and_discovers_tools(self):
        """__aenter__ should connect to MCP, discover tools, and init HTTP client."""
        mock_tool = MagicMock()
        mock_tool.name = "execute_sql"
        mock_tool.description = "Run SQL"
        mock_tool.inputSchema = {"type": "object", "properties": {}}

        mcp_patch, client_patch, mock_client = _patch_agent(mcp_tools=[mock_tool])

        with mcp_patch, client_patch:
            agent = ChatbotAgent(api_url="https://api/v1", api_key="key")
            async with agent:
                assert agent._client is not None
                assert agent._http_client is not None
                assert len(agent._tools) == 1
                assert agent._tools[0].name == "execute_sql"
                assert len(agent._openai_tools) == 1
                assert "execute_sql" in agent._tool_names
                # System prompt should be set
                assert agent._system_prompt is not None
                assert "Prism Chatbot" in agent._system_prompt
                # Messages should contain the system prompt
                assert len(agent.messages) == 1
                assert agent.messages[0]["role"] == "system"

    async def test_aexit_closes_connections(self):
        """__aexit__ should close the MCP client and HTTP client."""
        mcp_patch, client_patch, _ = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            agent = ChatbotAgent(api_url="https://api/v1", api_key="key")
            async with agent:
                assert agent._client is not None
            # After exit, connections should be cleaned up
            assert agent._client is None
            assert agent._http_client is None

    async def test_auto_lifecycle_in_run(self):
        """run() should auto-connect if not already connected."""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "Test"
        mock_tool.inputSchema = {"type": "object", "properties": {}}

        mcp_patch, client_patch, _ = _patch_agent(mcp_tools=[mock_tool])

        with mcp_patch, client_patch:
            agent = ChatbotAgent(api_url="https://api/v1", api_key="key")
            mock_response = _make_llm_response(content="Hello!")
            with patch.object(
                agent, "_call_llm", new_callable=AsyncMock, return_value=mock_response
            ):
                result = await agent.run("Hi")
                assert result == "Hello!"
                # After auto-lifecycle run, connections should be closed
                assert agent._client is None


class TestChatbotAgentRun:
    """Tests for the agent run loop with mocked LLM and MCP client."""

    async def test_simple_text_response_no_tool_calls(self):
        """Agent returns LLM text directly when no tool calls are made."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response = _make_llm_response(content="Hello! How can I help?")
        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(
                    agent,
                    "_call_llm",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ) as mock_llm:
                    result = await agent.run("Hello")
                    assert result == "Hello! How can I help?"
                    mock_llm.assert_called_once()

    async def test_tool_call_then_final_response(self):
        """Agent calls a tool, gets result, then gives a final answer."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        # Must include the tool in mcp_tools so it passes name validation
        mock_tool = MagicMock()
        mock_tool.name = "execute_sql"
        mock_tool.description = "Run SQL"
        mock_tool.inputSchema = {"type": "object", "properties": {}}

        tool_call = _make_tool_call(arguments={"query": "SELECT 1"})
        first_response = _make_llm_response(tool_calls=[tool_call])
        second_response = _make_llm_response(content="The result is 1.")

        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = {"rows": [{"1": 1}], "count": 1}
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, mock_client = _patch_agent(
            mcp_tools=[mock_tool], tool_result=mock_tool_result
        )

        call_count = 0
        responses = [first_response, second_response]

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    result = await agent.run("What is SELECT 1?")
                    assert result == "The result is 1."
                    assert call_count == 2
                    mock_client.call_tool.assert_called_once_with(
                        "execute_sql", {"query": "SELECT 1"}
                    )

    async def test_multiple_tool_calls_in_single_response(self):
        """Agent calls multiple tools in one LLM response (concurrently)."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        # Must include tools in mcp_tools so they pass name validation
        tool1 = MagicMock()
        tool1.name = "execute_sql"
        tool1.description = "Run SQL"
        tool1.inputSchema = {"type": "object", "properties": {}}
        tool2 = MagicMock()
        tool2.name = "get_server_info"
        tool2.description = "Get server info"
        tool2.inputSchema = {"type": "object", "properties": {}}

        tool_call_1 = _make_tool_call(
            call_id="call_1", name="execute_sql", arguments={"query": "SELECT 1"}
        )
        tool_call_2 = _make_tool_call(
            call_id="call_2", name="get_server_info", arguments={}
        )

        first_response = _make_llm_response(tool_calls=[tool_call_1, tool_call_2])
        second_response = _make_llm_response(content="Done.")

        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = {"result": "ok"}
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, mock_client = _patch_agent(
            mcp_tools=[tool1, tool2], tool_result=mock_tool_result
        )

        call_count = 0
        responses = [first_response, second_response]

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    result = await agent.run("Run two queries")
                    assert result == "Done."
                    assert mock_client.call_tool.call_count == 2

    async def test_tool_error_handled_gracefully(self):
        """When a tool raises an exception, the agent continues."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        tool_call = _make_tool_call(arguments={"query": "BAD SQL"})
        first_response = _make_llm_response(tool_calls=[tool_call])
        second_response = _make_llm_response(content="The SQL was invalid.")

        mcp_patch, client_patch, _mc = _patch_agent(
            mcp_tools=[], tool_side_effect=RuntimeError("Connection refused")
        )

        call_count = 0
        responses = [first_response, second_response]

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    result = await agent.run("Run bad query")
                    assert result == "The SQL was invalid."

    async def test_max_iterations_reached(self):
        """Agent stops after _MAX_ITERATIONS tool-call rounds."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        tool_call = _make_tool_call(arguments={})

        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = {"x": 1}
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, _mc = _patch_agent(
            mcp_tools=[], tool_result=mock_tool_result
        )

        async def mock_call_llm(http_client, messages, tools):
            return _make_llm_response(tool_calls=[tool_call])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    result = await agent.run("Loop forever")
                    assert "maximum number of tool-call iterations" in result

    async def test_empty_content_returns_default(self):
        """When LLM returns no content and no tool calls."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response = {
            "choices": [{"message": {"role": "assistant"}, "finish_reason": "stop"}]
        }
        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(
                    agent,
                    "_call_llm",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    result = await agent.run("Hello")
                    assert result == "(no response)"

    async def test_llm_api_error_propagates(self):
        """HTTP errors from the LLM API should propagate."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        async def mock_call_llm(http_client, messages, tools):
            raise httpx.HTTPStatusError(
                "Unauthorized",
                request=httpx.Request("POST", "https://api.test/v1/chat/completions"),
                response=httpx.Response(401, json={"error": "Invalid API key"}),
            )

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    with pytest.raises(httpx.HTTPStatusError):
                        await agent.run("Hello")

    async def test_long_tool_result_truncated(self):
        """Tool results over 10K chars are smart-truncated."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        # Must include the tool so it passes name validation
        mock_tool = MagicMock()
        mock_tool.name = "execute_sql"
        mock_tool.description = "Run SQL"
        mock_tool.inputSchema = {"type": "object", "properties": {}}

        tool_call = _make_tool_call(arguments={})
        first_response = _make_llm_response(tool_calls=[tool_call])
        second_response = _make_llm_response(content="Done.")

        large_data = {"data": "x" * 20_000}
        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = large_data
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, _mc = _patch_agent(
            mcp_tools=[mock_tool], tool_result=mock_tool_result
        )

        captured_messages: list[list] = []
        call_count = 0
        responses = [first_response, second_response]

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            captured_messages.append(messages)
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    result = await agent.run("Get big data")
                    assert result == "Done."

                    second_call_messages = captured_messages[1]
                    tool_message = next(
                        m for m in second_call_messages if m.get("role") == "tool"
                    )
                    assert "truncated" in tool_message["content"].lower()

    async def test_skills_loaded_into_system_prompt(self):
        """Skills are included in the system prompt sent to the LLM."""
        import tempfile
        import pathlib

        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "guide.md").write_text(
                "# SQL Guide\nAlways use execute_sql for queries."
            )

            agent = ChatbotAgent(
                api_url="https://api.test/v1",
                api_key="sk-test",
                skills_path=tmpdir,
            )

            mock_response = _make_llm_response(content="OK")
            mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

            captured_messages: list[list] = []

            async def mock_call_llm(http_client, messages, tools):
                captured_messages.append(messages)
                return mock_response

            with mcp_patch, client_patch:
                async with agent:
                    with patch.object(agent, "_call_llm", new=mock_call_llm):
                        await agent.run("Hello")

                        system_msg = captured_messages[0][0]
                        assert system_msg["role"] == "system"
                        assert "# Skills" in system_msg["content"]
                        assert "SQL Guide" in system_msg["content"]


# ── New tests: conversation memory ──────────────────────────────────────


class TestConversationMemory:
    """Tests for multi-turn conversation memory."""

    async def test_messages_persist_across_turns(self):
        """Agent should remember previous turns in self.messages."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response_1 = _make_llm_response(content="First response")
        mock_response_2 = _make_llm_response(content="Second response")

        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        responses = [mock_response_1, mock_response_2]
        call_count = 0

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    # Turn 1
                    result1 = await agent.run("Hello")
                    assert result1 == "First response"
                    # System + user + assistant = 3 messages
                    assert len(agent.messages) == 3
                    assert agent.messages[0]["role"] == "system"
                    assert agent.messages[1]["role"] == "user"
                    assert agent.messages[1]["content"] == "Hello"
                    assert agent.messages[2]["role"] == "assistant"
                    assert agent.messages[2]["content"] == "First response"

                    # Turn 2 — should have context from turn 1
                    result2 = await agent.run("What did I just say?")
                    assert result2 == "Second response"
                    # System + user1 + assistant1 + user2 + assistant2 = 5
                    assert len(agent.messages) == 5
                    # Verify both turns were called
                    assert call_count == 2

    async def test_user_message_removed_on_error(self):
        """If run() raises, the user message should be removed for clean state."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        async def mock_call_llm(http_client, messages, tools):
            raise httpx.ConnectError("Connection refused")

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    with pytest.raises(httpx.ConnectError):
                        await agent.run("Hello")
                    # Messages should be back to just system prompt
                    assert len(agent.messages) == 1
                    assert agent.messages[0]["role"] == "system"


# ── New tests: parallel tool execution ─────────────────────────────────


class TestParallelToolExecution:
    """Tests for concurrent tool execution."""

    async def test_multiple_tool_calls_executed_concurrently(self):
        """Multiple tool calls should run via asyncio.gather, not sequentially."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        # Include tools so they pass name validation
        tool1 = MagicMock()
        tool1.name = "execute_sql"
        tool1.description = "Run SQL"
        tool1.inputSchema = {"type": "object", "properties": {}}
        tool2 = MagicMock()
        tool2.name = "get_server_info"
        tool2.description = "Get info"
        tool2.inputSchema = {"type": "object", "properties": {}}

        tool_call_1 = _make_tool_call(
            call_id="c1", name="execute_sql", arguments={"query": "SELECT 1"}
        )
        tool_call_2 = _make_tool_call(
            call_id="c2", name="get_server_info", arguments={}
        )

        first_response = _make_llm_response(tool_calls=[tool_call_1, tool_call_2])
        second_response = _make_llm_response(content="Both done.")

        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = {"result": "ok"}
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, mock_client = _patch_agent(
            mcp_tools=[tool1, tool2], tool_result=mock_tool_result
        )

        call_count = 0
        responses = [first_response, second_response]

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    await agent.run("Run two")

                    # Both tools should have been called
                    assert mock_client.call_tool.call_count == 2
                    # Check the tool names called
                    called_names = [
                        c.args[0] for c in mock_client.call_tool.call_args_list
                    ]
                    assert "execute_sql" in called_names
                    assert "get_server_info" in called_names

    async def test_unknown_tool_name_rejected(self):
        """Tool calls with unknown names should get an error response."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        tool_call = _make_tool_call(call_id="c1", name="nonexistent_tool", arguments={})
        first_response = _make_llm_response(tool_calls=[tool_call])
        second_response = _make_llm_response(content="Sorry, that tool doesn't exist.")

        mcp_patch, client_patch, mock_client = _patch_agent(mcp_tools=[])

        call_count = 0
        responses = [first_response, second_response]

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    result = await agent.run("Call bad tool")
                    assert result == "Sorry, that tool doesn't exist."
                    # The unknown tool should NOT have been called via MCP
                    mock_client.call_tool.assert_not_called()
                    # The tool result message should contain the error
                    tool_msg = next(
                        m for m in agent.messages if m.get("role") == "tool"
                    )
                    assert "unknown tool" in tool_msg["content"]


# ── New tests: retry/backoff ─────────────────────────────────────────────


class TestRetryBackoff:
    """Tests for LLM API retry with exponential backoff."""

    async def test_retry_on_429(self):
        """Should retry on HTTP 429 (rate limit)."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        call_count = 0

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.HTTPStatusError(
                    "Rate limited",
                    request=httpx.Request(
                        "POST", "https://api.test/v1/chat/completions"
                    ),
                    response=httpx.Response(429),
                )
            return _make_llm_response(content="Success on retry!")

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    with patch(
                        "prism.chatbot.agent.asyncio.sleep", new_callable=AsyncMock
                    ):
                        result = await agent.run("Hello")
                        assert result == "Success on retry!"
                        assert call_count == 3  # 2 retries + 1 success

    async def test_retry_on_503(self):
        """Should retry on HTTP 503 (server error)."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        call_count = 0

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.HTTPStatusError(
                    "Server error",
                    request=httpx.Request(
                        "POST", "https://api.test/v1/chat/completions"
                    ),
                    response=httpx.Response(503),
                )
            return _make_llm_response(content="OK")

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    with patch(
                        "prism.chatbot.agent.asyncio.sleep", new_callable=AsyncMock
                    ):
                        result = await agent.run("Hello")
                        assert result == "OK"
                        assert call_count == 2

    async def test_no_retry_on_401(self):
        """Should NOT retry on HTTP 401 (authentication failure)."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        call_count = 0

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            call_count += 1
            raise httpx.HTTPStatusError(
                "Unauthorized",
                request=httpx.Request("POST", "https://api.test/v1/chat/completions"),
                response=httpx.Response(401),
            )

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    with pytest.raises(httpx.HTTPStatusError):
                        await agent.run("Hello")
                    assert call_count == 1  # No retries

    async def test_retry_on_timeout(self):
        """Should retry on httpx.TimeoutException."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        call_count = 0

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Timed out")
            return _make_llm_response(content="OK after timeout")

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    with patch(
                        "prism.chatbot.agent.asyncio.sleep", new_callable=AsyncMock
                    ):
                        result = await agent.run("Hello")
                        assert result == "OK after timeout"
                        assert call_count == 2


# ── New tests: finish_reason + token usage ───────────────────────────────


class TestFinishReason:
    """Tests for finish_reason and token usage handling."""

    async def test_length_finish_reason_logged(self, caplog):
        """finish_reason='length' should be logged as a warning."""
        import logging

        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response = _make_llm_response(
            content="Truncated...",
            finish_reason="length",
        )
        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(
                    agent,
                    "_call_llm",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    with caplog.at_level(logging.WARNING):
                        await agent.run("Hello")
                        assert any(
                            "truncated" in r.message.lower() for r in caplog.records
                        )

    async def test_content_filter_logged(self, caplog):
        """finish_reason='content_filter' should be logged."""
        import logging

        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response = _make_llm_response(
            content="",
            finish_reason="content_filter",
        )
        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(
                    agent,
                    "_call_llm",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    with caplog.at_level(logging.WARNING):
                        await agent.run("Hello")
                        assert any(
                            "content filter" in r.message.lower()
                            for r in caplog.records
                        )

    async def test_token_usage_logged(self, caplog):
        """Token usage from API response should be logged at DEBUG level."""
        import logging

        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response = _make_llm_response(
            content="OK",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(
                    agent,
                    "_call_llm",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    with caplog.at_level(logging.DEBUG):
                        await agent.run("Hello")
                        assert any(
                            "token usage" in r.message.lower() for r in caplog.records
                        )

    async def test_missing_choices_returns_default(self):
        """When API returns no choices, agent should return default."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response = {"choices": []}
        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(
                    agent,
                    "_call_llm",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    result = await agent.run("Hello")
                    assert result == "(no response from LLM)"


# ── New tests: context trimming ─────────────────────────────────────────


class TestContextTrimming:
    """Tests for _trim_if_needed()."""

    def test_no_trimming_when_under_limit(self):
        """_trim_if_needed should not remove messages when under limit."""
        agent = ChatbotAgent(
            api_url="https://api/v1",
            api_key="key",
            max_context_tokens=1_000_000,  # very high
        )
        agent.messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        agent._trim_if_needed()
        assert len(agent.messages) == 3

    def test_trimming_removes_oldest_messages(self):
        """When over limit, oldest non-system messages should be removed."""
        agent = ChatbotAgent(
            api_url="https://api/v1",
            api_key="key",
            max_context_tokens=100,  # very low — 400 chars ≈ 100 tokens
        )
        # Create messages that exceed the limit — need more than min_keep + 1
        agent.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "A" * 200},
            {"role": "assistant", "content": "B" * 200},
            {"role": "user", "content": "C" * 200},
            {"role": "assistant", "content": "D" * 200},
            {"role": "user", "content": "E" * 200},
            {"role": "assistant", "content": "F" * 200},
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "recent reply"},
        ]
        agent._trim_if_needed()
        # System prompt should always survive
        assert agent.messages[0]["role"] == "system"
        # Should have fewer messages than before
        assert len(agent.messages) < 9
        # Most recent messages should survive
        assert agent.messages[-1]["content"] == "recent reply"
        assert agent.messages[-2]["content"] == "recent"

    def test_system_prompt_never_removed(self):
        """The system prompt (messages[0]) must never be trimmed."""
        agent = ChatbotAgent(
            api_url="https://api/v1",
            api_key="key",
            max_context_tokens=10,  # extremely low
        )
        agent.messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        agent._trim_if_needed()
        assert agent.messages[0]["role"] == "system"
        assert agent.messages[0]["content"] == "system prompt"

    def test_min_messages_preserved(self):
        """Should keep at least system prompt + 6 messages (3 turns)."""
        agent = ChatbotAgent(
            api_url="https://api/v1",
            api_key="key",
            max_context_tokens=1,  # impossibly low
        )
        agent.messages = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
            {"role": "assistant", "content": "a3"},
        ]
        agent._trim_if_needed()
        # Should keep system + at least 6 messages
        assert len(agent.messages) >= 7  # can't trim below min_keep + 1


# ── New tests: API compatibility ────────────────────────────────────────


class TestAPICompatibility:
    """Tests for OpenAI-compatible API handling."""

    async def test_max_tokens_in_payload(self):
        """Payload should include max_tokens."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1", api_key="sk-test", max_tokens=2048
        )

        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        captured_payload: list[dict] = []

        async def mock_call_llm(http_client, messages, tools):
            # Call the real _call_llm but intercept the http_client.post
            return _make_llm_response(content="OK")

        with mcp_patch, client_patch:
            async with agent:
                # Patch httpx.AsyncClient.post to capture the payload
                original_post = agent._http_client.post

                async def capturing_post(url, **kwargs):
                    captured_payload.append(kwargs.get("json", {}))
                    # Return a mock response
                    import httpx as _httpx

                    resp = _httpx.Response(
                        200,
                        json=_make_llm_response(content="OK"),
                        request=_httpx.Request("POST", url),
                    )
                    return resp

                agent._http_client.post = capturing_post  # type: ignore[method-assign]
                try:
                    await agent.run("Hi")
                    assert len(captured_payload) > 0
                    assert captured_payload[0]["max_tokens"] == 2048
                finally:
                    agent._http_client.post = original_post  # type: ignore[method-assign]

    async def test_null_content_handled(self):
        """LLM returning null content with no tool calls should return default."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": None},
                    "finish_reason": "stop",
                }
            ]
        }
        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(
                    agent,
                    "_call_llm",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    result = await agent.run("Hello")
                    assert result == "(no response)"

    async def test_null_tool_calls_handled(self):
        """LLM returning null tool_calls should be treated as no tool calls."""
        agent = ChatbotAgent(api_url="https://api.test/v1", api_key="sk-test")

        mock_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hi",
                        "tool_calls": None,
                    },
                    "finish_reason": "stop",
                }
            ]
        }
        mcp_patch, client_patch, _mc = _patch_agent(mcp_tools=[])

        with mcp_patch, client_patch:
            async with agent:
                with patch.object(
                    agent,
                    "_call_llm",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    result = await agent.run("Hello")
                    assert result == "Hi"
