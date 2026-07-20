"""Toolbar widget — DBeaver-style toolbar with all action buttons.

Replicates the DBeaver toolbar layout:
  [New] [Open] [Save] | [Connect] [Disconnect] [Refresh] | [SQL] [Execute] [Cancel] [Clear] | [Namespace: USER]

Uses Unicode symbols for icons since Tkinter has no native icon support
without PIL image assets.
"""

from __future__ import annotations

from tkinter import LEFT, X, Frame, Label, ttk

from prism.gui import theme


class Toolbar(Frame):
    """DBeaver-style toolbar with action buttons."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=theme.TOOLBAR_BG, height=34, **kwargs)
        self.pack_propagate(False)
        self._ns_var = None  # tk.StringVar, set in _setup_widgets
        self._setup_widgets()

    def _setup_widgets(self) -> None:
        """Create toolbar buttons left-to-right."""
        # ── File actions ──────────────────────────────────────────────
        self._btn_new = self._icon_button("New", "📄", self._on_new)
        self._btn_open = self._icon_button("Open", "📂", self._on_open)
        self._btn_save = self._icon_button("Save", "💾", self._on_save)

        self._separator()

        # ── Connection actions ────────────────────────────────────────
        self._btn_connect = self._icon_button("Connect", "🔌", self._on_connect)
        self._btn_disconnect = self._icon_button("Disconnect", "⏏", self._on_disconnect)
        self._btn_refresh = self._icon_button("Refresh", "🔄", self._on_refresh)

        self._separator()

        # ── Query actions ─────────────────────────────────────────────
        self._btn_sql = self._icon_button("New SQL", "SQL", self._on_new_sql)

        # Execute (accent button)
        self._btn_execute = ttk.Button(
            self,
            text="▶ Execute",
            style="Accent.TButton",
            command=self._on_execute,
        )
        self._btn_execute.pack(side=LEFT, padx=(4, 2), pady=3)

        self._btn_cancel = ttk.Button(
            self,
            text="■ Cancel",
            style="Icon.TButton",
            state="disabled",
            command=self._on_cancel,
        )
        self._btn_cancel.pack(side=LEFT, padx=2, pady=3)

        self._btn_clear = ttk.Button(
            self,
            text="Clear",
            style="Icon.TButton",
            command=self._on_clear,
        )
        self._btn_clear.pack(side=LEFT, padx=2, pady=3)

        self._separator()

        # ── Auto-commit indicator ────────────────────────────────────
        Label(
            self,
            text="Auto",
            background=theme.TOOLBAR_BG,
            foreground=theme.FG_DIM,
            font=theme.ui_font_sm(),
        ).pack(side=LEFT, padx=(4, 2))
        Label(
            self,
            text="✓",
            background=theme.TOOLBAR_BG,
            foreground=theme.FG_SUCCESS,
            font=theme.ui_font_sm(),
        ).pack(side=LEFT, padx=(0, 8))

        self._separator()

        # ── Spacer + Namespace selector ───────────────────────────────
        spacer = Frame(self, background=theme.TOOLBAR_BG)
        spacer.pack(side=LEFT, fill=X, expand=True)

        Label(
            self,
            text="Namespace:",
            background=theme.TOOLBAR_BG,
            foreground=theme.FG,
            font=theme.ui_font_sm(),
        ).pack(side=LEFT, padx=(4, 2))

        from prism.settings import settings

        import tkinter as tk

        self._ns_var = tk.StringVar(value=settings.iris_namespace or "USER")
        self._ns_entry = ttk.Entry(self, textvariable=self._ns_var, width=10)
        self._ns_entry.pack(side=LEFT, padx=(0, 8), pady=3)

    def _icon_button(self, tooltip: str, icon: str, command) -> ttk.Button:
        """Create a flat icon button."""
        btn = ttk.Button(
            self,
            text=icon,
            style="Icon.TButton",
            command=command,
        )
        btn.pack(side=LEFT, padx=1, pady=3)
        return btn

    def _separator(self) -> None:
        """Add a vertical separator between button groups."""
        Frame(self, background=theme.BORDER_DIM, width=1).pack(
            side=LEFT, fill="y", padx=4, pady=4
        )

    # ── Callbacks (set by app.py) ─────────────────────────────────────

    def set_callbacks(
        self,
        on_new=None,
        on_open=None,
        on_save=None,
        on_connect=None,
        on_disconnect=None,
        on_refresh=None,
        on_new_sql=None,
        on_execute=None,
        on_cancel=None,
        on_clear=None,
    ) -> None:
        """Wire up toolbar button callbacks."""
        self._cb_new = on_new
        self._cb_open = on_open
        self._cb_save = on_save
        self._cb_connect = on_connect
        self._cb_disconnect = on_disconnect
        self._cb_refresh = on_refresh
        self._cb_new_sql = on_new_sql
        self._cb_execute = on_execute
        self._cb_cancel = on_cancel
        self._cb_clear = on_clear

    @property
    def namespace_var(self):
        """Return the namespace StringVar."""
        return self._ns_var

    # ── Button handlers (delegate to callbacks) ─────────────────────────

    def _on_new(self):
        cb = getattr(self, "_cb_new", None)
        if cb:
            cb()

    def _on_open(self):
        cb = getattr(self, "_cb_open", None)
        if cb:
            cb()

    def _on_save(self):
        cb = getattr(self, "_cb_save", None)
        if cb:
            cb()

    def _on_connect(self):
        cb = getattr(self, "_cb_connect", None)
        if cb:
            cb()

    def _on_disconnect(self):
        cb = getattr(self, "_cb_disconnect", None)
        if cb:
            cb()

    def _on_refresh(self):
        cb = getattr(self, "_cb_refresh", None)
        if cb:
            cb()

    def _on_new_sql(self):
        cb = getattr(self, "_cb_new_sql", None)
        if cb:
            cb()

    def _on_execute(self):
        cb = getattr(self, "_cb_execute", None)
        if cb:
            cb()

    def _on_cancel(self):
        cb = getattr(self, "_cb_cancel", None)
        if cb:
            cb()

    def _on_clear(self):
        cb = getattr(self, "_cb_clear", None)
        if cb:
            cb()

    # ── State management ────────────────────────────────────────────────

    def set_running(self, running: bool) -> None:
        """Toggle execute/cancel button states."""
        if running:
            self._btn_execute.config(state="disabled")
            self._btn_cancel.config(state="normal")
        else:
            self._btn_execute.config(state="normal")
            self._btn_cancel.config(state="disabled")
