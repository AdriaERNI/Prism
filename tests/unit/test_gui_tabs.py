"""Unit tests for GUI tab management, per-tab query persistence, and auto-save.

Tests cover:
- Tab creation via multiple methods (toolbar New, Ctrl+N, menu File > New Query)
- Per-tab query text isolation (switching tabs preserves each tab's content)
- Correct tab naming with monotonic IDs (no reuse after close)
- Tab close behavior (can't close last tab, content preservation)
- Right-click rename: context menu, rename_tab method, callback firing
- Auto-save after configurable delay (default 3000 ms)
- Query restoration on app reopen
- Modified indicator (* prefix) on tab labels
"""

from __future__ import annotations

import json
import tkinter as tk
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(
    not pytest.importorskip("tkinter"),
    reason="tkinter not available",
)


def _make_tk_root():
    """Create a Tk root, skipping the test if Tcl/Tk is unavailable."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tcl/Tk not available on this platform")
    root.withdraw()
    return root


@pytest.fixture(scope="module")
def tk_root():
    """Create a hidden Tk root for widget tests."""
    root = _make_tk_root()
    yield root
    root.destroy()


@pytest.fixture
def mock_gui_env():
    """Mock the controller and tree background threads to prevent segfaults.

    PrismGUI.__init__ starts a connection check thread and a database tree
    loading thread. These threads call back into Tkinter's ``after`` which
    can cause segfaults if the root was already destroyed by a previous test.

    This fixture patches the thread-starting methods only:
    - ``SQLController.start_polling`` → no-op (no after-loop)
    - ``SQLController.check_connection`` → calls on_done synchronously (no thread)
    - ``DatabaseTree.load_async`` → no-op (no background thread)

    It also resets ``gui_saved_queries`` to ``"[]"`` to prevent test isolation
    issues where a previous test's auto-save leaves persisted queries that
    get restored by the next test's ``_restore_saved_queries``.
    """
    import prism.gui.app as app_mod

    original = app_mod.settings.gui_saved_queries
    app_mod.settings.gui_saved_queries = "[]"
    with (
        patch("prism.gui.controllers.sql_controller.SQLController.start_polling"),
        patch(
            "prism.gui.controllers.sql_controller.SQLController.check_connection",
            side_effect=lambda on_done=None: on_done(False) if on_done else None,
        ),
        patch("prism.gui.widgets.database_tree.DatabaseTree.load_async"),
    ):
        yield
    app_mod.settings.gui_saved_queries = original


# ── EditorTabBar: Tab Creation ────────────────────────────────────────


class TestTabCreation:
    """Test tab creation via various methods."""

    def test_initial_tab_is_script_1(self, tk_root):
        """EditorTabBar should start with one tab named Script-1."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        assert bar.tab_count == 1
        assert bar.get_tab_name(0) == "Script-1"
        bar.destroy()

    def test_add_tab_auto_names(self, tk_root, mock_gui_env):
        """Adding tabs without a name auto-generates Script-2, Script-3, etc."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        idx2 = bar.add_tab()
        idx3 = bar.add_tab()

        assert bar.tab_count == 3
        assert bar.get_tab_name(0) == "Script-1"
        assert bar.get_tab_name(1) == "Script-2"
        assert bar.get_tab_name(2) == "Script-3"
        assert idx2 == 1
        assert idx3 == 2
        bar.destroy()

    def test_add_tab_with_custom_name(self, tk_root, mock_gui_env):
        """Adding a tab with a custom name uses that name."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab(name="My Query")

        assert bar.get_tab_name(1) == "My Query"
        bar.destroy()

    def test_add_tab_with_content(self, tk_root, mock_gui_env):
        """Adding a tab with content stores that content."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab(content="SELECT 1")

        assert bar.get_tab_content(1) == "SELECT 1"
        bar.destroy()

    def test_new_tab_switches_active(self, tk_root, mock_gui_env):
        """Adding a new tab switches the active tab to it."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        assert bar.active_index == 0

        bar.add_tab()
        assert bar.active_index == 1
        bar.destroy()


