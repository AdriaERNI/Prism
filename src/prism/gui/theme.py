"""Dark theme for Prism GUI — pixel-accurate DBeaver dark theme replication.

All colours, fonts, and ttk styles are centralised here so the rest of
the GUI never hardcodes visual values.

Colour values were extracted by analysing a DBeaver SQL editor screenshot
with Qwen3-VL-8B-Instruct and then refined for Tkinter's rendering.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ── Colour Palette (DBeaver Dark Theme) ──────────────────────────────

# Surfaces — DBeaver uses a unified dark background with subtle variations
BG = "#2e3436"  # main window / editor / results background
PANEL_BG = "#2e3436"  # sidebar background (same as main in DBeaver dark)
EDITOR_BG = "#2e3436"  # SQL editor background
RESULT_BG = "#2e3436"  # results table background (odd rows)
RESULT_ALT = "#3b4252"  # zebra-stripe alternate row (even rows)
HEADER_BG = "#3b4252"  # table header / column headers
TAB_BAR_BG = "#2e3436"  # tab bar above editor (unified with main)
TOOLBAR_BG = "#2e3436"  # toolbar background (unified)
STATUS_BG = "#2e3436"  # status bar background
HOVER_BG = "#3b4252"  # hover highlight for buttons/items
SELECTED_BG = "#4c78a8"  # selected item highlight (blue-gray)
SELECTED_FG = "#ffffff"  # selected item text

# Text
FG = "#d3d7cf"  # default text (light gray)
FG_DIM = "#888888"  # comments / placeholders / line numbers
FG_HEADER = "#ffffff"  # column headers / tab labels
FG_STATUS = "#d3d7cf"  # status bar text
FG_ERROR = "#f44747"  # errors
FG_SUCCESS = "#a3be8c"  # success messages (light green)
FG_WARNING = "#ebcb8b"  # warnings (amber)

# Syntax highlighting — DBeaver dark theme
SYNTAX_KEYWORD = "#88c0d0"  # SELECT, FROM, WHERE... (cyan)
SYNTAX_STRING = "#a3be8c"  # 'literal strings' (light green)
SYNTAX_NUMBER = "#b08ead"  # 42, 3.14 (muted purple)
SYNTAX_COMMENT = "#616e88"  # -- comments (muted blue-gray)
SYNTAX_FUNC = "#ebcb8b"  # COUNT(), SUM()... (amber)
SYNTAX_OPERATOR = "#d3d7cf"  # =, <>, AND, OR
SYNTAX_DEFAULT = "#d3d7cf"  # default text

# Borders & Separators
BORDER = "#4c78a8"  # separator lines (blue-gray, same as selection)
BORDER_DIM = "#3b4252"  # subtle gridlines in tables

# ── Fonts ─────────────────────────────────────────────────────────────

FONT_FAMILY = "Consolas"  # monospace editor
FONT_UI = "Segoe UI"  # UI text
FONT_SIZE = 11
FONT_SIZE_SM = 9  # status bar / tree / tabs


def font_available(family: str) -> bool:
    """Check if a font family is available on this system."""
    try:
        import tkinter.font as tkfont

        root = tk._default_root  # type: ignore[attr-defined]
        if root is None:
            return False
        return family in tkfont.families(root)
    except Exception:
        return False


def editor_font() -> tuple[str, int]:
    """Return the best available monospace font."""
    for f in (FONT_FAMILY, "Cascadia Mono", "DejaVu Sans Mono", "Courier New"):
        if font_available(f):
            return (f, FONT_SIZE)
    return ("Courier", FONT_SIZE)


def ui_font() -> tuple[str, int]:
    """Return the best available UI font."""
    for f in (FONT_UI, "Helvetica", "DejaVu Sans", "Arial"):
        if font_available(f):
            return (f, FONT_SIZE)
    return ("TkDefaultFont", FONT_SIZE)


def ui_font_sm() -> tuple[str, int]:
    """Return the small UI font for status bar / tree / tabs."""
    for f in (FONT_UI, "Helvetica", "DejaVu Sans", "Arial"):
        if font_available(f):
            return (f, FONT_SIZE_SM)
    return ("TkDefaultFont", FONT_SIZE_SM)


def apply_theme(root: tk.Tk) -> None:
    """Configure the root window and ttk styles with the DBeaver dark theme.

    Must be called once after ``tk.Tk()`` is created and before any
    widgets are instantiated.
    """
    root.configure(bg=BG)

    style = ttk.Style(root)

    # Use 'clam' as the base theme — most customisable across platforms
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    # ── General widget styles ────────────────────────────────────────
    style.configure(
        ".",
        background=BG,
        foreground=FG,
        bordercolor=BORDER_DIM,
        lightcolor=BORDER_DIM,
        darkcolor=BORDER_DIM,
        troughcolor=PANEL_BG,
        focuscolor=SELECTED_BG,
    )
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL_BG)
    style.configure("Toolbar.TFrame", background=TOOLBAR_BG)
    style.configure("TabBar.TFrame", background=TAB_BAR_BG)
    style.configure("Status.TFrame", background=STATUS_BG)
    style.configure("Separator.TFrame", background=BORDER, height=1)

    # ── Labels ───────────────────────────────────────────────────────
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=PANEL_BG, foreground=FG)
    style.configure("Toolbar.TLabel", background=TOOLBAR_BG, foreground=FG)
    style.configure("Status.TLabel", background=STATUS_BG, foreground=FG_STATUS)
    style.configure("StatusError.TLabel", background=STATUS_BG, foreground=FG_ERROR)
    style.configure("StatusSuccess.TLabel", background=STATUS_BG, foreground=FG_SUCCESS)
    style.configure("Header.TLabel", background=HEADER_BG, foreground=FG_HEADER)
    style.configure("TabBar.TLabel", background=TAB_BAR_BG, foreground=FG)
    style.configure("TabActive.TLabel", background=BG, foreground=FG_HEADER)
    style.configure("TabInactive.TLabel", background=TAB_BAR_BG, foreground=FG_DIM)

    # ── Buttons ───────────────────────────────────────────────────────
    style.configure(
        "TButton",
        background=TOOLBAR_BG,
        foreground=FG,
        borderwidth=0,
        focuscolor=SELECTED_BG,
        padding=(6, 3),
    )
    style.map(
        "TButton",
        background=[("active", HOVER_BG), ("pressed", SELECTED_BG)],
        foreground=[("disabled", FG_DIM)],
    )

    # Accent button (Execute)
    style.configure(
        "Accent.TButton",
        background="#4c78a8",
        foreground="#ffffff",
        borderwidth=0,
        padding=(10, 4),
    )
    style.map(
        "Accent.TButton",
        background=[("active", "#5d8ab3"), ("pressed", "#3a5f87")],
        foreground=[("disabled", FG_DIM)],
    )

    # Flat icon button (toolbar)
    style.configure(
        "Icon.TButton",
        background=TOOLBAR_BG,
        foreground=FG,
        borderwidth=0,
        padding=(4, 3),
    )
    style.map(
        "Icon.TButton",
        background=[("active", HOVER_BG), ("pressed", SELECTED_BG)],
    )

    # ── Entry ─────────────────────────────────────────────────────────
    style.configure(
        "TEntry",
        fieldbackground=EDITOR_BG,
        foreground=FG,
        borderwidth=1,
        bordercolor=BORDER_DIM,
        insertcolor=FG,
    )
    style.map("TEntry", bordercolor=[("focus", BORDER)])

    # ── Treeview (results table + database navigator) ─────────────────
    style.configure(
        "Treeview",
        background=RESULT_BG,
        foreground=FG,
        fieldbackground=RESULT_BG,
        borderwidth=0,
        rowheight=22,
    )
    style.configure(
        "Treeview.Heading",
        background=HEADER_BG,
        foreground=FG_HEADER,
        borderwidth=1,
        bordercolor=BORDER_DIM,
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", SELECTED_BG)],
        foreground=[("selected", SELECTED_FG)],
    )
    style.map("Treeview.Heading", background=[("active", HOVER_BG)])

    # ── Scrollbar ─────────────────────────────────────────────────────
    style.configure(
        "TScrollbar",
        background=PANEL_BG,
        troughcolor=PANEL_BG,
        borderwidth=0,
        arrowcolor=FG,
    )
    style.map("TScrollbar", background=[("active", HOVER_BG)])

    # ── Notebook (tabs) ───────────────────────────────────────────────
    style.configure("TNotebook", background=TAB_BAR_BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=TAB_BAR_BG,
        foreground=FG_DIM,
        padding=(12, 5),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG), ("active", HOVER_BG)],
        foreground=[("selected", FG)],
    )

    # ── PanedWindow (resizable splits) ───────────────────────────────
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=4, background=BORDER_DIM)

    # ── Menu ──────────────────────────────────────────────────────────
    root.option_add("*Menu.background", HEADER_BG)
    root.option_add("*Menu.foreground", FG)
    root.option_add("*Menu.activeBackground", SELECTED_BG)
    root.option_add("*Menu.activeForeground", FG_HEADER)
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.font", ui_font_sm())
