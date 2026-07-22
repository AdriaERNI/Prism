"""Tests for `prism chatbot` CLI command."""

from __future__ import annotations

import json
import os
import re
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from prism import settings as settings_module
from prism.cli.app import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect config_path() to a tmp file and clear env vars."""
    path = tmp_path / "prism" / "config.json"
    monkeypatch.setattr(settings_module, "config_path", lambda: path)
    for var in list(os.environ):
        if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
            monkeypatch.delenv(var, raising=False)
    return path


class TestChatbotHelp:
    """Tests for the --help output."""

    def test_help_command(self, runner):
        result = runner.invoke(app, ["chatbot", "--help"])
        assert result.exit_code == 0
        # Strip ANSI color codes (Windows CI renders them differently).
        clean = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        assert "chatbot" in clean.lower()
        assert "--api-url" in clean
        assert "--api-key" in clean
        assert "--model" in clean
        assert "--skills-path" in clean

    def test_command_registered_in_app(self, runner):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "chatbot" in result.stdout


class TestConfigIntegration:
    """Tests that chatbot settings appear in `prism config`."""

    def test_config_shows_chatbot_fields(self, runner, tmp_config):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "chatbot_api_url" in result.stdout
        assert "chatbot_api_key" in result.stdout
        assert "chatbot_skills_path" in result.stdout
        assert "chatbot_model" in result.stdout

    def test_config_shows_chatbot_defaults(self, runner, tmp_config):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        # Default model should be visible
        assert "gpt-4o" in result.stdout

    def test_chatbot_api_key_redacted(self, runner, tmp_config):
        from prism.settings import save_config

        save_config({"chatbot_api_key": "super-secret-key"})
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "super-secret-key" not in result.stdout
        assert "***" in result.stdout

    def test_save_chatbot_api_url(self, runner, tmp_config):
        result = runner.invoke(
            app,
            [
                "config",
                "--chatbot-api-url",
                "https://api.openai.com/v1",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(tmp_config.read_text())
        assert data["chatbot_api_url"] == "https://api.openai.com/v1"

    def test_save_chatbot_api_key(self, runner, tmp_config):
        result = runner.invoke(
            app,
            ["config", "--chatbot-api-key", "sk-mykey"],
        )
        assert result.exit_code == 0
        data = json.loads(tmp_config.read_text())
        assert data["chatbot_api_key"] == "sk-mykey"

    def test_save_chatbot_model(self, runner, tmp_config):
        result = runner.invoke(
            app,
            ["config", "--chatbot-model", "gpt-4o-mini"],
        )
        assert result.exit_code == 0
        data = json.loads(tmp_config.read_text())
        assert data["chatbot_model"] == "gpt-4o-mini"

    def test_save_chatbot_skills_path(self, runner, tmp_config):
        result = runner.invoke(
            app,
            ["config", "--chatbot-skills-path", "/tmp/skills"],
        )
        assert result.exit_code == 0
        data = json.loads(tmp_config.read_text())
        assert data["chatbot_skills_path"] == "/tmp/skills"

    def test_save_all_chatbot_fields_at_once(self, runner, tmp_config):
        result = runner.invoke(
            app,
            [
                "config",
                "--chatbot-api-url",
                "https://api.test/v1",
                "--chatbot-api-key",
                "sk-key",
                "--chatbot-model",
                "claude-3",
                "--chatbot-skills-path",
                "/skills",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(tmp_config.read_text())
        assert data == {
            "chatbot_api_url": "https://api.test/v1",
            "chatbot_api_key": "sk-key",
            "chatbot_model": "claude-3",
            "chatbot_skills_path": "/skills",
        }

    def test_api_key_not_in_stdout_when_saved(self, runner, tmp_config):
        result = runner.invoke(
            app,
            ["config", "--chatbot-api-key", "sk-secret"],
        )
        assert result.exit_code == 0
        assert "sk-secret" not in result.stdout
        assert "chatbot_api_key" in result.stdout


class TestSettingsFields:
    """Tests that the Settings model has the 4 chatbot fields."""

    def test_settings_has_chatbot_api_url(self):
        from prism.settings import Settings

        assert "chatbot_api_url" in Settings.model_fields

    def test_settings_has_chatbot_api_key(self):
        from prism.settings import Settings

        assert "chatbot_api_key" in Settings.model_fields

    def test_settings_has_chatbot_model(self):
        from prism.settings import Settings

        assert "chatbot_model" in Settings.model_fields

    def test_settings_has_chatbot_skills_path(self):
        from prism.settings import Settings

        assert "chatbot_skills_path" in Settings.model_fields

    def test_settings_count_is_25(self):
        """Original 21 + 4 chatbot fields = 25 total."""
        from prism.settings import Settings

        assert len(Settings.model_fields) == 25

    def test_chatbot_defaults(self):
        from prism.settings import Settings

        fields = Settings.model_fields
        assert fields["chatbot_api_url"].default == ""
        assert fields["chatbot_api_key"].default == ""
        assert fields["chatbot_skills_path"].default == ""
        assert fields["chatbot_model"].default == "gpt-4o"


class TestListSkills:
    """Tests for the --list-skills flag."""

    def test_no_skills_path_prints_message(self, runner, tmp_config):
        result = runner.invoke(app, ["chatbot", "--list-skills"])
        assert result.exit_code == 0
        assert "No skills" in result.stdout

    def test_empty_skills_dir(self, runner, tmp_config, tmp_path):
        from prism.settings import save_config

        save_config({"chatbot_skills_path": str(tmp_path)})
        result = runner.invoke(app, ["chatbot", "--list-skills"])
        assert result.exit_code == 0
        assert "No skills" in result.stdout

    def test_lists_skills_from_dir(self, runner, tmp_config, tmp_path, monkeypatch):
        from prism.settings import save_config

        (tmp_path / "sql.md").write_text("# SQL\nUse execute_sql.")
        (tmp_path / "docs.md").write_text("# Docs\nUse get_document.")

        save_config({"chatbot_skills_path": str(tmp_path)})
        # Patch the settings singleton to pick up the saved value
        monkeypatch.setattr(
            "prism.settings.settings.chatbot_skills_path", str(tmp_path)
        )
        result = runner.invoke(app, ["chatbot", "--list-skills"])
        assert result.exit_code == 0
        assert "sql" in result.stdout
        assert "docs" in result.stdout
        assert "2 skill" in result.stdout

    def test_list_skills_with_nonexistent_path(self, runner, tmp_config):
        from prism.settings import save_config

        save_config({"chatbot_skills_path": "/nonexistent/path"})
        result = runner.invoke(app, ["chatbot", "--list-skills"])
        assert result.exit_code == 0
        assert "No skills" in result.stdout


class TestMissingConfig:
    """Tests for error handling when config is missing."""

    def test_no_api_url_shows_error(self, runner, tmp_config):
        result = runner.invoke(app, ["chatbot", "Hello"])
        assert result.exit_code == 1
        assert "API URL" in result.output

    def test_no_api_key_shows_error(self, runner, tmp_config, monkeypatch):
        # URL is set but key is not
        monkeypatch.setattr(
            "prism.settings.settings.chatbot_api_url", "https://api.test/v1"
        )
        result = runner.invoke(app, ["chatbot", "Hello"])
        assert result.exit_code == 1
        assert "API key" in result.output

    def test_env_var_provides_url(self, runner, tmp_config, monkeypatch):
        """CHATBOT_API_URL env var should be picked up."""
        # Simulate env vars providing config (settings singleton is patched)
        monkeypatch.setattr(
            "prism.settings.settings.chatbot_api_url",
            "https://api.envvar.com/v1",
        )
        monkeypatch.setattr("prism.settings.settings.chatbot_api_key", "sk-env")

        # Mock the agent run to avoid real API calls
        async def mock_run_once(*args, **kwargs):
            return "Mocked response"

        monkeypatch.setattr("prism.cli.commands.chatbot._run_agent_once", mock_run_once)

        result = runner.invoke(app, ["chatbot", "Hello"])
        # Should succeed with the mocked response
        assert result.exit_code == 0
        assert "Mocked response" in result.output
        assert "No chatbot API URL" not in result.output

    def test_cli_flag_overrides_config(self, runner, tmp_config):
        from prism.settings import save_config

        save_config({"chatbot_api_url": "https://from-config/v1"})

        # Mock the agent run to avoid real API calls
        async def mock_run_once(*args, **kwargs):
            return "Mocked response"

        with patch("prism.cli.commands.chatbot._run_agent_once", mock_run_once):
            result = runner.invoke(
                app,
                [
                    "chatbot",
                    "Hello",
                    "--api-url",
                    "https://from-flag/v1",
                    "--api-key",
                    "sk-test",
                    "--no-save",
                ],
            )
            # Should not show the URL error
            assert "API URL" not in result.output


class TestSaveBehavior:
    """Tests for the --save/--no-save flag behaviour."""

    def test_default_saves_flags_to_config(self, runner, tmp_config):
        # Mock the agent run to avoid real API calls
        async def mock_run_once(*args, **kwargs):
            return "Mocked"

        with patch("prism.cli.commands.chatbot._run_agent_once", mock_run_once):
            runner.invoke(
                app,
                [
                    "chatbot",
                    "Hello",
                    "--api-url",
                    "https://api.save-test/v1",
                    "--api-key",
                    "sk-savetest",
                ],
            )
            # Even though the agent is mocked, the config was saved
        data = json.loads(tmp_config.read_text())
        assert data.get("chatbot_api_url") == "https://api.save-test/v1"
        assert data.get("chatbot_api_key") == "sk-savetest"

    def test_no_save_does_not_persist(self, runner, tmp_config):
        # Mock the agent run to avoid real API calls
        async def mock_run_once(*args, **kwargs):
            return "Mocked"

        with patch("prism.cli.commands.chatbot._run_agent_once", mock_run_once):
            runner.invoke(
                app,
                [
                    "chatbot",
                    "Hello",
                    "--api-url",
                    "https://api.nosave/v1",
                    "--api-key",
                    "sk-nosave",
                    "--no-save",
                ],
            )
            # Config should not have been written
            if tmp_config.exists():
                data = json.loads(tmp_config.read_text())
                assert "chatbot_api_url" not in data
