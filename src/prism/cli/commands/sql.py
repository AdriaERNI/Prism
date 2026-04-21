"""`prism sql` — run an SQL query against IRIS."""

from __future__ import annotations

import asyncio
import json
import sys

import typer

from prism.iris.api.sql import execute_query


def sql(
    query: str = typer.Argument(..., help="SQL query to execute"),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
) -> None:
    """Run an SQL query and print the IRIS response as JSON."""
    try:
        response = asyncio.run(execute_query(query, namespace=namespace))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(json.dumps(response, indent=2, default=str))
