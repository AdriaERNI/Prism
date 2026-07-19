"""Database navigator widget — tree sidebar showing schemas and tables.

Queries IRIS for table metadata via SQL and presents a hierarchical
tree: connection → schemas → tables.  Double-clicking a table inserts
its name into the SQL editor.
"""

from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from tkinter import BOTH, END, Frame, Scrollbar, ttk

from prism.gui import theme


class DatabaseTree(Frame):
    """Sidebar tree showing database schemas and tables."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=theme.PANEL_BG, width=250)
        self._setup_widgets()
        self._insert_callback = None

    def _setup_widgets(self) -> None:
        """Create the tree widget + scrollbar."""
        # Header
        header = Frame(self, background=theme.HEADER_BG, height=26)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Database Navigator",
            background=theme.HEADER_BG,
            foreground=theme.FG_HEADER,
            font=theme.ui_font_sm(),
            anchor="w",
        ).pack(side="left", padx=8)

        # Tree container
        tree_frame = Frame(self, background=theme.PANEL_BG)
        tree_frame.pack(fill=BOTH, expand=True)

        vsb = Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side="right", fill="y")

        self._tree = ttk.Treeview(
            tree_frame,
            show="tree",
            yscrollcommand=vsb.set,
            selectmode="browse",
        )
        self._tree.pack(side="left", fill=BOTH, expand=True)
        vsb.config(command=self._tree.yview)

        # Bind double-click
        self._tree.bind("<Double-1>", self._on_double_click)

    def set_insert_callback(self, callback) -> None:
        """Set callback for when a table name is double-clicked.

        Callback signature: ``callback(text: str) -> None``
        """
        self._insert_callback = callback

    def populate(self, tables: list[tuple[str, str]]) -> None:
        """Populate the tree from a list of (schema, table) tuples.

        Args:
            tables: List of (schema_name, table_name) pairs.
        """
        self._clear()

        root_node = self._tree.insert(
            "", END, text="IRIS Connection", open=True, tags=("root",)
        )

        # Group tables by schema
        schemas: dict[str, list[str]] = {}
        for schema, table in tables:
            schemas.setdefault(schema, []).append(table)

        for schema_name in sorted(schemas.keys()):
            schema_node = self._tree.insert(
                root_node,
                END,
                text=f"📁 {schema_name}",
                open=True,
                tags=("schema",),
            )
            for table_name in sorted(schemas[schema_name]):
                self._tree.insert(
                    schema_node,
                    END,
                    text=f"📊 {table_name}",
                    tags=("table",),
                )

    def load_async(self) -> None:
        """Load schemas/tables from IRIS in a background thread."""
        thread = threading.Thread(target=self._load_tables, daemon=True)
        thread.start()

    def _load_tables(self) -> None:
        """Query IRIS for table list (runs in background thread)."""
        try:
            from prism.iris.api.sql import execute_query

            # Query INFORMATION_SCHEMA for tables
            raw = asyncio.run(
                execute_query(
                    "SELECT SCHEMA_NAME, TABLE_NAME "
                    "FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_TYPE = 'TABLE' "
                    "ORDER BY SCHEMA_NAME, TABLE_NAME"
                )
            )

            tables: list[tuple[str, str]] = []
            content = raw.get("result", {}).get("content", [])
            for row in content:
                schema = row.get("SCHEMA_NAME", "")
                table = row.get("TABLE_NAME", "")
                if schema and table:
                    tables.append((schema, table))

            # Post back to Tk main loop
            if tables or not raw.get("status", {}).get("errors"):
                # Use a flag to indicate we should populate even if empty
                pass
            root = self.winfo_toplevel()
            root.after(0, lambda: self.populate(tables))

        except Exception:
            # If the metadata query fails, just leave the tree empty
            pass

    def _clear(self) -> None:
        """Remove all nodes from the tree."""
        for item in self._tree.get_children():
            self._tree.delete(item)

    def _on_double_click(self, event=None) -> None:
        """Insert table name into SQL editor on double-click."""
        if self._insert_callback is None:
            return

        selection = self._tree.selection()
        if not selection:
            return

        item = self._tree.item(selection[0])
        tags = item.get("tags", [])

        if "table" in tags:
            # Extract table name from "📊 TableName"
            text = item["text"]
            table_name = text.split(" ", 1)[1] if " " in text else text
            self._insert_callback(table_name)
        elif "schema" in tags:
            # Toggle expand/collapse
            node = selection[0]
            if self._tree.item(node, "open"):
                self._tree.item(node, open=False)
            else:
                self._tree.item(node, open=True)
