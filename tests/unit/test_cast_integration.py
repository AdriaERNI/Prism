"""Unit tests for cast template integration.

These tests verify the full cast pipeline using a cast repo that mirrors
the real Prism-CastTemplate-Public structure:

1. Create a cast repo temp directory with __init__.py + commands/
2. Import it via the manager (spec_from_file_location)
3. Verify __prism_name__ and app are correct
4. Enumerate commands via Click introspection
5. Run commands via the manager's run_command
6. Verify commands that import Prism's own modules work

No network or git access required — repos are created locally.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from prism.cast import manager
from prism.cli.app import app


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_cast_dir(tmp_path, monkeypatch):
    """Redirect cast_dir() to a temp directory."""
    monkeypatch.setattr(manager, "cast_dir", lambda: tmp_path / "cast")
    (tmp_path / "cast").mkdir(parents=True, exist_ok=True)
    return tmp_path / "cast"


def _make_template_repo(path: Path) -> Path:
    """Create a cast repo that mirrors Prism-CastTemplate-Public.

    Returns the repo path. The repo has:
    - __init__.py with __prism_name__ = "template" + Typer app
    - commands/ package with 6 commands (weather, ip, uuid, timestamp,
      portcheck, headers) matching the real template
    - A command that imports prism.settings (to verify Prism API access)
    """
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)

    commands_dir = path / "commands"
    commands_dir.mkdir(exist_ok=True)
    (commands_dir / "__init__.py").write_text('"""Commands package."""\n')

    # ── commands/uuid.py ──
    (commands_dir / "uuid.py").write_text(
        '"""Generate a random UUID."""\n'
        "import typer\n\n"
        "def uuid() -> None:\n"
        '    """Generate a random UUID."""\n'
        "    import uuid as _uuid\n"
        "    print(_uuid.uuid4())\n"
    )

    # ── commands/timestamp.py ──
    (commands_dir / "timestamp.py").write_text(
        '"""Print the current Unix timestamp."""\n'
        "import time\n"
        "import typer\n\n"
        "def timestamp() -> None:\n"
        '    """Print the current Unix timestamp."""\n'
        "    print(int(time.time()))\n"
    )

    # ── commands/portcheck.py ──
    (commands_dir / "portcheck.py").write_text(
        '"""Check if a port is open on a host."""\n'
        "import socket\n"
        "import sys\n"
        "import typer\n\n"
        "def portcheck(\n"
        '    host: str = typer.Argument(..., help="Hostname or IP"),\n'
        '    port: int = typer.Argument(..., help="Port number"),\n'
        ") -> None:\n"
        '    """Check if a port is open on a host."""\n'
        "    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    sock.settimeout(3)\n"
        "    try:\n"
        "        sock.connect((host, port))\n"
        '        print(f"OPEN   {host}:{port}")\n'
        "    except (socket.timeout, ConnectionRefusedError, OSError) as exc:\n"
        '        print(f"CLOSED {host}:{port} ({exc})")\n'
        "        sys.exit(1)\n"
        "    finally:\n"
        "        sock.close()\n"
    )

    # ── commands/echo_settings.py (imports Prism's own API) ──
    (commands_dir / "echo_settings.py").write_text(
        '"""Echo Prism connection settings — demonstrates Prism API access."""\n'
        "import typer\n\n"
        "def echo_settings() -> None:\n"
        '    """Show the IRIS base URL from Prism settings."""\n'
        "    from prism.settings import settings\n"
        '    print(f"iris_base_url={settings.iris_base_url}")\n'
    )

    # ── commands/echo_format.py (imports Prism's output formatter) ──
    (commands_dir / "echo_format.py").write_text(
        '"""Format output using Prism formatter."""\n'
        "import typer\n\n"
        "def echo_format() -> None:\n"
        '    """Format a dict as JSON using Prism output."""\n'
        "    from prism.output import format_output\n"
        '    typer.echo(format_output({"status": "ok", "cast": "works"}))\n'
    )

    # ── commands/echo_sql.py (imports Prism's SQL API) ──
    (commands_dir / "echo_sql.py").write_text(
        '"""Demonstrate Prism SQL API import (does not execute)."""\n'
        "import typer\n\n"
        "def echo_sql() -> None:\n"
        '    """Verify Prism SQL API is importable."""\n'
        "    from prism.iris.api.sql import execute_query\n"
        '    print(f"execute_query callable: {callable(execute_query)}")\n'
    )

    # ── Root __init__.py ──
    init_content = '''"""Cast template repo — useful everyday tools."""

import typer

__prism_name__ = "template"

app = typer.Typer(
    name="template",
    help="Useful everyday tools for developers",
    no_args_is_help=True,
    add_completion=False,
)

from .commands.uuid import uuid
from .commands.timestamp import timestamp
from .commands.portcheck import portcheck
from .commands.echo_settings import echo_settings
from .commands.echo_format import echo_format
from .commands.echo_sql import echo_sql

app.command()(uuid)
app.command()(timestamp)
app.command()(portcheck)
app.command()(echo_settings)
app.command()(echo_format)
app.command()(echo_sql)
'''
    (path / "__init__.py").write_text(init_content)

    return path


# ── Import & introspection ─────────────────────────────────────────


class TestCastImport:
    """Verify the manager can import a template-style repo."""

    def test_import_reads_prism_name(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "casttemplate"
        _make_template_repo(repo_path)

        mod = manager._import_cast(repo_path)
        assert hasattr(mod, "__prism_name__")
        assert mod.__prism_name__ == "template"

    def test_import_reads_app(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "casttemplate"
        _make_template_repo(repo_path)

        mod = manager._import_cast(repo_path)
        assert hasattr(mod, "app")
        import typer

        assert isinstance(mod.app, typer.Typer)

    def test_read_metadata_returns_alias(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "casttemplate"
        _make_template_repo(repo_path)

        alias, desc, commands = manager._read_cast_metadata(repo_path)
        assert alias == "template"
        assert "tools" in desc.lower()

    def test_read_metadata_enumerates_all_commands(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "casttemplate"
        _make_template_repo(repo_path)

        alias, desc, commands = manager._read_cast_metadata(repo_path)

        cmd_names = {c.name for c in commands}
        assert cmd_names == {
            "uuid",
            "timestamp",
            "portcheck",
            "echo-settings",
            "echo-format",
            "echo-sql",
        }

    def test_read_metadata_has_help_text(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "casttemplate"
        _make_template_repo(repo_path)

        alias, desc, commands = manager._read_cast_metadata(repo_path)

        for cmd in commands:
            assert cmd.help, f"Command '{cmd.name}' has empty help text"


# ── Add + list + run (CLI integration with mocked git) ─────────────


class TestCastAddAndRun:
    """End-to-end: add repo, list it, run commands, delete."""

    def test_add_registers_with_alias(self, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            repo = manager.add_repo(url)

        assert repo.name == "template"
        assert repo.url == url
        assert repo.path.exists()
        assert len(repo.commands) == 6

    def test_list_shows_commands(self, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)

        repos = manager.list_repos()
        assert len(repos) == 1
        assert repos[0].name == "template"
        cmd_names = {c.name for c in repos[0].commands}
        assert "uuid" in cmd_names
        assert "echo-format" in cmd_names

    def test_run_uuid_command(self, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("template", ["uuid"])

        assert exit_code == 0

    def test_run_timestamp_command(self, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("template", ["timestamp"])

        assert exit_code == 0

    def test_del_removes_repo(self, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)

        deleted = manager.del_repo(1)
        assert deleted.name == "template"
        assert len(manager.list_repos()) == 0


# ── Prism API access from cast commands ────────────────────────────


class TestPrismApiAccess:
    """Verify cast commands can import and use Prism's internal modules."""

    def test_echo_settings_imports_prism_settings(self, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("template", ["echo-settings"])

        assert exit_code == 0

    def test_echo_format_imports_prism_output(self, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("template", ["echo-format"])

        assert exit_code == 0

    def test_echo_sql_imports_prism_api(self, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("template", ["echo-sql"])

        assert exit_code == 0


# ── CLI runner integration ─────────────────────────────────────────


class TestCliIntegration:
    """Full CLI invocation: prism cast --add ... template uuid."""

    def test_cli_add_and_help(self, runner, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            result = runner.invoke(app, ["cast", "--add", url])

        assert result.exit_code == 0
        assert "template" in result.stdout
        assert "uuid" in result.stdout
        assert "echo-settings" in result.stdout
        assert "echo-sql" in result.stdout

    def test_cli_list_shows_alias(self, runner, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            runner.invoke(app, ["cast", "--add", url])
            result = runner.invoke(app, ["cast", "--list"])

        assert result.exit_code == 0
        assert "template" in result.stdout
        assert "echo-settings" in result.stdout

    def test_cli_del(self, runner, tmp_cast_dir):
        url = "https://github.com/AdriaERNI/Prism-CastTemplate-Public.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_template_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            runner.invoke(app, ["cast", "--add", url])
            result = runner.invoke(app, ["cast", "--del", "1"])

        assert result.exit_code == 0
        assert "template" in result.stdout
        assert "Deleted" in result.stdout
