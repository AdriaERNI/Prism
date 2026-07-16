"""Output formatting: JSON (default) or TOON.

Shared by both CLI commands and the MCP ``@logged_tool`` decorator.
"""

from __future__ import annotations

import json

import typer

from prism.settings import settings

VALID_FORMATS = ("json", "toon")

# Module-level format state set by the CLI global callback and read by commands.
_output_format: str = settings.prism_output_format


def get_output_format() -> str:
    """Return the active output format (``json`` or ``toon``)."""
    return _output_format


def set_output_format(fmt: str) -> None:
    """Set the active output format (called by the CLI callback).

    Validates *fmt* against the supported output formats.  If *fmt* is not
    a known format, prints a warning to stderr and keeps the default (json).
    """
    global _output_format
    fmt_lower = fmt.strip().lower()
    if fmt_lower not in VALID_FORMATS:
        typer.echo(
            f"Warning: unknown format '{fmt}'. "
            f"Supported formats: {', '.join(VALID_FORMATS)}. "
            f"Using '{_output_format}'.",
            err=True,
        )
        return
    _output_format = fmt_lower


def format_output(data: dict | list, fmt: str = "json") -> str:
    """Serialize *data* to the requested format string.

    If *fmt* is ``"toon"`` but the ``toons`` package is not installed,
    falls back to JSON with a warning on stderr instead of crashing.
    """
    if fmt == "toon":
        try:
            import toons
        except ImportError:
            typer.echo(
                "Warning: TOON format requires the 'toons' package. "
                "Install it with: pip install toons. "
                "Falling back to JSON.",
                err=True,
            )
            return json.dumps(data, indent=2, default=str)
        return toons.dumps(data)

    return json.dumps(data, indent=2, default=str)
