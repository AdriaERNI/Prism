"""Unit tests for the GUI SQL controller and syntax highlighting.

These tests run without a display — they test the controller logic
and the SQL editor regex patterns, not the actual Tk rendering.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch


from prism.gui.controllers.sql_controller import QueryResult, SQLController
from prism.gui.widgets.sql_editor import (
    _COMMENT_RE,
    _FUNCTION_RE,
    _KEYWORD_RE,
    _NUMBER_RE,
    _STRING_RE,
)


# ── QueryResult ───────────────────────────────────────────────────────


class TestQueryResult:
    """Tests for the QueryResult dataclass."""

    def test_empty_result(self):
        result = QueryResult()
        assert result.columns == []
        assert result.rows == []
        assert result.row_count == 0
        assert not result.is_error

    def test_error_result(self):
        result = QueryResult(error="Something went wrong")
        assert result.is_error
        assert result.error == "Something went wrong"

    def test_with_data(self):
        result = QueryResult(
            columns=["id", "name"],
            rows=[[1, "Alice"], [2, "Bob"]],
            row_count=2,
            elapsed=0.05,
        )
        assert result.columns == ["id", "name"]
        assert result.row_count == 2
        assert not result.is_error


# ── SQLController._parse_response ─────────────────────────────────────


class TestParseResponse:
    """Tests for the IRIS response parser."""

    def test_simple_select(self):
        raw = {
            "status": {"errors": [], "summary": ""},
            "console": [],
            "result": {
                "content": [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                ]
            },
        }
        result = SQLController._parse_response(raw, time.monotonic())
        assert result.columns == ["id", "name"]
        assert result.rows == [[1, "Alice"], [2, "Bob"]]
        assert result.row_count == 2
        assert not result.is_error

    def test_error_response(self):
        raw = {
            "status": {
                "errors": [{"error": "ERROR #5540: SQLCODE: -30 Table not found"}],
                "summary": "...",
            },
            "console": [],
            "result": {},
        }
        result = SQLController._parse_response(raw, time.monotonic())
        assert result.is_error
        assert "Table not found" in result.error

    def test_html_entity_unescaping(self):
        raw = {
            "status": {
                "errors": [{"error": "Table &#39;FOO&#39; not found"}],
                "summary": "",
            },
            "console": [],
            "result": {},
        }
        result = SQLController._parse_response(raw, time.monotonic())
        assert result.is_error
        assert "Table 'FOO' not found" in result.error

    def test_empty_result(self):
        raw = {
            "status": {"errors": [], "summary": ""},
            "console": [],
            "result": {"content": []},
        }
        result = SQLController._parse_response(raw, time.monotonic())
        assert result.columns == []
        assert result.rows == []
        assert result.row_count == 0
        assert not result.is_error

    def test_no_content_key(self):
        raw = {
            "status": {"errors": [], "summary": ""},
            "console": [],
            "result": {},
        }
        result = SQLController._parse_response(raw, time.monotonic())
        assert result.columns == []
        assert result.row_count == 0

    def test_null_values(self):
        raw = {
            "status": {"errors": [], "summary": ""},
            "console": [],
            "result": {
                "content": [
                    {"id": 1, "name": None},
                    {"id": 2, "name": "Bob"},
                ]
            },
        }
        result = SQLController._parse_response(raw, time.monotonic())
        assert result.rows == [[1, None], [2, "Bob"]]

    def test_multiple_columns_order_preserved(self):
        raw = {
            "status": {"errors": [], "summary": ""},
            "console": [],
            "result": {
                "content": [
                    {"z": 1, "a": 2, "m": 3},
                ]
            },
        }
        result = SQLController._parse_response(raw, time.monotonic())
        assert result.columns == ["z", "a", "m"]
        assert result.rows == [[1, 2, 3]]


# ── SQLController.execute ─────────────────────────────────────────────


class TestSQLControllerExecute:
    """Tests for the controller's execute method (with mocked async)."""

    def test_execute_calls_on_done(self):
        """Verify that execute launches a thread and calls on_done via poll."""
        mock_root = MagicMock()

        controller = SQLController(mock_root)

        # Mock the httpx AsyncClient to return a canned response.
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": {"errors": [], "summary": ""},
            "console": [],
            "result": {"content": [{"id": 1}]},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        # ``async with httpx.AsyncClient() as c:`` calls ``__aenter__``
        # which must return the mock client itself, not a new AsyncMock.
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("httpx.AsyncClient", return_value=mock_client):
            results: list[QueryResult] = []
            controller.execute("SELECT 1", on_done=results.append)
            if controller._thread:
                controller._thread.join(timeout=5)

            controller._poll()

        assert len(results) == 1
        assert results[0].row_count == 1
        assert results[0].columns == ["id"]

    def test_execute_while_running_ignored(self):
        """If a query is already running, the second call is ignored."""
        mock_root = MagicMock()
        controller = SQLController(mock_root)

        # Manually set running state
        controller._running = True

        with patch("httpx.AsyncClient") as mock_client_factory:
            controller.execute("SELECT 1", on_done=lambda r: None)
            time.sleep(0.1)

        mock_client_factory.assert_not_called()

    def test_execute_handles_exception(self):
        """Exceptions from httpx become error results."""
        mock_root = MagicMock()

        controller = SQLController(mock_root)

        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectionError("Cannot connect")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("httpx.AsyncClient", return_value=mock_client):
            results: list[QueryResult] = []
            controller.execute("SELECT 1", on_done=results.append)
            if controller._thread:
                controller._thread.join(timeout=5)

            controller._poll()

        assert len(results) == 1
        assert results[0].is_error
        assert "Cannot connect" in (results[0].error or "")


