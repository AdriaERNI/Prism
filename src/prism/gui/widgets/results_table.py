"""Results table widget — DBeaver-style results panel with tabs and toolbar.

Features:
- Tab bar (Result 1, Result 2, etc.) with close buttons
- Toolbar with Refresh, Save, Cancel, Export buttons
- ``ttk.Treeview`` with zebra striping
- Sortable columns (click header)
- Status line with row count + execution time
"""

from __future__ import annotations

from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    YES,
    Frame,
    Label,
    Scrollbar,
    ttk,
)

from prism.gui import theme
from prism.gui.controllers.sql_controller import QueryResult


class ResultsTable(Frame):
    """A results grid with tab bar, toolbar, zebra striping and sortable columns."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=theme.RESULT_BG)
        self._columns: list[str] = []
        self._sort_reverse: bool = False
        self._result_tab_count = 0
        self._setup_widgets()

    def _setup_widgets(self) -> None:
        """Create tab bar + toolbar + treeview + scrollbars + status."""
        # ── Tab bar (Result 1, ...) ───────────────────────────────────
        tab_bar = Frame(self, background=theme.TAB_BAR_BG, height=26)
        tab_bar.pack(side="top", fill=X)
        tab_bar.pack_propagate(False)

        self._tab_bar = tab_bar
        self._result_tabs: list[dict] = []
        self._add_result_tab()

        # ── Results toolbar ───────────────────────────────────────────
        toolbar = Frame(self, background=theme.HEADER_BG, height=28)
        toolbar.pack(side="top", fill=X)
        toolbar.pack_propagate(False)

        self._btn_refresh = ttk.Button(
            toolbar, text="🔄", style="Icon.TButton", command=self._on_refresh
        )
        self._btn_refresh.pack(side=LEFT, padx=2, pady=2)

        self._btn_save = ttk.Button(
            toolbar, text="💾", style="Icon.TButton", command=self._on_save
        )
        self._btn_save.pack(side=LEFT, padx=2, pady=2)

        self._btn_cancel = ttk.Button(
            toolbar, text="✕", style="Icon.TButton", command=self._on_cancel
        )
        self._btn_cancel.pack(side=LEFT, padx=2, pady=2)

        # Separator
        Frame(toolbar, background=theme.BORDER_DIM, width=1).pack(
            side=LEFT, fill="y", padx=4, pady=4
        )

        self._btn_filter = ttk.Button(
            toolbar, text="🔍 Filter", style="Icon.TButton", command=self._on_filter
        )
        self._btn_filter.pack(side=LEFT, padx=2, pady=2)

        self._btn_export = ttk.Button(
            toolbar, text="📥 Export", style="Icon.TButton", command=self._on_export
        )
        self._btn_export.pack(side=LEFT, padx=2, pady=2)

        # Spacer
        Frame(toolbar, background=theme.HEADER_BG).pack(side=LEFT, fill=X, expand=True)

        # Grid/Chart/Text view buttons
        self._btn_grid = ttk.Button(
            toolbar, text="Grid", style="Icon.TButton", command=self._on_grid_view
        )
        self._btn_grid.pack(side=LEFT, padx=2, pady=2)

        # ── Container for tree + scrollbars ────────────────────────────
        tree_frame = Frame(self, background=theme.RESULT_BG)
        tree_frame.pack(fill=BOTH, expand=YES)

        # Vertical scrollbar
        vsb = Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=RIGHT, fill="y")

        # Horizontal scrollbar
        hsb = Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side="bottom", fill=X)

        # Treeview
        self._tree = ttk.Treeview(
            tree_frame,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="browse",
        )
        self._tree.pack(side=LEFT, fill=BOTH, expand=YES)
        vsb.config(command=self._tree.yview)
        hsb.config(command=self._tree.xview)

        # Configure zebra striping tags
        self._tree.tag_configure("odd", background=theme.RESULT_BG)
        self._tree.tag_configure("even", background=theme.RESULT_ALT)

        # ── Status label (row count + elapsed) ────────────────────────
        self._status = Label(
            self,
            text="Ready",
            background=theme.STATUS_BG,
            foreground=theme.FG_STATUS,
            font=theme.ui_font_sm(),
            anchor="w",
            padx=8,
            pady=2,
        )
        self._status.pack(side="bottom", fill=X)

    def _add_result_tab(self) -> None:
        """Add a new result tab."""
        self._result_tab_count += 1
        tab_name = f"Result {self._result_tab_count}"

        tab_frame = Frame(self._tab_bar, background=theme.BG, height=26)
        tab_frame.pack(side=LEFT, padx=(1, 0))

        Label(
            tab_frame,
            text=f" {tab_name} ",
            background=theme.BG,
            foreground=theme.FG_HEADER,
            font=theme.ui_font_sm(),
            padx=6,
        ).pack(side=LEFT)

        close_label = Label(
            tab_frame,
            text="✕",
            background=theme.BG,
            foreground=theme.FG_DIM,
            font=theme.ui_font_sm(),
            padx=4,
        )
        close_label.pack(side=LEFT, padx=(0, 2))

        self._result_tabs.append(
            {
                "frame": tab_frame,
                "name": tab_name,
            }
        )

    # ── Public API ───────────────────────────────────────────────────

    def show_results(self, result: QueryResult) -> None:
        """Populate the table from a ``QueryResult``."""
        self.clear()

        if result.is_error:
            self._status.config(
                text=f"Error: {result.error}",
                foreground=theme.FG_ERROR,
            )
            return

        if not result.columns:
            self._status.config(
                text="Query executed successfully (no rows returned)",
                foreground=theme.FG_STATUS,
            )
            return

        self._columns = result.columns
        self._tree["columns"] = self._columns
        for col in self._columns:
            self._tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=120, minwidth=60, stretch=False)

        for i, row in enumerate(result.rows):
            tag = "even" if i % 2 == 0 else "odd"
            values = [self._format_cell(v) for v in row]
            self._tree.insert("", END, values=values, tags=(tag,))

        elapsed_ms = int(result.elapsed * 1000)
        self._status.config(
            text=f"{result.row_count} row(s) fetched  |  {elapsed_ms} ms",
            foreground=theme.FG_STATUS,
        )

    def clear(self) -> None:
        """Remove all rows and columns."""
        for item in self._tree.get_children():
            self._tree.delete(item)
        if self._columns:
            self._tree["columns"] = []
            self._columns = []
        self._status.config(text="Ready", foreground=theme.FG_STATUS)

    def show_message(self, message: str, is_error: bool = False) -> None:
        """Show a status message without a data grid."""
        self.clear()
        color = theme.FG_ERROR if is_error else theme.FG_STATUS
        self._status.config(text=message, foreground=color)

    # ── Toolbar button handlers (stubs — app.py can override) ──────────

    def _on_refresh(self):
        pass

    def _on_save(self):
        pass

    def _on_cancel(self):
        pass

    def _on_filter(self):
        pass

    def _on_export(self):
        pass

    def _on_grid_view(self):
        pass

    # ── Internal ─────────────────────────────────────────────────────

    def _sort_by(self, column: str) -> None:
        """Sort tree contents by *column* (toggle ascending/descending)."""
        items = list(self._tree.get_children(""))
        if not items:
            return

        data = [(self._tree.set(item, column), item) for item in items]
        try:
            data.sort(key=lambda x: float(x[0]), reverse=self._sort_reverse)
        except ValueError:
            data.sort(key=lambda x: x[0].lower(), reverse=self._sort_reverse)

        for i, (_, item) in enumerate(data):
            self._tree.move(item, "", i)

        self._sort_reverse = not self._sort_reverse

        for col in self._columns:
            text = col
            if col == column:
                text = f"{col} {'▼' if self._sort_reverse else '▲'}"
            self._tree.heading(col, text=text, command=lambda c=col: self._sort_by(c))

    @staticmethod
    def _format_cell(value) -> str:
        """Format a cell value for display."""
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (list, dict)):
            import json

            return json.dumps(value)
        return str(value)
