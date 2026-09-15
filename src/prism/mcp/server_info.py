"""MCP tools for IRIS server info."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import server_info as info_api
from prism.iris.sdk.http import handle_api_error
from prism.mcp._decorator import logged_tool


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def get_server_info(
    target_host: Annotated[
        str | None,
        Field(
            description="IRIS server hostname or IP address (e.g. '192.168.1.100'). "
            "Uses the configured default if omitted."
        ),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port (e.g. 52773). Uses the configured default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Get IRIS server version and available namespaces.

    **Runs on: IRIS server** (remote metadata query). Returns
    ``{"version": "...", "api": N, "namespaces": [...]}`` — verify
    connectivity, check the version, and discover namespaces before targeting
    one with other tools. Use target_host/target_port for another instance.
    """
    try:
        data = await info_api.get_server_info(
            target_host=target_host,
            target_port=target_port,
        )
    except Exception as exc:
        return {"error": handle_api_error(exc)}
    content = data.get("result", {}).get("content", {})
    return {
        "version": content.get("version", ""),
        "api": content.get("api", 0),
        "namespaces": content.get("namespaces", []),
    }
