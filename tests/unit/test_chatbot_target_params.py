"""Tests for chatbot agent target_host/target_port passthrough.

The chatbot discovers MCP tools via client.list_tools(), converts to OpenAI
format, and passes LLM-generated tool call arguments to client.call_tool().
These tests verify that target_host/target_port params are:

1. Present in tool schemas the chatbot discovers
2. Present in the OpenAI function-calling format sent to the LLM
3. Correctly forwarded through call_tool() to the underlying API
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from prism.chatbot.agent import (
    ChatbotAgent,
    _tools_summary,
    _tools_to_openai_format,
)


@pytest.fixture
def mcp_server():
    """Create a real MCP server (same as chatbot uses)."""
    from prism.mcp.server import create_mcp

    return create_mcp()


@pytest.fixture
def discovered_tools(mcp_server):
    """Tools discovered by connecting a FastMCP client to the server."""
    from fastmcp import Client

    async def _discover():
        async with Client(mcp_server) as client:
            return await client.list_tools()

    return asyncio.new_event_loop().run_until_complete(_discover())


class TestTargetParamsInSchemas:
    """Verify target_host/target_port appear in tool schemas."""

    def test_execute_sql_has_target_params(self, discovered_tools):
        """execute_sql schema includes target_host and target_port."""
        tool = next(t for t in discovered_tools if t.name == "execute_sql")
        props = tool.inputSchema.get("properties", {})
        assert "target_host" in props
        assert "target_port" in props

    def test_get_server_info_has_target_params(self, discovered_tools):
        """get_server_info schema includes target_host and target_port."""
        tool = next(t for t in discovered_tools if t.name == "get_server_info")
        props = tool.inputSchema.get("properties", {})
        assert "target_host" in props
        assert "target_port" in props

    def test_run_shell_does_not_have_target_params(self, discovered_tools):
        """run_shell is a local tool — should NOT have target params."""
        # run_shell is workspace-gated, may or may not be registered
        tool = next((t for t in discovered_tools if t.name == "run_shell"), None)
        if tool is None:
            pytest.skip("run_shell not registered (no workspace)")
        props = tool.inputSchema.get("properties", {})
        assert "target_host" not in props
        assert "target_port" not in props

    def test_all_iris_tools_have_target_params(self, discovered_tools):
        """Every IRIS-targeting tool should have target_host and target_port."""
        # Local-only tools that don't target IRIS
        local_tools = {"run_shell", "list_files", "read_file", "index_code"}
        for tool in discovered_tools:
            if tool.name in local_tools:
                continue
            props = tool.inputSchema.get("properties", {})
            # Every IRIS-targeting tool should have both params
            assert "target_host" in props, f"{tool.name} missing target_host"
            assert "target_port" in props, f"{tool.name} missing target_port"


class TestOpenAIFormatPreservesTargetParams:
    """Verify _tools_to_openai_format preserves target params."""

    def test_openai_format_has_target_params(self, discovered_tools):
        """OpenAI function schemas include target_host and target_port."""
        openai_tools = _tools_to_openai_format(discovered_tools)
        execute_sql = next(t for t in openai_tools if t["function"]["name"] == "execute_sql")
        params = execute_sql["function"]["parameters"]["properties"]
        assert "target_host" in params
        assert "target_port" in params

    def test_openai_format_target_param_descriptions(self, discovered_tools):
        """target_host description mentions IRIS or server."""
        openai_tools = _tools_to_openai_format(discovered_tools)
        execute_sql = next(t for t in openai_tools if t["function"]["name"] == "execute_sql")
        params = execute_sql["function"]["parameters"]["properties"]
        host_desc = params["target_host"].get("description", "").lower()
        assert "iris" in host_desc or "server" in host_desc or "host" in host_desc


class TestTargetParamsInToolSummary:
    """Verify tool summary doesn't break with target params."""

    def test_tools_summary_works(self, discovered_tools):
        """_tools_summary runs without error and lists tools."""
        summary = _tools_summary(discovered_tools)
        assert isinstance(summary, str)
        assert len(summary) > 0
        # At least execute_sql should be in the summary
        assert "execute_sql" in summary