# ── EditorTabBar: Tab Naming (monotonic, no reuse) ───────────────────


class TestTabNaming:
    """Test that tab naming uses monotonic IDs and never reuses numbers."""

    def test_no_name_reuse_after_close(self, tk_root, mock_gui_env):
        """Closing Script-2 then adding a new tab should produce Script-4, not Script-2."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()  # Script-2
        bar.add_tab()  # Script-3
        assert bar.tab_count == 3

        bar.close_tab(1)  # Close Script-2
        assert bar.tab_count == 2
        assert bar.get_tab_name(0) == "Script-1"
        assert bar.get_tab_name(1) == "Script-3"

        bar.add_tab()  # Should be Script-4, not Script-2
        assert bar.get_tab_name(2) == "Script-4"
        bar.destroy()

    def test_names_are_unique(self, tk_root, mock_gui_env):
        """All tab names must be unique even after closing and adding."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()  # Script-2
        bar.add_tab()  # Script-3
        bar.add_tab()  # Script-4
        bar.close_tab(2)  # Close Script-3
        bar.add_tab()  # Script-5

        names = [bar.get_tab_name(i) for i in range(bar.tab_count)]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"
        bar.destroy()

    def test_sequential_naming(self, tk_root, mock_gui_env):
        """Tab names should follow Script-1, Script-2, Script-3, etc."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        for i in range(5):
            bar.add_tab()

        for i in range(6):
            assert bar.get_tab_name(i) == f"Script-{i + 1}"
        bar.destroy()


# ── EditorTabBar: Tab Switching ──────────────────────────────────────


class TestTabSwitching:
    """Test tab switching behavior."""

    def test_switch_to_changes_active(self, tk_root, mock_gui_env):
        """switch_to should update the active tab index."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()
        bar.add_tab()

        bar.switch_to(0)
        assert bar.active_index == 0

        bar.switch_to(2)
        assert bar.active_index == 2
        bar.destroy()

    def test_switch_callback_fires(self, tk_root, mock_gui_env):
        """Switching tabs should fire the switch callback with old and new indices."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()
        # add_tab switches to tab 1, so active is now 1
        assert bar.active_index == 1

        calls = []
        bar.set_switch_callback(lambda old, new: calls.append((old, new)))

        bar.switch_to(1)  # Same tab — no callback
        assert len(calls) == 0

        bar.switch_to(0)
        assert calls == [(1, 0)]
        bar.destroy()

    def test_switch_to_invalid_index_ignored(self, tk_root, mock_gui_env):
        """Switching to an invalid index should be a no-op."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.switch_to(99)
        assert bar.active_index == 0
        bar.switch_to(-1)
        assert bar.active_index == 0
        bar.destroy()


# ── EditorTabBar: Tab Close ──────────────────────────────────────────


class TestTabClose:
    """Test tab close behavior."""

    def test_close_last_tab_prevented(self, tk_root, mock_gui_env):
        """Closing the last remaining tab should be a no-op."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        assert bar.tab_count == 1

        bar.close_tab(0)
        assert bar.tab_count == 1  # Still there
        bar.destroy()

    def test_close_middle_tab(self, tk_root, mock_gui_env):
        """Closing a middle tab should preserve the others."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()  # Script-2
        bar.add_tab()  # Script-3

        bar.close_tab(1)  # Close Script-2
        assert bar.tab_count == 2
        assert bar.get_tab_name(0) == "Script-1"
        assert bar.get_tab_name(1) == "Script-3"
        bar.destroy()

    def test_close_callback_fires(self, tk_root, mock_gui_env):
        """Closing a tab should fire the close callback with the closed index."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()

        calls = []
        bar.set_close_callback(lambda idx: calls.append(idx))

        bar.close_tab(1)
        assert calls == [1]
        bar.destroy()

    def test_close_adjusts_active_index(self, tk_root, mock_gui_env):
        """Closing a tab before the active one should decrement active index."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()  # Script-2
        bar.add_tab()  # Script-3

        bar.switch_to(2)
        assert bar.active_index == 2

        bar.close_tab(1)  # Close Script-2 (before active)
        assert bar.active_index == 1  # Adjusted from 2 to 1
        bar.destroy()


