"""Shared error-handling utilities for CLI commands.

All CLI command modules face the same set of failure modes when talking
to IRIS:

* ``httpx.ConnectError`` — server unreachable
* ``httpx.ConnectTimeout`` — connection timed out
* ``httpx.HTTPStatusError`` — server returned an error status
* ``TimeoutError`` — a native-terminal command timed out
* Any other ``Exception`` — unexpected error

Rather than repeating the same five-way ``isinstance`` ladder (or the
equivalent four ``except`` clauses) in every command file, every command
delegates to :func:`handle_command_error`, which prints a user-friendly
message to stderr and calls ``sys.exit(1)``.

Because the function always exits the process, its return type is
``NoReturn`` — this lets type checkers understand that code after the
call is unreachable, so there is no need for a redundant ``return``
statement.
"""

from __future__ import annotations

import sys
from typing import NoReturn

import httpx
import typer

from prism.iris.sdk.http import base_url


def handle_command_error(exc: Exception) -> NoReturn:
    """Print a user-friendly error message for *exc* and exit with code 1.

    Handles common IRIS connection failures with helpful guidance.
    Any other exception is printed as ``Error: {exc}``.
    """
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
