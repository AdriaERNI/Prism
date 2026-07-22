"""Tests for `prism config` — flag-based show/edit/reset and interactive mode."""

from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from prism import settings as settings_module
from prism.cli.app import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect config_path() to a tmp file and clear IRIS_*/PRISM_* env vars."""
    path = tmp_path / "prism" / "config.json"
    monkeypatch.setattr(settings_module, "config_path", lambda: path)
    for var in list(os.environ):
        if var.startswith(("IRIS_", "PRISM_")):
            monkeypatch.delenv(var, raising=False)
    return path


class TestShow:
    def test_no_args_prints_all_28_settings(self, runner, tmp_config):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        # All 28 field names should appear in the output.
        from prism.settings import Settings

        for name in Settings.model_fields:
            assert name in result.stdout

    def test_password_redacted(self, runner, tmp_config):
        result = runner.invoke(app, ["config"])
        assert "***" in result.stdout
        password_line = next(
            line for line in result.stdout.splitlines() if "iris_password" in line
        )
        assert "SYS" not in password_line
        assert "***" in password_line

    def test_workspace_unset_label(self, runner, tmp_config):
        result = runner.invoke(app, ["config"])
        assert "(unset)" in result.stdout

    def test_shows_default_marker_when_value_overridden(self, runner, tmp_config):
        from prism.settings import save_config

        save_config({"iris_base_url": "http://changed:1234"})
        result = runner.invoke(app, ["config"])
        assert "http://changed:1234" in result.stdout
        assert "(default: http://localhost:52773)" in result.stdout


class TestUpdateFlags:
    def test_short_flags_save_correctly(self, runner, tmp_config):
        result = runner.invoke(
            app, ["config", "-u", "admin", "-p", "secret", "-U", "http://x:52773"]
        )
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {
            "iris_username": "admin",
            "iris_password": "secret",
            "iris_base_url": "http://x:52773",
        }

    def test_long_flags_save_correctly(self, runner, tmp_config):
        result = runner.invoke(app, ["config", "--user", "u2", "--namespace", "MYAPP"])
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {
            "iris_username": "u2",
            "iris_namespace": "MYAPP",
        }

    def test_int_flag_super_port(self, runner, tmp_config):
        result = runner.invoke(app, ["config", "-P", "1973"])
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {"iris_superserver_port": 1973}

    def test_bool_debug_enable(self, runner, tmp_config):
        result = runner.invoke(app, ["config", "--debug"])
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {"iris_debug_enabled": True}

    def test_bool_debug_disable(self, runner, tmp_config):
        result = runner.invoke(app, ["config", "--no-debug"])
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {"iris_debug_enabled": False}

    def test_password_redacted_in_save_output(self, runner, tmp_config):
        result = runner.invoke(app, ["config", "-p", "topsecret"])
        assert result.exit_code == 0
        assert "topsecret" not in result.stdout
        assert "***" in result.stdout

    def test_combined_flags_in_one_call(self, runner, tmp_config):
        result = runner.invoke(
            app,
            [
                "config",
                "-u",
                "admin",
                "-w",
                "/tmp/ws",
                "--debug-max-depth",
                "5",
                "--test-auto-deploy",
            ],
        )
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {
            "iris_username": "admin",
            "iris_workspace": "/tmp/ws",
            "iris_debug_max_depth": 5,
            "iris_test_auto_deploy": True,
        }


class TestReset:
    def test_reset_single_key(self, runner, tmp_config):
        from prism.settings import save_config

        save_config({"iris_username": "admin", "iris_password": "secret"})
        result = runner.invoke(app, ["config", "-r", "iris_username"])
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {"iris_password": "secret"}

    def test_reset_multiple_keys(self, runner, tmp_config):
        from prism.settings import save_config

        save_config(
            {"iris_username": "u", "iris_password": "p", "iris_base_url": "http://x"}
        )
        result = runner.invoke(
            app, ["config", "-r", "iris_username", "-r", "iris_password"]
        )
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {"iris_base_url": "http://x"}

    def test_reset_unknown_key_errors(self, runner, tmp_config):
        result = runner.invoke(app, ["config", "-r", "totally_unknown"])
        assert result.exit_code == 1
        assert "Unknown" in result.stdout or "Unknown" in (result.stderr or "")

    def test_reset_all_deletes_file(self, runner, tmp_config):
        from prism.settings import save_config

        save_config({"iris_username": "admin"})
        assert tmp_config.exists()
        result = runner.invoke(app, ["config", "--reset-all"])
        assert result.exit_code == 0
        assert not tmp_config.exists()


class TestInteractive:
    def test_keep_all_makes_no_changes(self, runner, tmp_config):
        from prism.settings import Settings

        # 28 keeps, one per field.
        n_fields = len(Settings.model_fields)
        result = runner.invoke(app, ["config", "-i"], input="k\n" * n_fields)
        assert result.exit_code == 0
        assert "No changes" in result.stdout
        assert not tmp_config.exists()

    def test_change_a_value(self, runner, tmp_config):
        from prism.settings import Settings

        n_fields = len(Settings.model_fields)
        # Change the first field (iris_base_url), keep the rest.
        prompts = "c\nhttp://changed:9000\n" + "k\n" * (n_fields - 1)
        result = runner.invoke(app, ["config", "-i"], input=prompts)
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {
            "iris_base_url": "http://changed:9000"
        }

    def test_reset_a_value(self, runner, tmp_config):
        from prism.settings import Settings, save_config

        save_config({"iris_base_url": "http://stale"})
        n_fields = len(Settings.model_fields)
        # Default the first field, keep the rest.
        prompts = "d\n" + "k\n" * (n_fields - 1)
        result = runner.invoke(app, ["config", "-i"], input=prompts)
        assert result.exit_code == 0
        assert json.loads(tmp_config.read_text()) == {}

    def test_invalid_int_input_keeps_current(self, runner, tmp_config):
        from prism.settings import Settings

        fields = list(Settings.model_fields)
        port_idx = fields.index("iris_superserver_port")
        prompts = (
            "k\n" * port_idx
            + "c\nnot-a-number\n"
            + "k\n" * (len(fields) - port_idx - 1)
        )
        result = runner.invoke(app, ["config", "-i"], input=prompts)
        assert result.exit_code == 0
        assert "Invalid value" in result.stdout
        assert not tmp_config.exists()
