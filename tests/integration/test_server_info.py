"""Integration tests for IRIS server info."""

import json


class TestServerInfo:
    async def test_returns_version(self, live):
        result = await live.call_tool("get_server_info")
        data = json.loads(result.content[0].text)
        assert "version" in data
        assert len(data["version"]) > 0

    async def test_contains_namespaces(self, live):
        result = await live.call_tool("get_server_info")
        data = json.loads(result.content[0].text)
        assert "namespaces" in data
        assert "USER" in data["namespaces"]
