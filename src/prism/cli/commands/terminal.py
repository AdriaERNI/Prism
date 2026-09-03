"""`prism ws` (WebSocket) terminal command.

The WebSocket terminal uses the Atelier WebSocket terminal. It does NOT
upload our own ObjectScript helper (MCP.Terminal) and does NOT use the
native SuperServer ("superport") path.

Two modes:
- **Single command**: ``prism ws 'w "hello"'`` -- run one command and exit.
- **Interactive REPL**: ``prism ws`` (no command argument) -- enters a
  persistent terminal session with command history, line editing, and a
  smart prompt that mirrors the IRIS namespace.
"""

from __future__ import annotations

import asyncio

import typer

from prism.cli.errors import handle_command_error
from prism.cli.interactive import run_interactive
from prism.iris.api.terminal import execute_command_ws
from prism.output import format_output, get_output_format


def ws(
    command: str = typer.Argument(
        None,
        help="ObjectScript command to run (e.g. 'w \"hello\"'). "
        "If omitted, enters interactive terminal mode.",
    ),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Timeout in seconds", min=0.1),
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
            handle_command_error(exc)
            return  # handle_command_error calls sys.exit, but keeps type checkers happy

        typer.echo(format_output(result, get_output_format()))
        return

    # Interactive mode (with or without an initial command)

    initial_command: str | None = None
    if command and command.strip():
        initial_command = command.strip()

    run_interactive(namespace=namespace, timeout=timeout, initial_command=initial_command)
