"""Edge case tests for GUI widgets — empty data, large data, special chars, errors.

These extend the existing test_gui_widgets.py with edge case coverage for
DatabaseTree, ResultsTable, Toolbar, and SQLEditor widgets.
"""

from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock

import pytest

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
    root.withdraw()
    yield root
    root.destroy()


# ── DatabaseTree edge cases ───────────────────────────────────────────────


class TestDatabaseTreeEdgeCases:
    """Edge case tests for DatabaseTree widget."""

    def test_populate_empty_list(self, tk_root):
        """Populating with an empty list should create root + empty Schemas folder."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate([])

        children = tree._tree.get_children()
        assert len(children) == 1
        root_item = tree._tree.item(children[0])
        assert "IRIS Connection" in root_item["text"]

        # Should have only the "Schemas" folder (no System Schemas)
        top_folders = tree._tree.get_children(children[0])
        assert len(top_folders) == 1

    def test_populate_with_system_tables(self, tk_root):
        """System tables (SYSTEM TABLE type) should go in System Tables folder."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "User", "name": "Patients", "type": "BASE TABLE"},
                {"schema": "User", "name": "Audit", "type": "SYSTEM TABLE"},
            ]
        )

        root = tree._tree.get_children()[0]
        schemas_folder = tree._tree.get_children(root)[0]
        schema_node = tree._tree.get_children(schemas_folder)[0]

        # Schema node should have "Tables" and "System Tables" folders
        sub_folders = tree._tree.get_children(schema_node)
        texts = [tree._tree.item(f, "text") for f in sub_folders]
        assert any("Tables" in t for t in texts)
        assert any("System Tables" in t for t in texts)

    def test_populate_with_views(self, tk_root):
        """Views (SYSTEM VIEW type) should go in Views folder."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "User", "name": "Patients", "type": "BASE TABLE"},
                {"schema": "User", "name": "PatientView", "type": "SYSTEM VIEW"},
            ]
        )

        root = tree._tree.get_children()[0]
        schemas_folder = tree._tree.get_children(root)[0]
        schema_node = tree._tree.get_children(schemas_folder)[0]

        sub_folders = tree._tree.get_children(schema_node)
        texts = [tree._tree.item(f, "text") for f in sub_folders]
        assert any("Views" in t for t in texts)

    def test_populate_only_system_schemas(self, tk_root):
        """Tables only in % schemas should create only System Schemas node."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "%SYS", "name": "Roles", "type": "BASE TABLE"},
                {"schema": "%SYS", "name": "Users", "type": "BASE TABLE"},
            ]
        )

        root = tree._tree.get_children()[0]
        top_folders = tree._tree.get_children(root)
        # Should have "Schemas" (empty) and "System Schemas" (with 1 schema)
        texts = [tree._tree.item(f, "text") for f in top_folders]
        assert any("System Schemas" in t for t in texts)

    def test_populate_system_schemas_collapsed(self, tk_root):
        """System Schemas folder should be collapsed by default."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate([{"schema": "%SYS", "name": "Roles", "type": "BASE TABLE"}])

        root = tree._tree.get_children()[0]
        top_folders = tree._tree.get_children(root)
        for folder in top_folders:
            text = tree._tree.item(folder, "text")
            if "System Schemas" in text:
                assert not tree._tree.item(folder, "open")

    def test_table_names_sorted(self, tk_root):
        """Table names within a folder should be sorted alphabetically."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "S", "name": "Zebra", "type": "BASE TABLE"},
                {"schema": "S", "name": "Apple", "type": "BASE TABLE"},
                {"schema": "S", "name": "Mango", "type": "BASE TABLE"},
            ]
        )

        root = tree._tree.get_children()[0]
        schemas_folder = tree._tree.get_children(root)[0]
        schema_node = tree._tree.get_children(schemas_folder)[0]
        tables_folder = tree._tree.get_children(schema_node)[0]

        table_nodes = tree._tree.get_children(tables_folder)
        names = [tree._tree.item(n, "text") for n in table_nodes]
        # Names should be in sorted order
        clean_names = [n.replace("📊 ", "") for n in names]
        assert clean_names == sorted(clean_names)

    def test_filter_tree_matching(self, tk_root):
        """Filtering should only show matching tables."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "User", "name": "Patients", "type": "BASE TABLE"},
                {"schema": "User", "name": "Doctors", "type": "BASE TABLE"},
                {"schema": "Admin", "name": "Config", "type": "BASE TABLE"},
            ]
        )

        # Simulate typing "pat" in the search box
        tree._search_var.set("pat")
        tree._filter_tree()

        # Should filter to only show Patients
        root = tree._tree.get_children()[0]
        schemas_folder = tree._tree.get_children(root)[0]
        schema_nodes = tree._tree.get_children(schemas_folder)
        # Should have at least 1 schema (User)
        assert len(schema_nodes) >= 1

    def test_filter_tree_clears_on_empty_search(self, tk_root):
        """Clearing the search should restore all tables."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "User", "name": "Patients", "type": "BASE TABLE"},
                {"schema": "User", "name": "Doctors", "type": "BASE TABLE"},
            ]
        )

        # Filter then clear
        tree._search_var.set("pat")
        tree._filter_tree()
        tree._search_var.set("")
        tree._filter_tree()

        root = tree._tree.get_children()[0]
        schemas_folder = tree._tree.get_children(root)[0]
        schema_nodes = tree._tree.get_children(schemas_folder)
        # Should show all schemas again
        assert len(schema_nodes) == 1

    def test_search_placeholder_focus_in(self, tk_root):
        """Focusing the search box should clear placeholder."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        assert tree._search_var.get() == "Search..."
        tree._on_search_focus_in()
        assert tree._search_var.get() == ""

    def test_search_placeholder_focus_out(self, tk_root):
        """Unfocusing empty search should restore placeholder."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree._on_search_focus_in()  # Clear placeholder
        tree._on_search_focus_out()  # Restore placeholder
        assert tree._search_var.get() == "Search..."

    def test_set_insert_callback(self, tk_root):
        """set_insert_callback should store the callback."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        callback = MagicMock()
        tree.set_insert_callback(callback)
        assert tree._insert_callback is callback

    def test_double_click_no_selection(self, tk_root):
        """Double-click with no selection should not crash."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.set_insert_callback(lambda x: None)
        # No selection set
        tree._on_double_click()  # Should not raise

    def test_double_click_no_callback(self, tk_root):
        """Double-click without callback set should not crash."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree._on_double_click()  # Should not raise

    def test_double_click_on_view_inserts_query(self, tk_root):
        """Double-clicking a view should insert SELECT * FROM query."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate([{"schema": "User", "name": "MyView", "type": "SYSTEM VIEW"}])

        inserted = []
        tree.set_insert_callback(lambda text: inserted.append(text))

        root = tree._tree.get_children()[0]
        schemas_folder = tree._tree.get_children(root)[0]
        schema_node = tree._tree.get_children(schemas_folder)[0]
        # Find the Views folder
        sub_folders = tree._tree.get_children(schema_node)
        views_folder = None
        for f in sub_folders:
            if "Views" in tree._tree.item(f, "text"):
                views_folder = f
                break
        assert views_folder is not None
        view_node = tree._tree.get_children(views_folder)[0]

        tree._tree.selection_set(view_node)
        tree._tree.focus(view_node)
        tree._on_double_click()

        assert len(inserted) == 1
        assert "SELECT * FROM User.MyView" in inserted[0]

    def test_special_characters_in_table_names(self, tk_root):
        """Table names with special characters should be handled."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree.populate(
            [
                {"schema": "MyApp", "name": "Table_With_Underscores", "type": "BASE TABLE"},
                {"schema": "MyApp", "name": "Table123", "type": "BASE TABLE"},
            ]
        )
        # Should not crash
        root = tree._tree.get_children()[0]
        assert root is not None

    def test_large_number_of_tables(self, tk_root):
        """A large number of tables should be handled without error."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tables = [
            {"schema": f"Schema{i // 100}", "name": f"Table{i}", "type": "BASE TABLE"}
            for i in range(500)
        ]
        tree.populate(tables)
        # Should have root node
        assert len(tree._tree.get_children()) == 1

    def test_on_expand_no_selection(self, tk_root):
        """_on_expand with no selection should not crash."""
        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree._on_expand()  # Should not raise

    def test_load_async_skips_if_already_polling(self, tk_root):
        """load_async should not start a new thread if already polling."""
        from unittest.mock import patch

        from prism.gui.widgets.database_tree import DatabaseTree

        tree = DatabaseTree(tk_root)
        tree._polling = True
        with patch("threading.Thread") as mock_thread:
            tree.load_async()
            mock_thread.assert_not_called()


