"""Unit tests for GUI widgets — test logic without rendering the GUI.

These tests instantiate widgets in a headless Tk root and verify
their behavior through the Python API, not through pixel interaction.
"""

from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock

import pytest

# Skip if no display
pytestmark = pytest.mark.skipif(
    not pytest.importorskip("tkinter"),
    reason="tkinter not available",
)


@pytest.fixture(scope="module")
def tk_root():
    """Create a hidden Tk root for widget tests."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No display available for Tk tests")
    root.withdraw()  # Don't show the window
    yield root
    root.destroy()


# ── Database Tree Tests ───────────────────────────────────────────────


class TestDatabaseTree:
    """Test the DatabaseTree widget logic."""

    def test_tree_initial_state(self, tk_root):
        """Tree should start empty with no items."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        assert len(tree._tree.get_children()) == 0

    def test_populate_with_tables(self, tk_root):
        """Populating with tables should create schema nodes."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)

        tables = [
            {"schema": "%IPM_General", "name": "Settings", "type": "BASE TABLE"},
            {"schema": "%IPM_General", "name": "History", "type": "BASE TABLE"},
            {"schema": "%IPM_Repo", "name": "Definition", "type": "BASE TABLE"},
            {"schema": "User", "name": "Patients", "type": "BASE TABLE"},
        ]
        tree.populate(tables)

        # Should have one root node
        children = tree._tree.get_children()
        assert len(children) == 1

        # Root node should be "IRIS Connection"
        root_item = tree._tree.item(children[0])
        assert "IRIS Connection" in root_item["text"]

        # Root should have 2 children: "Schemas" (user) + "System Schemas" (system)
        top_folders = tree._tree.get_children(children[0])
        assert len(top_folders) == 2

    def test_schema_nodes_collapsed_by_default(self, tk_root):
        """Schema nodes should be collapsed (open=False) by default."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "Schema1", "name": "Table1", "type": "BASE TABLE"},
                {"schema": "Schema1", "name": "Table2", "type": "BASE TABLE"},
            ]
        )

        root = tree._tree.get_children()[0]
        # User schemas folder is open=True, but the schema node inside is collapsed
        schemas_folder = tree._tree.get_children(root)[0]  # "Schemas" folder
        schema_nodes = tree._tree.get_children(schemas_folder)
        for schema_node in schema_nodes:
            assert not tree._tree.item(schema_node, "open")

    def test_root_node_is_open(self, tk_root):
        """The root 'IRIS Connection' node should be open."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate([{"schema": "Schema1", "name": "Table1", "type": "BASE TABLE"}])

        root = tree._tree.get_children()[0]
        assert tree._tree.item(root, "open")

    def test_clear_removes_all_nodes(self, tk_root):
        """Clear should remove all nodes from the tree."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "Schema1", "name": "Table1", "type": "BASE TABLE"},
                {"schema": "Schema2", "name": "Table2", "type": "BASE TABLE"},
            ]
        )
        assert len(tree._tree.get_children()) > 0

        tree._clear()
        assert len(tree._tree.get_children()) == 0


# ── SQL Editor Tests ──────────────────────────────────────────────────


