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
    _input_is_unterminated,
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

    def test_clean_text_strips_ansi_error_codes(self):
        """Regression: IRIS sends errors as \\x1b[31;1m<SYNTAX>\\x1b[0m.

        _clean_text must remove the full ANSI escape sequence, not just
        the ESC byte.  Otherwise [31;1m<SYNTAX>[0m appears as literal text.
        """
        text = "\x1b[31;1m<SYNTAX>\x1b[0m"
        assert _clean_text(text) == "<SYNTAX>"

    def test_clean_text_strips_ansi_bold(self):
        """Regression: bold codes \\x1b[1m...\\x1b[0m must be stripped."""
        text = "\x1b[1mUSER>\x1b[0m"
        assert _clean_text(text) == "USER>"

    def test_clean_text_strips_ansi_dim(self):
        """Regression: dim codes \\x1b[2m...\\x1b[0m must be stripped."""
        text = "\x1b[2mhello\x1b[0m"
        assert _clean_text(text) == "hello"

    def test_clean_text_no_literal_bracket_garbage(self):
        """Regression: must not leave [31;1m or [0m as literal text."""
        text = "\x1b[31;1m<SYNTAX>\x1b[0m rest"
        result = _clean_text(text)
        assert "[31;1m" not in result
        assert "[0m" not in result
        assert result == "<SYNTAX> rest"


# ── Multi-line detection ───────────────────────────────────────────


class TestInputIsUnterminated:
    """Tests for _input_is_unterminated — detects multi-line constructs."""

    def test_balanced_braces(self):
        assert _input_is_unterminated("set x = {1, 2, 3}") is False

    def test_unterminated_open_brace(self):
        assert _input_is_unterminated("if x {") is True

    def test_unterminated_nested_braces(self):
        assert _input_is_unterminated("if x { set y = {1, 2} ") is True

    def test_balanced_parens(self):
        assert _input_is_unterminated("write $lb(1, 2, 3)") is False

    def test_unterminated_open_paren(self):
        assert _input_is_unterminated("write $lb(1, 2,") is True

    def test_braces_in_string_ignored(self):
        """Braces inside string literals should not affect detection."""
        assert _input_is_unterminated('set x = "hello { world"') is False

    def test_parens_in_string_ignored(self):
        assert _input_is_unterminated('set x = "func(arg"') is False

    def test_multiple_lines_balanced(self):
        """A multi-line construct that's now balanced should be complete."""
        text = "if x {\n  set y = 1\n}"
        assert _input_is_unterminated(text) is False

    def test_multiple_lines_still_unterminated(self):
        text = "if x {\n  set y = 1\n  if z {"
        assert _input_is_unterminated(text) is True

    def test_empty_string(self):
        assert _input_is_unterminated("") is False

    def test_only_text(self):
        assert _input_is_unterminated("write 1") is False

    def test_mismatched_brace_type(self):
        """``{ )`` is technically unbalanced (open brace, close paren)."""
        # open_brace=1, open_paren=-1 → unterminated (brace > 0)
        assert _input_is_unterminated("{ )") is True


# ── Prompt formatting ────────────────────────────────────────────────


