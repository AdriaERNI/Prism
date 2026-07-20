"""Prism GUI main window — DBeaver-inspired SQL editor layout.

Layout::

    ┌────────────────────────────────────────────────────────┐
    │  Menu Bar                                               │
    ├────────┬─────────────────────────────────────────────────┤
    │        │  Toolbar: [New][Open][Save] | [🔌][⏏][🔄] |     │
    │        │    [SQL][▶ Execute][■ Cancel][Clear] | [NS:USER] │
    │  Tree  ├─────────────────────────────────────────────────┤
    │  Nav   │  Tab Bar: [Script-1 ✕]                          │
    │        ├─────────────────────────────────────────────────┤
    │  +     │                                                 │
    │  Search│         SQL Editor (dark, line numbers)          │
    │  bar   │                                                 │
    │        ├─────────────────────────────────────────────────┤
    │        │  [Result 1 ✕] [🔄][💾][✕] | [Grid]               │
    │        ├─────────────────────────────────────────────────┤
    │        │         Results Table (zebra striped)             │
    ├────────┴─────────────────────────────────────────────────┤
    │  Status Bar: ● Connected | NS:USER | 37 rows | CET      │
    └────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import tkinter as tk
from tkinter import BOTH, TOP, X, YES, Frame, Menu, messagebox, ttk

from prism import __version__
from prism.gui import theme
from prism.gui.controllers.sql_controller import QueryResult, SQLController
from prism.gui.widgets.database_tree import DatabaseTree
from prism.gui.widgets.results_table import ResultsTable
from prism.gui.widgets.sql_editor import EditorTabBar, SQLEditor
from prism.gui.widgets.status_bar import StatusBar
from prism.gui.widgets.toolbar import Toolbar


class PrismGUI:
    """Main application window for the Prism SQL editor."""

    def __init__(self, root: tk.Tk, initial_query: str | None = None) -> None:
        self._root = root
        self._controller = SQLController(root)
        self._controller.start_polling()

        self._setup_window()
        self._setup_menu()
        self._setup_layout()
        self._bind_shortcuts()

        if initial_query:
            self._editor.set_text(initial_query)

        self._check_connection()
        self._db_tree.load_async()

    # ── Setup ────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        """Configure the main window."""
        self._root.title(f"Prism {__version__} — SQL Editor")
        self._root.geometry("1280x800")
        self._root.minsize(900, 550)
        self._root.configure(bg=theme.BG)
        self._set_window_icon()

    def _set_window_icon(self) -> None:
        """Set the Prism logo as the window icon.

        Looks for logo.ico / logo-256.png relative to the package root
        (src/prism/gui/app.py → 4 levels up = project root).
        """
        from pathlib import Path

        # src/prism/gui/app.py → parent ×4 = project root
        pkg_root = Path(__file__).resolve().parent.parent.parent.parent

        candidates = [
            pkg_root / "logo.ico",
            pkg_root / "docs" / "assets" / "logo-256.png",
            pkg_root / "logo-256.png",
            # Fallback: relative to src/ for installed packages
            Path(__file__).resolve().parent.parent.parent / "logo.ico",
        ]

        for icon_path in candidates:
            if not icon_path.exists():
                continue
            try:
                if icon_path.suffix == ".ico":
                    self._root.iconbitmap(str(icon_path))
                else:
                    icon_img = tk.PhotoImage(file=str(icon_path))
                    self._root.iconphoto(True, icon_img)
                    self._icon_image = icon_img
                break
            except (tk.TclError, FileNotFoundError):
                continue

    def _setup_menu(self) -> None:
        """Create the menu bar."""
        menubar = Menu(
            self._root,
            tearoff=0,
            bg=theme.HEADER_BG,
            fg=theme.FG,
            activebackground=theme.SELECTED_BG,
            activeforeground=theme.FG_HEADER,
            borderwidth=0,
        )

        # File menu
        file_menu = Menu(
            menubar,
            tearoff=0,
            bg=theme.HEADER_BG,
            fg=theme.FG,
            activebackground=theme.SELECTED_BG,
            activeforeground=theme.FG_HEADER,
            borderwidth=0,
        )
        file_menu.add_command(label="New Query\tCtrl+N", command=self._new_query)
        file_menu.add_command(label="Open File...\tCtrl+O", command=self._open_file)
        file_menu.add_command(label="Save File...\tCtrl+S", command=self._save_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit\tCtrl+Q", command=self._root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit menu
        edit_menu = Menu(
            menubar,
            tearoff=0,
            bg=theme.HEADER_BG,
            fg=theme.FG,
            activebackground=theme.SELECTED_BG,
            activeforeground=theme.FG_HEADER,
            borderwidth=0,
        )
        edit_menu.add_command(label="Undo\tCtrl+Z", command=self._undo)
        edit_menu.add_command(label="Redo\tCtrl+Y", command=self._redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut\tCtrl+X", command=self._cut)
        edit_menu.add_command(label="Copy\tCtrl+C", command=self._copy)
        edit_menu.add_command(label="Paste\tCtrl+V", command=self._paste)
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All\tCtrl+A", command=self._select_all)
        edit_menu.add_command(label="Clear", command=self._clear_editor)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # Query menu
        query_menu = Menu(
            menubar,
            tearoff=0,
            bg=theme.HEADER_BG,
            fg=theme.FG,
            activebackground=theme.SELECTED_BG,
            activeforeground=theme.FG_HEADER,
            borderwidth=0,
        )
        query_menu.add_command(label="Execute\tCtrl+Enter", command=self._execute_query)
        query_menu.add_command(
            label="Execute Selection", command=self._execute_selection
        )
        query_menu.add_command(label="Clear Results", command=self._clear_results)
        menubar.add_cascade(label="Query", menu=query_menu)

        # Help menu
        help_menu = Menu(
            menubar,
            tearoff=0,
            bg=theme.HEADER_BG,
            fg=theme.FG,
            activebackground=theme.SELECTED_BG,
            activeforeground=theme.FG_HEADER,
            borderwidth=0,
        )
        help_menu.add_command(label="About Prism", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self._root.config(menu=menubar)

    def _setup_layout(self) -> None:
        """Create the main layout: sidebar | (toolbar + editor + results) + status bar."""
        # Main horizontal paned window: sidebar | main area
        self._paned = ttk.Panedwindow(self._root, orient="horizontal")
        self._paned.pack(fill=BOTH, expand=YES)

        # ── Left: Database Navigator ─────────────────────────────────
        self._db_tree = DatabaseTree(self._paned)
        self._db_tree.set_insert_callback(self._insert_table_name)
        self._paned.add(self._db_tree, weight=0)

        # ── Right: Toolbar + Tab bar + Editor + Results ───────────────
        right_frame = Frame(self._paned, background=theme.BG)
        self._paned.add(right_frame, weight=1)

        # Toolbar
        self._toolbar = Toolbar(right_frame)
        self._toolbar.pack(fill=X, side=TOP)
        self._toolbar.set_callbacks(
            on_new=self._new_query,
            on_open=self._open_file,
            on_save=self._save_file,
            on_connect=self._check_connection,
            on_refresh=self._refresh_tree,
            on_new_sql=self._new_query,
            on_execute=self._execute_query,
            on_cancel=self._cancel_query,
            on_clear=self._clear_results,
        )

        # Separator below toolbar
        Frame(right_frame, background=theme.BORDER_DIM, height=1).pack(fill=X, side=TOP)

        # ── Editor tab bar ────────────────────────────────────────────
        self._editor_tab_bar = EditorTabBar(right_frame)
        self._editor_tab_bar.pack(fill=X, side=TOP)

        # Separator below tab bar
        Frame(right_frame, background=theme.BORDER_DIM, height=1).pack(fill=X, side=TOP)

        # ── Vertical paned: Editor (top) | Results (bottom) ──────────
        vpaned = ttk.Panedwindow(right_frame, orient="vertical")
        vpaned.pack(fill=BOTH, expand=YES)

        # SQL Editor
        self._editor = SQLEditor(vpaned)
        self._editor.set_execute_callback(self._execute_query)
        vpaned.add(self._editor, weight=3)

        # Results table — connect controller for UPDATE execution
        self._results = ResultsTable(vpaned)
        self._results.set_controller(self._controller)
        self._results.set_status_callback(self._on_results_status)
        vpaned.add(self._results, weight=2)

        # ── Status bar ────────────────────────────────────────────────
        self._status_bar = StatusBar(self._root)
        self._status_bar.pack(fill=X, side="bottom")

        # Give focus to editor
        self._editor.set_focus()

    def _bind_shortcuts(self) -> None:
        """Bind global keyboard shortcuts."""
        self._root.bind("<Control-Return>", lambda e: self._execute_query())
        self._root.bind("<Control-n>", lambda e: self._new_query())
        self._root.bind("<Control-s>", lambda e: self._save_file())
        self._root.bind("<Control-q>", lambda e: self._root.quit())

    # ── Connection ────────────────────────────────────────────────────

    def _check_connection(self) -> None:
        """Check if IRIS is reachable and update status bar (async, non-blocking)."""
        self._status_bar.set_status("Connecting...")
        self._controller.check_connection(on_done=self._on_connection_checked)

    def _on_connection_checked(self, connected: bool) -> None:
        """Handle connection check result (called on Tk main thread)."""
        ns_var = self._toolbar.namespace_var
        ns = None
        if connected:
            ns = (ns_var.get().strip() if ns_var else "USER") or "USER"
        self._status_bar.set_connected(connected, namespace=ns)
        if not connected:
            self._status_bar.set_status(
                "Cannot connect to IRIS — check settings", is_error=True
            )

    def _refresh_tree(self) -> None:
        """Refresh the database tree."""
        self._db_tree.load_async()

    # ── Query Execution ──────────────────────────────────────────────

    def _execute_query(self) -> None:
        """Execute the current SQL query."""
        if self._controller.is_running:
            self._status_bar.set_status(
                "Query already running — press Cancel to abort", is_error=True
            )
            return

        query = self._editor.get_selection_or_all()
        if not query.strip():
            self._status_bar.set_status("Error: query is empty", is_error=True)
            return

        self._last_query = query  # store for Refresh button

        self._toolbar.set_running(True)
        self._status_bar.set_running(True)
        self._results.show_message("Executing query...")

        ns_var = self._toolbar.namespace_var
        namespace = (ns_var.get().strip() if ns_var else "USER") or None

        # Detect source table from FROM clause so results can be edited
        self._detect_source_table(query)

        self._controller.execute(
            query,
            namespace=namespace,
            on_done=self._on_query_done,
        )

    def _detect_source_table(self, query: str) -> None:
        """Parse the FROM clause to detect schema.table for UPDATE generation.

        Handles patterns like:
            SELECT * FROM schema.table
            SELECT ... FROM schema.table WHERE ...

        Excludes system schemas (INFORMATION_SCHEMA, %*) so that
        metadata queries don't enable the Save button.

        Sets the source table on the results panel.
        """
        import re

        # Match: FROM schema.table (with optional alias)
        match = re.search(
            r"\bFROM\s+(\w+)\.(\w+)",
            query,
            re.IGNORECASE,
        )
        if match:
            schema, table = match.group(1), match.group(2)
            # Exclude system schemas — can't/shouldn't UPDATE them
            schema_upper = schema.upper()
            if schema.startswith("%") or schema_upper == "INFORMATION_SCHEMA":
                self._results.clear_source_table()
                return
            self._results.set_source_table(schema, table)
        else:
            self._results.clear_source_table()

    def _execute_selection(self) -> None:
        """Execute only the selected text, or all if no selection."""
        self._execute_query()

    def _cancel_query(self) -> None:
        """Cancel the currently running query."""
        if self._controller.cancel():
            self._status_bar.set_status("Cancelling query...")
        else:
            self._status_bar.set_status("No query running to cancel")

    def _on_query_done(self, result: QueryResult) -> None:
        """Handle query completion (called on Tk main thread)."""
        self._toolbar.set_running(False)
        self._status_bar.set_running(False)

        if result.is_error:
            self._results.show_results(result)
            self._status_bar.set_status(f"Error: {result.error}", is_error=True)
        else:
            self._results.show_results(result)
            elapsed_ms = int(result.elapsed * 1000)
            self._status_bar.set_status(
                f"OK — {result.row_count} row(s) in {elapsed_ms} ms"
            )

    # ── Editor Actions ───────────────────────────────────────────────

    def _insert_table_name(self, name: str) -> None:
        """Insert a table name from the database tree."""
        self._editor.insert_at_cursor(name)

    def _on_results_status(self, action: str) -> None:
        """Handle status callbacks from the results table."""
        if action == "refresh":
            # Re-run the last executed query
            if hasattr(self, "_last_query") and self._last_query:
                self._editor.set_text(self._last_query)
                self._execute_query()

    def _new_query(self) -> None:
        """Clear the editor for a new query."""
        self._editor.clear()
        self._results.clear()
        self._editor_tab_bar.add_tab(f"Script-{len(self._editor_tab_bar._tabs) + 1}")
        self._editor.set_focus()

    def _clear_results(self) -> None:
        """Clear the results panel."""
        self._results.clear()

    def _clear_editor(self) -> None:
        """Clear the editor."""
        self._editor.clear()

    def _open_file(self) -> None:
        """Open a .sql file into the editor."""
        from tkinter import filedialog

        filepath = filedialog.askopenfilename(
            title="Open SQL File",
            filetypes=[("SQL files", "*.sql"), ("All files", "*.*")],
        )
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self._editor.set_text(content)
                self._root.title(f"Prism {__version__} — {filepath}")
            except Exception as exc:
                messagebox.showerror("Error", f"Cannot open file:\n{exc}")

    def _save_file(self) -> None:
        """Save the editor content to a .sql file."""
        from tkinter import filedialog

        filepath = filedialog.asksaveasfilename(
            title="Save SQL File",
            defaultextension=".sql",
            filetypes=[("SQL files", "*.sql"), ("All files", "*.*")],
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(self._editor.get_text())
                self._root.title(f"Prism {__version__} — {filepath}")
                self._status_bar.set_status(f"Saved to {filepath}")
            except Exception as exc:
                messagebox.showerror("Error", f"Cannot save file:\n{exc}")

    # ── Edit Menu Actions ────────────────────────────────────────────

    def _undo(self) -> None:
        self._editor._text.event_generate("<<Undo>>")

    def _redo(self) -> None:
        self._editor._text.event_generate("<<Redo>>")

    def _cut(self) -> None:
        self._editor._text.event_generate("<<Cut>>")

    def _copy(self) -> None:
        self._editor._text.event_generate("<<Copy>>")

    def _paste(self) -> None:
        self._editor._text.event_generate("<<Paste>>")

    def _select_all(self) -> None:
        self._editor._text.tag_add("sel", "1.0", "end-1c")

    # ── Help ─────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        """Show the About dialog."""
        messagebox.showinfo(
            "About Prism",
            f"Prism {__version__}\n\n"
            "InterSystems IRIS CLI and MCP Server\n"
            "with tkinter SQL Editor GUI\n\n"
            "© Adria Sanchez",
        )


def launch(initial_query: str | None = None) -> None:
    """Create the root window and start the GUI.

    Args:
        initial_query: Optional SQL to pre-fill the editor.
    """
    root = tk.Tk()
    theme.apply_theme(root)
    PrismGUI(root, initial_query=initial_query)
    root.mainloop()
