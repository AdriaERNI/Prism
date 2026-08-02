"""`prism serve` — start the Prism MCP server."""

from __future__ import annotations

import logging

import typer

DEFAULT_PORT = 3000
VALID_TRANSPORTS = ("stdio", "http", "streamable-http")


def serve(
    transport: str = typer.Option(
        "streamable-http",
        "--transport",
        "-t",
        help="MCP transport: 'stdio' (stdin/stdout, no port needed) or "
        "'streamable-http' (default, listens on a port).",
    ),
    port: int = typer.Option(
        DEFAULT_PORT,
        "--port",
        "-p",
        help="Port to bind the MCP server to (ignored for stdio).",
        min=1,
        max=65535,
    ),
    skip_preflight: bool = typer.Option(
        False,
        "--skip-preflight",
        help="Skip the IRIS connectivity check at startup.",
    ),
) -> None:
    """Start the Prism MCP server.

    Supports two transports:

    - **streamable-http** (default): listens on a port, accessible via
      ``http://localhost:PORT/mcp``. Use for network-accessible setups.
    - **stdio**: communicates over stdin/stdout. Use for local MCP clients
      (Claude Code, VS Code Copilot, etc.) that spawn the server as a
      subprocess. No port is needed.
    """
    if transport not in VALID_TRANSPORTS:
        raise typer.BadParameter(
            f"Unknown transport: {transport!r}. Choose from: {', '.join(VALID_TRANSPORTS)}"
        )

    from prism.iris.sdk.log import logger
    from prism.iris.sdk.preflight import preflight_check
    from prism.mcp.server import mcp
    from prism.settings import settings

    logging.basicConfig(level=logging.WARNING)

    # stdio transport implies local execution — skip preflight unless
    # the user explicitly passes --skip-preflight=False.
    if transport == "stdio":
        skip_preflight = True

    if not skip_preflight:
        preflight_check()

    if transport == "stdio":
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
            transport="streamable-http",
            port=port,
            show_banner=False,
            log_level="warning",
        )