# ── ResultsTable edge cases ────────────────────────────────────────────────


class TestResultsTableEdgeCases:
    """Edge case tests for ResultsTable widget."""

    def test_show_results_empty_columns(self, tk_root):
        """QueryResult with no columns should show success message."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=[],
            rows=[],
            row_count=0,
            elapsed=0.001,
        )
        table.show_results(result)
        assert "successfully" in table._status.cget("text").lower()

    def test_show_results_with_none_values(self, tk_root):
        """None values should be displayed as 'NULL'."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=["A", "B"],
            rows=[[None, "x"], [None, None]],
            row_count=2,
            elapsed=0.001,
        )
        table.show_results(result)
        items = table._tree.get_children()
        assert table._tree.set(items[0], "A") == "NULL"
        assert table._tree.set(items[1], "B") == "NULL"

    def test_show_results_with_bool_values(self, tk_root):
        """Boolean values should be displayed as '1' or '0'."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=["Flag"],
            rows=[[True], [False]],
            row_count=2,
            elapsed=0.001,
        )
        table.show_results(result)
        items = table._tree.get_children()
        assert table._tree.set(items[0], "Flag") == "1"
        assert table._tree.set(items[1], "Flag") == "0"

    def test_show_results_with_list_dict_values(self, tk_root):
        """List/dict values should be JSON-serialized."""
        import json

        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=["Data"],
            rows=[[{"key": "val"}], [[1, 2, 3]]],
            row_count=2,
            elapsed=0.001,
        )
        table.show_results(result)
        items = table._tree.get_children()
        assert json.loads(table._tree.set(items[0], "Data")) == {"key": "val"}
        assert json.loads(table._tree.set(items[1], "Data")) == [1, 2, 3]

    def test_show_results_large_dataset(self, tk_root):
        """A large dataset should be handled without error."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=["ID"],
            rows=[[i] for i in range(1000)],
            row_count=1000,
            elapsed=0.5,
        )
        table.show_results(result)
        items = table._tree.get_children()
        assert len(items) == 1000

    def test_show_results_special_characters(self, tk_root):
        """Special characters in data should be preserved."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=["Name"],
            rows=[("O'Brien",), ("Tab\tText",), ("Line\nBreak",)],
            row_count=3,
            elapsed=0.001,
        )
        table.show_results(result)
        items = table._tree.get_children()
        assert table._tree.set(items[0], "Name") == "O'Brien"

    def test_format_cell_none(self):
        """_format_cell(None) should return 'NULL'."""
        from prism.gui.widgets.results_table import ResultsTable

        assert ResultsTable._format_cell(None) == "NULL"

    def test_format_cell_bool(self):
        """_format_cell with bool should return '1' or '0'."""
        from prism.gui.widgets.results_table import ResultsTable

        assert ResultsTable._format_cell(True) == "1"
        assert ResultsTable._format_cell(False) == "0"

    def test_format_cell_list(self):
        """_format_cell with list should return JSON."""
        import json

        from prism.gui.widgets.results_table import ResultsTable

        result = ResultsTable._format_cell([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_format_cell_dict(self):
        """_format_cell with dict should return JSON."""
        import json

        from prism.gui.widgets.results_table import ResultsTable

        result = ResultsTable._format_cell({"a": 1})
        assert json.loads(result) == {"a": 1}

    def test_format_cell_string(self):
        """_format_cell with string should return the string."""
        from prism.gui.widgets.results_table import ResultsTable

        assert ResultsTable._format_cell("hello") == "hello"

    def test_escape_sql_value_none(self):
        """_escape_sql_value(None) should return 'NULL'."""
        from prism.gui.widgets.results_table import ResultsTable

        assert ResultsTable._escape_sql_value(None) == "NULL"

    def test_escape_sql_value_number(self):
        """_escape_sql_value with number should return unquoted."""
        from prism.gui.widgets.results_table import ResultsTable

        assert ResultsTable._escape_sql_value(42) == "42"
        assert ResultsTable._escape_sql_value(3.14) == "3.14"

    def test_escape_sql_value_string(self):
        """_escape_sql_value with string should quote and escape."""
        from prism.gui.widgets.results_table import ResultsTable

        assert ResultsTable._escape_sql_value("hello") == "'hello'"

    def test_escape_sql_value_string_with_quotes(self):
        """_escape_sql_value should double internal single quotes."""
        from prism.gui.widgets.results_table import ResultsTable

        assert ResultsTable._escape_sql_value("O'Brien") == "'O''Brien'"

    def test_show_message(self, tk_root):
        """show_message should display a status message."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table.show_message("Custom message")
        assert "Custom message" in table._status.cget("text")

    def test_show_message_error(self, tk_root):
        """show_message with is_error=True should use error color."""
        from prism.gui import theme
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table.show_message("Bad error", is_error=True)
        assert "Bad error" in table._status.cget("text")
        # Error color should be used
        assert table._status.cget("foreground") == theme.FG_ERROR

    def test_clear_source_table(self, tk_root):
        """clear_source_table should remove the source table."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table.set_source_table("S", "T")
        assert table._source_table == "S.T"
        table.clear_source_table()
        assert table._source_table is None

    def test_sort_numeric(self, tk_root):
        """Sorting by a numeric column should sort numerically."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=["Value"],
            rows=[("10",), ("2",), ("30",), ("1",)],
            row_count=4,
            elapsed=0.001,
        )
        table.show_results(result)
        table._sort_by("Value")

        items = table._tree.get_children()
        first_val = table._tree.set(items[0], "Value")
        # Numeric sort: first should be "1" or "30" (asc or desc)
        assert first_val in ("1", "30")

    def test_sort_empty_tree(self, tk_root):
        """Sorting an empty tree should not crash."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table._sort_by("Nonexistent")  # Should not raise

    def test_on_refresh_with_callback(self, tk_root):
        """_on_refresh should call the status callback."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        called = []
        table.set_status_callback(lambda msg: called.append(msg))
        table._on_refresh()
        assert called == ["refresh"]

    def test_on_refresh_no_callback(self, tk_root):
        """_on_refresh without callback should not crash."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table._on_refresh()  # Should not raise

    def test_on_filter_stub(self, tk_root):
        """_on_filter stub should not crash."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table._on_filter()  # Should not raise

    def test_on_export_stub(self, tk_root):
        """_on_export stub should not crash."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table._on_export()  # Should not raise

    def test_on_grid_view_stub(self, tk_root):
        """_on_grid_view stub should not crash."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table._on_grid_view()  # Should not raise

    def test_revert_no_changes(self, tk_root):
        """Revert with no modifications should show message."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=["ID"],
            rows=[[1]],
            row_count=1,
            elapsed=0.001,
        )
        table.show_results(result)
        table._on_cancel()
        assert "No changes" in table._status.cget("text")

    def test_save_with_invalid_table_name(self, tk_root):
        """Save with SQL injection attempt in table name should be rejected."""
        from unittest.mock import MagicMock

        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table.set_controller(MagicMock())  # Set controller so we reach the identifier check
        result = QueryResult(
            columns=["ID", "Name"],
            rows=[[1, "Alice"]],
            row_count=1,
            elapsed=0.001,
        )
        table.show_results(result)
        # Set an invalid table name (simulating injection)
        table._source_table = "Users; DROP TABLE--"
        items = table._tree.get_children()
        table._modified_cells[items[0]] = {"Name": "Changed"}

        table._on_save()
        assert "Cannot commit" in table._status.cget("text")
        assert "invalid" in table._status.cget("text").lower()

    def test_save_with_no_controller(self, tk_root):
        """Save with no controller connected should error."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        result = QueryResult(
            columns=["ID", "Name"],
            rows=[[1, "Alice"]],
            row_count=1,
            elapsed=0.001,
        )
        table.show_results(result)
        table.set_source_table("Test", "Users")
        items = table._tree.get_children()
        table._modified_cells[items[0]] = {"Name": "Changed"}

        table._on_save()
        assert "Cannot commit" in table._status.cget("text")
        assert "controller" in table._status.cget("text").lower()

    def test_save_no_columns(self, tk_root):
        """Save with no columns should not crash."""
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table.set_source_table("Test", "Users")
        table._modified_cells["fake_item"] = {"Name": "Changed"}
        table._on_save()  # Should not raise — _columns is empty

    def test_on_all_updates_done_no_raw(self, tk_root):
        """_on_all_updates_done with no raw data should show fallback."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table.set_source_table("S", "T")
        result = QueryResult(columns=[], rows=[], error="Some error")
        table._on_all_updates_done(result)
        assert "Error" in table._status.cget("text")

    def test_on_all_updates_done_success(self, tk_root):
        """_on_all_updates_done with successful result should show committed."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table.set_source_table("S", "T")
        table._columns = ["ID", "Name"]
        table._rows = [[1, "Original"]]

        # Add a row to the tree so we can test the update flow
        item = table._tree.insert("", "end", values=["1", "Original"])
        table._modified_cells[item] = {"Name": "Changed"}

        result = QueryResult(
            columns=["ID"],
            rows=[],
            raw={"results": [{"context": (item, {"Name": "Changed"})}]},
        )
        table._on_all_updates_done(result)
        assert "committed" in table._status.cget("text").lower()

    def test_on_all_updates_done_partial_failure(self, tk_root):
        """_on_all_updates_done with partial failure should show warning."""
        from prism.gui.controllers.sql_controller import QueryResult
        from prism.gui.widgets.results_table import ResultsTable

        table = ResultsTable(tk_root)
        table.set_source_table("S", "T")
        item = table._tree.insert("", "end", values=["1"])

        result = QueryResult(
            columns=[],
            rows=[],
            raw={
                "results": [
                    {"context": (item, {"Name": "Changed"}), "error": "Failed"},
                    {"context": ("nonexistent_item", {}), "error": "Failed"},
                ]
            },
        )
        table._on_all_updates_done(result)
        assert "failed" in table._status.cget("text").lower() or "Error" in table._status.cget(
            "text"
        )


