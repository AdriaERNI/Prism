"""Unit tests for settings field count and config edge cases."""

import pytest

from prism.settings import Settings


class TestSettingsFields:
    """Regression guard for the Settings class."""

    def test_settings_has_28_fields(self):
        """Settings must have exactly 28 configurable fields.

        If this test fails, a field was added or removed — update
        docs/getting-started/configuration.md accordingly.
        """
        fields = set(Settings.model_fields.keys())
        assert len(fields) == 28, (
            f"Expected 28 settings fields, got {len(fields)}: {sorted(fields)}"
        )

    @pytest.mark.parametrize(
        "field_name",
        [
            "iris_base_url",
            "iris_username",
            "iris_password",
            "iris_namespace",
            "iris_workspace",
            "iris_api_prefix",
            "iris_compile_flags",
            "iris_superserver_port",
            "iris_terminal_method",
            "iris_terminal_max_output_chars",
            "iris_test_runner_class",
            "iris_test_runner_method",
            "iris_test_manager_class",
            "iris_test_auto_deploy",
            "prism_output_format",
            "iris_debug_enabled",
            "iris_debug_step_granularity",
            "iris_debug_max_data",
            "iris_debug_max_children",
            "iris_debug_max_depth",
            "iris_debug_idle_timeout",
            "chatbot_api_url",
            "chatbot_api_key",
            "chatbot_model",
            "chatbot_skills_path",
            "gui_query_autosave",
            "gui_autosave_delay_ms",
            "gui_saved_queries",
        ],
    )
    def test_field_exists(self, field_name):
        assert field_name in Settings.model_fields


class TestTerminalMethodConfig:
    """Test terminal method config values."""

    def test_terminal_method_default_is_native(self):
        s = Settings()
        assert s.iris_terminal_method == "native"

    def test_terminal_method_ws_from_env(self, monkeypatch):
        monkeypatch.setenv("IRIS_TERMINAL_METHOD", "ws")
        s = Settings()
        assert s.iris_terminal_method == "ws"

    def test_terminal_max_output_chars_default(self):
        s = Settings()
        assert s.iris_terminal_max_output_chars == 100_000

    def test_terminal_max_output_chars_from_env(self, monkeypatch):
        monkeypatch.setenv("IRIS_TERMINAL_MAX_OUTPUT_CHARS", "50000")
        s = Settings()
        assert s.iris_terminal_max_output_chars == 50000


class TestOutputFormatConfig:
    """Test output format config."""

    def test_output_format_default_is_json(self):
        s = Settings()
        assert s.prism_output_format == "json"

    def test_output_format_toon_from_env(self, monkeypatch):
        monkeypatch.setenv("PRISM_OUTPUT_FORMAT", "toon")
        s = Settings()
        assert s.prism_output_format == "toon"
