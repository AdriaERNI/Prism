"""MCP tools for IRIS server info."""

from prism.iris.api import server_info as info_api
from prism.mcp._decorator import logged_tool


@logged_tool
async def get_server_info() -> dict:
    """Get IRIS server information including version and available namespaces.

    Returns ``{"version": "...", "api": N, "namespaces": [...]}`` — use
    this to verify connectivity, check the server version, or discover
    available namespaces before targeting one with other tools.
    """
    data = await info_api.get_server_info()
    content = data.get("result", {}).get("content", {})
    return {
        "version": content.get("version", ""),
        "api": content.get("api", 0),
        "namespaces": content.get("namespaces", []),
    }
