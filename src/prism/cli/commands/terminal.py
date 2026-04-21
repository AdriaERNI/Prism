"""`prism terminal` (native) and `prism ws` (WebSocket) terminal commands."""

from __future__ import annotations

import asyncio
import json
import sys

import typer

from prism.iris.api.terminal import execute_command_ws
from prism.iris.sdk.terminal import execute_command as execute_command_native


def terminal(
    command: str = typer.Argument(..., help="ObjectScript command (e.g. 'Write 42')"),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", "-t", help="Timeout in seconds", min=0.1
    ),
) -> None:
    """Run an ObjectScript command via irisnative (SuperServer)."""
    try:
        result = asyncio.run(execute_command_native(command, namespace, timeout))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(json.dumps(result, indent=2, default=str))


def ws(
    command: str = typer.Argument(..., help="ObjectScript command (e.g. 'Write 42')"),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", "-t", help="Timeout in seconds", min=0.1
    ),
) -> None:
    """Run an ObjectScript command via the Atelier WebSocket terminal."""
    try:
        result = asyncio.run(execute_command_ws(command, namespace, timeout))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(json.dumps(result, indent=2, default=str))
