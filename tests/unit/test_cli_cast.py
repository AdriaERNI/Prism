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


def _make_fake_repo(
    path: Path,
    commands: dict[str, str] | None = None,
    cast_json: dict | None = None,
):
    """Create a fake git repo at *path* with command scripts.

    Args:
        commands: {name: content} — creates .sh scripts by default.
                  If content starts with '#!python', creates .py.
    cast_json: optional metadata dict written to cast.json.
    """
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)

    cmds_dir = path / "commands"
    cmds_dir.mkdir(exist_ok=True)

    if cast_json:
        (path / "cast.json").write_text(json.dumps(cast_json, indent=2))

    if commands:
        for name, content in commands.items():
            if content.startswith("#!python"):
                script = cmds_dir / f"{name}.py"
                script.write_text(content.replace("#!python\n", ""))
            else:
                script = cmds_dir / f"{name}.sh"
                script.write_text(content)
                script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


def _make_package_repo(path: Path, name: str, cast_json: dict | None = None):
    """Create a fake repo with a Python package command (dir + __main__.py)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)

    cmds_dir = path / "commands"
    cmds_dir.mkdir(exist_ok=True)

    pkg = cmds_dir / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "__main__.py").write_text(f"import sys\nprint('ran {name}', sys.argv[1:])\n")
    (pkg / "core.py").write_text(f"VALUE = 'core-{name}'\n")

    if cast_json:
        (path / "cast.json").write_text(json.dumps(cast_json, indent=2))


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
        manager._save_registry(
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


# ── Add repo (with alias support) ──────────────────────────────────


class TestAddRepo:
    def test_add_clones_and_registers(self, tmp_cast_dir):
        url = "https://github.com/user/Prism-TestRepo.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_fake_repo(target, {"hello": "#!/bin/bash\necho hello"})
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            repo = manager.add_repo(url)

        assert repo.name == "testrepo"
        assert repo.url == url
        assert repo.path.exists()
        assert (repo.path / ".git").exists()

        repos = manager.list_repos()
        assert len(repos) == 1
        assert repos[0].name == "testrepo"

    def test_add_with_custom_alias(self, tmp_cast_dir):
        """cast.json with 'name' field should override the slug."""
        url = "https://github.com/user/Prism-LongRepoName.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_fake_repo(
                target,
                {"tool": "#!/bin/bash\necho tool"},
                cast_json={"name": "short", "description": "My tools"},
            )
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            repo = manager.add_repo(url)

        assert repo.name == "short"
        assert repo.description == "My tools"

        # Path is still based on URL slug, not alias
        assert repo.path == tmp_cast_dir / "longreponame"

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

    def test_add_duplicate_alias_raises(self, tmp_cast_dir):
        url1 = "https://github.com/user/Prism-First.git"
        url2 = "https://github.com/user/Prism-Second.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_fake_repo(target, cast_json={"name": "same-alias"})
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            manager.add_repo(url1)
            with pytest.raises(RuntimeError, match="already in use"):
                manager.add_repo(url2)

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
        # Path is derived from URL slug, not the name
        manager._save_registry(
            [
                {"name": "repo-a", "url": "https://a.git", "description": ""},
                {"name": "repo-b", "url": "https://b.git", "description": ""},
            ]
        )
        # _slug_from_url("https://a.git") = "a", so dir = tmp_cast_dir / "a"
        (tmp_cast_dir / "a").mkdir()
        (tmp_cast_dir / "b").mkdir()

        deleted = manager.del_repo(1)
        assert deleted.name == "repo-a"
        assert not (tmp_cast_dir / "a").exists()

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
            [{"name": "repo-a", "url": "https://a.git", "description": ""}]
        )
        repo_path = tmp_cast_dir / "repo-a"
        _make_fake_repo(repo_path)

        def fake_pull(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "Already up to date.", "")

        with patch("subprocess.run", side_effect=fake_pull):
            results = manager.update_repos()

        assert len(results) == 1
        assert results[0][0] == "repo-a"

    def test_update_missing_repo(self, tmp_cast_dir):
        manager._save_registry(
            [{"name": "ghost", "url": "https://ghost.git", "description": ""}]
        )
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

    def test_finds_python_package_dir(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "pkg-repo"
        _make_package_repo(repo_path, "ip")

        cmds = manager.discover_commands(repo_path)
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
        assert "cast.json" not in cmds

    def test_descriptions_from_cast_json(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "desc-repo"
        _make_fake_repo(
            repo_path,
            {"weather": "#!/bin/bash\necho sun"},
            cast_json={"commands": {"weather": "Show weather"}},
        )
        cmds = manager.discover_commands(repo_path)
        assert cmds["weather"] == "Show weather"


# ── Resolve command ────────────────────────────────────────────────


class TestResolveCommand:
    def test_resolve_file_script(self, tmp_cast_dir):
        # _slug_from_url("https://x.git") = "x"
        repo_path = tmp_cast_dir / "x"
        _make_fake_repo(repo_path, {"weather": "#!/bin/bash\necho sun"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        repo, script = manager.resolve_command("myrepo", "weather")
        assert repo.name == "myrepo"
        assert script.name == "weather.sh"

    def test_resolve_package_dir(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "x"
        _make_package_repo(repo_path, "ip")
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        repo, pkg = manager.resolve_command("myrepo", "ip")
        assert pkg.is_dir()
        assert (pkg / "__main__.py").is_file()

    def test_resolve_missing_repo_raises(self, tmp_cast_dir):
        with pytest.raises(RuntimeError, match="not found"):
            manager.resolve_command("nonexistent", "cmd")

    def test_resolve_missing_command_raises(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "x"
        _make_fake_repo(repo_path, {"weather": "#!/bin/bash\necho sun"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        with pytest.raises(RuntimeError, match="not found"):
            manager.resolve_command("myrepo", "nonexistent")

    def test_resolve_case_insensitive_repo(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "x"
        _make_fake_repo(repo_path, {"weather": "#!/bin/bash\necho sun"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        repo, _ = manager.resolve_command("MYREPO", "weather")
        assert repo.name == "myrepo"


# ── Run command ────────────────────────────────────────────────────


class TestRunCommand:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="bash not available on Windows CI without WSL",
    )
    def test_run_shell_script(self, tmp_cast_dir):
        repo_path = tmp_cast_dir / "x"
        _make_fake_repo(repo_path, {"hello": "#!/bin/bash\necho hello-world"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("myrepo", "hello")

        assert exit_code == 0

    def test_run_python_package(self, tmp_cast_dir):
        """Python package dir with __main__.py should run via python -m."""
        repo_path = tmp_cast_dir / "x"
        _make_package_repo(repo_path, "ip")
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        original_run = subprocess.run

        def selective_mock(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=selective_mock):
            exit_code = manager.run_command("myrepo", "ip")

        assert exit_code == 0

    def test_run_passes_extra_args(self, tmp_cast_dir):
        """Extra args should be passed to the script."""
        repo_path = tmp_cast_dir / "x"
        _make_fake_repo(repo_path, {"echo": "#!/bin/bash\necho ARGS:$@"})
        manager._save_registry(
            [{"name": "myrepo", "url": "https://x.git", "description": ""}]
        )

        captured_cmd = []

        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            if cmd and cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            captured_cmd.append(cmd)
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            manager.run_command("myrepo", "echo", extra_args=["foo", "bar"])

        # The last captured command should include the extra args
        assert "foo" in captured_cmd[-1]
        assert "bar" in captured_cmd[-1]


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

    def test_add_with_custom_alias(self, runner, tmp_cast_dir):
        url = "https://github.com/user/Prism-LongName.git"

        def fake_clone(cmd, **kwargs):
            target = Path(cmd[-1])
            _make_fake_repo(
                target,
                {"tool": "#!/bin/bash\necho tool"},
                cast_json={"name": "short", "description": "Short alias"},
            )
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("subprocess.run", side_effect=fake_clone):
            result = runner.invoke(app, ["cast", "--add", url])

        assert result.exit_code == 0
        assert "short" in result.stdout
        assert "Short alias" in result.stdout

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
