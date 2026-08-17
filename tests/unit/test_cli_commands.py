"""Unit tests for CLI commands — gui, serve, chatbot edge cases.

Tests cover argument parsing, error handling, and edge cases for the
CLI commands with the lowest coverage.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from prism.cli.app import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text (CI renders help with colors)."""
    return _ANSI_RE.sub("", text)


# ── GUI command ──────────────────────────────────────────────────────────


class TestGuiCommand:
    """Tests for `prism gui` command."""

    def test_gui_help(self):
        """--help should show usage."""
        result = runner.invoke(app, ["gui", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "GUI" in output or "gui" in output.lower()

    def test_gui_tkinter_not_available(self):
        """If tkinter is not importable, should error with exit code 1."""
        with patch.dict("sys.modules", {"tkinter": None}):
            result = runner.invoke(app, ["gui"])
            assert result.exit_code == 1
            assert "tkinter" in result.output.lower()

    def test_gui_launch_called(self):
        """When tkinter is available and GUI module imports, launch() is called."""
        # Mock tkinter as available
        mock_tk = MagicMock()
        with (
            patch.dict("sys.modules", {"tkinter": mock_tk}),
            patch("prism.gui.app.launch") as mock_launch,
        ):
            result = runner.invoke(app, ["gui"])
            assert result.exit_code == 0
            mock_launch.assert_called_once()

    def test_gui_with_query_option(self):
        """--query should pass the query to launch()."""
        mock_tk = MagicMock()
        with (
            patch.dict("sys.modules", {"tkinter": mock_tk}),
            patch("prism.gui.app.launch") as mock_launch,
        ):
            result = runner.invoke(app, ["gui", "--query", "SELECT 1"])
            assert result.exit_code == 0
            mock_launch.assert_called_once_with(initial_query="SELECT 1")

    def test_gui_with_short_query_flag(self):
        """-q should work as an alias for --query."""
        mock_tk = MagicMock()
        with (
            patch.dict("sys.modules", {"tkinter": mock_tk}),
            patch("prism.gui.app.launch") as mock_launch,
        ):
            result = runner.invoke(app, ["gui", "-q", "SELECT 2"])
            assert result.exit_code == 0
            mock_launch.assert_called_once_with(initial_query="SELECT 2")

    def test_gui_import_error_handled(self):
        """If GUI module import fails, should error gracefully."""
        mock_tk = MagicMock()
        # Simulate the import of prism.gui.app failing
        with (
            patch.dict("sys.modules", {"tkinter": mock_tk, "prism.gui.app": None}),
            patch.dict("sys.modules", {"prism.gui": None}),
        ):
            result = runner.invoke(app, ["gui"])
            assert result.exit_code == 1


# ── Serve command ──────────────────────────────────────────────────────────


class TestServeCommand:
    """Tests for `prism serve` command."""

    def test_serve_help(self):
        """--help should show usage."""
        result = runner.invoke(app, ["serve", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "MCP server" in output
        assert "--port" in output
        assert "--skip-preflight" in output

    def test_serve_with_skip_preflight(self):
        """--skip-preflight should bypass preflight check."""
        with (
            patch("prism.mcp.server.mcp") as mock_mcp,
            patch("prism.iris.sdk.preflight.preflight_check") as mock_preflight,
        ):
            result = runner.invoke(app, ["serve", "--skip-preflight", "--port", "9999"])
            assert result.exit_code == 0
            mock_preflight.assert_not_called()
            mock_mcp.run.assert_called_once()

    def test_serve_calls_preflight_by_default(self):
        """Without --skip-preflight, preflight_check is called."""
        with (
            patch("prism.mcp.server.mcp") as mock_mcp,
            patch("prism.iris.sdk.preflight.preflight_check") as mock_preflight,
        ):
            result = runner.invoke(app, ["serve", "--port", "9999"])
            assert result.exit_code == 0
            mock_preflight.assert_called_once()
            mock_mcp.run.assert_called_once()

    def test_serve_passes_port_to_mcp(self):
        """Port option is passed to mcp.run()."""
        with (
            patch("prism.mcp.server.mcp") as mock_mcp,
            patch("prism.iris.sdk.preflight.preflight_check"),
        ):
            result = runner.invoke(app, ["serve", "--port", "8080"])
            assert result.exit_code == 0
            mock_mcp.run.assert_called_once()
            assert mock_mcp.run.call_args[1]["port"] == 8080

    def test_serve_default_port(self):
        """Default port is 3000."""
        with (
            patch("prism.mcp.server.mcp") as mock_mcp,
            patch("prism.iris.sdk.preflight.preflight_check"),
        ):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 0
            assert mock_mcp.run.call_args[1]["port"] == 3000

    def test_serve_default_transport_is_http(self):
        """Default transport is streamable-http."""
        with (
            patch("prism.mcp.server.mcp") as mock_mcp,
            patch("prism.iris.sdk.preflight.preflight_check"),
        ):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 0
            assert mock_mcp.run.call_args[1]["transport"] == "streamable-http"

    def test_serve_transport_stdio(self):
        """--transport stdio uses stdio transport and skips preflight."""
        with (
            patch("prism.mcp.server.mcp") as mock_mcp,
            patch("prism.iris.sdk.preflight.preflight_check") as mock_preflight,
        ):
            result = runner.invoke(app, ["serve", "--transport", "stdio"])
            assert result.exit_code == 0
            assert mock_mcp.run.call_args[1]["transport"] == "stdio"
            # stdio should NOT call preflight even without --skip-preflight
            mock_preflight.assert_not_called()

    def test_serve_transport_http_alias(self):
        """--transport http maps to streamable-http."""
        with (
            patch("prism.mcp.server.mcp") as mock_mcp,
            patch("prism.iris.sdk.preflight.preflight_check"),
        ):
            result = runner.invoke(app, ["serve", "--transport", "http"])
            assert result.exit_code == 0
            assert mock_mcp.run.call_args[1]["transport"] == "streamable-http"

    def test_serve_transport_sse(self):
        """--transport sse uses sse transport."""
        with (
            patch("prism.mcp.server.mcp") as mock_mcp,
            patch("prism.iris.sdk.preflight.preflight_check"),
        ):
            result = runner.invoke(app, ["serve", "--transport", "sse"])
            assert result.exit_code == 0
            assert mock_mcp.run.call_args[1]["transport"] == "sse"

    def test_serve_transport_invalid_rejects(self):
        """Invalid transport value is rejected."""
        with (
            patch("prism.mcp.server.mcp"),
            patch("prism.iris.sdk.preflight.preflight_check"),
        ):
            result = runner.invoke(app, ["serve", "--transport", "websocket"])
            assert result.exit_code != 0

    def test_serve_help_advertises_transport(self):
        """--help should show --transport option."""
        result = runner.invoke(app, ["serve", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "--transport" in output
        assert "stdio" in output


# ── Chatbot command ──────────────────────────────────────────────────────────


class TestChatbotCommand:
    """Tests for `prism chatbot` command edge cases."""

    def test_chatbot_no_api_url_errors(self, tmp_path, monkeypatch):
        """Without API URL configured, should error."""
        # Reset settings
        from prism import settings as settings_module

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        result = runner.invoke(app, ["chatbot", "hello"])
        assert result.exit_code == 1
        assert "api url" in result.output.lower()

    def test_chatbot_no_api_key_errors(self, tmp_path, monkeypatch):
        """With API URL but no API key, should error."""
        from prism import settings as settings_module

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        fresh.chatbot_api_url = "https://api.test/v1"
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        result = runner.invoke(app, ["chatbot", "hello"])
        assert result.exit_code == 1
        assert "api key" in result.output.lower()

    def test_chatbot_list_skills_no_skills(self, tmp_path, monkeypatch):
        """--list-skills with no skills path → exits."""
        from prism import settings as settings_module

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        result = runner.invoke(app, ["chatbot", "--list-skills"])
        assert result.exit_code == 0
        assert "no skills" in result.output.lower()

    def test_chatbot_list_skills_with_path(self, tmp_path, monkeypatch):
        """--list-skills with a skills path containing files → lists them."""
        from prism import settings as settings_module

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test-skill.md").write_text("# Test Skill\ncontent")

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        result = runner.invoke(app, ["chatbot", "--list-skills", "--skills-path", str(skills_dir)])
        assert result.exit_code == 0
        assert "test-skill" in result.output.lower()

    def test_chatbot_one_shot_value_error(self, tmp_path, monkeypatch):
        """One-shot mode with ValueError → exit 1."""
        from prism import settings as settings_module

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        fresh.chatbot_api_url = "https://api.test/v1"
        fresh.chatbot_api_key = "test-key"
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        with patch(
            "prism.cli.commands.chatbot._run_agent_once",
            new_callable=AsyncMock,
            side_effect=ValueError("Bad config"),
        ):
            result = runner.invoke(app, ["chatbot", "hello"])
            assert result.exit_code == 1
            assert "error" in result.output.lower()

    def test_chatbot_one_shot_generic_exception(self, tmp_path, monkeypatch):
        """One-shot mode with generic exception → exit 1."""
        from prism import settings as settings_module

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        fresh.chatbot_api_url = "https://api.test/v1"
        fresh.chatbot_api_key = "test-key"
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        with patch(
            "prism.cli.commands.chatbot._run_agent_once",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection failed"),
        ):
            result = runner.invoke(app, ["chatbot", "hello"])
            assert result.exit_code == 1

    def test_chatbot_one_shot_success(self, tmp_path, monkeypatch):
        """One-shot mode success → prints response."""
        from prism import settings as settings_module

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        fresh.chatbot_api_url = "https://api.test/v1"
        fresh.chatbot_api_key = "test-key"
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        with patch(
            "prism.cli.commands.chatbot._run_agent_once",
            new_callable=AsyncMock,
            return_value="Hello from the agent!",
        ):
            result = runner.invoke(app, ["chatbot", "hello"])
            assert result.exit_code == 0
            assert "Hello from the agent" in result.output

    def test_chatbot_no_save_flag(self, tmp_path, monkeypatch):
        """--no-save should not persist config."""
        from prism import settings as settings_module

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        fresh.chatbot_api_url = "https://api.test/v1"
        fresh.chatbot_api_key = "test-key"
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        with (
            patch("prism.cli.commands.chatbot.save_config") as mock_save,
            patch(
                "prism.cli.commands.chatbot._run_agent_once",
                new_callable=AsyncMock,
                return_value="ok",
            ),
        ):
            result = runner.invoke(
                app, ["chatbot", "hello", "--no-save", "--api-url", "https://new/v1"]
            )
            assert result.exit_code == 0
            mock_save.assert_not_called()

    def test_chatbot_save_flag_persists(self, tmp_path, monkeypatch):
        """Default --save should persist config flags."""
        from prism import settings as settings_module

        path = tmp_path / "prism" / "config.json"
        monkeypatch.setattr(settings_module, "config_path", lambda: path)
        for var in list(__import__("os").environ):
            if var.startswith(("IRIS_", "PRISM_", "CHATBOT_")):
                monkeypatch.delenv(var, raising=False)
        fresh = settings_module.Settings()
        fresh.chatbot_api_url = "https://api.test/v1"
        fresh.chatbot_api_key = "test-key"
        monkeypatch.setattr(settings_module, "settings", fresh)
        monkeypatch.setattr("prism.cli.commands.chatbot.settings", fresh)

        with (
            patch("prism.cli.commands.chatbot.save_config") as mock_save,
            patch(
                "prism.cli.commands.chatbot._run_agent_once",
                new_callable=AsyncMock,
                return_value="ok",
            ),
        ):
            result = runner.invoke(app, ["chatbot", "hello", "--api-url", "https://new/v1"])
            assert result.exit_code == 0
            mock_save.assert_called_once()

    def test_chatbot_save_config_from_flags(self):
        """Test _save_config_from_flags helper directly."""
        from prism.cli.commands.chatbot import _save_config_from_flags

        with patch("prism.cli.commands.chatbot.save_config") as mock_save:
            result = _save_config_from_flags(
                "https://api.test/v1",
                "sk-key",
                "gpt-4o-mini",
                "/skills",
            )
            assert result is True
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            assert saved["chatbot_api_url"] == "https://api.test/v1"
            assert saved["chatbot_api_key"] == "sk-key"
            assert saved["chatbot_model"] == "gpt-4o-mini"
            assert saved["chatbot_skills_path"] == "/skills"

    def test_chatbot_save_config_from_flags_none(self):
        """_save_config_from_flags with all None → returns False."""
        from prism.cli.commands.chatbot import _save_config_from_flags

        with patch("prism.cli.commands.chatbot.save_config") as mock_save:
            result = _save_config_from_flags(None, None, None, None)
            assert result is False
            mock_save.assert_not_called()

    def test_chatbot_save_config_strips_trailing_slash(self):
        """api_url trailing slash should be stripped."""
        from prism.cli.commands.chatbot import _save_config_from_flags

        with patch("prism.cli.commands.chatbot.save_config") as mock_save:
            _save_config_from_flags("https://api.test/v1/", None, None, None)
            saved = mock_save.call_args[0][0]
            assert saved["chatbot_api_url"] == "https://api.test/v1"


# ── index-* commands ──────────────────────────────────────────────────────


class TestIndexFeatureCommands:
    """CLI registration and basic invocation of the new index-* commands."""

    def test_index_search_help(self):
        result = runner.invoke(app, ["index-search", "--help"])
        assert result.exit_code == 0
        assert "query" in result.output

    def test_index_status_help(self):
        result = runner.invoke(app, ["index-status", "--help"])
        assert result.exit_code == 0
        assert "refresh" in result.output

    def test_index_search_calls_search_symbols(self):
        with patch(
            "prism.cli.commands.index.search_symbols",
            new=AsyncMock(return_value={"count": 1, "results": []}),
        ):
            result = runner.invoke(app, ["index-search", "GetX"])
        assert result.exit_code == 0
        assert "count" in result.output

    def test_index_node_calls_get_index_and_class_node(self):
        idx = {"cached": True, "classes": [], "call_graph": {}}
        with (
            patch("prism.cli.commands.index.get_index", new=AsyncMock(return_value=idx)),
            patch("prism.cli.commands.index.class_node", return_value={"name": "A"}),
        ):
            result = runner.invoke(app, ["index-node", "A"])
        assert result.exit_code == 0
        assert '"name": "A"' in result.output

    def test_index_refs_calls_class_refs(self):
        with (
            patch(
                "prism.cli.commands.index.get_index",
                new=AsyncMock(return_value={"cached": True, "classes": []}),
            ),
            patch(
                "prism.cli.commands.index.class_refs",
                return_value={"count": 0, "referenced_by": []},
            ),
        ):
            result = runner.invoke(app, ["index-refs", "A"])
        assert result.exit_code == 0
        assert "referenced_by" in result.output

    def test_index_impact_calls_method_impact(self):
        idx = {"cached": True, "classes": [], "call_graph": {}}
        with (
            patch("prism.cli.commands.index.get_index", new=AsyncMock(return_value=idx)),
            patch("prism.cli.commands.index.method_impact", return_value={"count": 2, "hops": {}}),
        ):
            result = runner.invoke(app, ["index-impact", "A.go"])
        assert result.exit_code == 0
        assert "hops" in result.output

    def test_index_path_calls_method_path(self):
        idx = {"cached": True, "classes": [], "call_graph": {}}
        with (
            patch("prism.cli.commands.index.get_index", new=AsyncMock(return_value=idx)),
            patch("prism.cli.commands.index.method_path", return_value={"found": True, "path": []}),
        ):
            result = runner.invoke(app, ["index-path", "A.go", "B.run"])
        assert result.exit_code == 0
        assert "found" in result.output

    def test_index_status_calls_api(self):
        with (
            patch(
                "prism.cli.commands.index.api_index_status",
                new=AsyncMock(return_value={"classes": 5, "fresh": True}),
            ),
        ):
            result = runner.invoke(app, ["index-status", "--prefix", "A"])
        assert result.exit_code == 0
        assert "fresh" in result.output

    def test_index_queries_help(self):
        """index-queries --help shows the query modes."""
        result = runner.invoke(app, ["index-queries", "--help"])
        assert result.exit_code == 0
        assert "callers_of_method" in result.output
        assert "find_path" in result.output

    def test_index_queries_calls_run_index_query(self):
        """index-queries forwards query + params to run_index_query."""
        with patch(
            "prism.cli.commands.index.run_index_query",
            new=AsyncMock(
                return_value={
                    "query": "callers_of_method",
                    "method": "A.go",
                    "total": 2,
                    "callers": ["B.run", "C.stop"],
                    "cached": True,
                }
            ),
        ) as m:
            result = runner.invoke(app, ["index-queries", "callers_of_method", "--method", "A.go"])
        assert result.exit_code == 0
        m.assert_awaited_once_with(
            "callers_of_method",
            method="A.go",
            class_name=None,
            source=None,
            target=None,
            top_n=20,
            limit=100,
            namespace=None,
            include_system=False,
            filter_prefix=None,
        )
        assert '"total": 2' in result.output
        assert "B.run" in result.output
