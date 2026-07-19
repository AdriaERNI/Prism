"""Database navigator widget — tree sidebar showing schemas and tables.

Queries IRIS for table metadata via SQL and presents a hierarchical
tree: connection → schemas → tables.  Double-clicking a table inserts
its name into the SQL editor.
"""

from __future__ import annotations

import asyncio
import queue
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
        self._result_queue: queue.Queue = queue.Queue()
        self._polling = False

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
            style="Treeview",
        )
        self._tree.pack(side="left", fill=BOTH, expand=True)
        vsb.config(command=self._tree.yview)

        # Tree item styling
        self._tree.tag_configure("root", foreground=theme.FG)
        self._tree.tag_configure("schema", foreground=theme.FG)
        self._tree.tag_configure("table", foreground=theme.FG_DIM)

        # Bind double-click
        self._tree.bind("<Double-1>", self._on_double_click)
        # Single-click on schema node toggles expand
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

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
                open=False,
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
        """Load schemas/tables from IRIS in a background thread.

        Uses a queue-based polling pattern (same as SQLController)
        because ``root.after()`` is NOT thread-safe when called
        from non-main threads — it silently fails.
        """
        if self._polling:
            return  # Already loading
        self._polling = True
        self._start_polling()
        thread = threading.Thread(target=self._load_tables, daemon=True)
        thread.start()

    def _start_polling(self) -> None:
        """Poll the result queue from the main Tk loop."""
        try:
            result = self._result_queue.get_nowait()
            self._polling = False
            if isinstance(result, list):
                self.populate(result)
            return  # Done
        except queue.Empty:
            pass
        # Re-poll in 100ms
        self.after(100, self._start_polling)

    def _load_tables(self) -> None:
        """Query IRIS for table list (runs in background thread).

        Uses a fresh asyncio event loop + fresh httpx client to avoid
        'Event loop is closed' errors from the shared httpx client.
        """
        try:
            import httpx

            from prism.iris.sdk.http import api_url, auth, parse_json
            from prism.settings import settings

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def _fetch():
                    url = f"{api_url(settings.iris_namespace or 'USER')}/action/query"
                    payload = {
                        "query": (
                            "SELECT TABLE_SCHEMA, TABLE_NAME "
                            "FROM INFORMATION_SCHEMA.TABLES "
                            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
                        ),
                    }
                    async with httpx.AsyncClient(
                        timeout=30.0,
                        auth=auth(),
                    ) as client:
                        resp = await client.post(url, json=payload)
                        resp.raise_for_status()
                        return parse_json(resp)

                raw = loop.run_until_complete(_fetch())
            finally:
                loop.close()

            tables: list[tuple[str, str]] = []
            content = raw.get("result", {}).get("content", [])
            for row in content:
                schema = row.get("TABLE_SCHEMA", "")
                table = row.get("TABLE_NAME", "")
                if schema and table:
                    tables.append((schema, table))

            self._result_queue.put(tables)

        except Exception:
            # If the metadata query fails, put empty list
            self._result_queue.put([])

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

    def _on_select(self, event=None) -> None:
        """Toggle expand/collapse on schema node single-click."""
        selection = self._tree.selection()
        if not selection:
            return
        item = self._tree.item(selection[0])
        tags = item.get("tags", [])
        if "schema" in tags:
            node = selection[0]
            if self._tree.item(node, "open"):
                self._tree.item(node, open=False)
            else:
                self._tree.item(node, open=True)
