"""``prism install`` — register Prism MCP server in external tools.

Supports Claude Code, Codex CLI, OpenCode, VS Code Copilot, and Hermes Agent.
Before writing anything, the user sees exactly which files will be
created or modified and what content will be added.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

# ── Service identifiers ──────────────────────────────────────────────

CLAUDE = "claude"
CODEX = "codex"
OPENCODE = "opencode"
HERMES = "hermes"
VSCODE = "vscode"

ALL_SERVICES = (CLAUDE, CODEX, OPENCODE, VSCODE, HERMES)

SERVICE_NAMES = {
    CLAUDE: "Claude Code",
    CODEX: "Codex CLI",
    OPENCODE: "OpenCode",
    VSCODE: "VS Code Copilot",
    HERMES: "Hermes Agent",
}

# ── Transport helpers ─────────────────────────────────────────────────

STDIO_COMMAND = "prism"
STDIO_ARGS = ["serve", "--transport", "stdio"]


def _default_url(port: int) -> str:
    """Return the default Prism MCP URL for *port*."""
    return f"http://localhost:{port}/mcp"


def _home() -> Path:
    """Return the user home directory."""
    return Path(os.path.expanduser("~"))


def _config_path(service: str) -> Path:
    """Return the config file path for *service* on the current OS.

    Linux / macOS / Windows paths are handled for each service.
    """
    home = _home()

    if service == CLAUDE:
        # ~/.claude.json (user scope, all platforms)
        return home / ".claude.json"

    if service == CODEX:
        # ~/.codex/config.toml (all platforms)
        return home / ".codex" / "config.toml"

    if service == OPENCODE:
        # ~/.config/opencode/opencode.json (Linux/macOS)
        # %APPDATA%\opencode\opencode.json (Windows)
        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
            return Path(appdata) / "opencode" / "opencode.json"
        xdg = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
        return Path(xdg) / "opencode" / "opencode.json"

    if service == VSCODE:
        # VS Code user settings.json (mcp section)
        # Linux: ~/.config/Code/User/settings.json
        # macOS: ~/Library/Application Support/Code/User/settings.json
        # Windows: %APPDATA%\Code\User\settings.json
        if sys.platform == "darwin":
            return home / "Library" / "Application Support" / "Code" / "User" / "settings.json"
        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
            return Path(appdata) / "Code" / "User" / "settings.json"
        xdg = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
        return Path(xdg) / "Code" / "User" / "settings.json"

    if service == HERMES:
        # ~/.hermes/config.yaml (all platforms)
        hermes_home = os.environ.get("HERMES_HOME", str(home / ".hermes"))
        return Path(hermes_home) / "config.yaml"

    raise ValueError(f"Unknown service: {service}")


# ── Readers / Writers ────────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning {} on missing / malformed."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write *data* to *path* as pretty JSON, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_toml(path: Path) -> str:
    """Read a TOML file as raw text (returns '' if missing)."""
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _write_toml(path: Path, text: str) -> None:
    """Write raw TOML text to *path*, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_yaml(path: Path) -> str:
    """Read a YAML file as raw text (returns '' if missing)."""
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _write_yaml(path: Path, text: str) -> None:
    """Write raw YAML text to *path*, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ── Per-service patchers ──────────────────────────────────────────────

SERVER_NAME = "prism"


# ── Claude Code ──────────────────────────────────────────────────────


def _patch_claude(url: str | None) -> tuple[Path, str, str]:
    """Patch Claude Code's ``~/.claude.json``.

    Returns (path, action, description) where action is 'create' or 'modify'.
    """
    path = _config_path(CLAUDE)
    data = _read_json(path)
    servers = data.setdefault("mcpServers", {})

    action = "create" if not path.is_file() else "modify"
    if url:
        servers[SERVER_NAME] = {"type": "http", "url": url}
    else:
        servers[SERVER_NAME] = {
            "type": "stdio",
            "command": STDIO_COMMAND,
            "args": STDIO_ARGS,
        }

    return path, action, json.dumps(data, indent=2, sort_keys=True)


def _apply_claude(url: str | None) -> Path:
    """Write the Claude Code config."""
    path = _config_path(CLAUDE)
    data = _read_json(path)
    servers = data.setdefault("mcpServers", {})
    if url:
        servers[SERVER_NAME] = {"type": "http", "url": url}
    else:
        servers[SERVER_NAME] = {
            "type": "stdio",
            "command": STDIO_COMMAND,
            "args": STDIO_ARGS,
        }
    _write_json(path, data)
    return path


# ── Codex CLI ─────────────────────────────────────────────────────────


def _patch_codex(url: str | None) -> tuple[Path, str, str]:
    """Patch Codex CLI's ``~/.codex/config.toml``.

    Codex uses TOML format.  We do a simple section replacement.
    """
    path = _config_path(CODEX)
    existing = _read_toml(path)
    action = "create" if not path.is_file() else "modify"

    if url:
        section = f"""[mcp_servers.{SERVER_NAME}]
