"""Tests for prism.iris.settings — user settings persistence and env injection."""

from __future__ import annotations

import json
import os
import stat

import pytest

from prism.iris import settings


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    """Redirect settings_path() to a tmp file and clear related env vars."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "settings_path", lambda: path)
    for env_name in settings.SETTING_TO_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    return path


class TestSettingsPath:
    def test_points_into_prism_config_dir(self):
        path = settings.settings_path()
        assert path.name == "settings.json"
        assert path.parent.name == "prism"


class TestLoadSave:
    def test_load_returns_empty_when_file_missing(self, tmp_settings):
        assert settings.load_settings() == {}

    def test_save_then_load_roundtrip(self, tmp_settings):
        data = {
            "url": "http://192.168.1.100:52773",
            "username": "_SYSTEM",
            "password": "SYS",
            "namespace": "USER",
            "superserver_port": 1972,
        }
        path = settings.save_settings(data)
        assert path == tmp_settings
        assert settings.load_settings() == data

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        path = tmp_path / "nested" / "deeper" / "settings.json"
        monkeypatch.setattr(settings, "settings_path", lambda: path)
        settings.save_settings({"url": "http://x"})
        assert path.exists()

    def test_load_returns_empty_on_invalid_json(self, tmp_settings):
        tmp_settings.write_text("not valid {")
        assert settings.load_settings() == {}

    def test_load_returns_empty_when_top_level_not_dict(self, tmp_settings):
        tmp_settings.write_text(json.dumps([1, 2, 3]))
        assert settings.load_settings() == {}

    def test_save_writes_pretty_json(self, tmp_settings):
        settings.save_settings({"b": 2, "a": 1})
        text = tmp_settings.read_text()
        # sort_keys + indent=2 => "a" appears before "b"
        assert text.index('"a"') < text.index('"b"')
        assert "\n  " in text

    @pytest.mark.skipif(os.name != "posix", reason="POSIX file mode only")
    def test_save_chmods_to_600_on_posix(self, tmp_settings):
        settings.save_settings({"url": "http://x"})
        mode = stat.S_IMODE(tmp_settings.stat().st_mode)
        assert mode == 0o600


class TestInjectSettings:
    def test_noop_when_file_missing(self, tmp_settings):
        settings.inject_settings()
        assert "IRIS_BASE_URL" not in os.environ

    def test_injects_all_mapped_values(self, tmp_settings):
        settings.save_settings(
            {
                "url": "http://a:1",
                "username": "u",
                "password": "p",
                "namespace": "N",
                "superserver_port": 9999,
            }
        )
        settings.inject_settings()
        assert os.environ["IRIS_BASE_URL"] == "http://a:1"
        assert os.environ["IRIS_USERNAME"] == "u"
        assert os.environ["IRIS_PASSWORD"] == "p"
        assert os.environ["IRIS_NAMESPACE"] == "N"
        assert os.environ["IRIS_SUPERSERVER_PORT"] == "9999"

    def test_does_not_overwrite_existing_env_var(self, tmp_settings, monkeypatch):
        monkeypatch.setenv("IRIS_BASE_URL", "http://from-env:52773")
        settings.save_settings({"url": "http://from-file:52773"})
        settings.inject_settings()
        assert os.environ["IRIS_BASE_URL"] == "http://from-env:52773"

    def test_ignores_unmapped_keys(self, tmp_settings):
        settings.save_settings({"url": "http://x", "unknown_key": "value"})
        settings.inject_settings()
        assert "UNKNOWN_KEY" not in os.environ

    def test_skips_null_values(self, tmp_settings):
        settings.save_settings({"url": "http://x", "username": None})
        settings.inject_settings()
        assert os.environ["IRIS_BASE_URL"] == "http://x"
        assert "IRIS_USERNAME" not in os.environ
