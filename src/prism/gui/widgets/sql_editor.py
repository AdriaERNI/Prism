"""SQL editor widget — ``tk.Text`` with syntax highlighting, line numbers, and tab bar.

Features:
- Tab bar above editor with script names + close buttons
- Line number gutter
- Real-time syntax highlighting via regex
- Right-click context menu
- Ctrl+Enter to execute query

Tab bar is managed by this widget so the editor owns its own tabs
(like DBeaver's script tabs).
"""

from tkinter import (
    BOTH,
    END,
    INSERT,
    LEFT,
    SEL_FIRST,
    SEL_LAST,
    TclError,
    WORD,
    YES,
    Canvas,
    Frame,
    Menu,
    Scrollbar,
    Text,
)
import tkinter as tk
import re

from prism.gui import theme


# ── SQL keyword list ──────────────────────────────────────────────────
SQL_KEYWORDS = [
    "SELECT",
    "FROM",
    "WHERE",
    "INSERT",
    "INTO",
    "VALUES",
    "UPDATE",
    "SET",
    "DELETE",
    "CREATE",
    "TABLE",
    "ALTER",
    "DROP",
    "INDEX",
    "VIEW",
    "JOIN",
    "INNER",
    "LEFT",
    "RIGHT",
    "OUTER",
    "FULL",
    "CROSS",
    "ON",
    "GROUP",
    "BY",
    "ORDER",
    "HAVING",
    "ASC",
    "DESC",
    "LIMIT",
    "TOP",
    "DISTINCT",
    "UNION",
    "ALL",
    "AND",
    "OR",
    "NOT",
    "IN",
    "EXISTS",
    "BETWEEN",
    "LIKE",
    "IS",
    "NULL",
    "AS",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "IF",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "TRANSACTION",
    "DATABASE",
    "SCHEMA",
    "GRANT",
    "REVOKE",
    "TRUNCATE",
    "MERGE",
    "WITH",
    "RECURSIVE",
    "OVER",
    "PARTITION",
    "ROW",
    "ROWS",
    "PRECEDING",
    "FOLLOWING",
    "UNBOUNDED",
    "CURRENT",
    "ROW_NUMBER",
]

SQL_FUNCTIONS = [
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "ABS",
    "ROUND",
    "CEILING",
    "FLOOR",
    "CONCAT",
    "SUBSTRING",
    "LENGTH",
    "TRIM",
    "UPPER",
    "LOWER",
    "COALESCE",
    "NULLIF",
    "CAST",
    "CONVERT",
    "DATE",
    "NOW",
    "GETDATE",
    "YEAR",
    "MONTH",
    "DAY",
    "EXTRACT",
    "POSITION",
]

# ── Regex patterns ───────────────────────────────────────────────────
_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in SQL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_FUNCTION_RE = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in SQL_FUNCTIONS) + r")\s*(?=\()",
    re.IGNORECASE,
)
_STRING_RE = re.compile(r"'(?:[^']|'')*'")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_COMMENT_RE = re.compile(r"--[^\n]*")

_TAG_CONFIG = {
    "keyword": {"foreground": theme.SYNTAX_KEYWORD},
    "function": {"foreground": theme.SYNTAX_FUNC},
    "string": {"foreground": theme.SYNTAX_STRING},
    "number": {"foreground": theme.SYNTAX_NUMBER},
    "comment": {"foreground": theme.SYNTAX_COMMENT},
}


