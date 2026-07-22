"""Tests for the chatbot agent (prism.chatbot.agent).

These tests mock the LLM API (_call_llm) and the MCP client to verify
the agent loop works correctly: sending messages, receiving tool calls,
executing tools, and returning final responses.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prism.chatbot.agent import (
    ChatbotAgent,
    _build_system_prompt,
    _extract_tool_result_text,
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
        # The first sentence is the full 200 chars (no newline), truncated to 100 chars
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


class TestChatbotAgentRun:
    """Tests for the agent run loop with mocked LLM and MCP client."""

    def _make_llm_response(
        self,
        content: str | None = None,
        tool_calls: list[dict] | None = None,
    ) -> dict:
        """Build a mock LLM chat completion response."""
        message: dict = {"role": "assistant"}
        if content is not None:
            message["content"] = content
        if tool_calls is not None:
            message["tool_calls"] = tool_calls
        return {"choices": [{"message": message}]}

    def _make_tool_call(
        self,
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

    def _patch_context(self, mcp_tools=None, tool_result=None, tool_side_effect=None):
        """Create a patch context for create_mcp and Client.

        Returns a tuple of (create_mcp_patch, client_patch, mock_client)
        where mock_client is the AsyncMock that Client() will return.
        """
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.list_tools = AsyncMock(return_value=mcp_tools or [])
        if tool_side_effect:
            mock_client.call_tool = AsyncMock(side_effect=tool_side_effect)
        elif tool_result is not None:
            mock_client.call_tool = AsyncMock(return_value=tool_result)
        else:
            mock_client.call_tool = AsyncMock()

        mcp_patch = patch("prism.chatbot.agent.create_mcp")
        client_patch = patch("prism.chatbot.agent.Client", return_value=mock_client)
        return mcp_patch, client_patch, mock_client

    async def test_simple_text_response_no_tool_calls(self):
        """Agent returns LLM text directly when no tool calls are made."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1",
            api_key="sk-test",
        )

        mock_response = self._make_llm_response(content="Hello! How can I help?")

        mcp_patch, client_patch, _mc = self._patch_context(mcp_tools=[])

        with mcp_patch, client_patch:
            with patch.object(
                agent, "_call_llm", new_callable=AsyncMock, return_value=mock_response
            ) as mock_llm:
                result = await agent.run("Hello")
                assert result == "Hello! How can I help?"
                mock_llm.assert_called_once()

    async def test_tool_call_then_final_response(self):
        """Agent calls a tool, gets result, then gives a final answer."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1",
            api_key="sk-test",
        )

        # First LLM response: tool call
        tool_call = self._make_tool_call(arguments={"query": "SELECT 1"})
        first_response = self._make_llm_response(tool_calls=[tool_call])
        # Second LLM response: final answer
        second_response = self._make_llm_response(content="The result is 1.")

        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = {"rows": [{"1": 1}], "count": 1}
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, mock_client = self._patch_context(
            mcp_tools=[], tool_result=mock_tool_result
        )

        call_count = 0
        responses = [first_response, second_response]

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            with patch.object(agent, "_call_llm", new=mock_call_llm):
                result = await agent.run("What is SELECT 1?")
                assert result == "The result is 1."
                assert call_count == 2
                mock_client.call_tool.assert_called_once_with(
                    "execute_sql", {"query": "SELECT 1"}
                )

    async def test_multiple_tool_calls_in_single_response(self):
        """Agent calls multiple tools in one LLM response."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1",
            api_key="sk-test",
        )

        tool_call_1 = self._make_tool_call(
            call_id="call_1",
            name="execute_sql",
            arguments={"query": "SELECT 1"},
        )
        tool_call_2 = self._make_tool_call(
            call_id="call_2",
            name="get_server_info",
            arguments={},
        )

        first_response = self._make_llm_response(tool_calls=[tool_call_1, tool_call_2])
        second_response = self._make_llm_response(content="Done.")

        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = {"result": "ok"}
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, mock_client = self._patch_context(
            mcp_tools=[], tool_result=mock_tool_result
        )

        call_count = 0
        responses = [first_response, second_response]

        async def mock_call_llm(http_client, messages, tools):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with mcp_patch, client_patch:
            with patch.object(agent, "_call_llm", new=mock_call_llm):
                result = await agent.run("Run two queries")
                assert result == "Done."
                assert mock_client.call_tool.call_count == 2

    async def test_tool_error_handled_gracefully(self):
        """When a tool raises an exception, the agent continues."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1",
            api_key="sk-test",
        )

        tool_call = self._make_tool_call(arguments={"query": "BAD SQL"})
        first_response = self._make_llm_response(tool_calls=[tool_call])
        second_response = self._make_llm_response(content="The SQL was invalid.")

        mcp_patch, client_patch, _mc = self._patch_context(
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
            with patch.object(agent, "_call_llm", new=mock_call_llm):
                result = await agent.run("Run bad query")
                assert result == "The SQL was invalid."

    async def test_max_iterations_reached(self):
        """Agent stops after _MAX_ITERATIONS tool-call rounds."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1",
            api_key="sk-test",
        )

        # Every response is a tool call — never produces final text
        tool_call = self._make_tool_call(arguments={})

        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = {"x": 1}
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, _mc = self._patch_context(
            mcp_tools=[], tool_result=mock_tool_result
        )

        async def mock_call_llm(http_client, messages, tools):
            return self._make_llm_response(tool_calls=[tool_call])

        with mcp_patch, client_patch:
            with patch.object(agent, "_call_llm", new=mock_call_llm):
                result = await agent.run("Loop forever")
                assert "maximum number of tool-call iterations" in result

    async def test_empty_content_returns_default(self):
        """When LLM returns no content and no tool calls."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1",
            api_key="sk-test",
        )

        mock_response = {"choices": [{"message": {"role": "assistant"}}]}

        mcp_patch, client_patch, _mc = self._patch_context(mcp_tools=[])

        with mcp_patch, client_patch:
            with patch.object(
                agent, "_call_llm", new_callable=AsyncMock, return_value=mock_response
            ):
                result = await agent.run("Hello")
                assert result == "(no response)"

    async def test_llm_api_error_propagates(self):
        """HTTP errors from the LLM API should propagate."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1",
            api_key="sk-test",
        )

        mcp_patch, client_patch, _mc = self._patch_context(mcp_tools=[])

        async def mock_call_llm(http_client, messages, tools):
            raise httpx.HTTPStatusError(
                "Unauthorized",
                request=httpx.Request("POST", "https://api.test/v1/chat/completions"),
                response=httpx.Response(401, json={"error": "Invalid API key"}),
            )

        import httpx

        with mcp_patch, client_patch:
            with patch.object(agent, "_call_llm", new=mock_call_llm):
                with pytest.raises(httpx.HTTPStatusError):
                    await agent.run("Hello")

    async def test_long_tool_result_truncated(self):
        """Tool results over 10K chars are truncated."""
        agent = ChatbotAgent(
            api_url="https://api.test/v1",
            api_key="sk-test",
        )

        tool_call = self._make_tool_call(arguments={})
        first_response = self._make_llm_response(tool_calls=[tool_call])
        second_response = self._make_llm_response(content="Done.")

        # Create a very large tool result
        large_data = {"data": "x" * 20_000}
        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.structured_content = large_data
        mock_tool_result.content = []
        mock_tool_result.data = None

        mcp_patch, client_patch, _mc = self._patch_context(
            mcp_tools=[], tool_result=mock_tool_result
        )

        # Capture messages sent to _call_llm
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
            with patch.object(agent, "_call_llm", new=mock_call_llm):
                result = await agent.run("Get big data")
                assert result == "Done."

                # Check the messages sent to the LLM contain truncated result
                second_call_messages = captured_messages[1]
                tool_message = next(
                    m for m in second_call_messages if m.get("role") == "tool"
                )
                assert "(truncated)" in tool_message["content"]

    async def test_skills_loaded_into_system_prompt(self):
        """Skills are included in the system prompt sent to the LLM."""
        import tempfile
        import pathlib

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a skill file
            (pathlib.Path(tmpdir) / "guide.md").write_text(
                "# SQL Guide\nAlways use execute_sql for queries."
            )

            agent = ChatbotAgent(
                api_url="https://api.test/v1",
                api_key="sk-test",
                skills_path=tmpdir,
            )

            mock_response = self._make_llm_response(content="OK")

            mcp_patch, client_patch, _mc = self._patch_context(mcp_tools=[])

            # Capture messages
            captured_messages: list[list] = []

            async def mock_call_llm(http_client, messages, tools):
                captured_messages.append(messages)
                return mock_response

            with mcp_patch, client_patch:
                with patch.object(agent, "_call_llm", new=mock_call_llm):
                    await agent.run("Hello")

                    # Check the system prompt in the first API call
                    system_msg = captured_messages[0][0]
                    assert system_msg["role"] == "system"
                    assert "# Skills" in system_msg["content"]
                    assert "SQL Guide" in system_msg["content"]
