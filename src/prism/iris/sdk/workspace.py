"""Workspace path safety, file I/O, and validation helpers."""

from __future__ import annotations

import re
from pathlib import Path

from prism.config import IRIS_WORKSPACE

_DOC_NAME_RE = re.compile(
    r"^[A-Za-z%][A-Za-z0-9]*(\.[A-Za-z%][A-Za-z0-9]*)*\.[a-z][a-z0-9]*$"
)


def validate_doc_name(name: str) -> None:
    """Validate an IRIS document name format.

    Valid examples: ``MyApp.Person.cls``, ``Test.Utils.mac``, ``%Library.String.cls``
    Raises ``ValueError`` with an actionable message on invalid names.
    """
    if not _DOC_NAME_RE.match(name):
        raise ValueError(
            f"Invalid document name: {name!r}. "
            f"Expected format: 'Package.Name.ext' (e.g. 'MyApp.Person.cls')."
        )


def workspace_root() -> Path:
    """Return the resolved workspace root directory.

    Raises ``RuntimeError`` if ``IRIS_WORKSPACE`` is not configured.
    """
    if not IRIS_WORKSPACE:
        raise RuntimeError("IRIS_WORKSPACE is not configured")
    return Path(IRIS_WORKSPACE).resolve()


def resolve_safe(relative_path: str) -> Path:
    """Resolve *relative_path* inside the workspace, blocking directory traversal.

    Raises ``ValueError`` if the resolved path escapes the workspace root.
    """
    root = workspace_root()
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(
            f"Path escapes workspace: {relative_path!r} resolves to {resolved}"
        )
    return resolved


def save_content(path: Path, lines: list[str]) -> Path:
    """Write *lines* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    return path


def load_content(path: Path) -> list[str]:
    """Read *path* and return its content split into lines."""
    if not path.is_file():
        raise FileNotFoundError(
            f"File not found in workspace: {path.name}. "
            f"Write the file to the workspace before calling put_document."
        )
    return path.read_text().split("\n")
