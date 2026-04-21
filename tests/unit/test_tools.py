"""Smoke tests — verify tool registration on the MCP server."""

from unittest.mock import patch

from fastmcp import Client

from prism.mcp.server import create_mcp


class TestToolsWithWorkspace:
    """When IRIS_WORKSPACE is set, workspace tools are registered."""

    async def test_workspace_tools_registered(self, tmp_path):
        with patch("prism.config.IRIS_WORKSPACE", str(tmp_path)):
            # Re-import to pick up patched config
            import prism.mcp as tools_pkg

            orig_skip = tools_pkg._SKIP_MODULES.copy()
            tools_pkg._SKIP_MODULES.discard("workspace")
            try:
                mcp = create_mcp()
                client = Client(mcp)
                async with client:
                    tools = await client.list_tools()
                    names = {t.name for t in tools}
                    assert "get_document" in names
                    assert "put_document" in names
                    assert "put_and_compile" in names
                    assert "list_documents" in names
                    assert "delete_document" in names
                    assert "compile_documents" in names
                    assert "execute_sql" in names
                    assert "execute_terminal" in names
                    assert "get_server_info" in names
                    assert "run_tests" in names
                    assert "list_tests" in names
                    assert "get_test_results" in names
            finally:
                tools_pkg._SKIP_MODULES = orig_skip


class TestToolsWithoutWorkspace:
    """When IRIS_WORKSPACE is empty, workspace tools are NOT registered."""

    async def test_workspace_tools_not_registered(self):
        with patch("prism.config.IRIS_WORKSPACE", ""):
            import prism.mcp as tools_pkg

            orig_skip = tools_pkg._SKIP_MODULES.copy()
            tools_pkg._SKIP_MODULES.add("workspace")
            try:
                mcp = create_mcp()
                client = Client(mcp)
                async with client:
                    tools = await client.list_tools()
                    names = {t.name for t in tools}
                    assert "get_document" in names
                    assert "put_document" not in names
                    assert "put_and_compile" not in names
                    # These should still be registered
                    assert "list_documents" in names
                    assert "delete_document" in names
                    assert "compile_documents" in names
                    assert "execute_sql" in names
                    assert "execute_terminal" in names
                    assert "get_server_info" in names
                    assert "run_tests" in names
                    assert "list_tests" in names
                    assert "get_test_results" in names
            finally:
                tools_pkg._SKIP_MODULES = orig_skip
