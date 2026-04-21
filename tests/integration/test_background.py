"""Integration tests for terminal execution.

Tests that execute_terminal can run ObjectScript commands and return results.
"""

import json

import pytest

from unittest.mock import patch

from tests.integration.conftest import stage_file


@pytest.fixture(autouse=True)
def _force_native():
    """Tests require the native terminal backend."""
    with patch("prism.iris.api.terminal.IRIS_TERMINAL_METHOD", "native"):
        yield


def _parse(result) -> dict:
    return json.loads(result.content[0].text)


@pytest.fixture
async def bg_helper(live, workspace):
    """Deploy the background test helper class to IRIS."""
    stage_file(workspace, "Test.MCPBgHelper.cls")
    await live.call_tool(
        "put_document",
        {"name": "Test.MCPBgHelper.cls", "path": "Test.MCPBgHelper.cls"},
    )
    result = await live.call_tool(
        "compile_documents",
        {"doc_names": ["Test.MCPBgHelper.cls"]},
    )
    data = json.loads(result.content[0].text)
    assert data["success"] is True


class TestTerminalExecution:
    """Tests for synchronous terminal execution."""

    async def test_blocking_terminal(self, live, workspace):
        """Calling execute_terminal blocks and returns output directly."""
        result = _parse(
            await live.call_tool(
                "execute_terminal",
                {"command": 'Write "sync-ok"'},
            )
        )

        assert "output" in result
        assert "sync-ok" in result["output"]