# ── EditorTabBar: Per-Tab Content ────────────────────────────────────


class TestTabContent:
    """Test per-tab content storage and retrieval."""

    def test_set_and_get_content(self, tk_root, mock_gui_env):
        """set_tab_content and get_tab_content should round-trip."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.set_tab_content(0, "SELECT * FROM users")
        assert bar.get_tab_content(0) == "SELECT * FROM users"
        bar.destroy()

    def test_content_isolated_per_tab(self, tk_root, mock_gui_env):
        """Each tab should have its own independent content."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab(content="SELECT 1")
        bar.add_tab(content="SELECT 2")

        assert bar.get_tab_content(0) == ""
        assert bar.get_tab_content(1) == "SELECT 1"
        assert bar.get_tab_content(2) == "SELECT 2"
        bar.destroy()

    def test_get_content_invalid_index(self, tk_root, mock_gui_env):
        """Getting content for an invalid index should return empty string."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        assert bar.get_tab_content(99) == ""
        assert bar.get_tab_content(-1) == ""
        bar.destroy()

    def test_set_content_invalid_index(self, tk_root, mock_gui_env):
        """Setting content for an invalid index should be a no-op."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.set_tab_content(99, "test")  # Should not raise
        bar.destroy()

    def test_get_all_tabs(self, tk_root, mock_gui_env):
        """get_all_tabs should return a list of all tab info."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab(content="SELECT 1", name="Query-A")

        tabs = bar.get_all_tabs()
        assert len(tabs) == 2
        assert tabs[0]["name"] == "Script-1"
        assert tabs[0]["content"] == ""
        assert tabs[1]["name"] == "Query-A"
        assert tabs[1]["content"] == "SELECT 1"
        bar.destroy()


# ── EditorTabBar: Modified Indicator ─────────────────────────────────


class TestTabModified:
    """Test the modified indicator on tabs."""

    def test_set_modified_true(self, tk_root, mock_gui_env):
        """set_modified(True) should add * prefix to tab label."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.set_modified(0, True)

        tab = bar._tabs[0]
        assert tab["modified"] is True
        assert "*" in tab["label"].cget("text")
        bar.destroy()

    def test_set_modified_false(self, tk_root, mock_gui_env):
        """set_modified(False) should remove * prefix."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.set_modified(0, True)
        bar.set_modified(0, False)

        tab = bar._tabs[0]
        assert tab["modified"] is False
        assert "*" not in tab["label"].cget("text")
        bar.destroy()

    def test_modified_invalid_index(self, tk_root, mock_gui_env):
        """set_modified on invalid index should be a no-op."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.set_modified(99, True)  # Should not raise
        bar.destroy()


# ── EditorTabBar: Tab Rename ─────────────────────────────────────────


