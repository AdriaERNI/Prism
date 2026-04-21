"""`prism info` — show IRIS server version and namespaces."""

from __future__ import annotations

import asyncio
import sys

import typer

from prism.output import get_output_format
from prism.iris.api.server_info import get_server_info
from prism.output import format_output


def info() -> None:
    """Print server version, installed namespaces, and feature flags."""
    try:
        response = asyncio.run(get_server_info())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(format_output(response, get_output_format()))