url = "{url}"
"""
    else:
        section = f"""[mcp_servers.{SERVER_NAME}]
command = "{STDIO_COMMAND}"
args = {json.dumps(STDIO_ARGS)}
"""

    # Remove any existing [mcp_servers.prism] block and append fresh
    lines = existing.splitlines()
    filtered: list[str] = []
    inside_prism = False
    for line in lines:
        stripped = line.strip()
        if stripped == f"[mcp_servers.{SERVER_NAME}]":
            inside_prism = True
            continue
        if inside_prism and stripped.startswith("[") and stripped.endswith("]"):
            inside_prism = False
        if not inside_prism:
            filtered.append(line)

    result = "\n".join(filtered).rstrip("\n")
    if result:
        result += "\n\n"
    result += section

    return path, action, result


def _apply_codex(url: str | None) -> Path:
    path, _, content = _patch_codex(url)
    _write_toml(path, content)
    return path


# ── OpenCode ─────────────────────────────────────────────────────────


def _patch_opencode(url: str | None) -> tuple[Path, str, str]:
    """Patch OpenCode's ``opencode.json``.

    Uses JSON with a ``mcp`` top-level key.
    Type is "remote" for HTTP transport, "local" for stdio.
    """
    path = _config_path(OPENCODE)
    data = _read_json(path)
    mcp = data.setdefault("mcp", {})

    action = "create" if not path.is_file() else "modify"
    if url:
        mcp[SERVER_NAME] = {"type": "remote", "url": url, "enabled": True}
    else:
        mcp[SERVER_NAME] = {
            "type": "local",
            "command": [STDIO_COMMAND, *STDIO_ARGS],
            "enabled": True,
        }

    return path, action, json.dumps(data, indent=2, sort_keys=True)


def _apply_opencode(url: str | None) -> Path:
    """Write the OpenCode config."""
    path = _config_path(OPENCODE)
    data = _read_json(path)
    mcp = data.setdefault("mcp", {})
    if url:
        mcp[SERVER_NAME] = {"type": "remote", "url": url, "enabled": True}
    else:
        mcp[SERVER_NAME] = {
            "type": "local",
            "command": [STDIO_COMMAND, *STDIO_ARGS],
            "enabled": True,
        }
    _write_json(path, data)
    return path


# ── VS Code Copilot ──────────────────────────────────────────────────


def _patch_vscode(url: str | None) -> tuple[Path, str, str]:
    """Patch VS Code's ``settings.json`` with MCP server config.

    VS Code Copilot uses the ``chat.mcp.servers`` setting in
    ``settings.json``.  HTTP transport uses ``url``, stdio uses
    ``command`` + ``args``.
    """
    path = _config_path(VSCODE)
    data = _read_json(path)
    servers = data.setdefault("chat.mcp.servers", {})

    action = "create" if not path.is_file() else "modify"
    if url:
        servers[SERVER_NAME] = {"type": "http", "url": url}
    else:
        servers[SERVER_NAME] = {
            "type": "stdio",
            "command": STDIO_COMMAND,
            "args": STDIO_ARGS,
        }

    return path, action, json.dumps(data, indent=2, sort_keys=True)


def _apply_vscode(url: str | None) -> Path:
    """Write the VS Code config."""
    path = _config_path(VSCODE)
    data = _read_json(path)
    servers = data.setdefault("chat.mcp.servers", {})
    if url:
        servers[SERVER_NAME] = {"type": "http", "url": url}
    else:
        servers[SERVER_NAME] = {
            "type": "stdio",
            "command": STDIO_COMMAND,
            "args": STDIO_ARGS,
        }
    _write_json(path, data)
    return path


# ── Hermes Agent ──────────────────────────────────────────────────────


def _patch_hermes(url: str | None) -> tuple[Path, str, str]:
    """Patch Hermes Agent's ``~/.hermes/config.yaml``.

    Uses YAML with a ``mcp_servers`` top-level key.
    Each server has a ``url`` (HTTP) or ``command``+``args`` (stdio).
    """
    path = _config_path(HERMES)
    existing = _read_yaml(path)
    action = "create" if not path.is_file() else "modify"

    if url:
        prism_block = f'mcp_servers:\n  {SERVER_NAME}:\n    url: "{url}"\n'
    else:
        prism_block = (
            f"mcp_servers:\n"
            f"  {SERVER_NAME}:\n"
            f'    command: "{STDIO_COMMAND}"\n'
            f"    args: {json.dumps(STDIO_ARGS)}\n"
        )

    if not existing:
        return path, action, prism_block

    # Try to parse and merge using a lightweight approach.
    # Since Hermes config.yaml is YAML, we try PyYAML if available,
    # otherwise fall back to text manipulation.
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(existing) or {}
        if not isinstance(data, dict):
            data = {}
        servers = data.setdefault("mcp_servers", {})
        if url:
            servers[SERVER_NAME] = {"url": url}
        else:
            servers[SERVER_NAME] = {"command": STDIO_COMMAND, "args": STDIO_ARGS}
        content = yaml.safe_dump(data, default_flow_style=False, sort_keys=True)
        return path, action, content
    except ImportError:
        # No PyYAML — do text-based block replacement
        lines = existing.splitlines()
        filtered: list[str] = []
        inside_prism = False
        for line in lines:
            stripped = line.strip()
            if stripped == f"  {SERVER_NAME}:":
                inside_prism = True
                continue
            if inside_prism and not stripped.startswith(" ") and stripped:
                inside_prism = False
            if not inside_prism:
                filtered.append(line)

        result = "\n".join(filtered).rstrip("\n")
        if "mcp_servers:" not in result:
            result = result.rstrip("\n") + "\n\n" + prism_block
        else:
            # Insert prism entry after the mcp_servers: line
            new_lines: list[str] = []
            for line in result.splitlines():
                new_lines.append(line)
                if line.strip() == "mcp_servers:":
                    new_lines.append(f"  {SERVER_NAME}:")
                    if url:
                        new_lines.append(f'    url: "{url}"')
                    else:
                        new_lines.append(f'    command: "{STDIO_COMMAND}"')
                        new_lines.append(f"    args: {json.dumps(STDIO_ARGS)}")
            result = "\n".join(new_lines) + "\n"

        return path, action, result


def _apply_hermes(url: str | None) -> Path:
    path, _, content = _patch_hermes(url)
    _write_yaml(path, content)
    return path


# ── Dispatch ──────────────────────────────────────────────────────────

PATCHERS = {
    CLAUDE: _patch_claude,
    CODEX: _patch_codex,
    OPENCODE: _patch_opencode,
    VSCODE: _patch_vscode,
    HERMES: _patch_hermes,
}

APPLIERS = {
    CLAUDE: _apply_claude,
    CODEX: _apply_codex,
    OPENCODE: _apply_opencode,
    VSCODE: _apply_vscode,
    HERMES: _apply_hermes,
}

# ── CLI ──────────────────────────────────────────────────────────────

VALID_TRANSPORTS = ("http", "stdio")


def install(
    service: str = typer.Argument(
        "all",
        help="Service to configure: claude, codex, opencode, vscode, hermes, or all.",
    ),
    port: int = typer.Option(
        3000, "--port", "-p", help="Port the Prism MCP server listens on (HTTP transport only)."
    ),
    url: str | None = typer.Option(
        None,
        "--url",
        help="Override the MCP server URL (default: http://localhost:PORT/mcp).",
    ),
    transport: str = typer.Option(
        "http",
        "--transport",
        "-t",
        help="Transport type: 'http' (default, requires 'prism serve' running) "
        "or 'stdio' (spawns 'prism serve --transport stdio' as a subprocess).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Set up Prism MCP server in external AI tools.

    Registers Prism as an MCP server in the target tool's config file.
    By default configures all supported services (Claude Code, Codex CLI,
    OpenCode, VS Code Copilot, Hermes Agent).

    \\b
    Examples:
        prism setup              # Set up all services (HTTP)
        prism setup claude       # Set up only Claude Code
        prism setup --transport stdio  # Use stdio (no port needed)
        prism setup --port 8080  # Use a different HTTP port
        prism setup vscode --transport stdio  # VS Code with stdio

    Before writing anything, shows which files will be created or modified
    and what content will be added.  Use --yes to skip the confirmation.
    """
    service = service.lower().strip()

    if service == "all":
        services = list(ALL_SERVICES)
    elif service in ALL_SERVICES:
        services = [service]
    else:
        typer.echo(
            f"Unknown service: {service!r}. Choose from: {', '.join(ALL_SERVICES)}, or 'all'.",
            err=True,
        )
        raise typer.Exit(code=1)

    if transport not in VALID_TRANSPORTS:
        typer.echo(
            f"Unknown transport: {transport!r}. Choose from: {', '.join(VALID_TRANSPORTS)}",
            err=True,
        )
        raise typer.Exit(code=1)

    # For stdio transport, url is None (no HTTP endpoint)
    mcp_url = url or _default_url(port) if transport == "http" else None

    # ── Preview ──────────────────────────────────────────────────
    typer.echo("")
    typer.echo("Prism MCP Setup Preview")
    typer.echo("=" * 60)
    if mcp_url:
        typer.echo("  Transport: HTTP")
        typer.echo(f"  MCP URL: {mcp_url}")
    else:
        typer.echo("  Transport: stdio")
        typer.echo(f"  Command: {STDIO_COMMAND} {' '.join(STDIO_ARGS)}")
    typer.echo(f"  Services: {', '.join(SERVICE_NAMES[s] for s in services)}")
    typer.echo("")

    plans: list[tuple[str, Path, str, str]] = []
    for svc in services:
        patcher = PATCHERS[svc]
        path, action, content = patcher(mcp_url)
        plans.append((svc, path, action, content))

    for svc, path, action, content in plans:
        typer.echo(f"  [{action.upper()}] {SERVICE_NAMES[svc]}")
        typer.echo(f"    File: {path}")
        typer.echo(f"    Server name: {SERVER_NAME}")
        typer.echo("    Content to write:")
        for line in content.splitlines():
            typer.echo(f"      {line}")
        typer.echo("")

    # ── Confirm ──────────────────────────────────────────────────
    if not yes:
        typer.echo("The files above will be created or modified.")
        confirm = typer.confirm("Proceed?", default=True)
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit()
        typer.echo("")

    # ── Apply ────────────────────────────────────────────────────
    for svc, path, _, _ in plans:
        applier = APPLIERS[svc]
        applier(mcp_url)
        typer.echo(f"  ✓ {SERVICE_NAMES[svc]} → {path}")

    typer.echo("")
    typer.echo("Done! Prism MCP server has been configured.")
    typer.echo("")
    if mcp_url:
        typer.echo("Make sure 'prism serve' is running before using the MCP tools.")
        typer.echo(f"Start it with:  prism serve --port {port}")
    else:
        typer.echo(
            "stdio transport: the MCP client will spawn 'prism serve --transport stdio' automatically."
        )