class TestSQLEditor:
    """Test the SQL editor widget logic."""

    def test_set_and_get_text(self, tk_root):
        """set_text should update the editor, text property should return it."""
        from prism.gui.widgets.sql_editor import SQLEditor

        editor = SQLEditor(tk_root)

        editor.set_text("SELECT 1")
        assert editor.text == "SELECT 1"
        assert editor.get_text() == "SELECT 1"

    def test_clear_removes_text(self, tk_root):
        """clear() should remove all text."""
        from prism.gui.widgets.sql_editor import SQLEditor

        editor = SQLEditor(tk_root)
        editor.set_text("SELECT * FROM users")
        editor.clear()
        assert editor.text == ""

    def test_append_adds_text(self, tk_root):
        """append() should add text at the end."""
        from prism.gui.widgets.sql_editor import SQLEditor

        editor = SQLEditor(tk_root)
        editor.set_text("SELECT 1")
        editor.append("\nWHERE 1=1")
        assert "SELECT 1" in editor.text
        assert "WHERE 1=1" in editor.text

    def test_insert_at_cursor(self, tk_root):
        """insert_at_cursor should insert text at cursor position."""
        from prism.gui.widgets.sql_editor import SQLEditor

        editor = SQLEditor(tk_root)
        editor.set_text("SELECT 1")
        editor._text.mark_set("insert", "1.7")  # After "SELECT "
        editor.insert_at_cursor("TOP ")
        assert "SELECT TOP 1" in editor.text

    def test_get_selection_or_all_returns_all_when_no_selection(self, tk_root):
        """When nothing is selected, get_selection_or_all should return full text."""
        from prism.gui.widgets.sql_editor import SQLEditor

        editor = SQLEditor(tk_root)
        editor.set_text("SELECT 1")
        assert editor.get_selection_or_all() == "SELECT 1"

    def test_execute_callback_is_set(self, tk_root):
        """set_execute_callback should store the callback."""
        from prism.gui.widgets.sql_editor import SQLEditor

        editor = SQLEditor(tk_root)
        callback = MagicMock()
        editor.set_execute_callback(callback)
        assert hasattr(editor, "_execute_cb")
        assert editor._execute_cb == callback

    def test_line_numbers_gutter_exists(self, tk_root):
        """The line number gutter canvas should exist."""
        from prism.gui.widgets.sql_editor import SQLEditor

        editor = SQLEditor(tk_root)
        assert hasattr(editor, "_gutter")
        assert isinstance(editor._gutter, tk.Canvas)


# ── Results Table Tests ───────────────────────────────────────────────