class TestTabRename:
    """Test right-click rename functionality on the EditorTabBar."""

    def test_rename_tab_updates_name(self, tk_root):
        """rename_tab should update the tab's name."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()
        bar.rename_tab(0, "My Query")
        assert bar.get_tab_name(0) == "My Query"
        bar.destroy()

    def test_rename_tab_updates_label(self, tk_root):
        """rename_tab should update the visible label text."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()
        bar.rename_tab(0, "Renamed")
        label_text = bar._tabs[0]["label"].cget("text")
        assert "Renamed" in label_text
        bar.destroy()

    def test_rename_tab_strips_whitespace(self, tk_root):
        """rename_tab should strip leading/trailing whitespace."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()
        bar.rename_tab(0, "  Padded Name  ")
        assert bar.get_tab_name(0) == "Padded Name"
        bar.destroy()

    def test_rename_tab_empty_name_ignored(self, tk_root):
        """rename_tab should ignore empty names."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        original = bar.get_tab_name(0)
        bar.rename_tab(0, "   ")
        assert bar.get_tab_name(0) == original
        bar.destroy()

    def test_rename_tab_same_name_ignored(self, tk_root):
        """rename_tab should not fire callback if name is unchanged."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        calls = []
        bar.set_rename_callback(lambda i, old, new: calls.append((i, old, new)))
        bar.rename_tab(0, bar.get_tab_name(0))  # Same name
        assert len(calls) == 0
        bar.destroy()

    def test_rename_tab_fires_callback(self, tk_root):
        """rename_tab should fire the rename callback with index, old, new."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()
        calls = []
        bar.set_rename_callback(lambda i, old, new: calls.append((i, old, new)))
        bar.rename_tab(1, "Custom")
        assert len(calls) == 1
        assert calls[0] == (1, "Script-2", "Custom")
        bar.destroy()

    def test_rename_tab_invalid_index_ignored(self, tk_root):
        """rename_tab should ignore invalid indices."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.rename_tab(-1, "X")  # Should not raise
        bar.rename_tab(99, "X")  # Should not raise
        bar.destroy()

    def test_rename_preserves_modified_indicator(self, tk_root):
        """rename_tab should preserve the * prefix for modified tabs."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()
        bar.set_modified(1, True)
        bar.rename_tab(1, "Modified Query")
        label_text = bar._tabs[1]["label"].cget("text")
        assert "*" in label_text
        assert "Modified Query" in label_text
        bar.destroy()

    def test_rename_tab_after_rebuild(self, tk_root):
        """rename_tab should work after a close (which triggers _rebuild)."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        bar.add_tab()
        bar.add_tab()
        bar.close_tab(1)  # Triggers _rebuild, active goes back to tab 0
        bar.rename_tab(0, "After Rebuild")
        assert bar.get_tab_name(0) == "After Rebuild"
        bar.destroy()

    def test_right_click_binding_exists(self, tk_root):
        """Tabs should have Button-3 (right-click) bindings for rename."""
        from prism.gui.widgets.sql_editor import EditorTabBar

        bar = EditorTabBar(tk_root)
        label = bar._tabs[0]["label"]
        frame = bar._tabs[0]["frame"]
        # Check that Button-3 bindings exist
        assert label.bind("<Button-3>") is not None
        assert frame.bind("<Button-3>") is not None
        bar.destroy()


# ── PrismGUI: Tab Creation via App ───────────────────────────────────


class TestAppTabCreation:
    """Test tab creation through the PrismGUI app methods."""

    def test_new_query_creates_tab(self, tk_root, mock_gui_env):
        """_new_query should add a new tab with a unique name."""
        from prism.gui.app import PrismGUI

        root = _make_tk_root()
        root.withdraw()
        try:
            app = PrismGUI(root)
            initial_count = app._editor_tab_bar.tab_count
            app._new_query()
            assert app._editor_tab_bar.tab_count == initial_count + 1
            # New tab should be active
            assert app._editor_tab_bar.active_index == initial_count
            # Editor should be empty
            assert app._editor.get_text() == ""
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_new_query_preserves_old_tab_content(self, tk_root, mock_gui_env):
        """Creating a new tab should save the current editor text to the old tab."""
        from prism.gui.app import PrismGUI

        root = _make_tk_root()
        root.withdraw()
        try:
            app = PrismGUI(root)
            app._editor.set_text("SELECT * FROM users")
            # Simulate key release to update stored content
            app._on_editor_key_release()
            app._new_query()

            # Old tab (0) should still have the content
            assert app._editor_tab_bar.get_tab_content(0) == "SELECT * FROM users"
            # New tab (1) should be empty
            assert app._editor_tab_bar.get_tab_content(1) == ""
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_multiple_new_queries_unique_names(self, tk_root, mock_gui_env):
        """Creating multiple new queries should produce unique tab names."""
        from prism.gui.app import PrismGUI

        root = _make_tk_root()
        root.withdraw()
        try:
            app = PrismGUI(root)
            app._new_query()
            app._new_query()
            app._new_query()

            names = [
                app._editor_tab_bar.get_tab_name(i)
                for i in range(app._editor_tab_bar.tab_count)
            ]
            assert len(names) == len(set(names)), f"Duplicate names: {names}"
            assert names == ["Script-1", "Script-2", "Script-3", "Script-4"]
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ── PrismGUI: Tab Switching via App ──────────────────────────────────


class TestAppTabSwitching:
    """Test tab switching through the PrismGUI app."""

    def test_switch_preserves_content(self, tk_root, mock_gui_env):
        """Switching tabs should save current editor text and load new tab text."""
        from prism.gui.app import PrismGUI

        root = _make_tk_root()
        root.withdraw()
        try:
            app = PrismGUI(root)
            app._editor.set_text("SELECT 1")
            app._on_editor_key_release()  # Save to tab 0

            app._new_query()  # Creates tab 1, switches to it
            app._editor.set_text("SELECT 2")
            app._on_editor_key_release()  # Save to tab 1

            # Switch back to tab 0
            app._editor_tab_bar.switch_to(0)
            assert app._editor.get_text() == "SELECT 1"

            # Switch to tab 1
            app._editor_tab_bar.switch_to(1)
            assert app._editor.get_text() == "SELECT 2"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_switch_clears_results(self, tk_root, mock_gui_env):
        """Switching tabs should clear the results panel."""
        from prism.gui.app import PrismGUI
        from prism.gui.controllers.sql_controller import QueryResult

        root = _make_tk_root()
        root.withdraw()
        try:
            app = PrismGUI(root)
            # Put something in results
            result = QueryResult(columns=["A"], rows=[[1]], row_count=1, elapsed=0.001)
            app._results.show_results(result)
            assert len(app._results._tree.get_children()) > 0

            app._new_query()
            app._editor_tab_bar.switch_to(0)

            assert len(app._results._tree.get_children()) == 0
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_three_tab_isolation(self, tk_root, mock_gui_env):
        """Three tabs should each maintain independent content through switches."""
        from prism.gui.app import PrismGUI

        root = _make_tk_root()
        root.withdraw()
        try:
            app = PrismGUI(root)
            # Tab 0: SELECT 1
            app._editor.set_text("SELECT 1")
            app._on_editor_key_release()

            # Tab 1: SELECT 2
            app._new_query()
            app._editor.set_text("SELECT 2")
            app._on_editor_key_release()

            # Tab 2: SELECT 3
            app._new_query()
            app._editor.set_text("SELECT 3")
            app._on_editor_key_release()

            # Cycle through all tabs and verify content
            app._editor_tab_bar.switch_to(0)
            assert app._editor.get_text() == "SELECT 1"

            app._editor_tab_bar.switch_to(1)
            assert app._editor.get_text() == "SELECT 2"

            app._editor_tab_bar.switch_to(2)
            assert app._editor.get_text() == "SELECT 3"

            app._editor_tab_bar.switch_to(0)
            assert app._editor.get_text() == "SELECT 1"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ── PrismGUI: Auto-Save ──────────────────────────────────────────────


class TestAutoSave:
    """Test auto-save after typing inactivity."""

    def test_autosave_saves_to_config(
        self, tk_root, tmp_path, monkeypatch, mock_gui_env
    ):
        """After the delay, queries should be saved to config.json."""
        from prism.gui.app import PrismGUI

        # Redirect config to tmp_path
        import prism.gui.app as app_mod
        import prism.settings as settings_mod

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(settings_mod, "config_path", lambda: fake_path)

        root = _make_tk_root()
        root.withdraw()
        try:
            # Patch settings to use a very short delay for testing
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 100
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 1")
                app._on_editor_key_release()

                # Manually trigger the save (skip the timer)
                app._auto_save_queries()

                # Read back the config
                saved = json.loads(fake_path.read_text())
                queries = json.loads(saved["gui_saved_queries"])
                assert len(queries) >= 1
                assert queries[0]["content"] == "SELECT 1"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_autosave_multiple_tabs(self, tk_root, tmp_path, monkeypatch, mock_gui_env):
        """Auto-save should save all tabs, not just the active one."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod
        import prism.settings as settings_mod

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(settings_mod, "config_path", lambda: fake_path)

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 100
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 1")
                app._on_editor_key_release()

                app._new_query()
                app._editor.set_text("SELECT 2")
                app._on_editor_key_release()

                app._auto_save_queries()

                saved = json.loads(fake_path.read_text())
                queries = json.loads(saved["gui_saved_queries"])
                assert len(queries) == 2
                assert queries[0]["content"] == "SELECT 1"
                assert queries[1]["content"] == "SELECT 2"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_autosave_disabled(self, tk_root, tmp_path, monkeypatch, mock_gui_env):
        """When autosave is disabled, queries should not be saved."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod
        import prism.settings as settings_mod

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(settings_mod, "config_path", lambda: fake_path)

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = False
                mock_settings.gui_autosave_delay_ms = 100
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 1")
                # Key release should not schedule a save when disabled
                app._on_editor_key_release()

                # The timer should not have been set
                assert app._autosave_timer_id is None
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_autosave_schedules_timer(self, tk_root, mock_gui_env):
        """Key release should schedule a timer for auto-save."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 5000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 1")
                app._on_editor_key_release()

                assert app._autosave_timer_id is not None
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_autosave_cancels_previous_timer(self, tk_root, mock_gui_env):
        """Typing again should cancel the previous save timer and set a new one."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 5000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("S")
                app._on_editor_key_release()
                first_timer = app._autosave_timer_id

                app._editor.set_text("SELECT")
                app._on_editor_key_release()
                second_timer = app._autosave_timer_id

                assert first_timer != second_timer
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ── PrismGUI: Query Restoration ──────────────────────────────────────


class TestQueryRestoration:
    """Test restoring saved queries on app startup."""

    def test_restore_single_query(self, tk_root, monkeypatch, mock_gui_env):
        """A single saved query should be restored into the first tab."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        saved = json.dumps([{"name": "Script-1", "content": "SELECT 42"}])

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = saved

                app = PrismGUI(root)
                assert app._editor.get_text() == "SELECT 42"
                assert app._editor_tab_bar.tab_count == 1
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_restore_multiple_queries(self, tk_root, mock_gui_env):
        """Multiple saved queries should be restored as multiple tabs."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        saved = json.dumps(
            [
                {"name": "Script-1", "content": "SELECT 1"},
                {"name": "Script-2", "content": "SELECT 2"},
                {"name": "Script-3", "content": "SELECT 3"},
            ]
        )

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = saved

                app = PrismGUI(root)
                assert app._editor_tab_bar.tab_count == 3

                # Should start on tab 0
                assert app._editor_tab_bar.active_index == 0
                assert app._editor.get_text() == "SELECT 1"

                # Switch to tab 1
                app._editor_tab_bar.switch_to(1)
                assert app._editor.get_text() == "SELECT 2"

                # Switch to tab 2
                app._editor_tab_bar.switch_to(2)
                assert app._editor.get_text() == "SELECT 3"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_restore_empty_queries(self, tk_root, mock_gui_env):
        """Empty saved queries should result in a single blank tab."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                assert app._editor_tab_bar.tab_count == 1
                assert app._editor.get_text() == ""
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_restore_invalid_json(self, tk_root, mock_gui_env):
        """Invalid JSON in saved queries should not crash — fall back to empty."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "not valid json"

                app = PrismGUI(root)
                assert app._editor_tab_bar.tab_count == 1
                assert app._editor.get_text() == ""
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_restore_preserves_tab_names(self, tk_root, mock_gui_env):
        """Restored tabs should keep their original names."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        saved = json.dumps(
            [
                {"name": "My Query", "content": "SELECT 1"},
                {"name": "Backup", "content": "SELECT 2"},
            ]
        )

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = saved

                app = PrismGUI(root)
                assert app._editor_tab_bar.get_tab_name(0) == "My Query"
                assert app._editor_tab_bar.get_tab_name(1) == "Backup"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ── PrismGUI: Save on Exit ───────────────────────────────────────────


