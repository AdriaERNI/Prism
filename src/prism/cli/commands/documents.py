"""`prism get-doc`, `list-docs`, `put-doc`, `delete-doc` — document CRUD."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer

from prism.iris.api.documents import (
    DocumentNotFound,
    delete_document,
    get_document,
    list_documents,
    put_document,
)


def get_doc(
    name: str = typer.Argument(..., help="Document name (e.g. MyApp.Person.cls)"),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
) -> None:
    """Retrieve a document from IRIS and print the response as JSON."""
    try:
        response = asyncio.run(get_document(name, namespace=namespace))
    except DocumentNotFound as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(json.dumps(response, indent=2, default=str))


def list_docs(
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
    doc_type: str = typer.Option(
        None, "--type", "-t", help="Filter by document type (e.g. cls, mac, int, inc)"
    ),
    generated: bool = typer.Option(
        False, "--generated", help="Include generated documents"
    ),
    filter: str = typer.Option(
        None, "--filter", "-f", help="Filter by name prefix (e.g. MyApp)"
    ),
) -> None:
    """List source documents on the IRIS server."""
    try:
        response = asyncio.run(
            list_documents(
                namespace=namespace,
                doc_type=doc_type,
                generated=generated,
                filter=filter,
            )
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(json.dumps(response, indent=2, default=str))


def put_doc(
    name: str = typer.Argument(..., help="Document name (e.g. MyApp.Person.cls)"),
    file: Path = typer.Argument(
        ...,
        help="Path to local file whose contents will be uploaded",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
) -> None:
    """Upload a local file to IRIS as the given document name."""
    content = file.read_text(encoding="utf-8").splitlines()

    try:
        response = asyncio.run(put_document(name, content, namespace=namespace))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(json.dumps(response, indent=2, default=str))


def delete_doc(
    name: str = typer.Argument(..., help="Document name (e.g. MyApp.Person.cls)"),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
) -> None:
    """Delete a document from IRIS."""
    try:
        response = asyncio.run(delete_document(name, namespace=namespace))
    except DocumentNotFound as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(json.dumps(response, indent=2, default=str))
