"""Unit tests for `prism cast` — repo management and command execution.

Tests use real temp directories and mock subprocess calls for git operations.
No network access required.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
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


@pytest.fixture
def tmp_cast_dir_with_registry(tmp_cast_dir):
    """Same as tmp_cast_dir but ensures registry starts empty."""
    return tmp_cast_dir


def _make_fake_repo(path: Path, commands: dict[str, str] | None = None):
    """Create a fake git repo at *path* with command scripts."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)

    cmds_dir = path / "commands"
    cmds_dir.mkdir(exist_ok=True)

    if commands:
        meta = {"description": "Test repo", "commands": {}}
        for name, content in commands.items():
            script = cmds_dir / f"{name}.sh"
            script.write_text(content)
            script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
            meta["commands"][name] = f"{name} command"
        (path / "cast.json").write_text(json.dumps(meta, indent=2))


# ── Slug derivation ─────────────────────────────────────────────────


class TestSlugFromUrl:
    def test_https_with_git_suffix(self):
        assert (
            _slug_from_url("https://github.com/user/Prism-CustomCastTemplate.git")
            == "customcasttemplate"
        )

    def test_https_without_git_suffix(self):
        assert _slug_from_url("https://github.com/user/MyCastRepo") == "mycastrepo"

    def test_prism_prefix_stripped(self):
        assert _slug_from_url("https://github.com/user/Prism-Weather.git") == "weather"

    def test_no_prism_prefix(self):
        assert _slug_from_url("https://github.com/user/tools.git") == "tools"

    def test_ssh_url(self):
        assert _slug_from_url("git@github.com:user/Prism-MyTools.git") == "mytools"

    def test_lowercase(self):
        assert (
            _slug_from_url("https://github.com/user/MixedCaseRepo.git")
            == "mixedcaserepo"
        )


# ── Registry ────────────────────────────────────────────────────────


class TestRegistry:
    def test_empty_registry(self, tmp_cast_dir):
        repos = manager.list_repos()
        assert repos == []

    def test_save_and_load(self, tmp_cast_dir):
        _save = manager._save_registry
        _save(
            [
                {
                    "name": "test-repo",
                    "url": "https://example.com/repo.git",
                    "description": "",
                }
            ]
        )
        repos = manager.list_repos()
        assert len(repos) == 1
        assert repos[0].name == "test-repo"
        assert repos[0].url == "https://example.com/repo.git"
        assert repos[0].path == tmp_cast_dir / "test-repo"


# ── Add repo ────────────────────────────────────────────────────────


class TestAddRepo:
    def test_add_clones_and_registers(self, tmp_cast_dir):
        url = "https://github.com/user/Prism-TestRepo.git"

        # Mock git clone to create a fake repo
        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_fake_repo(target, {"hello": "#!/bin/bash\necho hello"})
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            repo = manager.add_repo(url)

        assert repo.name == "testrepo"
        assert repo.url == url
        assert repo.path == tmp_cast_dir / "testrepo"
        assert repo.path.exists()
        assert (repo.path / ".git").exists()

        # Registry updated
        repos = manager.list_repos()
        assert len(repos) == 1
        assert repos[0].name == "testrepo"

    def test_add_duplicate_url_raises(self, tmp_cast_dir):
        url = "https://github.com/user/Prism-Dup.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_fake_repo(target)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url)
            with pytest.raises(RuntimeError, match="already registered"):
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
        # Setup: register two repos
        manager._save_registry(
            [
                {"name": "repo-a", "url": "https://a.git", "description": ""},
                {"name": "repo-b", "url": "https://b.git", "description": ""},
            ]
        )
        # Create fake directories
        (tmp_cast_dir / "repo-a").mkdir()
        (tmp_cast_dir / "repo-b").mkdir()

        deleted = manager.del_repo(1)
        assert deleted.name == "repo-a"
        assert not (tmp_cast_dir / "repo-a").exists()
        assert (tmp_cast_dir / "repo-b").exists()

        repos = manager.list_repos()
        assert len(repos) == 1
        assert repos[0].name == "repo-b"

    def test_del_invalid_index_raises(self, tmp_cast_dir):
        manager._save_registry(
            [{"name": "only", "url": "https://x.git", "description": ""}]
        )
        with pytest.raises(RuntimeError, match="Invalid index"):
            manager.del_repo(0)
        with pytest.raises(RuntimeError, match="Invalid index"):
            manager.del_repo(2)


# ── Update repos ───────────────────────────────────────────────────


class TestUpdateRepos:
    def test_update_all(self, tmp_cast_dir):
        manager._save_registry(
            [
                {"name": "repo-a", "url": "https://a.git", "description": ""},
            ]
        )
        repo_path = tmp_cast_dir / "repo-a"
        _make_fake_repo(repo_path)

        def fake_pull(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "Already up to date.", "")

        with patch("subprocess.run", side_effect=fake_pull):
            results = manager.update_repos()

        assert len(results) == 1
        assert results[0][0] == "repo-a"
        assert "updated" in results[0][1] or "ok" in results[0][1]

    def test_update_missing_repo(self, tmp_cast_dir):
        manager._save_registry(
            [
                {"name": "ghost", "url": "https://ghost.git", "description": ""},
            ]
        )
        # No directory created
        results = manager.update_repos()
        assert len(results) == 1
        assert "missing" in results[0][1]


# ── Command discovery ──────────────────────────────────────────────


