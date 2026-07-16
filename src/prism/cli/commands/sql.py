"""`prism sql` — run an SQL query against IRIS."""

from __future__ import annotations

import asyncio
import sys

import httpx
import typer

from prism.iris.api.sql import execute_query
from prism.iris.sdk.http import base_url
from prism.output import format_output, get_output_format


def sql(
    query: str = typer.Argument(..., help="SQL query to execute"),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
) -> None:
    """Run an SQL query and print the IRIS response as JSON."""
    if not query or not query.strip():
        typer.echo("Error: SQL query cannot be empty.", err=True)
        sys.exit(1)

    try:
        response = asyncio.run(execute_query(query, namespace=namespace))
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