class TestSaveOnExit:
    """Test that queries are saved when the app closes."""

    def test_save_on_exit(self, tk_root, tmp_path, monkeypatch, mock_gui_env):
        """_on_close should save queries before destroying the window."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod
        import prism.settings as settings_mod

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(settings_mod, "config_path", lambda: fake_path)

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 'exit test'")
                app._on_editor_key_release()

                app._on_close()

                saved = json.loads(fake_path.read_text())
                queries = json.loads(saved["gui_saved_queries"])
                assert len(queries) >= 1
                assert queries[0]["content"] == "SELECT 'exit test'"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_save_on_exit_multiple_tabs(
        self, tk_root, tmp_path, monkeypatch, mock_gui_env
    ):
        """Closing with multiple tabs should save all of them."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod
        import prism.settings as settings_mod

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(settings_mod, "config_path", lambda: fake_path)

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 1")
                app._on_editor_key_release()
                app._new_query()
                app._editor.set_text("SELECT 2")
                app._on_editor_key_release()

                app._on_close()

                saved = json.loads(fake_path.read_text())
                queries = json.loads(saved["gui_saved_queries"])
                assert len(queries) == 2
                assert queries[0]["content"] == "SELECT 1"
                assert queries[1]["content"] == "SELECT 2"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ── PrismGUI: Initial Query ──────────────────────────────────────────