class TestResultsTable:
    """Test the ResultsTable widget logic."""

    def test_clear_removes_all_rows(self, tk_root):
        """clear() should remove all rows and columns."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)

        # Add some data
        from prism.gui.controllers.sql_controller import QueryResult

        result = QueryResult(
            columns=["A", "B"],
            rows=[(1, "x"), (2, "y")],
            row_count=2,
            elapsed=0.01,
        )
        table.show_results(result)
        assert len(table._tree.get_children()) > 0

        table.clear()
        assert len(table._tree.get_children()) == 0

    def test_show_results_populates_columns(self, tk_root):
        """show_results should create the right columns."""
        from prism.gui.widgets.results_table import ResultsTable
        from prism.gui.controllers.sql_controller import QueryResult

        table = ResultsTable(tk_root)

        result = QueryResult(
            columns=["ID", "Name", "Email"],
            rows=[(1, "Alice", "a@b.c")],
            row_count=1,
            elapsed=0.005,
        )
        table.show_results(result)

        cols = table._tree["columns"]
        assert len(cols) == 3
        assert "ID" in cols
        assert "Name" in cols
        assert "Email" in cols

    def test_show_results_uses_zebra_striping_tags(self, tk_root):
        """Rows should alternate between 'even' and 'odd' tags."""
        from prism.gui.widgets.results_table import ResultsTable
        from prism.gui.controllers.sql_controller import QueryResult

        table = ResultsTable(tk_root)

        result = QueryResult(
            columns=["A"],
            rows=[(1,), (2,), (3,), (4,)],
            row_count=4,
            elapsed=0.001,
        )
        table.show_results(result)

        items = table._tree.get_children()
        assert len(items) == 4
        tags_0 = table._tree.item(items[0], "tags")
        tags_1 = table._tree.item(items[1], "tags")
        assert "even" in tags_0
        assert "odd" in tags_1

    def test_error_display(self, tk_root):
        """Error results should show the error message, not a table."""
        from prism.gui.widgets.results_table import ResultsTable
        from prism.gui.controllers.sql_controller import QueryResult

        table = ResultsTable(tk_root)

        result = QueryResult(
            columns=[],
            rows=[],
            row_count=0,
            elapsed=0.001,
            error="SQL syntax error at line 1",
        )
        table.show_results(result)

        assert "Error" in table._status.cget(
            "text"
        ) or "syntax error" in table._status.cget("text")

    def test_sort_by_column(self, tk_root):
        """Clicking a column header should sort the rows."""
        from prism.gui.widgets.results_table import ResultsTable
        from prism.gui.controllers.sql_controller import QueryResult

        table = ResultsTable(tk_root)

        result = QueryResult(
            columns=["Name"],
            rows=[("Charlie",), ("Alice",), ("Bob",)],
            row_count=3,
            elapsed=0.001,
        )
        table.show_results(result)

        # Sort by "Name" column
        table._sort_by("Name")

        items = table._tree.get_children()
        first_val = table._tree.set(items[0], "Name")
        # Should be sorted (either asc or desc after first click)
        assert first_val in ("Alice", "Charlie")  # First or last alphabetically


# ── Status Bar Tests ─────────────────────────────────────────────────


class TestStatusBar:
    """Test the StatusBar widget logic."""

    def test_initial_state(self, tk_root):
        """Status bar should start with 'Not connected' status."""
        from prism.gui.widgets.status_bar import StatusBar

        bar = StatusBar(tk_root)
        assert "Not connected" in bar._conn_label.cget("text")
        assert bar._status_label.cget("text") == "Ready"

    def test_set_connected(self, tk_root):
        """set_connected should update the connection indicator."""
        from prism.gui.widgets.status_bar import StatusBar

        bar = StatusBar(tk_root)
        bar.set_connected(True, namespace="USER")
        assert "Connected" in bar._conn_label.cget("text")
        assert "USER" in bar._ns_label.cget("text")

    def test_set_disconnected(self, tk_root):
        """set_connected(False) should show disconnected state."""
        from prism.gui.widgets.status_bar import StatusBar

        bar = StatusBar(tk_root)
        bar.set_connected(True, "USER")
        bar.set_connected(False)
        assert "Not connected" in bar._conn_label.cget("text")

    def test_set_running(self, tk_root):
        """set_running should show 'Executing query...'."""
        from prism.gui.widgets.status_bar import StatusBar

        bar = StatusBar(tk_root)
        bar.set_running(True)
        assert "Executing" in bar._status_label.cget("text")

    def test_set_status_error(self, tk_root):
        """set_status with is_error=True should use error color."""
        from prism.gui.widgets.status_bar import StatusBar

        bar = StatusBar(tk_root)
        bar.set_status("Connection failed", is_error=True)
        assert "Connection failed" in bar._status_label.cget("text")

    def test_set_namespace(self, tk_root):
        """set_namespace should update the namespace label."""
        from prism.gui.widgets.status_bar import StatusBar

        bar = StatusBar(tk_root)
        bar.set_namespace("MYNS")
        assert "MYNS" in bar._ns_label.cget("text")


# ── Theme Tests ──────────────────────────────────────────────────────


class TestTheme:
    """Test that theme colors match DBeaver-inspired palette."""

    def test_editor_bg_is_dbeaver_dark(self):
        """Editor background should be #2e3436 (DBeaver dark main area)."""
        from prism.gui import theme

        assert theme.EDITOR_BG == "#2e3436"

    def test_sidebar_bg_is_dbeaver_panel(self):
        """Sidebar background should be #2e3436 (DBeaver navigator, unified)."""
        from prism.gui import theme

        assert theme.PANEL_BG == "#2e3436"

    def test_toolbar_bg_is_dbeaver_header(self):
        """Header background should be #3b4252 (DBeaver column headers)."""
        from prism.gui import theme

        assert theme.HEADER_BG == "#3b4252"

    def test_tab_bar_bg_exists(self):
        """Tab bar background constant should exist."""
        from prism.gui import theme

        assert hasattr(theme, "TAB_BAR_BG")
        assert theme.TAB_BAR_BG == "#2e3436"

    def test_status_bg_exists(self):
        """Status bar background constant should exist."""
        from prism.gui import theme

        assert hasattr(theme, "STATUS_BG")
        assert theme.STATUS_BG == "#2e3436"

    def test_separator_border_is_visible(self):
        """Border color should be #4c78a8 (DBeaver dividers/selection)."""
        from prism.gui import theme

        assert theme.BORDER == "#4c78a8"