# ── Syntax Highlighting Regex Patterns ────────────────────────────────


class TestSyntaxHighlightingRegex:
    """Tests for the SQL syntax highlighting regex patterns."""

    def test_keyword_select(self):
        match = _KEYWORD_RE.search("SELECT * FROM employees")
        assert match is not None
        assert match.group(1).upper() == "SELECT"

    def test_keyword_from(self):
        matches = _KEYWORD_RE.findall("SELECT * FROM employees")
        assert "SELECT" in [m.upper() for m in matches]
        assert "FROM" in [m.upper() for m in matches]

    def test_keyword_where(self):
        matches = _KEYWORD_RE.findall("SELECT * FROM t WHERE x = 1")
        upper = [m.upper() for m in matches]
        assert "WHERE" in upper

    def test_keyword_case_insensitive(self):
        matches = _KEYWORD_RE.findall("select * from t")
        upper = [m.upper() for m in matches]
        assert "SELECT" in upper
        assert "FROM" in upper

    def test_non_keyword_not_matched(self):
        matches = _KEYWORD_RE.findall("SELECT name FROM employees")
        upper = [m.upper() for m in matches]
        assert "name" not in upper
        assert "employees" not in upper

    def test_string_literal(self):
        match = _STRING_RE.search("WHERE name = 'Alice'")
        assert match is not None
        assert match.group() == "'Alice'"

    def test_string_with_escaped_quote(self):
        match = _STRING_RE.search("WHERE name = 'O''Brien'")
        assert match is not None
        assert match.group() == "'O''Brien'"

    def test_string_empty(self):
        match = _STRING_RE.search("x = ''")
        assert match is not None
        assert match.group() == "''"

    def test_number_integer(self):
        match = _NUMBER_RE.search("WHERE id = 42")
        assert match is not None
        assert match.group() == "42"

    def test_number_decimal(self):
        match = _NUMBER_RE.search("WHERE price = 3.14")
        assert match is not None
        assert match.group() == "3.14"

    def test_comment_line(self):
        match = _COMMENT_RE.search("-- This is a comment\nSELECT 1")
        assert match is not None
        assert match.group() == "-- This is a comment"

    def test_comment_in_query(self):
        text = "SELECT 1 -- inline comment\nFROM dual"
        matches = _COMMENT_RE.findall(text)
        assert len(matches) == 1
        assert "inline comment" in matches[0]

    def test_function_count(self):
        match = _FUNCTION_RE.search("SELECT COUNT(*) FROM t")
        assert match is not None
        assert match.group(1).upper() == "COUNT"

    def test_function_sum(self):
        match = _FUNCTION_RE.search("SELECT SUM(x) FROM t")
        assert match is not None
        assert match.group(1).upper() == "SUM"

    def test_function_case_insensitive(self):
        match = _FUNCTION_RE.search("SELECT count(*) FROM t")
        assert match is not None
        assert match.group(1).upper() == "COUNT"

    def test_non_function_not_matched(self):
        """Words that aren't followed by '(' shouldn't match."""
        matches = _FUNCTION_RE.findall("SELECT name FROM employees")
        assert len(matches) == 0

    def test_complex_query_all_patterns(self):
        """Test all patterns in a complex query."""
        sql = (
            "SELECT COUNT(*) as cnt, AVG(price) as avg_price "
            "FROM orders "
            "WHERE status = 'pending' AND total > 100 "
            "-- only pending orders"
        )

        keywords = [m.upper() for m in _KEYWORD_RE.findall(sql)]
        assert "SELECT" in keywords
        assert "FROM" in keywords
        assert "WHERE" in keywords
        assert "AND" in keywords

        functions = [m.upper() for m in _FUNCTION_RE.findall(sql)]
        assert "COUNT" in functions
        assert "AVG" in functions

        strings = _STRING_RE.findall(sql)
        assert "'pending'" in strings

        numbers = _NUMBER_RE.findall(sql)
        assert "100" in numbers

        comments = _COMMENT_RE.findall(sql)
        assert len(comments) == 1
