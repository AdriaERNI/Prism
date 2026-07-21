"""Database navigator widget — DBeaver-style sidebar with proper IRIS hierarchy.

Tree structure::

    🔗 IRIS Connection (USER)
    ├── 📂 Schemas
    │   ├── 📁 User Tables  (BASE TABLE, non-% schemas)
    │   │   └── 📋 TableName
    │   │       ├── 📊 Columns  (lazy loaded)
    │   │       │   ├── ID: bigint
    │   │       │   └── Name: varchar(100)
    │   │       └── ...
    │   ├── 📁 System Tables  (SYSTEM TABLE)
    │   │   └── 📋 SysTableName
    │   └── 📁 Views  (SYSTEM VIEW)
    │       └── 📋 ViewName
    └── 📂 System Schemas
        └── 📁 SchemaName_%  (collapsed by default)
            └── ...

Features:
- Tab bar (Database Navigator / Projects)
- Search bar for filtering
- Lazy column loading on table expand
- Double-click inserts table name into SQL editor
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
        super().__init__(parent, background=theme.PANEL_BG, width=280)
        self.pack_propagate(False)
        self._insert_callback = None
        self._result_queue: queue.Queue = queue.Queue()
        self._polling = False
        self._all_tables: list[dict] = []
        self._column_queue: queue.Queue = queue.Queue()
        self._column_polling = False
        self._loaded_columns: set[str] = set()  # track which tables have columns loaded
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
        tab_inactive.pack(side="left")
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
            style="Sidebar.Treeview",
        )
        self._tree.pack(side="left", fill=BOTH, expand=True)
        vsb.config(command=self._tree.yview)

        # Tree item styling
        self._tree.tag_configure("root", foreground=theme.FG)
        self._tree.tag_configure("folder", foreground=theme.FG)
        self._tree.tag_configure("schema", foreground=theme.FG)
        self._tree.tag_configure("schema_sys", foreground=theme.FG_DIM)
        self._tree.tag_configure("table", foreground=theme.FG)
        self._tree.tag_configure("table_sys", foreground=theme.FG_DIM)
        self._tree.tag_configure("column", foreground=theme.FG_DIM)
        self._tree.tag_configure("view", foreground=theme.FG)

        # Bind events
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<<TreeviewExpand>>", self._on_expand)

        # Now that _tree exists, wire up search filtering
        self._search_var.trace_add("write", lambda *_: self._filter_tree())

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

    def populate(self, tables: list[dict]) -> None:
        """Populate the tree from a list of table dicts.

        Each dict has: schema, name, type (BASE TABLE / SYSTEM TABLE / SYSTEM VIEW)
        """
        self._all_tables = tables
        self._rebuild_tree(tables)

    def _rebuild_tree(self, tables: list[dict]) -> None:
        """Build the DBeaver-style tree hierarchy."""
        self._clear()
        self._loaded_columns.clear()

        # Determine namespace from settings
        from prism.settings import settings

        ns = settings.iris_namespace or "USER"
        root_node = self._tree.insert(
            "", END, text=f"🔗 IRIS Connection ({ns})", open=True, tags=("root",)
        )

        # Separate schemas: user schemas (not starting with %) vs system schemas
        user_schemas: dict[str, list[dict]] = {}
        sys_schemas: dict[str, list[dict]] = {}

        for t in tables:
            schema = t["schema"]
            if schema.startswith("%"):
                sys_schemas.setdefault(schema, []).append(t)
            else:
                user_schemas.setdefault(schema, []).append(t)

        # ── User Schemas node ─────────────────────────────────────────
        schemas_node = self._tree.insert(
            root_node,
            END,
            text=f"📂 Schemas ({len(user_schemas)})",
            open=True,
            tags=("folder",),
        )

        for schema_name in sorted(user_schemas.keys()):
            schema_tables = user_schemas[schema_name]
            self._build_schema_node(
                schemas_node, schema_name, schema_tables, is_system=False
            )

        # ── System Schemas node (collapsed) ───────────────────────────
        if sys_schemas:
            sys_node = self._tree.insert(
                root_node,
                END,
                text=f"📂 System Schemas ({len(sys_schemas)})",
                open=False,
                tags=("folder",),
            )
            for schema_name in sorted(sys_schemas.keys()):
                schema_tables = sys_schemas[schema_name]
                self._build_schema_node(
                    sys_node, schema_name, schema_tables, is_system=True
                )

    def _build_schema_node(
        self, parent: str, schema_name: str, tables: list[dict], is_system: bool
    ) -> None:
        """Build a schema node with Tables/Views sub-folders."""
        schema_tag = "schema_sys" if is_system else "schema"
        schema_icon = "📂" if not is_system else "📦"
        schema_node = self._tree.insert(
            parent,
            END,
            text=f"{schema_icon} {schema_name}",
            open=False,
            tags=(schema_tag,),
        )

        # Group by table type within schema
        base_tables = [t for t in tables if t["type"] == "BASE TABLE"]
        system_tables = [t for t in tables if t["type"] == "SYSTEM TABLE"]
        views = [t for t in tables if t["type"] == "SYSTEM VIEW"]

        if base_tables:
            tables_node = self._tree.insert(
                schema_node,
                END,
                text=f"📋 Tables ({len(base_tables)})",
                open=False,
                tags=("folder",),
            )
            for t in sorted(base_tables, key=lambda x: x["name"]):
                self._tree.insert(
                    tables_node,
                    END,
                    text=f"📊 {t['name']}",
                    open=False,
                    tags=("table",),
                    values=(schema_name, t["name"]),
                )

        if system_tables:
            sys_tables_node = self._tree.insert(
                schema_node,
                END,
                text=f"📋 System Tables ({len(system_tables)})",
                open=False,
                tags=("folder",),
            )
            for t in sorted(system_tables, key=lambda x: x["name"]):
                self._tree.insert(
                    sys_tables_node,
                    END,
                    text=f"📊 {t['name']}",
                    open=False,
                    tags=("table_sys",),
                    values=(schema_name, t["name"]),
                )

        if views:
            views_node = self._tree.insert(
                schema_node,
                END,
                text=f"📋 Views ({len(views)})",
                open=False,
                tags=("folder",),
            )
            for t in sorted(views, key=lambda x: x["name"]):
                self._tree.insert(
                    views_node,
                    END,
                    text=f"👁 {t['name']}",
                    open=False,
                    tags=("view",),
                    values=(schema_name, t["name"]),
                )

    def _filter_tree(self) -> None:
        """Filter tree by search text."""
        text = self._search_var.get().strip().lower()
        if not text or text == "search...":
            self._rebuild_tree(self._all_tables)
            return

        filtered = [
            t
            for t in self._all_tables
            if text in t["name"].lower() or text in t["schema"].lower()
        ]
        self._rebuild_tree(filtered)

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
        # C5: Always reschedule, even on error path — _polling stays True
        # until the queue delivers a result (empty or error).
        self.after(100, self._start_polling)

    def _load_tables(self) -> None:
        """Query IRIS for table list with schema, name, and type."""
        try:
            import httpx

            from prism.iris.sdk.http import api_url, auth, parse_json
            from prism.settings import settings

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # C5: Ensure _polling is cleared on unexpected errors
                async def _fetch():
                    ns = settings.iris_namespace or "USER"
                    url = f"{api_url(ns)}/action/query"
                    payload = {
                        "query": (
                            "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
                            "FROM INFORMATION_SCHEMA.TABLES "
                            "ORDER BY TABLE_SCHEMA, TABLE_TYPE, TABLE_NAME"
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

            tables: list[dict] = []
            content = raw.get("result", {}).get("content", [])
            for row in content:
                schema = row.get("TABLE_SCHEMA", "")
                name = row.get("TABLE_NAME", "")
                ttype = row.get("TABLE_TYPE", "")
                if schema and name:
                    tables.append({"schema": schema, "name": name, "type": ttype})

            self._result_queue.put(tables)

        except Exception:
            self._result_queue.put([])

    def _load_columns_async(self, schema: str, table: str, tree_node: str) -> None:
        """Load columns for a table in a background thread."""
        node_key = f"{schema}.{table}"
        if node_key in self._loaded_columns:
            return
        self._loaded_columns.add(node_key)

        thread = threading.Thread(
            target=self._load_columns_thread,
            args=(schema, table, tree_node),
            daemon=True,
        )
        thread.start()

    def _load_columns_thread(self, schema: str, table: str, tree_node: str) -> None:
        """Query IRIS for column metadata."""
        try:
            import httpx

            from prism.iris.sdk.http import api_url, auth, parse_json
            from prism.settings import settings

            # C4: Escape single quotes in schema/table to prevent SQL injection
            safe_schema = schema.replace("'", "''")
            safe_table = table.replace("'", "''")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def _fetch():
                    ns = settings.iris_namespace or "USER"
                    url = f"{api_url(ns)}/action/query"
                    payload = {
                        "query": (
                            "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH "
                            "FROM INFORMATION_SCHEMA.COLUMNS "
                            f"WHERE TABLE_SCHEMA = '{safe_schema}' AND TABLE_NAME = '{safe_table}' "
                            "ORDER BY ORDINAL_POSITION"
                        ),
                    }
                    async with httpx.AsyncClient(
                        timeout=15.0,
                        auth=auth(),
                    ) as client:
                        resp = await client.post(url, json=payload)
                        resp.raise_for_status()
                        return parse_json(resp)

                raw = loop.run_until_complete(_fetch())
            finally:
                loop.close()

            columns = []
            content = raw.get("result", {}).get("content", [])
            for row in content:
                col_name = row.get("COLUMN_NAME", "")
                data_type = row.get("DATA_TYPE", "")
                max_len = row.get("CHARACTER_MAXIMUM_LENGTH")
                if max_len:
                    type_str = f"{data_type}({max_len})"
                else:
                    type_str = data_type
                if col_name:
                    columns.append({"name": col_name, "type": type_str})

            self._column_queue.put((tree_node, columns))

        except Exception:
            self._column_queue.put((tree_node, []))

    def _start_column_polling(self, tree_node: str) -> None:
        """Poll for column results."""
        try:
            result = self._column_queue.get_nowait()
            node, columns = result
            self._populate_columns(node, columns)
            return
        except queue.Empty:
            pass
        self.after(100, lambda: self._start_column_polling(tree_node))

    def _populate_columns(self, tree_node: str, columns: list[dict]) -> None:
        """Populate the Columns folder under a table node."""
        # Check if node still exists
        try:
            self._tree.item(tree_node)
        except tk.TclError:
            return

        # Create a Columns folder
        columns_node = self._tree.insert(
            tree_node,
            END,
            text=f"📊 Columns ({len(columns)})",
            open=True,
            tags=("folder",),
        )
        for col in columns:
            self._tree.insert(
                columns_node,
                END,
                text=f"  🔑 {col['name']}: {col['type']}",
                tags=("column",),
            )

    def _on_expand(self, event=None) -> None:
        """Handle tree node expansion — auto-expand table folders and lazy load columns."""
        selection = self._tree.focus()
        if not selection:
            return

        item = self._tree.item(selection)
        tags = item.get("tags", [])

        # If a schema node is expanded, auto-expand its "Tables" folder so users
        # see table names immediately instead of a collapsed "Tables (N)" folder.
        if "schema" in tags or "schema_sys" in tags:
            for child in self._tree.get_children(selection):
                child_text = self._tree.item(child, "text")
                # Auto-expand the Tables / System Tables folder
                if child_text.startswith("📋 Tables") or child_text.startswith(
                    "📋 System Tables"
                ):
                    self._tree.item(child, open=True)
            return

        # If it's a table node, load columns
        if "table" in tags or "table_sys" in tags or "view" in tags:
            values = item.get("values", [])
            if len(values) >= 2:
                schema, table = values[0], values[1]
                node_key = f"{schema}.{table}"
                if node_key not in self._loaded_columns:
                    # Insert a placeholder
                    self._tree.insert(
                        selection,
                        END,
                        text="  Loading...",
                        tags=("column",),
                    )
                    self._load_columns_async(schema, table, selection)
                    self._start_column_polling(selection)

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

        if "table" in tags or "table_sys" in tags or "view" in tags:
            # Extract table name from values (schema, table) or from text
            values = item.get("values", [])
            if values and len(values) >= 2:
                schema, table_name = values[0], values[1]
            else:
                text = item["text"]
                parts = text.split(" ", 1)
                table_name = parts[1] if len(parts) > 1 else text
                schema = ""
            # Generate SELECT * query and insert into editor
            qualified = f"{schema}.{table_name}" if schema else table_name
            self._insert_callback(f"SELECT * FROM {qualified}")