class TestDiscoverCommands:
    def test_finds_scripts_in_commands_dir(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "test-repo"
        _make_fake_repo(
            repo_path,
            {"weather": "#!/bin/bash\necho sun", "ip": "#!/bin/bash\necho 1.2.3.4"},
        )

        cmds = manager.discover_commands(repo_path)
        assert "weather" in cmds
        assert "ip" in cmds

    def test_finds_scripts_in_root_if_no_commands_dir(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "flat-repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()
        script = repo_path / "hello.sh"
        script.write_text("#!/bin/bash\necho hi")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

        cmds = manager.discover_commands(repo_path)
        assert "hello" in cmds

    def test_ignores_readme_and_meta(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "clean-repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()
        cmds_dir = repo_path / "commands"
        cmds_dir.mkdir()
        (repo_path / "README.md").write_text("readme")
        (repo_path / "cast.json").write_text("{}")
        script = cmds_dir / "run.sh"
        script.write_text("#!/bin/bash\necho run")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

        cmds = manager.discover_commands(repo_path)
        assert "run" in cmds
        assert "README" not in cmds
        assert "README.md" not in cmds

    def test_descriptions_from_cast_json(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "desc-repo"
        _make_fake_repo(repo_path, {"weather": "#!/bin/bash\necho sun"})
        cmds = manager.discover_commands(repo_path)
        assert cmds["weather"] == "weather command"


# ── Resolve & run ──────────────────────────────────────────────────


class TestResolveCommand:
    def test_resolve_existing_command(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "myrepo"
        _make_fake_repo(repo_path, {"weather": "#!/bin/bash\necho sun"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        repo, script = manager.resolve_command("myrepo", "weather")
        assert repo.name == "myrepo"
        assert script.name == "weather.sh"

    def test_resolve_missing_repo_raises(self, tmp_cast_dir):
        with pytest.raises(RuntimeError, match="not found"):
            manager.resolve_command("nonexistent", "cmd")

    def test_resolve_missing_command_raises(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "myrepo"
        _make_fake_repo(repo_path, {"weather": "#!/bin/bash\necho sun"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        with pytest.raises(RuntimeError, match="not found"):
            manager.resolve_command("myrepo", "nonexistent")

    def test_resolve_case_insensitive_repo(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "myrepo"
        _make_fake_repo(repo_path, {"weather": "#!/bin/bash\necho sun"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        repo, _ = manager.resolve_command("MYREPO", "weather")
        assert repo.name == "myrepo"


class TestRunCommand:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="bash not available on Windows CI without WSL",
    )
    def test_run_executes_script(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "myrepo"
        _make_fake_repo(repo_path, {"hello": "#!/bin/bash\necho hello-world"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        # Mock subprocess.run for the command execution (not git clone)
        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            # Git operations return success
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            # Command execution — actually run it
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("myrepo", "hello")

        assert exit_code == 0


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
                    "description": "Handy tools",
                },
            ]
        )
        result = runner.invoke(app, ["cast", "--list"])
        assert result.exit_code == 0
        assert "tools" in result.stdout
        assert "Handy tools" in result.stdout
        assert "https://github.com/me/tools.git" in result.stdout


class TestCliCastAdd:
    def test_add_success(self, runner, tmp_cast_dir):
        url = "https://github.com/user/Prism-CoolTools.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_fake_repo(target, {"ip": "#!/bin/bash\necho 1.2.3.4"})
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
        assert "Error" in result.stdout or "Error" in (result.stderr or "")


class TestCliCastDel:
    def test_del_by_index(self, runner, tmp_cast_dir):
        manager._save_registry(
            [{"name": "repo-a", "url": "https://a.git", "description": ""}]
        )
        (tmp_cast_dir / "repo-a").mkdir()

        result = runner.invoke(app, ["cast", "--del", "1"])
        assert result.exit_code == 0
        assert "repo-a" in result.stdout
        assert "Deleted" in result.stdout

    def test_del_invalid_index(self, runner, tmp_cast_dir):
        result = runner.invoke(app, ["cast", "--del", "99"])
        assert result.exit_code == 1


class TestCliCastUpdate:
    def test_update_no_repos(self, runner, tmp_cast_dir):
        result = runner.invoke(app, ["cast", "--update"])
        assert result.exit_code == 0
        assert "No cast repos" in result.stdout

    def test_update_with_repos(self, runner, tmp_cast_dir):
        manager._save_registry(
            [{"name": "repo-a", "url": "https://a.git", "description": ""}]
        )
        repo_path = tmp_cast_dir / "repo-a"
        _make_fake_repo(repo_path)

        def fake_pull(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "Already up to date.", "")

        with patch("subprocess.run", side_effect=fake_pull):
            result = runner.invoke(app, ["cast", "--update"])

        assert result.exit_code == 0
        assert "repo-a" in result.stdout


class TestCliCastRun:
    def test_no_args_shows_usage(self, runner, tmp_cast_dir):
        result = runner.invoke(app, ["cast"])
        assert result.exit_code == 1

    def test_missing_dot_in_target(self, runner, tmp_cast_dir):
        result = runner.invoke(app, ["cast", "justname"])
        assert result.exit_code == 1
        assert "must be" in result.stdout or "must be" in (result.stderr or "")

    def test_run_unknown_repo(self, runner, tmp_cast_dir):
        result = runner.invoke(app, ["cast", "unknown.weather"])
        assert result.exit_code == 1
        assert "not found" in result.stdout or "not found" in (result.stderr or "")
