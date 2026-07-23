"""MCP tool for reading files from the workspace.

Provides ``read_file`` — a tool that lets the chatbot agent read file
contents from the configured workspace (``IRIS_WORKSPACE``). This gives
the agent the ability to inspect source code, config files, documentation,
and any other text file within the project directory.

Security:
- Path traversal is blocked (paths are resolved within the workspace root)
- Binary files are detected and rejected with a helpful message
- File size is capped at 100K chars for the LLM context
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field

from prism.mcp._decorator import logged_tool

_MAX_FILE_CHARS = 100_000


def _is_binary(path: Path, sample_size: int = 8192) -> bool:
    """Heuristic: check if a file is binary by reading the first bytes.

    A file is considered binary if:
    - It contains a null byte (\\x00)
    - More than 20% of bytes are non-printable control characters
      (excluding common whitespace: tab, newline, carriage return)

    UTF-8 multibyte characters are NOT considered binary — only
    actual control characters and null bytes trigger the detection.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
        # If the chunk contains a null byte, it's likely binary
        if b"\x00" in chunk:
            return True
        # Check for high ratio of non-printable, non-whitespace bytes
        # Only count bytes < 32 that aren't tab(9), newline(10), CR(13)
        if chunk:
            control = sum(1 for b in chunk if b < 32 and b not in (9, 10, 13))
            if control / len(chunk) > 0.20:
                return True
    except OSError:
        pass
    return False


def _truncate_content(text: str, max_chars: int = _MAX_FILE_CHARS) -> str:
    """Truncate file content to fit within the LLM context."""
    if len(text) <= max_chars:
        return text
    # Try to cut at a line boundary
    cut = text.rfind("\n", 0, max_chars)
    if cut == -1 or cut < max_chars * 0.5:
        cut = max_chars
    return text[:cut] + f"\n\n[... file truncated, {len(text) - cut} more chars]"


@logged_tool
async def read_file(
    path: Annotated[
        str,
        Field(
            description="Relative path to the file within the workspace. "
            "Examples: 'src/main.py', 'config/app.json', 'README.md'. "
            "Absolute paths outside the workspace are rejected."
        ),
    ],
    encoding: Annotated[
        str,
        Field(
            description="File encoding to use for reading. Default 'utf-8'. "
            "Use 'latin-1' for files with unknown encoding."
        ),
    ] = "utf-8",
) -> dict:
    """Read a file from the workspace and return its contents.

    The file must be inside the configured workspace directory
    (``IRIS_WORKSPACE``). Path traversal is blocked — relative paths
    like ``../etc/passwd`` are rejected.

    The tool detects binary files (images, executables, archives) and
    returns a message instead of garbled content. Text files are read
    with the specified encoding (default UTF-8).

    Use this tool to:
    - Read source code files for review or debugging
    - Inspect configuration files (JSON, YAML, .env, TOML)
    - Read documentation (Markdown, README, docs)
    - View log files or text output
    - Check file contents before pushing to IRIS

    The content is truncated at 100,000 characters for large files.
    The truncation point is at a line boundary when possible.
    """
    from prism.iris.sdk.workspace import resolve_safe, workspace_root

    try:
        root = workspace_root()
    except RuntimeError:
        return {
            "content": "",
            "path": path,
            "error": "IRIS_WORKSPACE is not configured. Set it to enable file reading.",
            "size": 0,
        }

    try:
        file_path = resolve_safe(path)
    except ValueError as exc:
        return {
            "content": "",
            "path": path,
            "error": str(exc),
            "size": 0,
        }

    if not file_path.exists():
        return {
            "content": "",
            "path": path,
            "error": f"File not found: {path}. "
            f"The file does not exist in the workspace "
            f"({root}).",
            "size": 0,
        }

    if file_path.is_dir():
        return {
            "content": "",
            "path": path,
            "error": f"Path is a directory, not a file: {path}. "
            f"Use list_files to list directory contents.",
            "size": 0,
        }

    # Check for binary files
    if _is_binary(file_path):
        return {
            "content": "",
            "path": path,
            "error": "File appears to be binary (image, executable, "
            "or archive). This tool only reads text files.",
            "size": file_path.stat().st_size,
            "is_binary": True,
        }

    try:
        content = file_path.read_text(encoding=encoding)
    except UnicodeDecodeError:
        # Try with a more permissive encoding
        try:
            content = file_path.read_text(encoding="latin-1")
        except OSError as exc:
            return {
                "content": "",
                "path": path,
                "error": f"Failed to read file: {exc}",
                "size": 0,
            }
    except OSError as exc:
        return {
            "content": "",
            "path": path,
            "error": f"Failed to read file: {exc}",
            "size": 0,
        }

    truncated = _truncate_content(content)
    return {
        "content": truncated,
        "path": str(file_path.relative_to(root)),
        "absolute_path": str(file_path),
        "size": len(content),
        "lines": content.count("\n") + 1,
        "truncated": len(content) > _MAX_FILE_CHARS,
        "encoding": encoding,
    }


@logged_tool
async def list_files(
    path: Annotated[
        str | None,
        Field(
            description="Relative directory path within the workspace to list. "
            "Defaults to the workspace root. "
            "Examples: '', 'src', 'tests/unit'."
        ),
    ] = None,
    pattern: Annotated[
        str | None,
        Field(
            description="Glob pattern to filter files. "
            "Examples: '*.py', '*.json', '**/*.cls'. "
            "If omitted, all files and directories are listed."
        ),
    ] = None,
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of results to return. Default 200.",
            gt=0,
            le=1000,
        ),
    ] = 200,
) -> dict:
    """List files and directories in the workspace.

    Returns a structured listing of files and subdirectories within the
    specified path. Use glob patterns to filter results (e.g. ``*.py``,
    ``**/*.cls``).

    Use this tool to:
    - Discover what files exist in the project
    - Find source files for a specific task
    - Browse directory structure before reading specific files
    - Check if a file exists before writing or compiling it
    """
    from prism.iris.sdk.workspace import resolve_safe, workspace_root

    try:
        root = workspace_root()
    except RuntimeError:
        return {
            "files": [],
            "path": path or "",
            "error": "IRIS_WORKSPACE is not configured.",
            "count": 0,
        }

    try:
        target = resolve_safe(path or ".") if path else root
    except ValueError as exc:
        return {
            "files": [],
            "path": path or "",
            "error": str(exc),
            "count": 0,
        }

    if not target.exists():
        return {
            "files": [],
            "path": path or "",
            "error": f"Path not found: {path}",
            "count": 0,
        }

    if not target.is_dir():
        return {
            "files": [],
            "path": path or "",
            "error": f"Not a directory: {path}",
            "count": 0,
        }

    # Collect files
    files: list[dict] = []
    if pattern:
        # Use glob pattern
        for p in sorted(target.glob(pattern))[:max_results]:
            rel = p.relative_to(root)
            files.append(
                {
                    "name": p.name,
                    "path": str(rel).replace("\\", "/"),
                    "is_dir": p.is_dir(),
                    "size": p.stat().st_size if p.is_file() else 0,
                }
            )
    else:
        # List directory contents
        for p in sorted(target.iterdir())[:max_results]:
            rel = p.relative_to(root)
            files.append(
                {
                    "name": p.name,
                    "path": str(rel).replace("\\", "/"),
                    "is_dir": p.is_dir(),
                    "size": p.stat().st_size if p.is_file() else 0,
                }
            )

    return {
        "files": files,
        "path": path or ".",
        "count": len(files),
        "truncated": len(files) >= max_results,
    }
