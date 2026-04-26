"""Output formatting: JSON (default) or TOON.

Shared by both CLI commands and the MCP ``@logged_tool`` decorator.
"""

from __future__ import annotations

import json

from prism.settings import settings

# Module-level format state set by the CLI global callback and read by commands.
_output_format: str = settings.prism_output_format


def get_output_format() -> str:
    """Return the active output format (``json`` or ``toon``)."""
    return _output_format


def set_output_format(fmt: str) -> None:
    """Set the active output format (called by the CLI callback)."""
    global _output_format
    _output_format = fmt


def format_output(data: dict | list, fmt: str = "json") -> str:
    """Serialize *data* to the requested format string.

    Raises ``RuntimeError`` when *fmt* is ``"toon"`` but the optional
    ``toons`` package is not installed.
    """
    if fmt == "toon":
        try:
            import toons
        except ImportError:
            raise RuntimeError(
                "TOON format requires the 'toons' package: pip install prism-mcp[toon]"
            )
        return toons.dumps(data)

    return json.dumps(data, indent=2, default=str)
