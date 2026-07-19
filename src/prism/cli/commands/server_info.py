"""`prism info` — show IRIS server version and namespaces."""

from __future__ import annotations

import asyncio

import typer

from prism.cli.errors import handle_command_error
from prism.iris.api.server_info import get_server_info
from prism.output import format_output, get_output_format


def info() -> None:
    """Print server version, installed namespaces, and feature flags."""
    try:
        response = asyncio.run(get_server_info())
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(response, get_output_format()))
