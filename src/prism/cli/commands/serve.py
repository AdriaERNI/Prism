"""`prism serve` — start the Prism MCP server."""

from __future__ import annotations

import logging

import typer

DEFAULT_PORT = 3000

# Maps user-facing transport names to FastMCP transport values.
# Users can type "http" (short) or "streamable-http" (full).
TRANSPORT_ALIASES: dict[str, str] = {
    "http": "streamable-http",
    "streamable-http": "streamable-http",
    "streamable_http": "streamable-http",
    "stdio": "stdio",
    "sse": "sse",
}


def serve(
    port: int = typer.Option(
        DEFAULT_PORT,
        "--port",
        "-p",
        help="Port to bind the MCP server to (HTTP/SSE transport only).",
        min=1,
        max=65535,
    ),
    transport: str = typer.Option(
        "http",
        "--transport",
        "-t",
        help="Transport protocol: 'http' (streamable-http, default), 'stdio', or 'sse'.",
    ),
    skip_preflight: bool = typer.Option(
        False,
        "--skip-preflight",
        help="Skip the IRIS connectivity check at startup.",
    ),
) -> None:
    """Start the Prism MCP server.

    Supports two transports:

    - **http** (default): Streamable-HTTP transport, accessible at
      ``http://localhost:PORT/mcp``. Use this for IDEs and remote clients.

    - **stdio**: JSON-RPC over stdin/stdout. Use this for local MCP
      clients that spawn the server as a child process (e.g. Claude Desktop,
      Cursor). No port is opened.

    - **sse**: Server-Sent Events transport (legacy, use 'http' instead).
    """
    from prism.iris.sdk.log import logger
    from prism.iris.sdk.preflight import preflight_check
    from prism.mcp.server import mcp
    from prism.settings import settings

    # Resolve alias → FastMCP transport value
    transport_key = transport.lower().strip()
    if transport_key not in TRANSPORT_ALIASES:
        raise typer.BadParameter(
            f"Invalid transport '{transport}'. Choose from: {', '.join(TRANSPORT_ALIASES.keys())}."
        )
    transport_value = TRANSPORT_ALIASES[transport_key]

    logging.basicConfig(level=logging.WARNING)

    if transport_value != "stdio" and not skip_preflight:
        preflight_check()

    if transport_value == "stdio":
        logger.info("Prism MCP server starting (stdio transport)")
        mcp.run(
            transport="stdio",
            show_banner=False,
            log_level="warning",
        )
    else:
        ws_info = (
            f" | workspace: {settings.iris_workspace}"
            if settings.iris_workspace
            else " | workspace: off"
        )
        logger.info(f"Prism ready at http://localhost:{port}/mcp{ws_info}")
        mcp.run(
            transport=transport_value,
            port=port,
            show_banner=False,
            log_level="warning",
        )
