"""Results table widget — ``ttk.Treeview`` with zebra striping and status.

Displays query results in a scrollable grid with:
- Auto-generated columns from the query result
- Alternating row colours (zebra striping)
- Horizontal + vertical scrollbars
- Sorting by clicking column headers
- Row count and execution time below the table
"""

from __future__ import annotations

from tkinter import BOTH, END, LEFT, RIGHT, X, Y, YES, Frame, Label, Scrollbar, ttk

from prism.gui import theme
from prism.gui.controllers.sql_controller import QueryResult


class ResultsTable(Frame):
    """A results grid with zebra striping and sortable columns."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=theme.RESULT_BG)
        self._columns: list[str] = []
        self._sort_reverse: bool = False
        self._setup_widgets()

    def _setup_widgets(self) -> None:
        """Create Treeview + scrollbars + status label."""
        # Container for tree + scrollbars
        tree_frame = Frame(self, background=theme.RESULT_BG)
        tree_frame.pack(fill=BOTH, expand=YES)

        # Vertical scrollbar
        vsb = Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=RIGHT, fill=Y)

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

        # Status label (row count + elapsed)
        self._status = Label(
            self,
            text="Ready",
            background=theme.PANEL_BG,
            foreground=theme.FG_STATUS,
            font=theme.ui_font_sm(),
            anchor="w",
            padx=8,
            pady=3,
        )
        self._status.pack(side="bottom", fill=X)

        # Configure zebra striping tags
        self._tree.tag_configure("even", background=theme.RESULT_BG)
        self._tree.tag_configure("odd", background=theme.RESULT_ALT)
        self._tree.tag_configure(
            "error", background=theme.RESULT_BG, foreground=theme.FG_ERROR
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

        # Set up columns
        self._columns = result.columns
        self._tree["columns"] = self._columns
        for col in self._columns:
            self._tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=120, minwidth=60, stretch=False)

        # Insert rows with zebra striping
        for i, row in enumerate(result.rows):
            tag = "even" if i % 2 == 0 else "odd"
            values = [self._format_cell(v) for v in row]
            self._tree.insert("", END, values=values, tags=(tag,))

        # Update status
        elapsed_ms = int(result.elapsed * 1000)
        self._status.config(
            text=f"{result.row_count} row(s) fetched  |  {elapsed_ms} ms",
            foreground=theme.FG_STATUS,
        )

    def clear(self) -> None:
        """Remove all rows and columns."""
        # Remove existing items
        for item in self._tree.get_children():
            self._tree.delete(item)

        # Reset columns
        if self._columns:
            self._tree["columns"] = []
            self._columns = []

        self._status.config(text="Ready", foreground=theme.FG_STATUS)

    def show_message(self, message: str, is_error: bool = False) -> None:
        """Show a status message without a data grid."""
        self.clear()
        color = theme.FG_ERROR if is_error else theme.FG_STATUS
        self._status.config(text=message, foreground=color)

    # ── Internal ─────────────────────────────────────────────────────

    def _sort_by(self, column: str) -> None:
        """Sort tree contents by *column* (toggle ascending/descending)."""
        items = list(self._tree.get_children(""))
        if not items:
            return

        # Get values for the sort key
        data = [(self._tree.set(item, column), item) for item in items]

        # Try numeric sort first, fall back to string
        try:
            data.sort(key=lambda x: float(x[0]), reverse=self._sort_reverse)
        except ValueError:
            data.sort(key=lambda x: x[0].lower(), reverse=self._sort_reverse)

        for i, (_, item) in enumerate(data):
            self._tree.move(item, "", i)

        self._sort_reverse = not self._sort_reverse

        # Update heading to show sort arrow
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
