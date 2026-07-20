"""Status bar widget — DBeaver-style status bar at the bottom.

Shows:
- Connection status (colored dot + text)
- Current namespace
- Query result info (row count + execution time)
- Timezone indicator
"""

from __future__ import annotations

import datetime

from tkinter import LEFT, X, Frame, Label

from prism.gui import theme
from prism.iris.sdk.http import base_url


class StatusBar(Frame):
    """Bottom status bar showing connection info and execution state."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=theme.STATUS_BG, height=24)
        self.pack_propagate(False)
        self._setup_widgets()

    def _setup_widgets(self) -> None:
        # Connection indicator (colored dot)
        self._conn_dot = Label(
            self,
            text="●",
            foreground=theme.FG_DIM,
            background=theme.STATUS_BG,
            font=theme.ui_font_sm(),
        )
        self._conn_dot.pack(side=LEFT, padx=(8, 4))

        # Connection text
        self._conn_label = Label(
            self,
            text="Not connected",
            foreground=theme.FG_STATUS,
            background=theme.STATUS_BG,
            font=theme.ui_font_sm(),
        )
        self._conn_label.pack(side=LEFT, padx=(0, 12))

        # Namespace
        self._ns_label = Label(
            self,
            text="",
            foreground=theme.FG_STATUS,
            background=theme.STATUS_BG,
            font=theme.ui_font_sm(),
        )
        self._ns_label.pack(side=LEFT, padx=(0, 12))

        # Spacer
        spacer = Frame(self, background=theme.STATUS_BG)
        spacer.pack(side=LEFT, fill=X, expand=True)

        # Right-aligned status (query results)
        self._status_label = Label(
            self,
            text="Ready",
            foreground=theme.FG_STATUS,
            background=theme.STATUS_BG,
            font=theme.ui_font_sm(),
        )
        self._status_label.pack(side=LEFT, padx=(12, 8))

        # Timezone indicator
        tz = datetime.datetime.now(datetime.timezone.utc).astimezone()
        tz_name = tz.tzname() or "UTC"
        self._tz_label = Label(
            self,
            text=tz_name,
            foreground=theme.FG_DIM,
            background=theme.STATUS_BG,
            font=theme.ui_font_sm(),
        )
        self._tz_label.pack(side=LEFT, padx=(0, 8))

    # ── Public API ───────────────────────────────────────────────────

    def set_connected(self, connected: bool, namespace: str | None = None) -> None:
        """Update the connection indicator."""
        if connected:
            self._conn_dot.config(foreground=theme.FG_SUCCESS)
            url = base_url()
            ns = namespace or "USER"
            self._conn_label.config(text=f"Connected to {url}")
            self._ns_label.config(text=f"Namespace: {ns}")
        else:
            self._conn_dot.config(foreground=theme.FG_ERROR)
            self._conn_label.config(text="Not connected")
            self._ns_label.config(text="")

    def set_running(self, running: bool) -> None:
        """Show running indicator."""
        if running:
            self._status_label.config(
                text="Executing query...", foreground=theme.SYNTAX_KEYWORD
            )
        else:
            self._status_label.config(text="Ready", foreground=theme.FG_STATUS)

    def set_status(self, message: str, is_error: bool = False) -> None:
        """Set a status message."""
        color = theme.FG_ERROR if is_error else theme.FG_SUCCESS
        self._status_label.config(text=message, foreground=color)

    def set_namespace(self, namespace: str) -> None:
        """Update the namespace display."""
        self._ns_label.config(text=f"Namespace: {namespace}")
