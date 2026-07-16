"""Unit tests for `prism cast` — Typer plugin system.

Tests use real temp directories and mock subprocess for git operations.
No network access required — cast repos are created as temp packages.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from prism.cast import manager
from prism.cast.manager import _slug_from_url
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


def _make_cast_repo(path: Path, name: str = "test-cast", commands: dict | None = None):
    """Create a fake cast repo with __init__.py + Typer app.

    Args:
        path: Where to create the repo (must include .git dir).
        name: The __prism_name__ value.
        commands: {cmd_name: docstring} — creates stub command functions.
    """
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)

    cmds_dir = path / "commands"
    cmds_dir.mkdir(exist_ok=True)
    (cmds_dir / "__init__.py").write_text("")

    if commands is None:
        commands = {"hello": "Say hello.", "bye": "Say goodbye."}

    # Write command modules
    import_lines = []
    reg_lines = []
    for cmd_name, docstring in commands.items():
        (cmds_dir / f"{cmd_name}.py").write_text(
            f"import typer\n\n"
            f"def {cmd_name}() -> None:\n"
            f'    """{docstring}"""\n'
            f"    print('{cmd_name} executed')\n"
        )
        import_lines.append(f"from .commands.{cmd_name} import {cmd_name}")
        reg_lines.append(f"app.command()({cmd_name})")

    (path / "__init__.py").write_text(
        "import typer\n\n"
        f'__prism_name__ = "{name}"\n\n'
        f'app = typer.Typer(name="{name}", help="{name} cast repo", '
        f"no_args_is_help=True, add_completion=False)\n\n"
        + "\n".join(import_lines)
        + "\n"
        + "\n".join(reg_lines)
        + "\n"
    )


# ── Slug derivation ─────────────────────────────────────────────────


class TestSlugFromUrl:
    def test_https_with_git_suffix(self):
        assert (
            _slug_from_url("https://github.com/user/Prism-CastTemplate.git")
            == "casttemplate"
        )

    def test_prism_prefix_stripped(self):
        assert _slug_from_url("https://github.com/user/Prism-Weather.git") == "weather"

    def test_no_prism_prefix(self):
        assert _slug_from_url("https://github.com/user/tools.git") == "tools"

    def test_ssh_url(self):
        assert _slug_from_url("git@github.com:user/Prism-MyTools.git") == "mytools"


# ── Registry ────────────────────────────────────────────────────────


class TestRegistry:
    def test_empty_registry(self, tmp_cast_dir):
        assert manager.list_repos() == []

    def test_save_and_load(self, tmp_cast_dir):
        manager._save_registry(
            [
                {
                    "name": "test",
                    "url": "https://x.git",
                    "slug": "x",
                    "description": "",
                    "commands": [],
                }
            ]
        )
        repos = manager.list_repos()
        assert len(repos) == 1
        assert repos[0].name == "test"
        assert repos[0].url == "https://x.git"


# ── Add repo (import-based) ────────────────────────────────────────


class TestAddRepo:
    def test_add_clones_and_imports(self, tmp_cast_dir):
        url = "https://github.com/user/Prism-TestRepo.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_cast_repo(
                target,
                name="testrepo",
                commands={"hello": "Say hello.", "bye": "Say bye."},
            )
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            repo = manager.add_repo(url)

        assert repo.name == "testrepo"
        assert repo.url == url
        assert repo.path.exists()
        assert (repo.path / ".git").exists()
        assert len(repo.commands) == 2
        cmd_names = {c.name for c in repo.commands}
        assert "hello" in cmd_names
        assert "bye" in cmd_names

        # Registry has cached metadata
        repos = manager.list_repos()
        assert len(repos) == 1
        assert repos[0].name == "testrepo"
        assert repos[0].commands[0].name in ("hello", "bye")

    def test_add_duplicate_url_raises(self, tmp_cast_dir):
        url = "https://github.com/user/Prism-Dup.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_cast_repo(target, name="dup")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)
            with pytest.raises(RuntimeError, match="already registered"):
                manager.add_repo(url)

    def test_add_duplicate_alias_raises(self, tmp_cast_dir):
        urls = [
            "https://github.com/user/Prism-First.git",
            "https://github.com/user/Prism-Second.git",
        ]

        call_count = [0]

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_cast_repo(target, name="same-alias")
            call_count[0] += 1
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(urls[0])
            with pytest.raises(RuntimeError, match="already in use"):
                manager.add_repo(urls[1])

    def test_add_missing_prism_name_raises(self, tmp_cast_dir):
        url = "https://github.com/user/Prism-BadRepo.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)
            (target / ".git").mkdir()
            (target / "__init__.py").write_text("import typer\napp = typer.Typer()\n")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            with pytest.raises(RuntimeError, match="__prism_name__"):
                manager.add_repo(url)

    def test_add_missing_app_raises(self, tmp_cast_dir):
        url = "https://github.com/user/Prism-NoApp.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)
            (target / ".git").mkdir()
            (target / "__init__.py").write_text('__prism_name__ = "noapp"\n')
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            with pytest.raises(RuntimeError, match="does not define `app`"):
                manager.add_repo(url)

    def test_add_clone_failure_raises(self, tmp_cast_dir):
        url = "https://github.com/user/nonexistent.git"

        def fake_clone(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "fatal: not found")

        with patch("subprocess.run", side_effect=fake_clone):
            with pytest.raises(RuntimeError, match="Failed to clone"):
                manager.add_repo(url)


# ── Delete repo ────────────────────────────────────────────────────


class TestDelRepo:
    def test_del_by_index(self, tmp_cast_dir):
        manager._save_registry(
            [
                {
                    "name": "a",
                    "url": "https://a.git",
                    "slug": "a",
                    "description": "",
                    "commands": [],
                },
                {
                    "name": "b",
                    "url": "https://b.git",
                    "slug": "b",
                    "description": "",
                    "commands": [],
                },
            ]
        )
        (tmp_cast_dir / "a").mkdir()
        (tmp_cast_dir / "b").mkdir()

        deleted = manager.del_repo(1)
        assert deleted.name == "a"
        assert not (tmp_cast_dir / "a").exists()

        repos = manager.list_repos()
        assert len(repos) == 1
        assert repos[0].name == "b"

    def test_del_invalid_index(self, tmp_cast_dir):
        manager._save_registry(
            [
                {
                    "name": "only",
                    "url": "https://x.git",
                    "slug": "x",
                    "description": "",
                    "commands": [],
                }
            ]
        )
        with pytest.raises(RuntimeError, match="Invalid index"):
            manager.del_repo(0)
        with pytest.raises(RuntimeError, match="Invalid index"):
            manager.del_repo(2)


# ── Update repos ───────────────────────────────────────────────────


class TestUpdateRepos:
    def test_update_missing_repo(self, tmp_cast_dir):
        manager._save_registry(
            [
                {
                    "name": "ghost",
                    "url": "https://ghost.git",
                    "slug": "ghost",
                    "description": "",
                    "commands": [],
                }
            ]
        )
        results = manager.update_repos()
        assert len(results) == 1
        assert "missing" in results[0][1]


# ── get_cast_app + run_command ────────────────────────────────────


class TestGetCastApp:
    def test_get_app_returns_typer(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "x"
        _make_cast_repo(
            repo_path,
            name="myrepo",
            commands={"hello": "Say hello.", "bye": "Say bye."},
        )
        manager._save_registry(
            [
                {
                    "name": "myrepo",
                    "url": "https://x.git",
                    "slug": "x",
                    "description": "",
                    "commands": [],
                }
            ]
        )

        app = manager.get_cast_app("myrepo")
        assert app is not None

    def test_get_app_unknown_raises(self, tmp_cast_dir):
        with pytest.raises(RuntimeError, match="not found"):
            manager.get_cast_app("nonexistent")

    def test_get_app_case_insensitive(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "x"
        _make_cast_repo(
            repo_path,
            name="myrepo",
            commands={"hello": "Say hello.", "bye": "Say bye."},
        )
        manager._save_registry(
            [
                {
                    "name": "myrepo",
                    "url": "https://x.git",
                    "slug": "x",
                    "description": "",
                    "commands": [],
                }
            ]
        )

        app = manager.get_cast_app("MYREPO")
        assert app is not None


class TestRunCommand:
    def test_run_executes_command(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "x"
        _make_cast_repo(
            repo_path,
            name="myrepo",
            commands={"hello": "Say hello.", "bye": "Say bye."},
        )
        manager._save_registry(
            [
                {
                    "name": "myrepo",
                    "url": "https://x.git",
                    "slug": "x",
                    "description": "",
                    "commands": [],
                }
            ]
        )

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("myrepo", ["hello"])

        assert exit_code == 0

    def test_run_unknown_command_returns_error(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "x"
        _make_cast_repo(
            repo_path,
            name="myrepo",
            commands={"hello": "Say hello.", "bye": "Say bye."},
        )
        manager._save_registry(
            [
                {
                    "name": "myrepo",
                    "url": "https://x.git",
                    "slug": "x",
                    "description": "",
                    "commands": [],
                }
            ]
        )

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("myrepo", ["nonexistent"])

        # Typer returns exit code 2 for unknown commands
        assert exit_code != 0


# ── CLI integration ─────────────────────────────────────────────────


class TestCliCastList:
    def test_list_empty(self, runner, tmp_cast_dir):
        result = runner.invoke(app, ["cast", "--list"])
        assert result.exit_code == 0
        assert "No cast repos" in result.stdout

    def test_list_with_repos(self, runner, tmp_cast_dir):
        manager._save_registry(
            [
                {
                    "name": "tools",
                    "url": "https://github.com/me/tools.git",
                    "slug": "tools",
                    "description": "Handy tools",
                    "commands": [
                        {"name": "ip", "help": "Show IP"},
                        {"name": "uuid", "help": "Gen UUID"},
                    ],
                }
            ]
        )
        result = runner.invoke(app, ["cast", "--list"])
        assert result.exit_code == 0
        assert "tools" in result.stdout
        assert "Handy tools" in result.stdout
        assert "ip" in result.stdout


class TestCliCastAdd:
    def test_add_success(self, runner, tmp_cast_dir):
        url = "https://github.com/user/Prism-CoolTools.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_cast_repo(target, name="cooltools", commands={"ip": "Show IP."})
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            result = runner.invoke(app, ["cast", "--add", url])

        assert result.exit_code == 0
        assert "cooltools" in result.stdout
        assert url in result.stdout
        assert "ip" in result.stdout

    def test_add_clone_failure(self, runner, tmp_cast_dir):
        url = "https://github.com/user/nonexistent.git"

        def fake_clone(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "fatal: not found")

        with patch("subprocess.run", side_effect=fake_clone):
            result = runner.invoke(app, ["cast", "--add", url])

        assert result.exit_code == 1


class TestCliCastDel:
    def test_del_by_index(self, runner, tmp_cast_dir):
        manager._save_registry(
            [
                {
                    "name": "a",
                    "url": "https://a.git",
                    "slug": "a",
                    "description": "",
                    "commands": [],
                }
            ]
        )
        (tmp_cast_dir / "a").mkdir()

        result = runner.invoke(app, ["cast", "--del", "1"])
        assert result.exit_code == 0
        assert "Deleted" in result.stdout
        assert "'a'" in result.stdout

    def test_del_invalid_index(self, runner, tmp_cast_dir):
        result = runner.invoke(app, ["cast", "--del", "99"])
        assert result.exit_code == 1


class TestCliCastUpdate:
    def test_update_no_repos(self, runner, tmp_cast_dir):
        result = runner.invoke(app, ["cast", "--update"])
        assert result.exit_code == 0
        assert "No cast repos" in result.stdout
