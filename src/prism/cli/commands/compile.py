"""`prism compile` — compile one or more documents on IRIS."""

from __future__ import annotations

import asyncio
import sys

import typer

from prism.output import get_output_format
from prism.iris.api.compile import compile_documents
from prism.output import format_output


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
    try:
        response = asyncio.run(
            compile_documents(documents, namespace=namespace, flags=flags)
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(format_output(response, get_output_format()))
