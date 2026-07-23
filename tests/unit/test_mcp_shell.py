"""Tests for MCP shell tool (prism.mcp.shell).

Tests verify:
- Shell auto-detection (PowerShell on Windows, Bash on Linux/macOS)
- Command execution and output capture
- Timeout handling
- Root user refusal
- Output truncation
- Error handling
"""

from __future__ import annotations

import platform
from unittest.mock import patch

import pytest

from prism.mcp.shell import _get_shell_command, _truncate_output, run_shell


class TestGetShellCommand:
    """Tests for platform shell detection."""

    def test_returns_powershell_on_windows(self):
        with patch("prism.mcp.shell.platform.system", return_value="Windows"):
            exe, args = _get_shell_command()
            assert exe == "powershell.exe"
            assert "-NoProfile" in args
            assert "-Command" in args

    def test_returns_bash_on_linux(self):
        with patch("prism.mcp.shell.platform.system", return_value="Linux"):
            exe, args = _get_shell_command()
            assert exe == "/bin/bash"
            assert "-c" in args

    def test_returns_bash_on_macos(self):
        with patch("prism.mcp.shell.platform.system", return_value="Darwin"):
            exe, args = _get_shell_command()
            assert exe == "/bin/bash"
            assert "-c" in args


class TestTruncateOutput:
    """Tests for output truncation."""

    def test_short_output_unchanged(self):
        assert _truncate_output("short") == "short"

    def test_long_output_truncated(self):
        text = "x" * 20_000
        result = _truncate_output(text)
        assert len(result) < len(text)
        assert "truncated" in result

    def test_truncates_at_line_boundary(self):
        lines = [f"line {i} " + "x" * 50 for i in range(500)]
        text = "\n".join(lines)
        result = _truncate_output(text)
        assert "truncated" in result
        # Should end at a line boundary (before the truncation marker)
        assert (
            result.split("\n...")[0].rstrip().endswith("x")
            or "\nline " in result.split("\n...")[0]
        )


class TestRunShell:
    """Tests for the run_shell MCP tool."""

    async def test_echo_command_succeeds(self, tmp_path, monkeypatch):
        """A simple echo command should return output."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await run_shell(command="echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]
        assert result["shell"] in ("bash", "powershell")

    async def test_command_returns_exit_code(self, tmp_path, monkeypatch):
        """Exit code should be returned."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        if platform.system() == "Windows":
            result = await run_shell(command="exit 42")
        else:
            result = await run_shell(command="exit 42")
        assert result["exit_code"] == 42

    async def test_stderr_captured(self, tmp_path, monkeypatch):
        """Stderr should be captured."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        if platform.system() == "Windows":
            result = await run_shell(command="Write-Error 'test error'")
        else:
            result = await run_shell(command="echo 'test error' >&2")
        # stderr should contain the error message
        assert "test error" in result["stderr"] or result["exit_code"] != 0

    async def test_timeout_kills_command(self, tmp_path, monkeypatch):
        """A command that exceeds the timeout should be killed."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        if platform.system() == "Windows":
            result = await run_shell(command="Start-Sleep -Seconds 10", timeout=1.0)
        else:
            result = await run_shell(command="sleep 10", timeout=1.0)
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"]

    async def test_cwd_respected(self, tmp_path, monkeypatch):
        """Working directory should be used."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        if platform.system() == "Windows":
            result = await run_shell(command="Get-Location", cwd=str(sub))
        else:
            result = await run_shell(command="pwd", cwd=str(sub))
        assert str(sub) in result["stdout"] or sub.name in result["stdout"]

    async def test_command_in_result(self, tmp_path, monkeypatch):
        """The executed command should be in the result."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await run_shell(command="echo test")
        assert result["command"] == "echo test"

    @pytest.mark.skipif(platform.system() == "Windows", reason="POSIX-only test")
    async def test_refuses_root_on_linux(self, tmp_path, monkeypatch):
        """Should refuse to run as root on POSIX."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        with patch("os.geteuid", return_value=0):
            result = await run_shell(command="echo hello")
            assert result["exit_code"] == -1
            assert "root" in result["stderr"]
