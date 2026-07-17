"""Interactive REPL for the IRIS WebSocket terminal.

Provides a real terminal-like experience over the IRIS Atelier WebSocket
endpoint. Uses ``prompt_toolkit`` for cross-platform line editing, command
history (up/down arrows), and a smart prompt that mirrors the current IRIS
namespace (e.g. ``USER>``).

Two modes:
- **Interactive**: ``prism ws`` drops into a REPL loop.
- **Single command**: ``prism ws 'w "hello"'`` runs one command and exits.

The interactive session is persistent — variables, globals, and namespace
state persist across commands within the same session, just like a real
IRIS terminal.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import typer

# prompt_toolkit is optional at import time — we degrade gracefully on
# environments where it's not available (e.g. minimal Docker images).
# The interactive REPL requires it; single-command mode does not.
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory

    _HAS_PROMPT_TOOLKIT = True
except ImportError:
    PromptSession = None  # type: ignore[assignment, misc]
    FileHistory = None  # type: ignore[assignment, misc]
    _HAS_PROMPT_TOOLKIT = False

from prism.iris.api.interactive_ws import InteractiveWSSession
from prism.iris.api.terminal import TerminalError
from prism.settings import settings

# ── ANSI helpers ──────────────────────────────────────────────────────

_ANSI_RESET = "\x1b[0m"
_ANSI_BOLD = "\x1b[1m"
_ANSI_CYAN = "\x1b[36m"
_ANSI_RED = "\x1b[31m"
_ANSI_GREEN = "\x1b[32m"
_ANSI_DIM = "\x1b[2m"

# IRIS WebSocket prompts include ANSI codes like \x1b[1mUSER>\x1b[0m
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


def _history_path() -> Path:
    """Return the path to the persistent history file."""
    from platformdirs import user_data_path

    data_dir = user_data_path("prism", appauthor=False)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "ws_history"


def _get_version() -> str:
    """Return the Prism version."""
    from prism import __version__

    return __version__


# ── Special commands ──────────────────────────────────────────────────

_LOCAL_COMMANDS = {
    "exit": "Exit the terminal session",
    "quit": "Exit the terminal session (same as exit)",
    "clear": "Clear the screen",
    "help": "Show local commands and usage",
    "history": "Show recent command history",
}


def _is_exit_command(text: str) -> bool:
    return text.strip().lower() in ("exit", "quit", "q", "/exit", "/quit")


def _is_clear_command(text: str) -> bool:
    return text.strip().lower() in ("clear", "cls", "/clear")


def _is_help_command(text: str) -> bool:
    return text.strip().lower() in ("help", "?", "/help")


def _is_history_command(text: str) -> bool:
    return text.strip().lower() in ("history", "/history")


def _print_help() -> None:
    """Print help text for local REPL commands."""
    typer.echo(f"\n{_ANSI_BOLD}Prism WebSocket Terminal -- Local Commands{_ANSI_RESET}")
    typer.echo(f"  {'Command':<12} {'Description'}")
    typer.echo(f"  {'-' * 12} {'-' * 40}")
    for cmd, desc in _LOCAL_COMMANDS.items():
        typer.echo(f"  {cmd:<12} {desc}")
    typer.echo(
        "\n  Type any ObjectScript command and press Enter to execute it on IRIS."
    )
    typer.echo("  Variables and state persist between commands within this session.\n")


def _print_startup_banner(namespace: str) -> None:
    """Print a startup banner when entering interactive mode."""
    version = _get_version()
    typer.echo(
        f"{_ANSI_CYAN}{_ANSI_BOLD}Prism {_ANSI_RESET}{_ANSI_CYAN}{version}"
        f"{_ANSI_RESET} -- Interactive WebSocket Terminal"
    )
    typer.echo(
        f"{_ANSI_DIM}Connected to IRIS at {settings.iris_base_url}"
        f" in namespace {namespace}{_ANSI_RESET}"
    )
    typer.echo(
        f"{_ANSI_DIM}Type 'help' for local commands, 'exit' to quit.{_ANSI_RESET}\n"
    )


def _format_prompt(prompt_text: str) -> str:
    """Format the IRIS prompt for display."""
    plain = _strip_ansi(prompt_text).strip()
    if not plain:
        plain = f"{settings.iris_namespace}>"
    return f"{_ANSI_BOLD}{_ANSI_GREEN}{plain}{_ANSI_RESET} "


def _print_output(text: str) -> None:
    """Print command output to stdout."""
    if text:
        cleaned = _clean_text(text)
        typer.echo(cleaned)


def _clean_text(text: str) -> str:
    """Remove control characters but preserve newlines and tabs."""
    return "".join(
        ch for ch in text if ch in "\n\r\t" or (ord(ch) >= 32 and ch != "\x7f")
    )


def _print_history(prompt_session: PromptSession) -> None:
    """Print recent command history from prompt_toolkit's history."""
    typer.echo(f"\n{_ANSI_BOLD}Command History{_ANSI_RESET}")
    try:
        strings = list(prompt_session.history.get_strings())
        if not strings:
            typer.echo(f"  {_ANSI_DIM}(empty){_ANSI_RESET}")
        else:
            recent = strings[-20:]
            start_idx = max(0, len(strings) - 20)
            for i, entry in enumerate(recent, start_idx + 1):
                display = entry if len(entry) <= 80 else entry[:77] + "..."
                typer.echo(f"  {_ANSI_DIM}{i:4d}{_ANSI_RESET}  {display}")
    except Exception:
        typer.echo(f"  {_ANSI_DIM}(history unavailable){_ANSI_RESET}")
    typer.echo()


