"""Unit tests for the interactive REPL helpers and CLI command.

Tests cover:
- ANSI stripping / prompt formatting
- Local command detection (exit, clear, help, history)
- CLI command: single-command mode still works
- CLI command: interactive mode requires no command arg
- History file path resolution
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from prism.cli.app import app
from prism.cli.interactive import (
    _clean_text,
    _format_prompt,
    _is_clear_command,
    _is_exit_command,
    _is_help_command,
    _is_history_command,
    _strip_ansi,
)

runner = CliRunner()


# ── ANSI helpers ─────────────────────────────────────────────────────


class TestAnsiHelpers:
    def test_strip_ansi_removes_bold(self):
        text = "\x1b[1mUSER>\x1b[0m"
        assert _strip_ansi(text) == "USER>"

    def test_strip_ansi_removes_color(self):
        text = "\x1b[36mhello\x1b[0m"
        assert _strip_ansi(text) == "hello"

    def test_strip_ansi_no_codes(self):
        assert _strip_ansi("plain text") == "plain text"

    def test_strip_ansi_multiple_codes(self):
        text = "\x1b[1m\x1b[36mUSER>\x1b[0m\x1b[0m"
        assert _strip_ansi(text) == "USER>"

    def test_clean_text_preserves_newlines(self):
        assert _clean_text("hello\nworld") == "hello\nworld"

    def test_clean_text_strips_control_chars(self):
        assert _clean_text("ok\x00bad\x07") == "okbad"

    def test_clean_text_preserves_tabs(self):
        assert _clean_text("a\tb") == "a\tb"


# ── Prompt formatting ────────────────────────────────────────────────


class TestFormatPrompt:
    def test_prompt_with_ansi(self):
        result = _format_prompt("\x1b[1mUSER>\x1b[0m")
        # Should contain plain USER> and ANSI formatting
        assert "USER>" in result
        assert "\x1b[" in result  # has ANSI codes

    def test_prompt_empty_uses_default(self):
        from prism.settings import settings

        result = _format_prompt("")
        assert settings.iris_namespace in result
        assert ">" in result

    def test_prompt_plain_text(self):
        result = _format_prompt("SAMPLES>")
        assert "SAMPLES>" in result


# ── Local command detection ─────────────────────────────────────────


class TestLocalCommands:
    class TestExitCommand:
        @pytest.mark.parametrize(
            "text", ["exit", "EXIT", "quit", "q", "/exit", "/quit"]
        )
        def test_recognized(self, text):
            assert _is_exit_command(text) is True

        @pytest.mark.parametrize("text", ["ex", "quite", "set x=1", "", "write 1"])
        def test_not_recognized(self, text):
            assert _is_exit_command(text) is False

    class TestClearCommand:
        @pytest.mark.parametrize("text", ["clear", "CLEAR", "cls", "/clear"])
        def test_recognized(self, text):
            assert _is_clear_command(text) is True

        @pytest.mark.parametrize("text", ["clea", "clr", "write 1", ""])
        def test_not_recognized(self, text):
            assert _is_clear_command(text) is False

    class TestHelpCommand:
        @pytest.mark.parametrize("text", ["help", "HELP", "?", "/help"])
        def test_recognized(self, text):
            assert _is_help_command(text) is True

    class TestHistoryCommand:
        @pytest.mark.parametrize("text", ["history", "HISTORY", "/history"])
        def test_recognized(self, text):
            assert _is_history_command(text) is True


# ── CLI: ws command single-command mode ─────────────────────────────


class TestWsSingleCommand:
    """The existing single-command mode must still work."""

    def test_ws_command_is_registered(self):
        """`prism ws --help` should show the new --interactive option."""
        result = runner.invoke(app, ["ws", "--help"])
        assert result.exit_code == 0
        assert "--interactive" in result.output or "-i" in result.output

    def test_ws_with_command_runs_single(self):
        """`prism ws 'w \"hello\"'` runs a single command."""
        mock_result = {
            "namespace": "USER",
            "command": 'w "hello"',
            "output": "hello",
            "prompt": "USER>",
        }
        with patch(
            "prism.cli.commands.terminal.execute_command_ws",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = runner.invoke(app, ["ws", 'w "hello"'])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["output"] == "hello"

    def test_ws_with_interactive_flag_enters_interactive(self):
        """`prism ws 'cmd' --interactive` enters interactive mode."""
        called = {}

        def fake_run_interactive(namespace, timeout, initial_command):
            called["namespace"] = namespace
            called["timeout"] = timeout
            called["initial_command"] = initial_command
            return None

        with patch(
            "prism.cli.interactive.run_interactive", side_effect=fake_run_interactive
        ):
            result = runner.invoke(app, ["ws", "set x=42", "--interactive"])

        assert result.exit_code == 0
        assert called["initial_command"] == "set x=42"

    def test_ws_no_command_calls_run_interactive(self):
        """`prism ws` (no args) enters interactive mode."""
        called = {}

        def fake_run_interactive(namespace, timeout, initial_command):
            called["namespace"] = namespace
            called["timeout"] = timeout
            called["initial_command"] = initial_command
            return None

        with patch(
            "prism.cli.interactive.run_interactive", side_effect=fake_run_interactive
        ):
            result = runner.invoke(app, ["ws"])

        assert result.exit_code == 0
        assert called["initial_command"] is None
        assert called["namespace"] is None  # default

    def test_ws_no_command_with_namespace(self):
        """`prism ws -n SAMPLES` passes namespace to interactive mode."""
        called = {}

        def fake_run_interactive(namespace, timeout, initial_command):
            called["namespace"] = namespace
            called["initial_command"] = initial_command
            return None

        with patch(
            "prism.cli.interactive.run_interactive", side_effect=fake_run_interactive
        ):
            result = runner.invoke(app, ["ws", "-n", "SAMPLES"])

        assert result.exit_code == 0
        assert called["namespace"] == "SAMPLES"

    def test_ws_command_timeout_option(self):
        """`prism ws -t 5` passes timeout to interactive mode."""
        called = {}

        def fake_run_interactive(namespace, timeout, initial_command):
            called["timeout"] = timeout
            return None

        with patch(
            "prism.cli.interactive.run_interactive", side_effect=fake_run_interactive
        ):
            result = runner.invoke(app, ["ws", "-t", "5"])

        assert result.exit_code == 0
        assert called["timeout"] == 5.0


# ── CLI: ws command error handling ─────────────────────────────────


class TestWsErrorHandling:
    def test_ws_single_command_error(self):
        """Single command failures exit with code 1."""
        with patch(
            "prism.cli.commands.terminal.execute_command_ws",
            new_callable=AsyncMock,
            side_effect=ConnectionError("cannot connect"),
        ):
            result = runner.invoke(app, ["ws", "write 1"])

        assert result.exit_code == 1
        assert (
            "cannot connect" in result.output.lower()
            or "error" in result.output.lower()
        )