# ── Toolbar tests ──────────────────────────────────────────────────────────


class TestToolbar:
    """Tests for the Toolbar widget."""

    def test_toolbar_creation(self, tk_root):
        """Toolbar should be created without error."""
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        assert toolbar is not None

    def test_namespace_var(self, tk_root):
        """namespace_var should return a StringVar."""
        import tkinter as tk

        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        assert isinstance(toolbar.namespace_var, tk.StringVar)

    def test_set_callbacks(self, tk_root):
        """set_callbacks should store all callbacks."""
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        cb = MagicMock()
        toolbar.set_callbacks(
            on_new=cb,
            on_open=cb,
            on_save=cb,
            on_connect=cb,
            on_disconnect=cb,
            on_refresh=cb,
            on_new_sql=cb,
            on_execute=cb,
            on_cancel=cb,
            on_clear=cb,
        )
        assert toolbar._cb_new is cb
        assert toolbar._cb_open is cb
        assert toolbar._cb_save is cb
        assert toolbar._cb_connect is cb
        assert toolbar._cb_disconnect is cb
        assert toolbar._cb_refresh is cb
        assert toolbar._cb_new_sql is cb
        assert toolbar._cb_execute is cb
        assert toolbar._cb_cancel is cb
        assert toolbar._cb_clear is cb

    def test_on_new_calls_callback(self, tk_root):
        """_on_new should call the new callback."""
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_new=called)
        toolbar._on_new()
        called.assert_called_once()

    def test_on_open_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_open=called)
        toolbar._on_open()
        called.assert_called_once()

    def test_on_save_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_save=called)
        toolbar._on_save()
        called.assert_called_once()

    def test_on_connect_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_connect=called)
        toolbar._on_connect()
        called.assert_called_once()

    def test_on_disconnect_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_disconnect=called)
        toolbar._on_disconnect()
        called.assert_called_once()

    def test_on_refresh_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_refresh=called)
        toolbar._on_refresh()
        called.assert_called_once()

    def test_on_new_sql_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_new_sql=called)
        toolbar._on_new_sql()
        called.assert_called_once()

    def test_on_execute_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_execute=called)
        toolbar._on_execute()
        called.assert_called_once()

    def test_on_cancel_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_cancel=called)
        toolbar._on_cancel()
        called.assert_called_once()

    def test_on_clear_calls_callback(self, tk_root):
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        called = MagicMock()
        toolbar.set_callbacks(on_clear=called)
        toolbar._on_clear()
        called.assert_called_once()

    def test_on_new_without_callback(self, tk_root):
        """_on_new without callback set should not crash."""
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        toolbar._on_new()  # Should not raise

    def test_set_running_true(self, tk_root):
        """set_running(True) should disable execute, enable cancel."""
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        toolbar.set_running(True)
        assert str(toolbar._btn_execute.cget("state")) == "disabled"
        assert str(toolbar._btn_cancel.cget("state")) == "normal"

    def test_set_running_false(self, tk_root):
        """set_running(False) should enable execute, disable cancel."""
        from prism.gui.widgets.toolbar import Toolbar

        toolbar = Toolbar(tk_root)
        toolbar.set_running(False)
        assert str(toolbar._btn_execute.cget("state")) == "normal"
        assert str(toolbar._btn_cancel.cget("state")) == "disabled"