class EditorTabBar(Frame):
    """Tab bar above the SQL editor showing script names.

    Supports:
    - Multiple tabs with unique sequential names (Script-1, Script-2, …)
    - Active tab highlighting
    - Tab switching via click
    - Close button per tab
    - Per-tab content tracking (stored as strings)
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=theme.TAB_BAR_BG, height=28, **kwargs)
        self.pack_propagate(False)
        self._tabs: list[dict] = []
        self._active_tab = 0
        self._next_id = 1  # monotonic counter for unique tab names
        self._on_switch_callback = None
        self._on_close_callback = None
        self._setup_widgets()

    def _setup_widgets(self) -> None:
        """Create initial tab."""
        self.add_tab()

    @property
    def tab_count(self) -> int:
        """Return the number of open tabs."""
        return len(self._tabs)

    @property
    def active_index(self) -> int:
        """Return the index of the currently active tab."""
        return self._active_tab

    def set_switch_callback(self, callback) -> None:
        """Set callback called when user switches to a different tab.

        Callback signature: callback(old_index: int, new_index: int)
        """
        self._on_switch_callback = callback

    def set_close_callback(self, callback) -> None:
        """Set callback called when user closes a tab.

        Callback signature: callback(closed_index: int)
        """
        self._on_close_callback = callback

    def add_tab(
        self, name: str | None = None, content: str = "", modified: bool = False
    ) -> int:
        """Add a new tab with a unique name. Returns the tab index.

        Args:
            name: Optional tab name. If None, auto-generates ``Script-N``
                  using a monotonic counter (never reuses numbers).
            content: Initial text content for this tab.
            modified: Whether the tab shows a modified indicator.
        """
        if name is None:
            name = f"Script-{self._next_id}"
        self._next_id += 1

        tab_frame = Frame(self, background=theme.BG, height=28)
        tab_frame.pack(side=LEFT, padx=(1, 0))

        prefix = "*" if modified else ""
        label_text = f" {prefix}{name} "
        label = tk.Label(
            tab_frame,
            text=label_text,
            background=theme.BG,
            foreground=theme.FG_HEADER,
            font=theme.ui_font_sm(),
            padx=6,
        )
        label.pack(side=LEFT)

        close_label = tk.Label(
            tab_frame,
            text="✕",
            background=theme.BG,
            foreground=theme.FG_DIM,
            font=theme.ui_font_sm(),
            padx=4,
        )
        close_label.pack(side=LEFT, padx=(0, 2))

        tab_info = {
            "frame": tab_frame,
            "label": label,
            "close": close_label,
            "name": name,
            "modified": modified,
            "content": content,
        }
        self._tabs.append(tab_info)

        idx = len(self._tabs) - 1

        # Bind click on label to switch tab
        label.bind("<Button-1>", lambda e, i=idx: self.switch_to(i))
        tab_frame.bind("<Button-1>", lambda e, i=idx: self.switch_to(i))

        # Bind close
        close_label.bind("<Button-1>", lambda e, i=idx: self.close_tab(i))

        # Switch to the new tab
        self.switch_to(idx)
        return idx

    def switch_to(self, idx: int) -> None:
        """Switch active tab to *idx* and trigger callback."""
        if idx < 0 or idx >= len(self._tabs):
            return
        old = self._active_tab
        self._active_tab = idx
        self._update_styles()
        if self._on_switch_callback and old != idx:
            self._on_switch_callback(old, idx)

    def _update_styles(self) -> None:
        """Update visual styling: active tab highlighted, others dimmed."""
        for i, tab in enumerate(self._tabs):
            if i == self._active_tab:
                tab["frame"].config(background=theme.EDITOR_BG)
                tab["label"].config(background=theme.EDITOR_BG, foreground=theme.FG)
                tab["close"].config(background=theme.EDITOR_BG)
            else:
                tab["frame"].config(background=theme.BG)
                tab["label"].config(background=theme.BG, foreground=theme.FG_DIM)
                tab["close"].config(background=theme.BG, foreground=theme.FG_DIM)

    def close_tab(self, idx: int) -> None:
        """Close a tab by index."""
        if idx < 0 or idx >= len(self._tabs):
            return
        # Don't close the last tab — always keep at least one
        if len(self._tabs) <= 1:
            return
        self._tabs.pop(idx)
        self._tabs[idx] if idx < len(self._tabs) else None  # no-op safety
        # Rebuild the tab bar
        self._rebuild()
        # Adjust active index
        if self._active_tab >= len(self._tabs):
            self._active_tab = len(self._tabs) - 1
        elif idx < self._active_tab:
            self._active_tab -= 1
        self._update_styles()
        if self._on_close_callback:
            self._on_close_callback(idx)

    def _rebuild(self) -> None:
        """Destroy and re-create all tab widgets (after close/reorder)."""
        for tab in self._tabs:
            tab["frame"].destroy()
        # Re-create widgets for remaining tabs
        for i, tab in enumerate(self._tabs):
            tab_frame = Frame(self, background=theme.BG, height=28)
            tab_frame.pack(side=LEFT, padx=(1, 0))

            prefix = "*" if tab["modified"] else ""
            label = tk.Label(
                tab_frame,
                text=f" {prefix}{tab['name']} ",
                background=theme.BG,
                foreground=theme.FG_HEADER,
                font=theme.ui_font_sm(),
                padx=6,
            )
            label.pack(side=LEFT)

            close_label = tk.Label(
                tab_frame,
                text="✕",
                background=theme.BG,
                foreground=theme.FG_DIM,
                font=theme.ui_font_sm(),
                padx=4,
            )
            close_label.pack(side=LEFT, padx=(0, 2))

            tab["frame"] = tab_frame
            tab["label"] = label
            tab["close"] = close_label

            label.bind("<Button-1>", lambda e, idx=i: self.switch_to(idx))
            tab_frame.bind("<Button-1>", lambda e, idx=i: self.switch_to(idx))
            close_label.bind("<Button-1>", lambda e, idx=i: self.close_tab(idx))

    def set_modified(self, idx: int, modified: bool) -> None:
        """Update tab modified indicator."""
        if idx < 0 or idx >= len(self._tabs):
            return
        tab = self._tabs[idx]
        tab["modified"] = modified
        prefix = "*" if modified else ""
        tab["label"].config(text=f" {prefix}{tab['name']} ")

    def get_tab_content(self, idx: int) -> str:
        """Return stored content for tab *idx*."""
        if idx < 0 or idx >= len(self._tabs):
            return ""
        return self._tabs[idx].get("content", "")

    def set_tab_content(self, idx: int, content: str) -> None:
        """Store content for tab *idx*."""
        if idx < 0 or idx >= len(self._tabs):
            return
        self._tabs[idx]["content"] = content

    def get_tab_name(self, idx: int) -> str:
        """Return the name of tab *idx*."""
        if idx < 0 or idx >= len(self._tabs):
            return ""
        return self._tabs[idx]["name"]

    def get_all_tabs(self) -> list[dict]:
        """Return a list of all tab info dicts (copies)."""
        return [
            {
                "name": t["name"],
                "content": t.get("content", ""),
                "modified": t["modified"],
            }
            for t in self._tabs
        ]


class SQLEditor(Frame):
    """A text editor with SQL syntax highlighting and line numbers."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=theme.EDITOR_BG)
        self._setup_widgets()
        self._setup_tags()
        self._setup_events()

    # ── Setup ────────────────────────────────────────────────────────

    def _setup_widgets(self) -> None:
        """Create text widget + line number gutter + vertical scrollbar."""
        # Scrollbar
        self._vbar = Scrollbar(self, orient="vertical")
        self._vbar.pack(side="right", fill="y")

        # Line number gutter (canvas on the left)
        self._gutter = Canvas(
            self,
            width=40,
            background=theme.PANEL_BG,
            highlightthickness=0,
            borderwidth=0,
        )
        self._gutter.pack(side="left", fill="y")

        # Separator between gutter and editor
        Frame(self, background=theme.BORDER_DIM, width=1).pack(side="left", fill="y")

        # Text widget
        self._text = Text(
            self,
            background=theme.EDITOR_BG,
            foreground=theme.SYNTAX_DEFAULT,
            insertbackground=theme.FG,
            selectbackground=theme.SELECTED_BG,
            selectforeground=theme.SELECTED_FG,
            font=theme.editor_font(),
            undo=True,
            wrap=WORD,
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=6,
            tabs=("4m",),
            tabstyle="wordprocessor",
        )
        self._text.pack(side="left", fill=BOTH, expand=YES)

        # Link scrollbar
        self._vbar.config(command=self._text.yview)
        self._text.config(yscrollcommand=self._on_text_scroll)

        # Gutter redraw on scroll and content change
        self._text.bind("<Configure>", lambda e: self._redraw_gutter())
        self._text.bind("<KeyRelease>", self._on_key_release, add="+")
        self._redraw_gutter()

    def _on_text_scroll(self, *args) -> None:
        """Forward scroll to scrollbar + redraw gutter."""
        self._vbar.set(*args)
        self._redraw_gutter()

    def _redraw_gutter(self) -> None:
        """Redraw line numbers in the gutter canvas."""
        self._gutter.delete("all")
        try:
            first_line = int(self._text.index("@0,0").split(".")[0])
            last_line = int(self._text.index("@0,999999").split(".")[0])
        except Exception:
            return

        font_obj = theme.editor_font()
        try:
            line_bbox = self._text.bbox("1.0")
            if line_bbox:
                line_height = line_bbox[3]
            else:
                line_height = 18
        except Exception:
            line_height = 18

        gutter_width = self._gutter.winfo_width() or 40
        for line_num in range(first_line, last_line + 1):
            y = (line_num - first_line) * line_height
            self._gutter.create_text(
                gutter_width - 6,
                y + 3,
                anchor="ne",
                text=str(line_num),
                fill=theme.FG_DIM,
                font=font_obj,
            )

    def _setup_tags(self) -> None:
        """Configure text tags for syntax highlighting."""
        for tag, config in _TAG_CONFIG.items():
            self._text.tag_config(tag, **config)
        self._text.tag_config(
            "sel", background=theme.SELECTED_BG, foreground=theme.SELECTED_FG
        )

    def _setup_events(self) -> None:
        """Bind events for syntax highlighting and shortcuts."""
        self._text.bind("<KeyRelease>", self._on_key_release)
        self._text.bind("<Control-Return>", self._on_ctrl_enter)
        self._text.bind("<Control-a>", self._on_select_all)
        self._text.bind("<Button-3>", self._on_right_click)

    # ── Public API ───────────────────────────────────────────────────

    @property
    def text(self) -> str:
        """Return the full text of the editor."""
        return self._text.get("1.0", "end-1c")

    def get_text(self) -> str:
        """Return the full text (alias for ``.text``)."""
        return self.text

    def set_text(self, content: str) -> None:
        """Replace the entire editor content."""
        self._text.delete("1.0", END)
        self._text.insert("1.0", content)
        self._highlight_all()

    def get_selection_or_all(self) -> str:
        """Return selected text, or full text if nothing selected."""
        try:
            selected = self._text.get(SEL_FIRST, SEL_LAST)
            if selected.strip():
                return selected
        except TclError:
            pass
        return self.text

    def clear(self) -> None:
        """Clear all text."""
        self._text.delete("1.0", END)

    def append(self, text: str) -> None:
        """Append text at end of editor."""
        self._text.insert(END, text)
        self._highlight_all()

    def insert_at_cursor(self, text: str) -> None:
        """Insert *text* at current cursor position."""
        self._text.insert(INSERT, text)
        self._highlight_all()

    def set_focus(self) -> None:
        """Give keyboard focus to the editor."""
        self._text.focus_set()

    def set_execute_callback(self, callback) -> None:
        """Set callback for Ctrl+Enter (run query)."""
        self._execute_cb = callback

    # ── Syntax Highlighting ──────────────────────────────────────────

    def _on_key_release(self, event=None) -> None:
        """Re-highlight visible text after each keystroke."""
        self._redraw_gutter()
        if event and event.keysym in (
            "Up",
            "Down",
            "Left",
            "Right",
            "Home",
            "End",
            "Page_Up",
            "Page_Down",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
        ):
            return
        self._highlight_visible()

    def _highlight_visible(self) -> None:
        """Highlight only the currently visible text range."""
        index_y = self._text.yview()
        if index_y[0] == 0.0 and index_y[1] == 0.0:
            return

        first_line = int(self._text.index("@0,0 linestart").split(".")[0])
        total_lines = int(self._text.index("end-1c").split(".")[0])
        last_line = min(
            first_line + (total_lines - first_line) + 2
            if index_y[1] >= 1.0
            else first_line + max(int((index_y[1] - index_y[0]) * total_lines) + 2, 30),
            total_lines + 1,
        )

        self._highlight_range(f"{first_line}.0", f"{last_line}.end")

    def _highlight_all(self) -> None:
        """Highlight the entire document."""
        self._highlight_range("1.0", "end-1c")

    def _highlight_range(self, start: str, end: str) -> None:
        """Apply syntax highlighting to a range of text."""
        for tag in _TAG_CONFIG:
            self._text.tag_remove(tag, start, end)

        text = self._text.get(start, end)
        if not text:
            return

        base_line = int(start.split(".")[0])
        base_col = int(start.split(".")[1])

        def offset_to_index(offset: int) -> str:
            prefix = text[:offset]
            lines = prefix.count("\n")
            if lines == 0:
                col = base_col + offset
            else:
                last_nl = prefix.rfind("\n")
                col = offset - last_nl - 1
            return f"{base_line + lines}.{col}"

        for match in _COMMENT_RE.finditer(text):
            s, e = match.span()
            self._text.tag_add("comment", offset_to_index(s), offset_to_index(e))

        for match in _STRING_RE.finditer(text):
            s, e = match.span()
            self._text.tag_add("string", offset_to_index(s), offset_to_index(e))

        for match in _NUMBER_RE.finditer(text):
            s, e = match.span()
            self._text.tag_add("number", offset_to_index(s), offset_to_index(e))

        for match in _KEYWORD_RE.finditer(text):
            s, e = match.span()
            self._text.tag_add("keyword", offset_to_index(s), offset_to_index(e))

        for match in _FUNCTION_RE.finditer(text):
            s, e = match.span()
            self._text.tag_add("function", offset_to_index(s), offset_to_index(e))

    # ── Events ───────────────────────────────────────────────────────

    def _on_ctrl_enter(self, event=None):
        """Ctrl+Enter: execute query."""
        cb = getattr(self, "_execute_cb", None)
        if cb:
            cb()
        return "break"

    def _on_select_all(self, event=None):
        """Ctrl+A: select all text."""
        self._text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _on_right_click(self, event=None):
        """Show context menu."""
        menu = Menu(
            self._text,
            tearoff=0,
            bg=theme.HEADER_BG,
            fg=theme.FG,
            activebackground=theme.SELECTED_BG,
            activeforeground=theme.FG_HEADER,
            borderwidth=0,
        )
        menu.add_command(label="Cut", command=self._cut)
        menu.add_command(label="Copy", command=self._copy)
        menu.add_command(label="Paste", command=self._paste)
        menu.add_separator()
        menu.add_command(
            label="Select All",
            command=lambda: self._text.tag_add("sel", "1.0", "end-1c"),
        )
        menu.add_command(label="Clear", command=self.clear)
        try:
            if event is not None:
                menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _cut(self):
        self._text.event_generate("<<Cut>>")

    def _copy(self):
        self._text.event_generate("<<Copy>>")

    def _paste(self):
        self._text.event_generate("<<Paste>>")
