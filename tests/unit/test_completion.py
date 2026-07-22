"""Tests for Prism CLI tab completion (Typer/Click shell completion).

These tests verify that Typer's built-in shell completion is enabled and
returns the correct command names when the completion environment variables
are set. Click's completion mechanism uses:

- ``_PRISM_COMPLETE=complete_bash`` (or ``complete_zsh``, ``complete_fish``)
- ``COMP_WORDS`` -- space-separated words typed so far
- ``COMP_CWORD`` -- 0-based index of the word being completed

On a real terminal, the shell completion script (installed via
``prism --install-completion``) calls the CLI with these env vars set and
passes the output to ``COMPREPLY``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

# Use the installed prism console script (via uv run) so Click's program
# name detection matches the _PRISM_COMPLETE env var.
PRISM_CMD = ["uv", "run", "prism"]


def _run_completion(words: str, cword: int) -> list[str]:
    """Run prism with completion env vars and return the suggestions."""
    env = os.environ.copy()
    env["_PRISM_COMPLETE"] = "complete_bash"
    env["COMP_WORDS"] = words
    env["COMP_CWORD"] = str(cword)
    result = subprocess.run(
        PRISM_CMD,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        cwd=Path(__file__).resolve().parent.parent.parent,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _run_prism_help() -> str:
    """Run prism --help and return stdout."""
    result = subprocess.run(
        PRISM_CMD + ["--help"],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=Path(__file__).resolve().parent.parent.parent,
    )
    return result.stdout


# --- Phase 1: Completion is enabled ---


class TestCompletionEnabled:
    """Verify that Typer's completion flags are present in --help."""

    def test_help_shows_install_completion(self):
        """--help should list --install-completion."""
        stdout = _run_prism_help()
        assert "--install-completion" in stdout

    def test_help_shows_show_completion(self):
        """--help should list --show-completion."""
        stdout = _run_prism_help()
        assert "--show-completion" in stdout


# --- Phase 2: Command name completion ---


class TestCommandCompletion:
    """Tab-completion for top-level prism commands."""

    def test_complete_all_commands(self):
        """Empty word after 'prism ' should return all commands."""
        result = _run_completion("prism ", 1)
        expected = {
            "config",
            "sql",
            "terminal",
            "ws",
            "compile",
            "get-doc",
            "list-docs",
            "put-doc",
            "delete-doc",
            "info",
            "test",
            "list-tests",
            "index",
            "serve",
            "setup",
            "cast",
        }
        assert expected.issubset(set(result))

    def test_complete_conf_to_config(self):
        """'prism conf' + Tab should return 'config'."""
        result = _run_completion("prism conf", 1)
        assert result == ["config"]

    def test_complete_s_returns_sql_serve_setup(self):
        """'prism s' + Tab should return 'sql', 'serve', and 'setup'."""
        result = _run_completion("prism s", 1)
        assert set(result) == {"sql", "serve", "setup"}

    def test_complete_c_returns_config_compile_cast_chatbot(self):
        """'prism c' + Tab should return commands starting with 'c'."""
        result = _run_completion("prism c", 1)
        assert set(result) == {"config", "compile", "cast", "chatbot"}

    def test_complete_exact_command(self):
        """'prism sql' + Tab should return 'sql' (exact match)."""
        result = _run_completion("prism sql", 1)
        assert "sql" in result

    def test_complete_no_match(self):
        """'prism xyz' + Tab should return no suggestions."""
        result = _run_completion("prism xyz", 1)
        assert result == []


# --- Phase 3: Subcommand completion (cast) ---
#
# Cast subcommand completion depends on installed cast repos. On CI (fresh
# checkout, no casts cloned), 'prism cast ' returns no subcommands because
# cast repos are registered dynamically from ~/.prism/cast/registry.json.
# We skip cast subcommand tests when no casts are installed.


def _casts_installed() -> bool:
    """Check if any cast repos are registered."""
    import json

    registry = Path.home().joinpath(".prism", "cast", "registry.json")
    if not registry.exists():
        return False
    try:
        data = json.loads(registry.read_text())
        repos = data if isinstance(data, list) else data.get("repos", [])
        return len(repos) > 0
    except Exception:
        return False


@pytest.mark.skipif(
    not _casts_installed(),
    reason="no cast repos installed (fresh CI environment)",
)
class TestCastSubcommandCompletion:
    """Tab-completion for 'prism cast' subcommands."""

    def test_complete_cast_subcommands(self):
        """'prism cast ' + Tab should return 'template' (always registered)."""
        result = _run_completion("prism cast ", 2)
        assert "template" in result

    def test_complete_cast_t(self):
        """'prism cast t' + Tab should return 'template'."""
        result = _run_completion("prism cast t", 2)
        assert result == ["template"]

    def test_complete_cast_template_commands(self):
        """'prism cast template ' + Tab should return template commands."""
        result = _run_completion("prism cast template ", 3)
        expected = {"headers", "ip", "portcheck", "timestamp", "uuid", "weather"}
        assert expected.issubset(set(result))

    def test_complete_cast_template_w(self):
        """'prism cast template w' + Tab should return 'weather'."""
        result = _run_completion("prism cast template w", 3)
        assert result == ["weather"]


# --- Phase 4: Option/flag completion ---


class TestOptionCompletion:
    """Tab-completion for command options (flags)."""

    def test_complete_config_options(self):
        """'prism config -' + Tab should return config options."""
        result = _run_completion("prism config -", 2)
        assert "--help" in result
        assert "--user" in result
        assert "--password" in result
        assert "--namespace" in result

    def test_complete_global_option(self):
        """'prism --' + Tab should return global options."""
        result = _run_completion("prism --", 1)
        assert "--help" in result
        assert "--version" in result
        assert "--install-completion" in result

    def test_complete_short_option(self):
        """'prism config -' should include short options like -u."""
        result = _run_completion("prism config -", 2)
        assert "-u" in result
        assert "-p" in result
        assert "-n" in result


# --- Phase 5: Completion script generation ---


class TestCompletionScript:
    """Verify that --show-completion generates a valid script."""

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_show_completion_generates_script(self, shell):
        """--show-completion SHELL should produce non-empty output."""
        result = subprocess.run(
            PRISM_CMD + ["--show-completion", shell],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=Path(__file__).resolve().parent.parent.parent,
        )
        assert result.returncode == 0
        # Output should contain the prism completion function
        assert "prism" in result.stdout.lower()
        assert len(result.stdout.strip()) > 10
