"""`prism info` — show IRIS server version and namespaces."""

from __future__ import annotations

import asyncio
import sys

import httpx
import typer

from prism.iris.api.server_info import get_server_info
from prism.iris.sdk.http import base_url
from prism.output import format_output, get_output_format


def info() -> None:
    """Print server version, installed namespaces, and feature flags."""
    try:
        response = asyncio.run(get_server_info())
    except httpx.ConnectError:
        typer.echo(
            f"Error: Cannot connect to IRIS at {base_url()}. Is the server running?",
            err=True,
        )
        sys.exit(1)
    except httpx.ConnectTimeout:
        typer.echo(
            f"Error: Connection to IRIS at {base_url()} timed out.",
            err=True,
        )
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        typer.echo(
            f"Error: IRIS returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:200]}",
            err=True,
        )
        sys.exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(format_output(response, get_output_format()))
