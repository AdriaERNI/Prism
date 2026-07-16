"""`prism terminal` (native) and `prism ws` (WebSocket) terminal commands.

The ``ws`` command supports two modes:

- **Single command**: ``prism ws 'w "hello"'`` -- run one command and exit.
- **Interactive REPL**: ``prism ws`` (no command argument) -- enters a
  persistent terminal session with command history, line editing, and a
  smart prompt that mirrors the IRIS namespace.
"""

from __future__ import annotations

import asyncio
import sys

import httpx
import typer

from prism.iris.api.terminal import execute_command_ws
from prism.iris.sdk.http import base_url
from prism.iris.sdk.terminal import execute_command as execute_command_native
from prism.output import format_output, get_output_format


def _handle_error(exc: Exception) -> None:
    """Print a user-friendly error message and exit."""
    if isinstance(exc, httpx.ConnectError):
        typer.echo(
            f"Error: Cannot connect to IRIS at {base_url()}. Is the server running?",
            err=True,
        )
    elif isinstance(exc, httpx.ConnectTimeout):
        typer.echo(
            f"Error: Connection to IRIS at {base_url()} timed out.",
            err=True,
        )
    elif isinstance(exc, httpx.HTTPStatusError):
        typer.echo(
            f"Error: IRIS returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:200]}",
            err=True,
        )
    elif isinstance(exc, TimeoutError):
        typer.echo(f"Error: Command timed out — {exc}", err=True)
    else:
        typer.echo(f"Error: {exc}", err=True)
    sys.exit(1)


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
    if not command or not command.strip():
        typer.echo("Error: command cannot be empty.", err=True)
        sys.exit(1)

    try:
        result = asyncio.run(execute_command_native(command, namespace, timeout))
    except Exception as exc:
        _handle_error(exc)
        return  # _handle_error calls sys.exit, but keeps type checkers happy

    typer.echo(format_output(result, get_output_format()))


def ws(
    command: str = typer.Argument(
        None,
        help="ObjectScript command to run (e.g. 'w \"hello\"'). "
        "If omitted, enters interactive terminal mode.",
    ),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", "-t", help="Timeout in seconds", min=0.1
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Force interactive mode even when a command is provided.",
    ),
) -> None:
    """Run an ObjectScript command or start an interactive terminal session.

    Single command mode:

        prism ws 'w \"hello\"'
        prism ws 'Write $ZVersion'

    Interactive mode (no command argument):

        prism ws
        prism ws -n SAMPLES

    Interactive mode preserves variables between commands:

        USER> set x=42
        USER> write x
        42
    """
    # If command is provided and --interactive not forced, run single command
    if command and command.strip() and not interactive:
        try:
            result = asyncio.run(execute_command_ws(command, namespace, timeout))
        except Exception as exc:
            _handle_error(exc)
            return  # _handle_error calls sys.exit, but keeps type checkers happy

        typer.echo(format_output(result, get_output_format()))
        return

    # Interactive mode (with or without an initial command)
    from prism.cli.interactive import run_interactive

    initial_command: str | None = None
    if command and command.strip():
        initial_command = command.strip()

    run_interactive(
        namespace=namespace, timeout=timeout, initial_command=initial_command
    )
