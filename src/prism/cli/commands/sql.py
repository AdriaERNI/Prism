"""`prism sql` — run an SQL query against IRIS."""

from __future__ import annotations

import asyncio
import sys

import typer

from prism.cli.errors import handle_command_error
from prism.iris.api.sql import execute_query
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
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(response, get_output_format()))
