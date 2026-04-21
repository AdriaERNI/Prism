"""`prism serve` — start the Prism MCP server."""

from __future__ import annotations

import logging

import typer

DEFAULT_PORT = 3000


def serve(
    port: int = typer.Option(
        DEFAULT_PORT, "--port", "-p", help="Port to bind the MCP server to."
    ),
    skip_preflight: bool = typer.Option(
        False,
        "--skip-preflight",
        help="Skip the IRIS connectivity check at startup.",
    ),
) -> None:
    """Start the Prism MCP server (streamable-http transport)."""
    from prism.config import IRIS_WORKSPACE
    from prism.iris.sdk.log import logger
    from prism.iris.sdk.preflight import preflight_check
    from prism.mcp.server import mcp

    logging.basicConfig(level=logging.WARNING)

    if not skip_preflight:
        preflight_check()

    ws_info = (
        f" | workspace: {IRIS_WORKSPACE}" if IRIS_WORKSPACE else " | workspace: off"
    )
    logger.info(f"Prism ready at http://localhost:{port}/mcp{ws_info}")
    mcp.run(
        transport="streamable-http",
        port=port,
        show_banner=False,
        log_level="warning",
    )
