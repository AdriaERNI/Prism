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
- **Code Indexing** — Build a compact, token-efficient index of all classes using `%Dictionary` metadata
- **MCP Server** — Expose all tools to AI assistants (Claude Code, Claude Desktop, Cursor, GitHub Copilot)
- **GUI** — tkinter SQL editor with database navigator, inline-editable results grid, and multi-tab editing
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

## Installation

### Windows (recommended)

Download the latest installer from
[GitHub Releases](https://github.com/AdriaERNI/Prism/releases/latest):

- **`prism-X.Y.Z-setup.exe`** — Inno Setup installer. Installs `prism.exe`
  to `C:\Program Files\prism\` and adds it to the system `PATH`.
- **`prism.exe`** — Standalone PyInstaller binary. Drop it anywhere on your
  `PATH`.

After installing, open a **new terminal** and verify:

```powershell
prism --help
prism info
```

### Linux / macOS (development)

```bash
git clone https://github.com/AdriaERNI/Prism.git
cd Prism
uv sync
uv run prism --help
```

Or install via pip:

```bash
pip install prism
```

See the [installation guide](https://adriaerni.github.io/Prism/getting-started/installation/)
for more details.

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
| `prism index` | Build a compact class index |
| `prism config` | View or edit settings |
| `prism cast` | Run custom commands from Git repos |
| `prism serve` | Start the MCP server |
| `prism setup` | Register Prism MCP in external AI tools |
| `prism gui` | Launch the tkinter SQL editor GUI |

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

11 tools are always available, 2 workspace-gated (`put_document`, `put_and_compile`),
and 9 debug-gated (`debug_*`) — up to 22 total.

See the [full tool reference](https://adriaerni.github.io/Prism/mcp/tools/) for details.

## MCP Client Configuration

> **Tip:** Run `prism setup` to automatically register Prism MCP in Claude
> Code, Codex CLI, OpenCode, and Hermes Agent. See
> [setup docs](https://adriaerni.github.io/Prism/commands/setup/) for details.

The manual configurations below are for clients not yet supported by
`prism setup` (Claude Desktop, Cursor, VS Code Copilot).

### Claude Code

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "prism": {
      "type": "http",
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
    "prism": {
      "command": "prism",
      "args": ["serve"]
    }
  }
}
```

### GitHub Copilot (VS Code)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "prism": {
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
    "prism": {
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
├── gui/               # tkinter SQL editor GUI
│   ├── app.py           # Main window, menu, layout, shortcuts
│   ├── theme.py         # Dark colour palette
│   ├── controllers/     # SQL execution controller (async)
│   └── widgets/         # DatabaseTree, SQLEditor, ResultsTable, StatusBar, Toolbar
├── cast/              # Cast plugin system (import-based Typer plugins)
│   └── manager.py      # Clone, import, cache, run commands
└── cli/               # Typer CLI commands (async wrappers)
```

## Testing

```bash
uv run pytest tests/unit/ -v                    # No IRIS needed (586 tests)
IRIS_BASE_URL=http://localhost:52773 \
  uv run pytest tests/integration/ -v            # Needs IRIS (87 tests)
uv run pytest tests/gui/ -v                      # GUI tests (29 tests, needs display)
uv run ruff check . && uv run ruff format --check .  # Lint
```

Full testing guide: [docs/testing.md](docs/testing.md)

## Releases

Prism follows a [Git Flow](https://nvie.com/posts/a-successful-git-branching-model/)
release workflow with two protected branches: `development` (active work)
and `main` (stable releases).

Download the latest Windows installer or standalone exe from
[GitHub Releases](https://github.com/AdriaERNI/Prism/releases/latest).

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