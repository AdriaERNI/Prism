"""Results table widget — DBeaver-style results panel with editing + commit.

Features:
- Tab bar (Result 1, Result 2, etc.) with close buttons
- Toolbar with Refresh, Save, Cancel, Export buttons
- ``ttk.Treeview`` with zebra striping
- Sortable columns (click header)
- **Editable cells**: double-click a cell to edit via Entry overlay
- **Modification tracking**: changed cells highlighted, Save generates UPDATE
- **Commit / Rollback**: Save → IRIS UPDATE, Cancel → revert changes
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
from typing import Callable

from prism.gui import theme
from prism.gui.controllers.sql_controller import QueryResult, SQLController


class ResultsTable(Frame):
    """An editable results grid with tab bar, toolbar, and commit support."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=theme.RESULT_BG)
        self._columns: list[str] = []
        self._rows: list[list] = []  # original data (unmodified)
        self._sort_reverse: bool = False
        self._result_tab_count = 0
        # Editing state
        self._modified_cells: dict[
            str, dict[str, str]
        ] = {}  # {item_id: {col: new_value}}
        self._source_table: str | None = None  # e.g. "Ens.AlarmRequest"
        self._controller: SQLController | None = None  # for executing UPDATEs
        self._on_status: Callable | None = None  # status callback to app
        self._setup_widgets()

    def set_controller(self, controller: SQLController) -> None:
        """Set the SQL controller for executing UPDATE statements."""
        self._controller = controller

    def set_status_callback(self, callback: Callable) -> None:
        """Set a callback to report status messages to the main app."""
        self._on_status = callback

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
            toolbar, text="💾 Save", style="Icon.TButton", command=self._on_save
        )
        self._btn_save.pack(side=LEFT, padx=2, pady=2)

        self._btn_cancel = ttk.Button(
            toolbar, text="↩ Revert", style="Icon.TButton", command=self._on_cancel
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

        # Treeview — with grid lines and better styling
        self._tree = ttk.Treeview(
            tree_frame,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="browse",
            style="Treeview",
        )
        self._tree.pack(side=LEFT, fill=BOTH, expand=YES)
        vsb.config(command=self._tree.yview)
        hsb.config(command=self._tree.xview)

        # Configure zebra striping tags + modified cell highlight
        self._tree.tag_configure("odd", background=theme.RESULT_BG)
        self._tree.tag_configure("even", background=theme.RESULT_ALT)
        self._tree.tag_configure("modified", background="#5a4a2a")  # amber tint

        # ── Cell edit overlay ─────────────────────────────────────────
        self._entry: ttk.Entry | None = None
        self._editing_item: str | None = None
        self._editing_col: str | None = None

        # Double-click to edit a cell
        self._tree.bind("<Double-1>", self._on_cell_double_click)
        # Enter key to start editing selected cell
        self._tree.bind("<Return>", self._on_cell_edit_key)

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
        self._rows = [list(row) for row in result.rows]

        self._tree["columns"] = self._columns
        for col in self._columns:
            self._tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=130, minwidth=60, stretch=False, anchor="w")

        for i, row in enumerate(self._rows):
            tag = "even" if i % 2 == 0 else "odd"
            values = [self._format_cell(v) for v in row]
            self._tree.insert("", END, values=values, tags=(tag,))

        # Auto-size columns based on content width
        self._auto_size_columns()

        elapsed_ms = int(result.elapsed * 1000)
        self._status.config(
            text=f"{result.row_count} row(s) fetched  |  {elapsed_ms} ms",
            foreground=theme.FG_STATUS,
        )

    def set_source_table(self, schema: str, table: str) -> None:
        """Manually set the source table for UPDATE generation."""
        self._source_table = f"{schema}.{table}" if schema else table

    def clear_source_table(self) -> None:
        """Clear the source table so Save is disabled."""
        self._source_table = None

    def clear(self) -> None:
        """Remove all rows and columns, reset editing state."""
        self._cancel_edit()
        for item in self._tree.get_children():
            self._tree.delete(item)
        if self._columns:
            self._tree["columns"] = []
            self._columns = []
        self._rows = []
        self._modified_cells = {}
        self._status.config(text="Ready", foreground=theme.FG_STATUS)

    def show_message(self, message: str, is_error: bool = False) -> None:
        """Show a status message without a data grid."""
        self.clear()
        color = theme.FG_ERROR if is_error else theme.FG_STATUS
        self._status.config(text=message, foreground=color)

    def _auto_size_columns(self) -> None:
        """Auto-size columns based on content width.

        Measures header text and first N rows of data to find the widest
        cell, then sets the column width to fit (capped at 350px).
        """
        import tkinter.font as tkfont

        if not self._columns or not self._rows:
            return

        try:
            font_obj = tkfont.nametofont("TkDefaultFont")
            header_font = tkfont.Font(font=font_obj.actual())
            header_font.configure(weight="bold")
        except Exception:
            return

        sample_rows = self._rows[:50]
        for idx, col in enumerate(self._columns):
            header_w = header_font.measure(col) + 24

            max_data_w = 0
            for row in sample_rows:
                if idx < len(row):
                    val = self._format_cell(row[idx])
                    w = font_obj.measure(str(val)) + 24
                    if w > max_data_w:
                        max_data_w = w

            best_w = max(header_w, max_data_w, 60)
            best_w = min(best_w, 350)
            self._tree.column(col, width=best_w, minwidth=60, stretch=False, anchor="w")

    # ── Cell Editing ─────────────────────────────────────────────────

    def _on_cell_double_click(self, event) -> None:
        """Start editing the cell under the cursor on double-click."""
        region = self._tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self._tree.identify_column(event.x)
        item = self._tree.identify_row(event.y)
        if item and col:
            self._start_edit(item, col)

    def _on_cell_edit_key(self, event) -> None:
        """Start editing the focused cell when Enter is pressed."""
        item = self._tree.focus()
        if not item:
            return
        # Get the column under the mouse or the first column
        col = "#1"  # default to first column
        self._start_edit(item, col)

    def _start_edit(self, item: str, col: str) -> None:
        """Open an Entry widget over the cell to edit its value."""
        self._cancel_edit()

        # Convert column id like "#1" to column name
        col_idx = int(col.replace("#", "")) - 1
        if col_idx < 0 or col_idx >= len(self._columns):
            return
        col_name = self._columns[col_idx]

        # Get current value
        current = self._tree.set(item, col_name)

        # Get cell bounding box
        try:
            x, y, w, h = self._tree.bbox(item, col)
        except Exception:
            return

        # Create Entry overlay
        self._entry = ttk.Entry(self._tree, style="Cell.TEntry")
        self._entry.place(x=x, y=y, width=w, height=h)
        self._entry.insert(0, current)
        self._entry.select_range(0, END)
        self._entry.focus_set()

        self._editing_item = item
        self._editing_col = col_name

        # Commit on Enter / FocusOut, cancel on Escape
        self._entry.bind("<Return>", lambda e: self._commit_edit())
        self._entry.bind("<FocusOut>", lambda e: self._commit_edit())
        self._entry.bind("<Escape>", lambda e: self._cancel_edit())

    def _commit_edit(self) -> None:
        """Save the edited cell value and mark it as modified."""
        if (
            self._entry is None
            or self._editing_item is None
            or self._editing_col is None
        ):
            return

        new_value = self._entry.get()
        item = self._editing_item
        col = self._editing_col

        # Get original value
        col_idx = self._columns.index(col)
        original = self._format_cell(self._rows[self._tree.index(item)][col_idx])

        self._cancel_edit()

        # If value changed, track it
        if new_value != original:
            # Store modification
            if item not in self._modified_cells:
                self._modified_cells[item] = {}
            self._modified_cells[item][col] = new_value

            # Update the cell display
            self._tree.set(item, col, new_value)

            # Highlight the row as modified
            tags = list(self._tree.item(item, "tags"))
            if "modified" not in tags:
                tags.append("modified")
            self._tree.item(item, tags=tags)

            # Update status
            total_changes = sum(len(v) for v in self._modified_cells.values())
            self._status.config(
                text=f"⚠ {total_changes} cell(s) modified — click 💾 Save to commit",
                foreground=theme.FG_WARNING
                if hasattr(theme, "FG_WARNING")
                else "#ebcb8b",
            )

    def _cancel_edit(self) -> None:
        """Close the Entry overlay without saving."""
        if self._entry is not None:
            self._entry.destroy()
            self._entry = None
        self._editing_item = None
        self._editing_col = None

    # ── Save (Commit) ────────────────────────────────────────────────

    def _on_save(self) -> None:
        """Generate and execute UPDATE statements for all modified cells.

        All UPDATEs are batched into a single background thread via
        ``execute_updates`` so the UI stays responsive and multi-row
        saves work correctly.
        """
        if not self._modified_cells:
            self._status.config(text="No changes to save", foreground=theme.FG_STATUS)
            return

        if not self._source_table:
            self._status.config(
                text="Cannot commit: source table unknown (set via set_source_table)",
                foreground=theme.FG_ERROR,
            )
            return

        if not self._controller:
            self._status.config(
                text="Cannot commit: no SQL controller connected",
                foreground=theme.FG_ERROR,
            )
            return

        if not self._columns:
            return

        # C3: Whitelist identifiers to prevent SQL injection
        import re

        def _is_safe_identifier(name: str) -> bool:
            """Only allow alphanumeric + underscore identifiers."""
            return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name))

        # Validate source table (schema.table)
        if "." in self._source_table:
            schema_part, table_part = self._source_table.split(".", 1)
        else:
            schema_part, table_part = "", self._source_table

        if not _is_safe_identifier(table_part) or (
            schema_part and not _is_safe_identifier(schema_part)
        ):
            self._status.config(
                text=f"Cannot commit: invalid table name '{self._source_table}'",
                foreground=theme.FG_ERROR,
            )
            return

        pk_col = self._columns[0]  # assume first column is the primary key

        # Validate PK column name
        if not _is_safe_identifier(pk_col):
            self._status.config(
                text=f"Cannot commit: invalid column name '{pk_col}'",
                foreground=theme.FG_ERROR,
            )
            return

        # Build all UPDATE statements + their context (item, changes)
        statements: list[tuple[str, tuple[str, dict[str, str]]]] = []

        for item, changes in self._modified_cells.items():
            if not changes:
                continue

            # Validate each column name
            for col_name in changes:
                if not _is_safe_identifier(col_name):
                    self._status.config(
                        text=f"Cannot commit: invalid column name '{col_name}'",
                        foreground=theme.FG_ERROR,
                    )
                    return

            # Get the PK original value for this row
            col_idx = self._tree.index(item)
            original_pk = self._format_cell(self._rows[col_idx][0])

            # Build SET clause with escaped values
            set_clauses = []
            for col_name, new_val in changes.items():
                escaped = self._escape_sql_value(new_val)
                set_clauses.append(f"{col_name} = {escaped}")

            set_clause = ", ".join(set_clauses)

            # WHERE clause using the original PK value
            pk_escaped = self._escape_sql_value(original_pk)
            where_clause = f"{pk_col} = {pk_escaped}"

            sql = f"UPDATE {self._source_table} SET {set_clause} WHERE {where_clause}"

            # Context carries the item ID and changes for the callback
            context = (item, dict(changes))
            statements.append((sql, context))

        if not statements:
            return

        total = len(statements)
        self._status.config(
            text=f"Saving {total} update(s)...",
            foreground=theme.FG_WARNING if hasattr(theme, "FG_WARNING") else "#ebcb8b",
        )

        # N1: Execute all UPDATEs in a single batch (one background thread)
        queued = self._controller.execute_updates(
            statements,
            on_done=self._on_all_updates_done,
        )

        if not queued:
            self._status.config(
                text="Controller busy — wait for current operation",
                foreground=theme.FG_ERROR,
            )

    @staticmethod
    def _escape_sql_value(value) -> str:
        """Escape a value for safe inclusion in SQL.

        Numbers are returned unquoted; strings are single-quoted with
        internal single quotes doubled.
        """
        if value is None:
            return "NULL"
        # Try to interpret as a number
        s = str(value)
        try:
            float(s)
            # It's a number — return without quotes
            return s
        except (ValueError, TypeError):
            pass
        # It's a string — escape and quote
        escaped = s.replace("'", "''")
        return f"'{escaped}'"

    def _on_all_updates_done(self, result: QueryResult) -> None:
        """Handle completion of all UPDATE statements (Tk main thread).

        N3: Defensive against stale tree items — if the user ran a new
        query or cleared results between Save and callback, we gracefully
        skip the UI update instead of crashing.
        """
        if not result.raw or "results" not in result.raw:
            # Fallback for single-statement results
            if result.is_error:
                self._status.config(
                    text=f"Error: {result.error}",
                    foreground=theme.FG_ERROR,
                )
            else:
                self._status.config(
                    text=f"✓ Changes committed to {self._source_table}",
                    foreground=theme.FG_STATUS,
                )
            return

        results_list = result.raw.get("results", [])
        total = len(results_list)

        # Process each statement result — update local cache + remove modified tags
        committed = 0
        for stmt_result in results_list:
            context = stmt_result.get("context")
            if context is None:
                continue

            item, changes = context

            if "error" in stmt_result:
                # This particular UPDATE failed — leave the cell marked as modified
                continue

            committed += 1

            # N3: Wrap in try/except — tree may have been cleared
            try:
                col_idx = self._tree.index(item)
                for col_name, new_val in changes.items():
                    cidx = self._columns.index(col_name)
                    self._rows[col_idx][cidx] = new_val

                # Remove modification state for this item
                if item in self._modified_cells:
                    del self._modified_cells[item]

                # Remove modified tag
                tags = list(self._tree.item(item, "tags"))
                if "modified" in tags:
                    tags.remove("modified")
                    self._tree.item(item, tags=tags)
            except Exception:
                # Tree was cleared or item no longer exists — skip UI update
                pass

        # Update status line
        if result.is_error and committed == 0:
            self._status.config(
                text=f"Error: {result.error}",
                foreground=theme.FG_ERROR,
            )
        elif committed == total:
            self._status.config(
                text=f"✓ {committed} cell(s) committed to {self._source_table}",
                foreground=theme.FG_STATUS,
            )
        else:
            failed = total - committed
            self._status.config(
                text=f"⚠ {committed} saved, {failed} failed — {self._source_table}",
                foreground=theme.FG_WARNING
                if hasattr(theme, "FG_WARNING")
                else "#ebcb8b",
            )

    # ── Cancel / Revert ──────────────────────────────────────────────

    def _on_cancel(self) -> None:
        """Revert all modifications back to original values."""
        if not self._modified_cells:
            self._status.config(text="No changes to revert", foreground=theme.FG_STATUS)
            return

        # Restore original values
        for item, changes in self._modified_cells.items():
            col_idx = self._tree.index(item)
            for col_name in changes:
                cidx = self._columns.index(col_name)
                original = self._format_cell(self._rows[col_idx][cidx])
                self._tree.set(item, col_name, original)

        # Clear modification state
        self._modified_cells = {}

        # Remove modified tags
        for item in self._tree.get_children():
            tags = list(self._tree.item(item, "tags"))
            if "modified" in tags:
                tags.remove("modified")
                self._tree.item(item, tags=tags)

        # Restore zebra striping
        for i, item in enumerate(self._tree.get_children()):
            tag = "even" if i % 2 == 0 else "odd"
            self._tree.item(item, tags=(tag,))

        self._status.config(text="Changes reverted", foreground=theme.FG_STATUS)

    # ── Refresh ──────────────────────────────────────────────────────

    def _on_refresh(self) -> None:
        """Re-run the last query (delegates to app.py via callback)."""
        if self._on_status:
            self._on_status("refresh")

    # ── Unused stubs ─────────────────────────────────────────────────

    def _on_filter(self):
        pass

    def _on_export(self):
        pass

    def _on_grid_view(self):
        pass

    # ── Sort ─────────────────────────────────────────────────────────

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

    # ── Helpers ──────────────────────────────────────────────────────

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

    @property
    def modified_count(self) -> int:
        """Number of modified cells."""
        return sum(len(v) for v in self._modified_cells.values())

    @property
    def is_modified(self) -> bool:
        """Whether any cells have been modified."""
        return len(self._modified_cells) > 0