class TestFormatPrompt:
    def test_prompt_with_ansi(self):
        result = _format_prompt("\x1b[1mUSER>\x1b[0m")
        # _format_prompt may return an ANSI object (when prompt_toolkit is
        # available) or a plain string.  Convert to string for assertions.
        result_str = str(result)
        # Should contain plain USER>
        assert "USER>" in result_str

    def test_prompt_empty_uses_default(self):
        from prism.settings import settings

        result = _format_prompt("")
        result_str = str(result)
        assert settings.iris_namespace in result_str
        assert ">" in result_str

    def test_prompt_plain_text(self):
        result = _format_prompt("SAMPLES>")
        result_str = str(result)
        assert "SAMPLES>" in result_str

    def test_prompt_returns_ansi_object_when_available(self):
        """Regression: _format_prompt must return an ANSI() object, not a
        raw string.  Passing a raw string with ESC bytes to
        prompt_toolkit's prompt_async() causes the ESC byte (0x1b) to be
        rendered as literal ``^[`` text — the ``weird characters`` bug.
        """
        from prism.cli.interactive import _HAS_PROMPT_TOOLKIT

        result = _format_prompt("\x1b[1mUSER>\x1b[0m")
        if _HAS_PROMPT_TOOLKIT:
            # When prompt_toolkit is installed, result should be an ANSI
            # object — NOT a plain str.  ANSI objects are recognised by
            # prompt_toolkit and the escape codes are parsed, not shown
            # as literal ^[ text.
            from prompt_toolkit.formatted_text import ANSI as PT_ANSI

            assert isinstance(result, PT_ANSI), (
                f"Expected ANSI object, got {type(result).__name__}. "
                "Raw str with ESC bytes causes ^[ display bug."
            )
        else:
            assert isinstance(result, str)

    def test_prompt_no_visible_escape_chars(self):
        """Regression: the rendered prompt must NOT contain literal ^[
        characters that come from unparsed ESC bytes."""
        result = _format_prompt("\x1b[1mUSER>\x1b[0m")
        result_str = str(result)
        # The ^[ sequence is how terminals display an unparsed ESC byte.
        # If _format_prompt returns a proper ANSI() object, str() of it
        # should NOT contain literal ^[ characters.
        assert "^[" not in result_str, (
            "Prompt contains ^[ literal — ANSI codes not parsed by prompt_toolkit"
        )


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


# ── _make_on_read callback ─────────────────────────────────────────


class TestMakeOnRead:
    """Verify the on_read callback factory for ObjectScript read commands."""

    def test_make_on_read_returns_callable(self):
        from prism.cli.interactive import _make_on_read

        cb = _make_on_read(None)
        assert callable(cb)

    @pytest.mark.asyncio
    async def test_make_on_read_without_session_uses_input(self):
        """Without a PromptSession, _make_on_read falls back to input()."""
        from prism.cli.interactive import _make_on_read

        cb = _make_on_read(None)
        with patch("builtins.input", return_value="user_input"):
            result = await cb("Enter name: ")
        assert result == "user_input"

    @pytest.mark.asyncio
    async def test_make_on_read_strips_ansi_from_prompt(self):
        """The callback strips ANSI codes from the read prompt text
        before embedding it into the hint string."""
        from prism.cli.interactive import _make_on_read

        cb = _make_on_read(None)
        with patch("builtins.input", return_value="val") as mock_input:
            await cb("\x1b[32mEnter value:\x1b[0m ")
        received = mock_input.call_args[0][0]

        # The original ANSI escape (\x1b[32m / \x1b[0m) should be stripped,
        # but _make_on_read adds its own formatting codes (bold cyan).
        # The key is that the prompt text "Enter value:" survived without
        # the original green color codes, and our own formatting is present.
        assert "\x1b[32m" not in received  # original green stripped
        assert "Enter value" in received

    @pytest.mark.asyncio
    async def test_make_on_read_empty_prompt_uses_default_label(self):
        """Empty read prompt text defaults to 'Input:'."""
        from prism.cli.interactive import _make_on_read

        cb = _make_on_read(None)
        with patch("builtins.input", return_value="x") as mock_input:
            await cb("")
        received = mock_input.call_args[0][0]
        assert "Input" in received


# ── EOFError handling ──────────────────────────────────────────────


class TestEOFHandling:
    """Verify that EOFError is handled gracefully in run_interactive."""

    def test_run_interactive_eof_error_exits_cleanly(self):
        """Ctrl+D (EOFError) exits without traceback."""

        with patch(
            "prism.cli.interactive.asyncio.run",
            side_effect=EOFError(),
        ):
            result = runner.invoke(app, ["ws"])
        assert result.exit_code == 0
        assert "Goodbye" in result.output
