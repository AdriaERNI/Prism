"""`prism compile` — compile one or more documents on IRIS."""

from __future__ import annotations

import asyncio
import sys

import typer

from prism.cli.errors import handle_command_error
from prism.iris.api.compile import compile_documents
from prism.output import format_output, get_output_format


def compile(
    documents: list[str] = typer.Argument(
        ...,
        help="One or more document names to compile (e.g. MyApp.Person.cls)",
    ),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
    flags: str = typer.Option(
        None,
        "--flags",
        help="Compile flags (defaults to IRIS_COMPILE_FLAGS, typically 'cuk')",
    ),
) -> None:
    """Compile documents on IRIS."""
    if not documents:
        typer.echo("Error: at least one document name is required.", err=True)
        sys.exit(1)

    # Validate document names are non-empty
    empty = [d for d in documents if not d.strip()]
    if empty:
        typer.echo("Error: document names cannot be empty.", err=True)
        sys.exit(1)

    try:
        response = asyncio.run(
            compile_documents(documents, namespace=namespace, flags=flags)
        )
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(response, get_output_format()))