class TestChatbotToolCallForwarding:
    """Verify the chatbot forwards target_host/target_port from LLM tool calls.

    The chatbot's _execute_tool_calls() parses JSON arguments from the LLM
    response and passes them directly to client.call_tool(). We mock the
    client.call_tool() to capture what arguments were forwarded.
    """

    def _make_agent(self):
        """Create a ChatbotAgent without connecting (mock the client)."""
        with patch("prism.chatbot.agent.settings") as mock_settings:
            mock_settings.chatbot_api_url = "http://test/v1"
            mock_settings.chatbot_api_key = "sk-test"
            mock_settings.chatbot_model = "test-model"
            mock_settings.chatbot_skills_path = None
            agent = ChatbotAgent.__new__(ChatbotAgent)
            agent.api_url = "http://test/v1"
            agent.api_key = "sk-test"
            agent.model = "test-model"
            agent.skills_path = None
            agent.timeout = 30
            agent.max_context_tokens = 8000
            agent.messages = []
            agent._system_prompt = "test system prompt"
            agent._tools = []
            agent._openai_tools = []
            agent._tool_names = {"execute_sql", "get_server_info"}
            agent._mcp_server = None
            agent._client = AsyncMock()
            agent._http_client = None
            return agent

    @pytest.mark.asyncio
    async def test_target_host_forwarded_to_call_tool(self):
        """When LLM includes target_host in arguments, it's forwarded."""
        agent = self._make_agent()

        # Simulate the LLM returning a tool call with target_host
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "execute_sql",
                    "arguments": json.dumps(
                        {
                            "query": "SELECT 1",
                            "target_host": "10.0.0.50",
                            "target_port": 52774,
                        }
                    ),
                },
            }
        ]

        # Mock call_tool to capture arguments
        captured_args: dict[str, Any] = {}

        async def mock_call_tool(name, args):
            captured_args["name"] = name
            captured_args["args"] = args
            # Return a mock result
            mock_result = AsyncMock()
            mock_result.is_error = False
            mock_result.content = []
            return mock_result

        agent._client.call_tool = mock_call_tool

        await agent._execute_tool_calls(tool_calls)

        # Verify target_host and target_port were forwarded
        assert captured_args["name"] == "execute_sql"
        assert captured_args["args"]["target_host"] == "10.0.0.50"
        assert captured_args["args"]["target_port"] == 52774
        assert captured_args["args"]["query"] == "SELECT 1"

    @pytest.mark.asyncio
    async def test_no_target_params_still_works(self):
        """When LLM omits target params, call_tool still gets the other args."""
        agent = self._make_agent()

        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "execute_sql",
                    "arguments": json.dumps({"query": "SELECT 1"}),
                },
            }
        ]

        captured_args: dict[str, Any] = {}

        async def mock_call_tool(name, args):
            captured_args["name"] = name
            captured_args["args"] = args
            mock_result = AsyncMock()
            mock_result.is_error = False
            mock_result.content = []
            return mock_result

        agent._client.call_tool = mock_call_tool

        await agent._execute_tool_calls(tool_calls)

        assert captured_args["args"]["query"] == "SELECT 1"
        # target_host should not be in args if LLM didn't send it
        assert "target_host" not in captured_args["args"]

    @pytest.mark.asyncio
    async def test_target_params_in_tool_result_message(self):
        """Tool result message is added to conversation after target call."""
        agent = self._make_agent()
        agent.messages = [{"role": "system", "content": "system"}]

        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_server_info",
                    "arguments": json.dumps(
                        {
                            "target_host": "prod-iris.local",
                            "target_port": 80,
                        }
                    ),
                },
            }
        ]

        async def mock_call_tool(name, args):
            mock_result = AsyncMock()
            mock_result.is_error = False
            mock_result.content = []
            return mock_result

        agent._client.call_tool = mock_call_tool

        await agent._execute_tool_calls(tool_calls)

        # A tool result message should be appended
        tool_msg = agent.messages[-1]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_1"
        assert tool_msg["name"] == "get_server_info"
