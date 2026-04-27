"""Tests for prism.settings — pydantic-settings, config.json persistence."""

from __future__ import annotations

import json
import os
import stat

import pytest

from prism import settings as settings_module
from prism.settings import Settings, clear_config, reset_keys, save_config


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect config_path() to a tmp file and clear IRIS_* env vars."""
    path = tmp_path / "prism" / "config.json"
    monkeypatch.setattr(settings_module, "config_path", lambda: path)
    for var in list(os.environ):
        if var.startswith(("IRIS_", "PRISM_")):
            monkeypatch.delenv(var, raising=False)
    return path


class TestConfigPath:
    def test_lives_under_a_single_prism_dir(self):
        # On Windows platformdirs would otherwise nest prism\prism — appauthor=False
        # collapses that to a single segment.
        path = settings_module.config_path()
        assert path.name == "config.json"
        assert path.parent.name == "prism"
        assert path.parent.parent.name != "prism"


class TestSaveConfig:
    def test_creates_parent_dirs(self, tmp_config):
        save_config({"iris_base_url": "http://x"})
        assert tmp_config.exists()
        assert tmp_config.parent.is_dir()

    def test_round_trip(self, tmp_config):
        data = {
            "iris_base_url": "http://192.168.1.100:52773",
            "iris_username": "_SYSTEM",
            "iris_password": "SYS",
            "iris_namespace": "USER",
            "iris_superserver_port": 1972,
        }
        path = save_config(data)
        assert path == tmp_config
        assert json.loads(tmp_config.read_text()) == data

    def test_merges_with_existing(self, tmp_config):
        save_config({"iris_base_url": "http://a", "iris_username": "u"})
        save_config({"iris_password": "p"})
        loaded = json.loads(tmp_config.read_text())
        assert loaded == {
            "iris_base_url": "http://a",
            "iris_username": "u",
            "iris_password": "p",
        }

    def test_writes_pretty_sorted_json(self, tmp_config):
        save_config({"iris_username": "u", "iris_base_url": "http://x"})
        text = tmp_config.read_text()
        # sort_keys=True + indent=2 → iris_base_url comes before iris_username
        assert text.index('"iris_base_url"') < text.index('"iris_username"')
        assert "\n  " in text

    @pytest.mark.skipif(os.name != "posix", reason="POSIX file mode only")
    def test_chmods_to_600_on_posix(self, tmp_config):
        save_config({"iris_password": "secret"})
        mode = stat.S_IMODE(tmp_config.stat().st_mode)
        assert mode == 0o600

    def test_overwrites_existing_keys(self, tmp_config):
        save_config({"iris_base_url": "http://old"})
        save_config({"iris_base_url": "http://new"})
        loaded = json.loads(tmp_config.read_text())
        assert loaded == {"iris_base_url": "http://new"}


class TestSettingsLoading:
    def test_defaults_when_no_env_no_file(self, tmp_config):
        s = Settings()
        assert s.iris_base_url == "http://localhost:52773"
        assert s.iris_username == "_SYSTEM"
        assert s.iris_namespace == "USER"
        assert s.iris_api_prefix == "api/atelier/v8"

    def test_env_var_overrides_default(self, tmp_config, monkeypatch):
        monkeypatch.setenv("IRIS_BASE_URL", "http://from-env:52773")
        s = Settings()
        assert s.iris_base_url == "http://from-env:52773"

    def test_config_json_overrides_default(self, tmp_config):
        save_config({"iris_base_url": "http://from-file:52773"})
        s = Settings()
        assert s.iris_base_url == "http://from-file:52773"

    def test_env_wins_over_config_json(self, tmp_config, monkeypatch):
        save_config({"iris_base_url": "http://from-file"})
        monkeypatch.setenv("IRIS_BASE_URL", "http://from-env")
        s = Settings()
        assert s.iris_base_url == "http://from-env"

    def test_invalid_json_falls_back_to_defaults(self, tmp_config):
        tmp_config.parent.mkdir(parents=True, exist_ok=True)
        tmp_config.write_text("not valid {")
        s = Settings()
        assert s.iris_base_url == "http://localhost:52773"

    def test_unknown_keys_in_config_json_are_ignored(self, tmp_config):
        save_config({"iris_base_url": "http://x", "totally_unknown": "value"})
        s = Settings()
        assert s.iris_base_url == "http://x"

    def test_int_field_coerced_from_string_env(self, tmp_config, monkeypatch):
        monkeypatch.setenv("IRIS_SUPERSERVER_PORT", "9999")
        s = Settings()
        assert s.iris_superserver_port == 9999

    def test_bool_field_coerced_from_string_env(self, tmp_config, monkeypatch):
        monkeypatch.setenv("IRIS_DEBUG_ENABLED", "true")
        s = Settings()
        assert s.iris_debug_enabled is True

        monkeypatch.setenv("IRIS_DEBUG_ENABLED", "false")
        s2 = Settings()
        assert s2.iris_debug_enabled is False


class TestResetKeys:
    def test_removes_specified_keys(self, tmp_config):
        save_config(
            {
                "iris_base_url": "http://x",
                "iris_username": "u",
                "iris_password": "p",
            }
        )
        reset_keys(["iris_username", "iris_password"])
        loaded = json.loads(tmp_config.read_text())
        assert loaded == {"iris_base_url": "http://x"}

    def test_unknown_keys_are_ignored(self, tmp_config):
        save_config({"iris_base_url": "http://x"})
        reset_keys(["totally_unknown", "another"])
        loaded = json.loads(tmp_config.read_text())
        assert loaded == {"iris_base_url": "http://x"}

    def test_noop_when_file_missing(self, tmp_config):
        # Should not raise; should not create the file.
        reset_keys(["iris_base_url"])
        assert not tmp_config.exists()

    def test_does_not_rewrite_when_no_keys_match(self, tmp_config):
        save_config({"iris_base_url": "http://x"})
        original_mtime = tmp_config.stat().st_mtime_ns
        reset_keys(["iris_username"])  # not present
        assert tmp_config.stat().st_mtime_ns == original_mtime

    @pytest.mark.skipif(os.name != "posix", reason="POSIX file mode only")
    def test_preserves_chmod_600_after_reset(self, tmp_config):
        save_config({"iris_base_url": "http://x", "iris_password": "secret"})
        reset_keys(["iris_password"])
        mode = stat.S_IMODE(tmp_config.stat().st_mode)
        assert mode == 0o600


class TestClearConfig:
    def test_deletes_existing_file(self, tmp_config):
        save_config({"iris_base_url": "http://x"})
        assert tmp_config.exists()
        clear_config()
        assert not tmp_config.exists()

    def test_noop_when_file_missing(self, tmp_config):
        clear_config()
        assert not tmp_config.exists()

    def test_returns_path_either_way(self, tmp_config):
        assert clear_config() == tmp_config
        save_config({"iris_base_url": "http://x"})
        assert clear_config() == tmp_config
