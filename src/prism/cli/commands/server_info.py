"""`prism info` — show IRIS server version and namespaces."""

from __future__ import annotations

import asyncio
import json
import sys

import typer

from prism.iris.api.server_info import get_server_info


def info() -> None:
    """Print server version, installed namespaces, and feature flags."""
    try:
        response = asyncio.run(get_server_info())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(json.dumps(response, indent=2, default=str))
