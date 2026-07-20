"""Database navigator widget — DBeaver-style sidebar with tabs, search, and tree.

Features:
- Tab bar at top (Database Navigator / Projects)
- Search bar for filtering
- Hierarchical tree: connection → schemas → tables
- Collapse/expand on single click
- Double-click inserts table name into SQL editor
- Node icons using Unicode symbols
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
        super().__init__(parent, background=theme.PANEL_BG, width=260)
        self.pack_propagate(False)
        self._insert_callback = None
        self._result_queue: queue.Queue = queue.Queue()
        self._polling = False
        self._all_tables: list[tuple[str, str]] = []
        self._setup_widgets()

    def _setup_widgets(self) -> None:
        """Create tab bar + search + tree."""
        # ── Tab bar (Database Navigator / Projects) ──────────────────
        tab_bar = Frame(self, background=theme.TAB_BAR_BG, height=26)
        tab_bar.pack(fill="x", side="top")
        tab_bar.pack_propagate(False)

        # Active tab
        tab_active = Frame(tab_bar, background=theme.BG, height=26)
        tab_active.pack(side="left", padx=(2, 0))
        tk.Label(
            tab_active,
            text=" Database Navigator ",
            background=theme.BG,
            foreground=theme.FG_HEADER,
            font=theme.ui_font_sm(),
            padx=4,
        ).pack(side="left")

        # Inactive tab
        tab_inactive = Frame(tab_bar, background=theme.TAB_BAR_BG, height=26)
        tab_inactive.pack(side="left", padx=(0, 0))
        tk.Label(
            tab_inactive,
            text=" Projects ",
            background=theme.TAB_BAR_BG,
            foreground=theme.FG_DIM,
            font=theme.ui_font_sm(),
            padx=4,
        ).pack(side="left")

        # Separator below tab bar
        Frame(self, background=theme.BORDER_DIM, height=1).pack(fill="x", side="top")

        # ── Search bar ────────────────────────────────────────────────
        search_frame = Frame(self, background=theme.PANEL_BG, height=28)
        search_frame.pack(fill="x", side="top")
        search_frame.pack_propagate(False)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_tree())
        self._search_entry = tk.Entry(
            search_frame,
            textvariable=self._search_var,
            background=theme.EDITOR_BG,
            foreground=theme.FG,
            insertbackground=theme.FG,
            relief="flat",
            borderwidth=0,
            font=theme.ui_font_sm(),
            highlightthickness=1,
            highlightbackground=theme.BORDER_DIM,
            highlightcolor=theme.BORDER,
        )
        self._search_entry.pack(fill="x", side="left", padx=4, pady=4, expand=True)
        # Placeholder
        self._search_entry.insert(0, "Search...")
        self._search_entry.config(foreground=theme.FG_DIM)
        self._search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self._search_entry.bind("<FocusOut>", self._on_search_focus_out)

        # ── Tree container ────────────────────────────────────────────
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

        # Bind events
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

    def _on_search_focus_in(self, event=None) -> None:
        """Clear placeholder on focus."""
        if self._search_var.get() == "Search...":
            self._search_entry.delete(0, END)
            self._search_entry.config(foreground=theme.FG)

    def _on_search_focus_out(self, event=None) -> None:
        """Restore placeholder if empty."""
        if not self._search_var.get():
            self._search_entry.insert(0, "Search...")
            self._search_entry.config(foreground=theme.FG_DIM)

    def set_insert_callback(self, callback) -> None:
        """Set callback for when a table name is double-clicked."""
        self._insert_callback = callback

    def populate(self, tables: list[tuple[str, str]]) -> None:
        """Populate the tree from a list of (schema, table) tuples."""
        self._all_tables = tables
        self._rebuild_tree(tables)

    def _rebuild_tree(self, tables: list[tuple[str, str]]) -> None:
        """Rebuild the full tree from a table list."""
        self._clear()

        root_node = self._tree.insert(
            "", END, text="🔗 IRIS Connection", open=True, tags=("root",)
        )

        # Group tables by schema
        schemas: dict[str, list[str]] = {}
        for schema, table in tables:
            schemas.setdefault(schema, []).append(table)

        for schema_name in sorted(schemas.keys()):
            schema_node = self._tree.insert(
                root_node,
                END,
                text=f"📂 {schema_name}",
                open=False,
                tags=("schema",),
            )
            for table_name in sorted(schemas[schema_name]):
                self._tree.insert(
                    schema_node,
                    END,
                    text=f"📋 {table_name}",
                    tags=("table",),
                )

    def _filter_tree(self) -> None:
        """Filter tree by search text."""
        text = self._search_var.get().strip().lower()
        if not text or text == "search...":
            self._rebuild_tree(self._all_tables)
            return

        # Filter matching tables
        filtered = [
            (s, t)
            for s, t in self._all_tables
            if text in t.lower() or text in s.lower()
        ]
        self._rebuild_tree(filtered)
        # Expand all schemas when filtering
        for item in self._tree.get_children():
            root = item
            for child in self._tree.get_children(root):
                self._tree.item(child, open=True)

    def load_async(self) -> None:
        """Load schemas/tables from IRIS in a background thread."""
        if self._polling:
            return
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
            return
        except queue.Empty:
            pass
        self.after(100, self._start_polling)

    def _load_tables(self) -> None:
        """Query IRIS for table list (runs in background thread)."""
        try:
            import httpx

            from prism.iris.sdk.http import api_url, auth, parse_json
            from prism.settings import settings

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def _fetch():
                    ns = settings.iris_namespace or "USER"
                    url = f"{api_url(ns)}/action/query"
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
            text = item["text"]
            table_name = text.split(" ", 1)[1] if " " in text else text
            self._insert_callback(table_name)
        elif "schema" in tags:
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
