"""`prism compile` — compile one or more documents on IRIS."""

from __future__ import annotations

import asyncio
import sys

import httpx
import typer

from prism.iris.api.compile import compile_documents
from prism.iris.sdk.http import base_url
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
