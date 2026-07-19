"""Tests for CLI command edge cases and error handling.

Tests that commands validate inputs, produce friendly error messages,
and return correct exit codes when things go wrong — mirroring the
robustness expected from professional CLI tools like Docker.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from prism.cli.app import app

runner = CliRunner()


# ── Output format validation ─────────────────────────────────────────


class TestFormatValidation:
    """The --format global flag should reject unknown formats."""

    def test_invalid_format_warns_but_continues(self):
        """Unknown formats warn on stderr and fall back to JSON."""
        result = runner.invoke(app, ["--format", "xml", "info"])
        assert "unknown format 'xml'" in result.output.lower()

    def test_format_json_works(self):
        """--format json should work without warnings."""
        result = runner.invoke(app, ["--format", "json", "--version"])
        assert result.exit_code == 0

    def test_format_toon_falls_back_when_not_installed(self):
        """--format toon should fall back to JSON if toons is not installed."""
        with patch.dict("sys.modules", {"toons": None}):
            from prism.output import format_output

            result_str = format_output({"key": "value"}, "toon")
            assert json.loads(result_str) == {"key": "value"}


# ── SQL command edge cases ────────────────────────────────────────────


class TestSqlEdgeCases:
    """SQL command should validate input before hitting IRIS."""

    def test_empty_query_errors(self):
        result = runner.invoke(app, ["sql", ""])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_whitespace_query_errors(self):
        result = runner.invoke(app, ["sql", "   "])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()


# ── Terminal command edge cases ───────────────────────────────────────


class TestTerminalEdgeCases:
    """Terminal and ws commands should validate input."""

    def test_empty_terminal_command_errors(self):
        result = runner.invoke(app, ["terminal", ""])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_whitespace_terminal_command_errors(self):
        result = runner.invoke(app, ["terminal", "   "])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_empty_ws_command_enters_interactive(self):
        """Empty ws command enters interactive mode (not an error)."""
        result = runner.invoke(app, ["ws", ""])
        # Empty string is treated as no command — enters interactive mode.
        # On CI without IRIS, the connection will fail, so we just check
        # that the CLI didn't reject the empty command as a usage error.
        assert "cannot be empty" not in result.output.lower()

    def test_whitespace_ws_command_enters_interactive(self):
        """Whitespace-only ws command enters interactive mode."""
        result = runner.invoke(app, ["ws", "   "])
        assert "cannot be empty" not in result.output.lower()


# ── Compile command edge cases ────────────────────────────────────────


class TestCompileEdgeCases:
    """Compile command should validate document names."""

    def test_empty_document_name_errors(self):
        result = runner.invoke(app, ["compile", ""])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_whitespace_document_name_errors(self):
        result = runner.invoke(app, ["compile", "   "])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_no_documents_errors(self):
        """Compile with no document names should error."""
        result = runner.invoke(app, ["compile"])
        assert result.exit_code != 0


# ── Document command edge cases ───────────────────────────────────────


class TestDocumentEdgeCases:
    """get-doc, put-doc, delete-doc should validate document names."""

    def test_get_doc_empty_name_errors(self):
        result = runner.invoke(app, ["get-doc", ""])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_get_doc_whitespace_name_errors(self):
        result = runner.invoke(app, ["get-doc", "   "])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_put_doc_empty_name_errors(self):
        # Create a temp file to pass as the file argument
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cls", delete=False) as f:
            f.write("Class Foo.Bar {}\n")
            f.flush()
            result = runner.invoke(app, ["put-doc", "", f.name])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_delete_doc_empty_name_errors(self):
        result = runner.invoke(app, ["delete-doc", ""])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_delete_doc_whitespace_name_errors(self):
        result = runner.invoke(app, ["delete-doc", "   "])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()


# ── Test command edge cases ───────────────────────────────────────────


class TestTestEdgeCases:
    """test command should validate class name."""

    def test_empty_test_class_errors(self):
        result = runner.invoke(app, ["test", ""])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()

    def test_whitespace_test_class_errors(self):
        result = runner.invoke(app, ["test", "   "])
        assert result.exit_code == 1
        assert "cannot be empty" in result.output.lower()


# ── Serve command edge cases ──────────────────────────────────────────


class TestServeEdgeCases:
    """serve command should validate port range."""

    def test_port_zero_rejected(self):
        result = runner.invoke(app, ["serve", "--port", "0"])
        assert result.exit_code != 0

    def test_port_negative_rejected(self):
        result = runner.invoke(app, ["serve", "--port", "-1"])
        assert result.exit_code != 0

    def test_port_too_large_rejected(self):
        result = runner.invoke(app, ["serve", "--port", "70000"])
        assert result.exit_code != 0


# ── Cast command edge cases ───────────────────────────────────────────


class TestCastEdgeCases:
    """cast --del with no repos should give a helpful message."""

    def test_cast_del_no_repos(self):
        with patch("prism.cli.commands.cast.manager.list_repos", return_value=[]):
            result = runner.invoke(app, ["cast", "--del", "0"])
            assert result.exit_code == 1
            assert "no cast repos" in result.output.lower()


# ── Config command validation ─────────────────────────────────────────


class TestConfigValidation:
    """config should validate enum-like fields."""

    def test_invalid_output_format_rejected(self):
        result = runner.invoke(app, ["config", "-f", "invalid_format"])
        assert result.exit_code == 1
        assert "invalid output format" in result.output.lower()

    def test_invalid_terminal_method_rejected(self):
        result = runner.invoke(app, ["config", "--terminal-method", "invalid"])
        assert result.exit_code == 1
        assert "invalid terminal method" in result.output.lower()

    def test_reset_unknown_key_errors(self):
        result = runner.invoke(app, ["config", "--reset", "nonexistent_key"])
        assert result.exit_code == 1
        assert "unknown setting" in result.output.lower()


# ── Connection error handling ─────────────────────────────────────────


class TestConnectionErrorHandling:
    """All commands should show friendly errors when IRIS is unreachable."""

    @patch("prism.cli.commands.sql.execute_query", side_effect=Exception("connection"))
    def test_sql_connection_error_handled(self, _mock):
        """When IRIS is unreachable, sql command should error gracefully."""
        # This test verifies that the except clause catches the error
        # and doesn't let a raw traceback through
        result = runner.invoke(app, ["sql", "SELECT 1"])
        # Should exit with error code, not crash with traceback
        assert result.exit_code == 1
        assert "error" in result.output.lower()


# ── Setup command edge cases ──────────────────────────────────────────


class TestSetupEdgeCases:
    """setup command should reject unknown services."""

    def test_unknown_service_rejected(self):
        result = runner.invoke(app, ["setup", "invalid-service"])
        assert result.exit_code == 1
        assert "unknown service" in result.output.lower()

    def test_setup_help_shows_examples(self):
        """--help should show examples of usage."""
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "Examples" in result.output or "examples" in result.output.lower()