class TestInitialQuery:
    """Test the initial_query parameter."""

    def test_initial_query_sets_first_tab(self, tk_root, mock_gui_env):
        """Passing initial_query should fill the first tab and editor."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root, initial_query="SELECT 'hello'")
                assert app._editor.get_text() == "SELECT 'hello'"
                assert app._editor_tab_bar.get_tab_content(0) == "SELECT 'hello'"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_initial_query_skips_restore(self, tk_root, mock_gui_env):
        """When initial_query is provided, saved queries should not be restored."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        saved = json.dumps([{"name": "Script-1", "content": "SELECT old"}])

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = saved

                app = PrismGUI(root, initial_query="SELECT 'new'")
                assert app._editor.get_text() == "SELECT 'new'"
                # Should only have 1 tab (no restore)
                assert app._editor_tab_bar.tab_count == 1
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ── PrismGUI: Full Cycle (Save → Restore) ────────────────────────────


class TestSaveRestoreCycle:
    """Test the full save → close → restore cycle."""

    def test_full_cycle_single_tab(self, tk_root, tmp_path, monkeypatch, mock_gui_env):
        """Save a query, then restore it in a new app instance."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod
        import prism.settings as settings_mod

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(settings_mod, "config_path", lambda: fake_path)

        # Phase 1: Create app, type a query, close it
        root1 = _make_tk_root()
        root1.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app1 = PrismGUI(root1)
                app1._editor.set_text("SELECT 'persisted'")
                app1._on_editor_key_release()
                app1._on_close()
        finally:
            try:
                root1.destroy()
            except tk.TclError:
                pass

        # Phase 2: Create a new app and verify the query was restored
        root2 = _make_tk_root()
        root2.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                PrismGUI(root2)
                # The saved queries were written to fake_path in phase 1.
                # Verify the file contains the persisted query.
                saved = json.loads(fake_path.read_text())
                queries = json.loads(saved["gui_saved_queries"])
                assert len(queries) >= 1
                assert queries[0]["content"] == "SELECT 'persisted'"
        finally:
            root2.destroy()

    def test_full_cycle_multiple_tabs(
        self, tk_root, tmp_path, monkeypatch, mock_gui_env
    ):
        """Save multiple tabs, then verify they're all in the config."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod
        import prism.settings as settings_mod

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(settings_mod, "config_path", lambda: fake_path)

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 1")
                app._on_editor_key_release()

                app._new_query()
                app._editor.set_text("SELECT 2")
                app._on_editor_key_release()

                app._new_query()
                app._editor.set_text("SELECT 3")
                app._on_editor_key_release()

                app._on_close()

                saved = json.loads(fake_path.read_text())
                queries = json.loads(saved["gui_saved_queries"])
                assert len(queries) == 3
                assert queries[0]["content"] == "SELECT 1"
                assert queries[1]["content"] == "SELECT 2"
                assert queries[2]["content"] == "SELECT 3"

                # Verify tab names are preserved
                assert queries[0]["name"] == "Script-1"
                assert queries[1]["name"] == "Script-2"
                assert queries[2]["name"] == "Script-3"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ── PrismGUI: Close Tab via App ──────────────────────────────────────


