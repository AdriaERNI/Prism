"""`prism gui` — launch the tkinter SQL editor GUI."""

from __future__ import annotations

import typer


def gui(
    query: str = typer.Option(
        None,
        "--query",
        "-q",
        help="SQL query to pre-fill the editor with on startup.",
    ),
) -> None:
    """Launch the Prism GUI SQL editor (requires a display)."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        typer.echo(
            "Error: tkinter is not available. Install python3-tk "
            "(Linux) or ensure Tk is installed (macOS/Windows).",
            err=True,
        )
        raise typer.Exit(1)

    try:
        from prism.gui.app import launch
    except ImportError as exc:
        typer.echo(f"Error: cannot import GUI module: {exc}", err=True)
        raise typer.Exit(1)

    launch(initial_query=query)
