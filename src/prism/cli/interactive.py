"""Interactive REPL for the IRIS WebSocket terminal.

Provides a real terminal-like experience over the IRIS Atelier WebSocket
endpoint. Uses ``prompt_toolkit`` for cross-platform line editing, command
history (up/down arrows), and a smart prompt that mirrors the current IRIS
namespace (e.g. ``USER>``).

Two modes:
- **Interactive**: ``prism ws`` drops into a REPL loop.
- **Single command**: ``prism ws 'w "hello"'`` runs one command and exits.

The interactive session is persistent -- variables, globals, and namespace
state persist across commands within the same session, just like a real
IRIS terminal.
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

import typer

# prompt_toolkit is optional at import time -- we degrade gracefully on
# environments where it's not available (e.g. minimal Docker images).
# The interactive REPL requires it; single-command mode does not.
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.history import FileHistory

    _HAS_PROMPT_TOOLKIT = True
except ImportError:
    PromptSession = None  # type: ignore[assignment, misc]
    ANSI = None  # type: ignore[assignment, misc]
    FileHistory = None  # type: ignore[assignment, misc]
    _HAS_PROMPT_TOOLKIT = False

if TYPE_CHECKING:
    from prompt_toolkit.formatted_text import ANSI as _ANSIType

from prism.iris.api.interactive_ws import InteractiveWSSession
from prism.iris.api.terminal import TerminalError
from prism.settings import settings

# -- ANSI helpers ------------------------------------------------------

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


# -- Special commands --------------------------------------------------

_LOCAL_COMMANDS = {
    "exit": "Exit the terminal session",
    "quit": "Exit the terminal session (same as exit)",
    "clear": "Clear the screen",
    "help": "Show local commands and usage",
    "history": "Show recent command history",
}

# Leading characters for multi-line editing mode, matching IRIS terminal
# behaviour and the vscode-objectscript plugin.
_MULTILINE_PROMPT = "... "


def _is_exit_command(text: str) -> bool:
    return text.strip().lower() in ("exit", "quit", "q", "/exit", "/quit")


def _is_clear_command(text: str) -> bool:
    return text.strip().lower() in ("clear", "cls", "/clear")


def _is_help_command(text: str) -> bool:
    return text.strip().lower() in ("help", "?", "/help")


def _is_history_command(text: str) -> bool:
    return text.strip().lower() in ("history", "/history")


def _input_is_unterminated(text: str) -> bool:
    """Check if *text* has unmatched ``{`` or ``(`` braces.

    Used to detect multi-line ObjectScript constructs (``if { ... }``,
    ``for { ... }``, etc.) so we can show a ``... `` continuation prompt
    instead of sending an incomplete command to IRIS.  String literals
    enclosed in double quotes are skipped.

    Ported from the vscode-objectscript plugin's ``_inputIsUnterminated``.
    """
    in_string = False
    open_paren = 0
    open_brace = 0
    for ch in text:
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == "(":
                open_paren += 1
            elif ch == ")":
                open_paren -= 1
            elif ch == "{":
                open_brace += 1
            elif ch == "}":
                open_brace -= 1
    return open_paren > 0 or open_brace > 0


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


def _format_prompt(prompt_text: str, multiline: bool = False) -> str | _ANSIType:
    """Format the IRIS prompt for display.

    Returns a :class:`~prompt_toolkit.formatted_text.ANSI` object so that
    prompt_toolkit properly parses the embedded escape codes.  Passing a
    raw string with ANSI codes to ``prompt_async()`` causes prompt_toolkit
    to render the ESC byte as literal ``^[`` text — the "weird characters"
    users see in the prompt.

    When *multiline* is True, returns the ``... `` continuation prompt
    instead of the IRIS namespace prompt.
    """
    if multiline:
        formatted = f"{_ANSI_DIM}{_MULTILINE_PROMPT}{_ANSI_RESET}"
    else:
        plain = _strip_ansi(prompt_text).strip()
        if not plain:
            plain = f"{settings.iris_namespace}>"
        formatted = f"{_ANSI_BOLD}{_ANSI_GREEN}{plain}{_ANSI_RESET} "
    # Wrap in ANSI() so prompt_toolkit parses the escape sequences
    # instead of printing the ESC byte as literal ^[ text.
    if ANSI is not None:
        return ANSI(formatted)
    return formatted


def _print_output(text: str) -> None:
    """Print command output to stdout.

    The library layer (``interactive_ws.py`` / ``terminal.py``) already
    strips ANSI escape sequences via ``_clean_text()``.  We apply the same
    defensive stripping here in case output arrives through a different
    path, then print without adding an extra newline (the output already
    contains the necessary line breaks from IRIS).
    """
    if text:
        cleaned = _strip_ansi(text)
        # Remove any remaining control characters except newlines/tabs
        cleaned = "".join(
            ch for ch in cleaned if ch in "\n\r\t" or (ord(ch) >= 32 and ch != "\x7f")
        )
        # Ensure the output ends with a newline so the next prompt appears
        # on its own line.  Without this, the prompt follows the output on
        # the same line (e.g. "helloUSER>" instead of "hello\nUSER>").
        if not cleaned.endswith("\n"):
            cleaned += "\n"
        typer.echo(cleaned, nl=False)


def _clean_text(text: str) -> str:
    """Remove ANSI escape sequences and control characters.

    Strips full ANSI escape sequences (``\\x1b[...m``) and any remaining
    control characters, preserving newlines, tabs, and printable text.
    """
    stripped = _strip_ansi(text)
    return "".join(
        ch for ch in stripped if ch in "\n\r\t" or (ord(ch) >= 32 and ch != "\x7f")
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


# -- Interactive REPL --------------------------------------------------


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
    except EOFError:
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
    try:
        prompt_session: PromptSession = PromptSession(
            history=FileHistory(str(history_file)),
        )
    except Exception as exc:
        # On Windows, prompt_toolkit raises NoConsoleScreenBufferError when
        # there's no real console (e.g. piped through WinRM, CI, or redirect).
        # Fall back to a simple input() loop so the terminal still works,
        # albeit without history navigation and advanced line editing.
        typer.echo(
            f"{_ANSI_DIM}Note: Advanced line editing unavailable ({exc}).\n"
            f"Using basic input mode.{_ANSI_RESET}\n",
        )
        await _simple_repl(session, timeout)
        return

    # Buffer for multi-line input (when braces/parens are unmatched)
    multiline_buffer: str = ""

    while True:
        try:
            # Show the continuation prompt if we're in multi-line mode
            is_multiline = bool(multiline_buffer)
            prompt_str = _format_prompt(session.prompt, multiline=is_multiline)
            user_input = await prompt_session.prompt_async(prompt_str)
        except KeyboardInterrupt:
            # Ctrl+C handling:
            # - If IRIS is evaluating a command, send an interrupt to IRIS
            #   instead of killing the REPL.  This matches real IRIS terminal
            #   behaviour and the vscode-objectscript plugin.
            # - If at the prompt (not evaluating), clear the current input
            #   and multi-line buffer, then show a fresh prompt.
            if session.is_evaluating:
                typer.echo(f"\n{_ANSI_DIM}^C — interrupting IRIS...{_ANSI_RESET}")
                try:
                    await session.interrupt()
                    # Wait for the server to respond with a new prompt
                    # by running a no-op wait.  The interrupt will cause
                    # the pending _wait_for_prompt() to receive an
                    # <INTERRUPT> output and a new prompt.
                except Exception:
                    pass
            else:
                # At the prompt — clear input and multi-line buffer
                multiline_buffer = ""
                typer.echo(f"\n{_ANSI_DIM}^C{_ANSI_RESET}")
            continue
        except EOFError:
            typer.echo(f"\n{_ANSI_DIM}Goodbye.{_ANSI_RESET}")
            break

        text = user_input.strip()
        if not text:
            continue

        # Handle local commands (only when not in multi-line mode)
        if not multiline_buffer:
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

        # Multi-line editing: accumulate input until braces/parens are balanced
        if multiline_buffer:
            multiline_buffer += "\n" + text
        else:
            multiline_buffer = text

        if _input_is_unterminated(multiline_buffer):
            # Need more input — stay in multi-line mode
            continue

        # Input is complete — send the full command to IRIS
        full_command = multiline_buffer
        multiline_buffer = ""

        try:
            result = await session.run(
                full_command, on_read=_make_on_read(prompt_session)
            )
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


def _make_on_read(
    prompt_session: PromptSession | None = None,
) -> Callable[[str], Awaitable[str]]:
    """Create an on_read callback for handling ObjectScript ``read`` commands.

    When IRIS sends a ``read`` message, this callback prompts the user for
    input (using prompt_toolkit if available, otherwise plain input()).
    """

    async def on_read(prompt_text: str) -> str:
        plain = _strip_ansi(prompt_text).strip()
        label = plain if plain else "Input:"
        hint = f"{_ANSI_BOLD}{_ANSI_CYAN}{label} {_ANSI_RESET}"
        if prompt_session is not None:
            try:
                # Wrap in ANSI() so prompt_toolkit parses escape codes
                # instead of rendering ESC as literal ^[ text.
                if ANSI is not None:
                    return await prompt_session.prompt_async(ANSI(hint))
                return await prompt_session.prompt_async(hint)
            except (EOFError, KeyboardInterrupt):
                return ""
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: input(hint))

    return on_read


async def _simple_repl(session: InteractiveWSSession, timeout: float) -> None:
    """Fallback REPL using ``input()`` when ``prompt_toolkit`` is unavailable.

    This runs on Windows when there's no real console (WinRM, CI, pipe).
    No history navigation or advanced line editing -- just a basic loop.
    Supports multi-line editing via the same brace-matching logic.
    """

    loop = asyncio.get_event_loop()
    history: list[str] = []
    multiline_buffer: str = ""

    while True:
        # input() is blocking -- run in a thread so we don't stall the event loop
        is_multiline = bool(multiline_buffer)
        prompt_str = _format_prompt(session.prompt, multiline=is_multiline)
        try:
            user_input = await loop.run_in_executor(None, lambda: input(prompt_str))
        except (EOFError, KeyboardInterrupt):
            if session.is_evaluating:
                typer.echo(f"\n{_ANSI_DIM}^C — interrupting IRIS...{_ANSI_RESET}")
                try:
                    await session.interrupt()
                except Exception:
                    pass
                continue
            typer.echo(f"\n{_ANSI_DIM}Goodbye.{_ANSI_RESET}")
            break

        text = user_input.strip()
        if not text:
            continue

        if not multiline_buffer:
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
                if history:
                    for i, entry in enumerate(history[-20:], 1):
                        display = entry if len(entry) <= 80 else entry[:77] + "..."
                        typer.echo(f"  {i:4d}  {display}")
                else:
                    typer.echo(f"  {_ANSI_DIM}(empty){_ANSI_RESET}")
                continue

        # Multi-line editing
        if multiline_buffer:
            multiline_buffer += "\n" + text
        else:
            multiline_buffer = text

        if _input_is_unterminated(multiline_buffer):
            continue

        full_command = multiline_buffer
        multiline_buffer = ""
        history.append(full_command)

        try:
            result = await session.run(full_command, on_read=_make_on_read(None))
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