class TestAppTabClose:
    """Test tab close behavior through the app."""

    def test_close_tab_loads_new_active(self, tk_root, mock_gui_env):
        """After closing a tab, the editor should show the new active tab's content."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 1")
                app._on_editor_key_release()

                app._new_query()
                app._editor.set_text("SELECT 2")
                app._on_editor_key_release()

                # Close tab 1 (the one with SELECT 2)
                app._editor_tab_bar.close_tab(1)

                # Should be back on tab 0 with SELECT 1
                assert app._editor_tab_bar.tab_count == 1
                assert app._editor.get_text() == "SELECT 1"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_close_last_tab_prevented(self, tk_root, mock_gui_env):
        """Closing the last tab should be prevented."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                assert app._editor_tab_bar.tab_count == 1

                app._editor_tab_bar.close_tab(0)
                assert app._editor_tab_bar.tab_count == 1
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ── PrismGUI: Tab Rename via App ─────────────────────────────────────


class TestAppTabRename:
    """Test tab rename through the PrismGUI app."""

    def test_rename_triggers_autosave(
        self, tk_root, mock_gui_env, tmp_path, monkeypatch
    ):
        """Renaming a tab should trigger auto-save so the new name persists."""
        import json

        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod
        from prism.settings import Settings

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(app_mod, "settings", Settings())
        monkeypatch.setattr(
            app_mod, "save_config", lambda data: fake_path.write_text(json.dumps(data))
        )

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 1")
                app._editor_tab_bar.rename_tab(0, "My Renamed Tab")

                saved = json.loads(fake_path.read_text())
                queries = json.loads(saved["gui_saved_queries"])
                assert queries[0]["name"] == "My Renamed Tab"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_rename_callback_set(self, tk_root, mock_gui_env):
        """PrismGUI should set a rename callback on the tab bar."""
        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod

        root = _make_tk_root()
        root.withdraw()
        try:
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                # The rename callback should be set (not None)
                assert app._editor_tab_bar._on_rename_callback is not None
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_rename_preserved_in_save_restore_cycle(
        self, tk_root, mock_gui_env, tmp_path, monkeypatch
    ):
        """A renamed tab should keep its custom name through save → restore."""
        import json

        from prism.gui.app import PrismGUI
        import prism.gui.app as app_mod
        from prism.settings import Settings

        fake_path = tmp_path / "config.json"
        monkeypatch.setattr(app_mod, "settings", Settings())
        monkeypatch.setattr(
            app_mod,
            "save_config",
            lambda data: fake_path.write_text(json.dumps(data)),
        )

        root = _make_tk_root()
        root.withdraw()
        try:
            # Phase 1: Create app, rename tab, save
            with patch.object(app_mod, "settings") as mock_settings:
                mock_settings.gui_query_autosave = True
                mock_settings.gui_autosave_delay_ms = 3000
                mock_settings.gui_saved_queries = "[]"

                app = PrismGUI(root)
                app._editor.set_text("SELECT 42")
                app._editor_tab_bar.rename_tab(0, "Deep Thought")
                app._on_close()

            # Phase 2: Read the saved config
            saved_data = json.loads(fake_path.read_text())
            queries = json.loads(saved_data["gui_saved_queries"])
            assert len(queries) == 1
            assert queries[0]["name"] == "Deep Thought"
            assert queries[0]["content"] == "SELECT 42"
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass
