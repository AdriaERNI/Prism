"""Prism GUI main window — ties together all widgets into the SQL editor.

Layout::

    ┌──────────────────────────────────────────────────┐
    │  Menu Bar                                         │
    ├────────┬─────────────────────────────────────────┤
    │        │  Toolbar: [▶ Execute] [■ Cancel] [Clear] │
    │  Tree  ├─────────────────────────────────────────┤
    │  Nav   │                                         │
    │        │         SQL Editor (dark)               │
    │        │                                         │
    │        ├─────────────────────────────────────────┤
    │        │         Results Table                    │
    ├────────┴─────────────────────────────────────────┤
    │  Status Bar                                       │
    └──────────────────────────────────────────────────┘
"""

from __future__ import annotations

import tkinter as tk
from tkinter import BOTH, LEFT, TOP, X, YES, Frame, Menu, messagebox, ttk

from prism import __version__
from prism.gui import theme
from prism.gui.controllers.sql_controller import QueryResult, SQLController
from prism.gui.widgets.database_tree import DatabaseTree
from prism.gui.widgets.results_table import ResultsTable
from prism.gui.widgets.sql_editor import SQLEditor
from prism.gui.widgets.status_bar import StatusBar
from prism.iris.sdk.http import base_url
from prism.settings import settings


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
        self._root.geometry("1200x750")
        self._root.minsize(800, 500)
        self._root.configure(bg=theme.BG)
        self._set_window_icon()

    def _set_window_icon(self) -> None:
        """Set the Prism logo as the window icon."""
        from pathlib import Path

        # Try logo.ico (Windows) and logo PNG (Linux/macOS)
        # Look in the package directory and common locations
        candidates = [
            Path(__file__).parent.parent.parent / "logo.ico",
            Path(__file__).parent.parent.parent / "docs" / "assets" / "logo-256.png",
            Path(__file__).parent.parent / "logo.ico",
        ]

        for icon_path in candidates:
            if not icon_path.exists():
                continue
            try:
                if icon_path.suffix == ".ico":
                    self._root.iconbitmap(str(icon_path))
                else:
                    # Convert PNG to PhotoImage for icon
                    icon_img = tk.PhotoImage(file=str(icon_path))
                    self._root.iconphoto(True, icon_img)
                    # Keep a reference to prevent GC
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

        # ── Right: Toolbar + Editor + Results ────────────────────────
        right_frame = Frame(self._paned, background=theme.BG)
        self._paned.add(right_frame, weight=1)

        # Toolbar
        toolbar = Frame(right_frame, background=theme.HEADER_BG, height=36)
        toolbar.pack(fill=X, side=TOP)
        toolbar.pack_propagate(False)

        # Separator below toolbar
        Frame(right_frame, background=theme.BORDER, height=1).pack(fill=X, side=TOP)

        # Execute button
        self._btn_execute = ttk.Button(
            toolbar,
            text="▶ Execute",
            style="Accent.TButton",
            command=self._execute_query,
        )
        self._btn_execute.pack(side=LEFT, padx=(8, 4), pady=4)

        # Cancel button
        self._btn_cancel = ttk.Button(
            toolbar,
            text="■ Cancel",
            state="disabled",
            command=self._cancel_query,
        )
        self._btn_cancel.pack(side=LEFT, padx=4, pady=4)

        # Clear button
        self._btn_clear = ttk.Button(
            toolbar,
            text="Clear",
            command=self._clear_results,
        )
        self._btn_clear.pack(side=LEFT, padx=4, pady=4)

        # Spacer
        spacer = Frame(toolbar, background=theme.HEADER_BG)
        spacer.pack(side=LEFT, fill=X, expand=YES)

        # Namespace selector
        tk.Label(
            toolbar,
            text="Namespace:",
            background=theme.HEADER_BG,
            foreground=theme.FG,
            font=theme.ui_font_sm(),
        ).pack(side=LEFT, padx=(4, 2), pady=4)
        self._ns_var = tk.StringVar(value=settings.iris_namespace or "USER")
        self._ns_entry = ttk.Entry(toolbar, textvariable=self._ns_var, width=12)
        self._ns_entry.pack(side=LEFT, padx=(0, 8), pady=4)

        # ── Tab bar above editor ───────────────────────────────────────
        tab_bar = Frame(right_frame, background=theme.TAB_BAR_BG, height=26)
        tab_bar.pack(fill=X, side=TOP)
        tab_bar.pack_propagate(False)

        # Active tab
        tab_frame = Frame(tab_bar, background=theme.BG, height=26)
        tab_frame.pack(side=LEFT, padx=(4, 0), pady=0)
        tk.Label(
            tab_frame,
            text=" Query 1 ",
            background=theme.BG,
            foreground=theme.FG,
            font=theme.ui_font_sm(),
            padx=8,
        ).pack(side=LEFT, padx=0)
        # Close button on tab
        tk.Label(
            tab_frame,
            text="✕",
            background=theme.BG,
            foreground=theme.FG_DIM,
            font=theme.ui_font_sm(),
            padx=4,
        ).pack(side=LEFT, padx=(0, 2))

        # ── Vertical paned: Editor (top) | Results (bottom) ──────────
        vpaned = ttk.Panedwindow(right_frame, orient="vertical")
        vpaned.pack(fill=BOTH, expand=YES)

        # SQL Editor
        self._editor = SQLEditor(vpaned)
        self._editor.set_execute_callback(self._execute_query)
        vpaned.add(self._editor, weight=3)

        # Results table
        self._results = ResultsTable(vpaned)
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
        """Check if IRIS is reachable and update status bar."""
        import httpx

        try:
            url = base_url()
            r = httpx.get(f"{url}/csp/sys/UtilHome.csp", timeout=3.0)
            connected = r.status_code in (200, 302, 401)
        except Exception:
            connected = False

        ns = self._ns_var.get() or "USER" if connected else None
        self._status_bar.set_connected(connected, namespace=ns)

    # ── Query Execution ──────────────────────────────────────────────

    def _execute_query(self) -> None:
        """Execute the current SQL query."""
        query = self._editor.get_selection_or_all()
        if not query.strip():
            self._status_bar.set_status("Error: query is empty", is_error=True)
            return

        # Disable execute, enable cancel
        self._btn_execute.config(state="disabled")
        self._btn_cancel.config(state="normal")
        self._status_bar.set_running(True)
        self._results.show_message("Executing query...")

        namespace = self._ns_var.get().strip() or None
        self._controller.execute(
            query,
            namespace=namespace,
            on_done=self._on_query_done,
        )

    def _execute_selection(self) -> None:
        """Execute only the selected text, or all if no selection."""
        self._execute_query()

    def _cancel_query(self) -> None:
        """Cancel is not yet supported (would need async cancellation)."""
        self._status_bar.set_status("Cancel not yet implemented", is_error=True)

    def _on_query_done(self, result: QueryResult) -> None:
        """Handle query completion (called on Tk main thread)."""
        self._btn_execute.config(state="normal")
        self._btn_cancel.config(state="disabled")
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

    def _new_query(self) -> None:
        """Clear the editor for a new query."""
        self._editor.clear()
        self._results.clear()
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