# ── Interactive REPL ──────────────────────────────────────────────────


def run_interactive(
    namespace: str | None = None,
    timeout: float = 30.0,
    initial_command: str | None = None,
) -> None:
    """Run the interactive WebSocket terminal REPL.

    If *initial_command* is provided, it is executed first on the same
    session before entering the interactive loop. This allows
    ``prism ws 'set x=42' --interactive`` to run the command then keep
    the session open for further input.

    Requires ``prompt_toolkit``. If not available, prints an error with
    installation instructions.
    """
    if not _HAS_PROMPT_TOOLKIT:
        typer.echo(
            f"{_ANSI_RED}Error: Interactive mode requires the 'prompt_toolkit' package.\n"
            f"Install it with: pip install prompt_toolkit{_ANSI_RESET}",
            err=True,
        )
        sys.exit(1)

    try:
        asyncio.run(_async_interactive(namespace, timeout, initial_command))
    except KeyboardInterrupt:
        typer.echo(f"\n{_ANSI_DIM}Goodbye.{_ANSI_RESET}")


async def _async_interactive(
    namespace: str | None,
    timeout: float,
    initial_command: str | None = None,
) -> None:
    """Async implementation of the interactive REPL."""
    ns = namespace or settings.iris_namespace

    try:
        session = InteractiveWSSession(namespace=ns, timeout=timeout)
        await session.connect()
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Run initial command if provided (--interactive with a command)
    if initial_command:
        try:
            result = await session.run(initial_command)
            typer.echo(result.get("output", ""))
        except TerminalError as exc:
            typer.echo(f"{_ANSI_RED}{exc}{_ANSI_RESET}", err=True)
        except Exception as exc:
            typer.echo(f"{_ANSI_RED}Error: {exc}{_ANSI_RESET}", err=True)

    _print_startup_banner(session.namespace)

    history_file = _history_path()
    prompt_session: PromptSession = PromptSession(
        history=FileHistory(str(history_file)),
    )

    while True:
        try:
            prompt_str = _format_prompt(session.prompt)
            user_input = await prompt_session.prompt_async(prompt_str)
        except (EOFError, KeyboardInterrupt):
            typer.echo(f"\n{_ANSI_DIM}Goodbye.{_ANSI_RESET}")
            break

        text = user_input.strip()
        if not text:
            continue

        # Handle local commands
        if _is_exit_command(text):
            typer.echo(f"{_ANSI_DIM}Goodbye.{_ANSI_RESET}")
            break
        if _is_clear_command(text):
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            continue
        if _is_help_command(text):
            _print_help()
            continue
        if _is_history_command(text):
            _print_history(prompt_session)
            continue

        # Execute ObjectScript command on IRIS
        try:
            result = await session.run(text)
            _print_output(result.get("output", ""))
        except TerminalError as exc:
            typer.echo(f"{_ANSI_RED}{exc}{_ANSI_RESET}", err=True)
        except asyncio.TimeoutError:
            typer.echo(
                f"{_ANSI_RED}Error: Command timed out after {timeout}s{_ANSI_RESET}",
                err=True,
            )
        except Exception as exc:
            typer.echo(f"{_ANSI_RED}Error: {exc}{_ANSI_RESET}", err=True)

    await session.close()
