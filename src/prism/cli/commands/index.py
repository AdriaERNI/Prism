"""prism index — build a compact index of IRIS source code."""

from __future__ import annotations

import asyncio
import sys

import httpx
import typer

from prism.iris.api.index import build_index, index_summary
from prism.iris.sdk.http import base_url
from prism.output import format_output, get_output_format


def index(
    namespace: str = typer.Option(
        "", "--namespace", "-n", help="IRIS namespace to index."
    ),
    include_system: bool = typer.Option(
        False, "--system", help="Include system classes."
    ),
    prefix: str = typer.Option(
        "", "--prefix", help="Only index classes with this prefix."
    ),
    summary: bool = typer.Option(
        False, "--summary", help="Only show counts, no class details."
    ),
) -> None:
    """Build a compact index of classes in an IRIS namespace.

    Useful for understanding the structure of large IRIS codebases without
    reading every document. Outputs class hierarchies, methods, properties,
    SQL projections, imports, and dependencies as JSON.
    """
    ns = namespace or None
    prefix_val = prefix or None

    try:
        if summary:
            result = asyncio.run(index_summary(ns))
        else:
            result = asyncio.run(
                build_index(
                    namespace=ns,
                    include_system=include_system,
                    filter_prefix=prefix_val,
                )
            )
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

    typer.echo(format_output(result, get_output_format()))
