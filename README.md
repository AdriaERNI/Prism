<div align="center">
  <img src="logo.svg" width="200" alt="Prism Logo" />
  
  # Prism
  
  **Prism lets AI see through IRIS.**
  
  MCP server and CLI for InterSystems IRIS development — SQL queries, document
  management, compilation, debugging, testing, and ObjectScript execution via
  the Atelier REST API.
  
  [![Documentation](https://img.shields.io/badge/docs-mkdocs-indigo)](https://adriaerni.github.io/Prism/)
  [![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/downloads/)
  [![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue)](LICENSE)
</div>

---

## Features

- **SQL** — Run queries, DDL, stored procedures against any IRIS namespace
- **Documents** — Upload, fetch, compile, and delete `.cls`, `.mac`, `.inc` files
- **Terminal** — Execute ObjectScript via native (SuperServer) or WebSocket backend
- **Debugging** — Interactive step-through debugger with breakpoints, variable inspection, and stack traces
- **Testing** — Run `%UnitTest` test classes, list test methods, view historical results
- **MCP Server** — Expose all tools to AI assistants (Claude Code, Claude Desktop, Cursor, GitHub Copilot)
- **Cast Plugins** — Extend Prism with custom commands from any Git repository
- **Cross-platform** — Windows installer, Linux/macOS via pip/uv

## Quick Start

```bash
# Install
uv sync

# Configure (or use environment variables)
uv run prism config -u _SYSTEM -p SYS -U http://localhost:52773 -n USER

# Run a SQL query
uv run prism sql "SELECT TOP 5 Name FROM %Dictionary.ClassDefinition"

# Start the MCP server
uv run prism serve
```

Need an IRIS instance? Start one with Docker:

```bash
docker run -d --name iris -p 52773:52773 -p 1972:1972 intersystemsdc/iris-community:latest
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `prism sql` | Run an SQL query |
| `prism terminal` | Run ObjectScript via native SuperServer |
| `prism ws` | Run ObjectScript via WebSocket |
| `prism put-doc` | Upload a file to IRIS |
| `prism get-doc` | Fetch a document from IRIS |
| `prism list-docs` | List source documents |
| `prism delete-doc` | Delete a document |
| `prism compile` | Compile documents |
| `prism info` | Server version and namespaces |
| `prism test` | Run unit test classes |
| `prism list-tests` | Discover test classes |
| `prism config` | View or edit settings |
| `prism cast` | Run custom commands from Git repos |
| `prism serve` | Start the MCP server |

Global option: `prism --format toon` for TOON output.

## Shell completion

Tab completion is available for bash, zsh, fish, and PowerShell:

```bash
prism --install-completion    # auto-detect shell
```

After running, restart your terminal. Then `prism conf` + Tab auto-completes
to `prism config`, `prism s` + Tab cycles through `sql` and `serve`, etc.

See the [commands overview](https://adriaerni.github.io/Prism/commands/) for details.

## MCP Tools

10 tools are always available, 2 workspace-gated (`put_document`, `put_and_compile`),
and 9 debug-gated (`debug_*`) — up to 21 total.

See the [full tool reference](https://adriaerni.github.io/Prism/mcp/tools/) for details.

## MCP Client Configuration

### Claude Code

Add to `~/.claude/settings.json` or `.claude/settings.json`:

```json
{
  "mcpServers": {
    "iris": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "iris": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/prism", "prism", "serve"]
    }
  }
}
```

### GitHub Copilot (VS Code)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "iris": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "iris": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_BASE_URL` | `http://localhost:52773` | IRIS instance URL |
| `IRIS_USERNAME` | `_SYSTEM` | Authentication username |
| `IRIS_PASSWORD` | `SYS` | Authentication password |
| `IRIS_NAMESPACE` | `USER` | Default namespace |
| `IRIS_WORKSPACE` | *(empty)* | Local directory for MCP file I/O tools |
| `IRIS_COMPILE_FLAGS` | `cuk` | Compiler flags |
| `IRIS_DEBUG_ENABLED` | `false` | Enable debug tools (`debug_*`) |
| `IRIS_TERMINAL_METHOD` | `native` | Terminal backend: `native` or `ws` |

See the [configuration guide](https://adriaerni.github.io/Prism/getting-started/configuration/) for all 21 settings.

## Project Structure

```
src/prism/
├── settings.py        # Pydantic settings (env, .env, config.json)
├── iris/
│   ├── sdk/            # HTTP client, workspace, debug protocols, terminal
│   └── api/            # Thin IRIS REST API wrappers (sql, docs, compile, debug)
├── mcp/               # MCP tools with @logged_tool decorator
│   ├── _decorator.py   # Logging + auto-discovery
│   ├── server.py       # FastMCP server
│   └── *.py            # One module per tool domain
├── cast/              # Cast plugin system (import-based Typer plugins)
│   └── manager.py      # Clone, import, cache, run commands
└── cli/               # Typer CLI commands (async wrappers)
```

## Testing

```bash
uv run pytest tests/unit/ -v                    # No IRIS needed (276 tests)
IRIS_BASE_URL=http://localhost:52773 \
  uv run pytest tests/integration/ -v            # Needs IRIS (72 tests)
uv run ruff check . && uv run ruff format --check .  # Lint
```

Full testing guide: [docs/testing.md](docs/testing.md)

## Releases

Prism follows a [Git Flow](https://nvie.com/posts/a-successful-git-branching-model/)
release workflow with two protected branches: `development` (active work)
and `main` (stable releases).

Download the latest Windows installer or standalone exe from
[GitHub Releases](https://github.com/AdriaERNI/Prism/releases).

| Artifact | Description |
|----------|-------------|
| `prism-X.Y.Z-setup.exe` | Windows installer (Inno Setup, adds to PATH) |
| `prism.exe` | Standalone Windows binary (PyInstaller) |
| `prism-X.Y.Z-py3-none-any.whl` | Python wheel (`pip install prism`) |

See the [release guide](https://adriaerni.github.io/Prism/releases/) for the
full release workflow, branch model, hotfix procedure, and CI pipeline details.

## Documentation

Full documentation at **[adriaerni.github.io/Prism](https://adriaerni.github.io/Prism/)**

## License

Copyright © 2026 Adria Sanchez.

Licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
You may use, modify, and distribute this software freely, including for
commercial purposes, as long as you share your source code under the same
license. SaaS/hosting providers must also share their source code (network
clause).

See [LICENSE](LICENSE) for full terms.