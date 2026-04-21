"""Integration tests for the terminal tool — runs against both backends.

Each test is parametrized via the ``terminal_method`` fixture to run
with both ``native`` (irisnative via SuperServer) and ``ws`` (WebSocket).
"""

import json


class TestTerminal:
    async def test_write_hello(self, live, terminal_method):
        result = await live.call_tool("execute_terminal", {"command": 'write "hello"'})
        data = json.loads(result.content[0].text)
        assert "hello" in data["output"]

    async def test_arithmetic(self, live, terminal_method):
        result = await live.call_tool("execute_terminal", {"command": "write 2 + 3"})
        data = json.loads(result.content[0].text)
        assert "5" in data["output"]

    async def test_system_variable(self, live, terminal_method):
        result = await live.call_tool(
            "execute_terminal", {"command": "write $zversion"}
        )
        data = json.loads(result.content[0].text)
        assert "IRIS" in data["output"]

    async def test_set_and_write(self, live, terminal_method):
        result = await live.call_tool(
            "execute_terminal",
            {"command": 'set x="world" write "hello " _ x'},
        )
        data = json.loads(result.content[0].text)
        assert "hello world" in data["output"]

    async def test_namespace_override(self, live, terminal_method):
        result = await live.call_tool(
            "execute_terminal",
            {"command": "write $namespace", "namespace": "USER"},
        )
        data = json.loads(result.content[0].text)
        assert "USER" in data["output"]
