"""Unit tests for the ``prism setup`` command.

Tests cover:
  - Config file path resolution per service / OS
  - Patchers (preview generation) for all 4 services
  - Appliers (actual file writing) for all 4 services
  - Idempotency (running twice doesn't duplicate)
  - Preservation of existing config
  - CLI integration via Typer's CliRunner
  - Error handling (invalid service name)
  - Custom URL and port options
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prism.cli.app import app
from prism.cli.commands.install import (
    CLAUDE,
    CODEX,
    HERMES,
    OPENCODE,
    SERVER_NAME,
    _config_path,
    _default_url,
    _patch_claude,
    _patch_codex,
    _patch_hermes,
    _patch_opencode,
    _apply_claude,
    _apply_codex,
    _apply_hermes,
    _apply_opencode,
)

runner = CliRunner()

IS_WINDOWS = sys.platform == "win32"


def _expected_opencode_path(tmp_home: Path) -> Path:
    """Return the expected OpenCode config path for the current OS."""
    if IS_WINDOWS:
        return tmp_home / "AppData" / "Roaming" / "opencode" / "opencode.json"
    return tmp_home / ".config" / "opencode" / "opencode.json"


# ── Helpers ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary HOME and patch os.path.expanduser.

    Also patches APPDATA (Windows) and XDG_CONFIG_HOME (Linux/macOS) so
    that _config_path() for OpenCode resolves inside the temp directory
    on every platform.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))

    # Windows: APPDATA is used for the OpenCode config path
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(appdata))

    # Linux/macOS: XDG_CONFIG_HOME is used for the OpenCode config path
    xdg_config = tmp_path / ".config"
    xdg_config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

    # HERMES_HOME so Hermes config resolves inside temp
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    return tmp_path


# ── URL helper ────────────────────────────────────────────────────────


class TestDefaultUrl:
    def test_default_port(self) -> None:
        assert _default_url(3000) == "http://localhost:3000/mcp"

    def test_custom_port(self) -> None:
        assert _default_url(8080) == "http://localhost:8080/mcp"

    def test_port_1(self) -> None:
        assert _default_url(1) == "http://localhost:1/mcp"


# ── Config file paths ──────────────────────────────────────────────────


class TestConfigPath:
    def test_claude_path(self, tmp_home: Path) -> None:
        assert _config_path(CLAUDE) == tmp_home / ".claude.json"

    def test_codex_path(self, tmp_home: Path) -> None:
        assert _config_path(CODEX) == tmp_home / ".codex" / "config.toml"

    def test_opencode_path(self, tmp_home: Path) -> None:
        assert _config_path(OPENCODE) == _expected_opencode_path(tmp_home)

    def test_hermes_path(self, tmp_home: Path) -> None:
        assert _config_path(HERMES) == tmp_home / ".hermes" / "config.yaml"

    def test_unknown_service_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown service"):
            _config_path("unknown")


# ── Claude Code patcher ──────────────────────────────────────────────


class TestPatchClaude:
    def test_create_new(self, tmp_home: Path) -> None:
        url = "http://localhost:3000/mcp"
        path, action, content = _patch_claude(url)

        assert action == "create"
        assert path == tmp_home / ".claude.json"
        data = json.loads(content)
        assert data["mcpServers"][SERVER_NAME] == {"type": "http", "url": url}

    def test_modify_existing(self, tmp_home: Path) -> None:
        # Write existing config
        config_file = tmp_home / ".claude.json"
        config_file.write_text(json.dumps({"theme": "dark"}))
        url = "http://localhost:3000/mcp"
        path, action, content = _patch_claude(url)

        assert action == "modify"
        data = json.loads(content)
        assert data["theme"] == "dark"
        assert data["mcpServers"][SERVER_NAME] == {"type": "http", "url": url}

    def test_update_existing_prism(self, tmp_home: Path) -> None:
        config_file = tmp_home / ".claude.json"
        old_url = "http://localhost:9999/mcp"
        config_file.write_text(
            json.dumps({"mcpServers": {SERVER_NAME: {"type": "http", "url": old_url}}})
        )
        new_url = "http://localhost:3000/mcp"
        path, action, content = _patch_claude(new_url)

        assert action == "modify"
        data = json.loads(content)
        assert data["mcpServers"][SERVER_NAME]["url"] == new_url


class TestApplyClaude:
    def test_writes_file(self, tmp_home: Path) -> None:
        url = "http://localhost:3000/mcp"
        path = _apply_claude(url)

        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["mcpServers"][SERVER_NAME] == {"type": "http", "url": url}

    def test_preserves_existing(self, tmp_home: Path) -> None:
        config_file = tmp_home / ".claude.json"
        config_file.write_text(
            json.dumps(
                {
                    "theme": "dark",
                    "mcpServers": {"other": {"type": "http", "url": "http://x"}},
                }
            )
        )
        url = "http://localhost:3000/mcp"
        _apply_claude(url)

        data = json.loads(config_file.read_text())
        assert data["theme"] == "dark"
        assert "other" in data["mcpServers"]
        assert SERVER_NAME in data["mcpServers"]


# ── Codex patcher ─────────────────────────────────────────────────────


class TestPatchCodex:
    def test_create_new(self, tmp_home: Path) -> None:
        url = "http://localhost:3000/mcp"
        path, action, content = _patch_codex(url)

        assert action == "create"
        assert path == tmp_home / ".codex" / "config.toml"
        assert f"[mcp_servers.{SERVER_NAME}]" in content
        assert f'url = "{url}"' in content

    def test_modify_existing(self, tmp_home: Path) -> None:
        config_file = tmp_home / ".codex" / "config.toml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('model = "o4-mini"\n')
        url = "http://localhost:3000/mcp"
        path, action, content = _patch_codex(url)

        assert action == "modify"
        assert 'model = "o4-mini"' in content
        assert f"[mcp_servers.{SERVER_NAME}]" in content

    def test_replace_existing_prism(self, tmp_home: Path) -> None:
        config_file = tmp_home / ".codex" / "config.toml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            f'[mcp_servers.{SERVER_NAME}]\nurl = "http://old:9999/mcp"\n'
        )
        url = "http://localhost:3000/mcp"
        _, _, content = _patch_codex(url)

        # Should not have duplicate sections
        assert content.count(f"[mcp_servers.{SERVER_NAME}]") == 1
        assert url in content
        assert "http://old:9999/mcp" not in content


class TestApplyCodex:
    def test_writes_file(self, tmp_home: Path) -> None:
        url = "http://localhost:3000/mcp"
        path = _apply_codex(url)

        assert path.is_file()
        content = path.read_text()
        assert f"[mcp_servers.{SERVER_NAME}]" in content
        assert url in content

    def test_preserves_existing(self, tmp_home: Path) -> None:
        config_file = tmp_home / ".codex" / "config.toml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            'model = "o4-mini"\n\n[mcp_servers.existing]\ncommand = "foo"\n'
        )
        _apply_codex("http://localhost:3000/mcp")

        content = config_file.read_text()
        assert 'model = "o4-mini"' in content
        assert "[mcp_servers.existing]" in content
        assert f"[mcp_servers.{SERVER_NAME}]" in content


# ── OpenCode patcher ──────────────────────────────────────────────────


class TestPatchOpencode:
    def test_create_new(self, tmp_home: Path) -> None:
        url = "http://localhost:3000/mcp"
        path, action, content = _patch_opencode(url)

        assert action == "create"
        assert path == _expected_opencode_path(tmp_home)
        data = json.loads(content)
        assert data["mcp"][SERVER_NAME] == {
            "type": "remote",
            "url": url,
            "enabled": True,
        }

    def test_modify_existing(self, tmp_home: Path) -> None:
        config_file = _expected_opencode_path(tmp_home)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps({"theme": "dark"}))
        url = "http://localhost:3000/mcp"
        path, action, content = _patch_opencode(url)

        assert action == "modify"
        data = json.loads(content)
        assert data["theme"] == "dark"
        assert data["mcp"][SERVER_NAME]["url"] == url


class TestApplyOpencode:
    def test_writes_file(self, tmp_home: Path) -> None:
        url = "http://localhost:3000/mcp"
        path = _apply_opencode(url)

        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["mcp"][SERVER_NAME]["type"] == "remote"
        assert data["mcp"][SERVER_NAME]["url"] == url
        assert data["mcp"][SERVER_NAME]["enabled"] is True


# ── Hermes patcher ────────────────────────────────────────────────────


class TestPatchHermes:
    def test_create_new(self, tmp_home: Path) -> None:
        url = "http://localhost:3000/mcp"
        path, action, content = _patch_hermes(url)

        assert action == "create"
        assert path == tmp_home / ".hermes" / "config.yaml"
        assert "mcp_servers:" in content
        assert SERVER_NAME in content
        assert url in content

    def test_modify_existing(self, tmp_home: Path) -> None:
        config_file = tmp_home / ".hermes" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("provider: openai\nmodel: gpt-4\n")
        url = "http://localhost:3000/mcp"
        path, action, content = _patch_hermes(url)

        assert action == "modify"
        assert "provider: openai" in content or "provider:" in content
        assert url in content


class TestApplyHermes:
    def test_writes_file(self, tmp_home: Path) -> None:
        url = "http://localhost:3000/mcp"
        path = _apply_hermes(url)

        assert path.is_file()
        content = path.read_text()
        assert SERVER_NAME in content
        assert url in content

    def test_preserves_existing(self, tmp_home: Path) -> None:
        config_file = tmp_home / ".hermes" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            "provider: openai\nmodel: gpt-4\nmcp_servers:\n  existing:\n    url: http://x:9/mcp\n"
        )
        _apply_hermes("http://localhost:3000/mcp")

        content = config_file.read_text()
        assert "provider: openai" in content
        assert "existing:" in content
        assert SERVER_NAME in content


# ── Idempotency ───────────────────────────────────────────────────────


class TestIdempotency:
    @pytest.mark.parametrize("service", [CLAUDE, CODEX, OPENCODE, HERMES])
    def test_run_twice_no_duplicates(self, service: str, tmp_home: Path) -> None:
        from prism.cli.commands.install import APPLIERS, PATCHERS

        url = "http://localhost:3000/mcp"
        # Apply twice
        APPLIERS[service](url)
        APPLIERS[service](url)

        # Patch should still show only one prism entry
        path, action, content = PATCHERS[service](url)
        if service in (CLAUDE, OPENCODE):
            count = content.count(f'"{SERVER_NAME}"')
            assert count == 1, f"Duplicate entries found in {service}"
        elif service == CODEX:
            count = content.count(f"[mcp_servers.{SERVER_NAME}]")
            assert count == 1, f"Duplicate sections found in {service}"
        elif service == HERMES:
            # Hermes YAML has prism: at 2-space indent
            lines = [
                line
                for line in content.splitlines()
                if line.strip() == f"{SERVER_NAME}:"
            ]
            assert len(lines) == 1, f"Duplicate entries found in {service}"


# ── CLI integration ───────────────────────────────────────────────────


class TestCli:
    def test_help(self) -> None:
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "Set up Prism MCP server" in result.output
        assert "claude" in result.output

    def test_invalid_service(self) -> None:
        result = runner.invoke(app, ["setup", "foobar"])
        assert result.exit_code == 1
        assert "Unknown service" in result.output

    def test_setup_claude_yes(self, tmp_home: Path) -> None:
        result = runner.invoke(app, ["setup", "claude", "--yes"])
        assert result.exit_code == 0
        assert "Claude Code" in result.output
        config_file = tmp_home / ".claude.json"
        assert config_file.is_file()
        data = json.loads(config_file.read_text())
        assert SERVER_NAME in data["mcpServers"]

    def test_setup_all_yes(self, tmp_home: Path) -> None:
        result = runner.invoke(app, ["setup", "--yes"])
        assert result.exit_code == 0
        assert "Claude Code" in result.output
        assert "Codex CLI" in result.output
        assert "OpenCode" in result.output
        assert "Hermes Agent" in result.output
        assert (tmp_home / ".claude.json").is_file()
        assert (tmp_home / ".codex" / "config.toml").is_file()
        assert (_expected_opencode_path(tmp_home)).is_file()
        assert (tmp_home / ".hermes" / "config.yaml").is_file()

    def test_setup_with_custom_port(self, tmp_home: Path) -> None:
        result = runner.invoke(app, ["setup", "claude", "--port", "8080", "--yes"])
        assert result.exit_code == 0
        assert "8080" in result.output
        data = json.loads((tmp_home / ".claude.json").read_text())
        assert "8080" in data["mcpServers"][SERVER_NAME]["url"]

    def test_setup_with_custom_url(self, tmp_home: Path) -> None:
        custom_url = "https://prism.example.com/mcp"
        result = runner.invoke(app, ["setup", "claude", "--url", custom_url, "--yes"])
        assert result.exit_code == 0
        assert custom_url in result.output
        data = json.loads((tmp_home / ".claude.json").read_text())
        assert data["mcpServers"][SERVER_NAME]["url"] == custom_url

    def test_setup_aborted_no_file(self, tmp_home: Path) -> None:
        result = runner.invoke(app, ["setup", "claude"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output
        assert not (tmp_home / ".claude.json").exists()

    def test_setup_confirmed_creates_file(self, tmp_home: Path) -> None:
        result = runner.invoke(app, ["setup", "claude"], input="y\n")
        assert result.exit_code == 0
        assert (tmp_home / ".claude.json").is_file()

    def test_setup_preview_shows_content(self, tmp_home: Path) -> None:
        result = runner.invoke(app, ["setup", "claude", "--yes"])
        assert result.exit_code == 0
        assert "Content to write:" in result.output
        assert "mcpServers" in result.output

    def test_setup_preview_shows_action(self, tmp_home: Path) -> None:
        # First run: CREATE
        result = runner.invoke(app, ["setup", "claude", "--yes"])
        assert "[CREATE]" in result.output

        # Second run: MODIFY
        result = runner.invoke(app, ["setup", "claude", "--yes"])
        assert "[MODIFY]" in result.output

    def test_setup_each_service(self, tmp_home: Path) -> None:
        for svc in ("claude", "codex", "opencode", "hermes"):
            result = runner.invoke(app, ["setup", svc, "--yes"])
            assert result.exit_code == 0, f"Failed for {svc}: {result.output}"

    def test_setup_default_is_all(self, tmp_home: Path) -> None:
        result = runner.invoke(app, ["setup", "--yes"])
        assert result.exit_code == 0
        # All 4 files should exist
        assert (tmp_home / ".claude.json").is_file()
        assert (tmp_home / ".codex" / "config.toml").is_file()
        assert (_expected_opencode_path(tmp_home)).is_file()
        assert (tmp_home / ".hermes" / "config.yaml").is_file()

    def test_setup_shows_start_serve_hint(self, tmp_home: Path) -> None:
        result = runner.invoke(app, ["setup", "claude", "--yes"])
        assert "prism serve" in result.output
        assert "3000" in result.output

    def test_setup_idempotent_via_cli(self, tmp_home: Path) -> None:
        """Running setup twice should not duplicate entries."""
        runner.invoke(app, ["setup", "claude", "--yes"])
        runner.invoke(app, ["setup", "claude", "--yes"])

        data = json.loads((tmp_home / ".claude.json").read_text())
        assert len(data["mcpServers"]) == 1
        assert SERVER_NAME in data["mcpServers"]
