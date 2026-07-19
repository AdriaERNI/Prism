"""Dark theme for Prism GUI — DBeaver-inspired color palette and ttk styles.

This module centralises all colours, fonts, and widget style configuration
so that the rest of the GUI code never hardcodes visual values.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ── Colour Palette ────────────────────────────────────────────────────
# Inspired by DBeaver's dark theme.

# Surfaces
BG = "#1e1e1e"  # main window background
PANEL_BG = "#252526"  # sidebar / panels
EDITOR_BG = "#1e1e1e"  # SQL editor background
RESULT_BG = "#1e1e1e"  # results table background
RESULT_ALT = "#2a2a2a"  # zebra-stripe alternate row
HEADER_BG = "#3c3c3c"  # table header / toolbar
HOVER_BG = "#2d2d4e"  # hover highlight
SELECTED_BG = "#094771"  # selected item

# Text
FG = "#d4d4d4"  # default text
FG_DIM = "#858585"  # comments / placeholders
FG_HEADER = "#ffffff"  # column headers
FG_STATUS = "#cccccc"  # status bar text
FG_ERROR = "#f44747"  # errors
FG_SUCCESS = "#6a9955"  # success messages

# Syntax highlighting
SYNTAX_KEYWORD = "#569cd6"  # SELECT, FROM, WHERE...
SYNTAX_STRING = "#ce9178"  # 'literal strings'
SYNTAX_NUMBER = "#b5cea8"  # 42, 3.14
SYNTAX_COMMENT = "#6a9955"  # -- comments
SYNTAX_FUNC = "#dcdcaa"  # COUNT(), SUM()...
SYNTAX_OPERATOR = "#d4d4d4"  # =, <>, AND, OR
SYNTAX_DEFAULT = "#d4d4d4"

# Borders
BORDER = "#3c3c3c"
BORDER_DIM = "#2d2d2d"

# ── Fonts ─────────────────────────────────────────────────────────────

FONT_FAMILY = "Consolas"  # monospace editor (fallback Cascadia/DejaVu Sans Mono)
FONT_UI = "Segoe UI"  # UI text (fallback system default)
FONT_SIZE = 11
FONT_SIZE_SM = 9  # status bar / tree


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
    """Return the small UI font for status bar / tree."""
    for f in (FONT_UI, "Helvetica", "DejaVu Sans", "Arial"):
        if font_available(f):
            return (f, FONT_SIZE_SM)
    return ("TkDefaultFont", FONT_SIZE_SM)


def apply_theme(root: tk.Tk) -> None:
    """Configure the root window and ttk styles with the Prism dark theme.

    Must be called once after ``tk.Tk()`` is created and before any
    widgets are instantiated.
    """
    root.configure(bg=BG)

    style = ttk.Style(root)

    # Use 'clam' as the base theme — it's the most customisable across platforms
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass  # fall back to default theme

    # ── General widget styles ────────────────────────────────────────
    style.configure(
        ".",
        background=BG,
        foreground=FG,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        troughcolor=PANEL_BG,
        focuscolor=SELECTED_BG,
    )
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL_BG)
    style.configure("Header.TFrame", background=HEADER_BG)

    # ── Labels ───────────────────────────────────────────────────────
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=PANEL_BG, foreground=FG)
    style.configure("Status.TLabel", background=PANEL_BG, foreground=FG_STATUS)
    style.configure("StatusError.TLabel", background=PANEL_BG, foreground=FG_ERROR)
    style.configure("StatusSuccess.TLabel", background=PANEL_BG, foreground=FG_SUCCESS)
    style.configure("Header.TLabel", background=HEADER_BG, foreground=FG_HEADER)

    # ── Buttons ───────────────────────────────────────────────────────
    style.configure(
        "TButton",
        background=HEADER_BG,
        foreground=FG,
        borderwidth=0,
        focuscolor=SELECTED_BG,
        padding=(8, 4),
    )
    style.map(
        "TButton",
        background=[("active", HOVER_BG), ("pressed", SELECTED_BG)],
        foreground=[("disabled", FG_DIM)],
    )

    # Accent button (Execute)
    style.configure(
        "Accent.TButton",
        background="#0e639c",
        foreground="#ffffff",
        borderwidth=0,
        padding=(12, 5),
    )
    style.map(
        "Accent.TButton",
        background=[("active", "#1177bb"), ("pressed", "#094771")],
        foreground=[("disabled", FG_DIM)],
    )

    # ── Entry ─────────────────────────────────────────────────────────
    style.configure(
        "TEntry",
        fieldbackground=EDITOR_BG,
        foreground=FG,
        borderwidth=1,
        bordercolor=BORDER,
        insertcolor=FG,
    )
    style.map("TEntry", bordercolor=[("focus", "#0e639c")])

    # ── Treeview (results table + database navigator) ─────────────────
    style.configure(
        "Treeview",
        background=RESULT_BG,
        foreground=FG,
        fieldbackground=RESULT_BG,
        borderwidth=0,
        rowheight=24,
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
        foreground=[("selected", FG_HEADER)],
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
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=PANEL_BG,
        foreground=FG_DIM,
        padding=(16, 6),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG), ("active", HOVER_BG)],
        foreground=[("selected", FG)],
    )

    # ── PanedWindow (resizable splits) ───────────────────────────────
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=4, background=BORDER)

    # ── Menu ──────────────────────────────────────────────────────────
    root.option_add("*Menu.background", HEADER_BG)
    root.option_add("*Menu.foreground", FG)
    root.option_add("*Menu.activeBackground", SELECTED_BG)
    root.option_add("*Menu.activeForeground", FG_HEADER)
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.font", ui_font_sm())
