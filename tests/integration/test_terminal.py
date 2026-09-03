"""Integration tests for the terminal tool — runs against the WebSocket backend.

The terminal uses the Atelier WebSocket terminal; it does NOT upload our own
ObjectScript helper (MCP.Terminal) and does NOT use the native SuperServer
("superport") path.
"""

import json


class TestTerminal:
    async def test_write_hello(self, live):
        result = await live.call_tool("execute_terminal", {"command": 'write "hello"'})
        data = json.loads(result.content[0].text)
        assert "hello" in data["output"]

    async def test_arithmetic(self, live):
        result = await live.call_tool("execute_terminal", {"command": "write 2 + 3"})
        data = json.loads(result.content[0].text)
        assert "5" in data["output"]

    async def test_system_variable(self, live):
        result = await live.call_tool("execute_terminal", {"command": "write $zversion"})
        data = json.loads(result.content[0].text)
        assert "IRIS" in data["output"]

    async def test_set_and_write(self, live):
        result = await live.call_tool(
            "execute_terminal",
            {"command": 'set x="world" write "hello " _ x'},
        )
        data = json.loads(result.content[0].text)
        assert "hello world" in data["output"]

    async def test_namespace_override(self, live):
        result = await live.call_tool(
            "execute_terminal",
            {"command": "write $namespace", "namespace": "USER"},
        )
        data = json.loads(result.content[0].text)
        assert "USER" in data["output"]
