# Prism

**Prism lets AI see through IRIS.** MCP server for InterSystems IRIS development via the Atelier REST API. Provides tools for SQL queries, document management, compilation, debugging, testing, and ObjectScript execution.

## Setup

```bash
uv sync
cp .env.example .env
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_BASE_URL` | `http://localhost:52773` | IRIS instance URL |
| `IRIS_USERNAME` | `_SYSTEM` | Authentication username |
| `IRIS_PASSWORD` | `SYS` | Authentication password |
| `IRIS_NAMESPACE` | `USER` | Default namespace for all operations |
| `IRIS_WORKSPACE` | *(empty)* | Local directory for file I/O tools (`get_document`, `put_document`, `put_and_compile`). Disabled when empty |
| `IRIS_COMPILE_FLAGS` | `cuk` | Compiler flags: `c`=compile, `u`=skip up-to-date, `k`=keep generated source |
| `IRIS_API_V1` | `api/atelier/v1` | Atelier v1 API prefix |
| `IRIS_API_V2` | `api/atelier/v2` | Atelier v2 API prefix |

## Run

```bash
uv run python main.py
# or
python -m prism
```

## Tools

| Tool | Description |
|------|-------------|
| `execute_sql` | Run SQL queries (SELECT, INSERT, UPDATE, DELETE, CALL) |
| `execute_terminal` | Run ObjectScript commands via WebSocket terminal |
| `list_documents` | List source code files in a namespace |
| `get_document` | Read a document's content |
| `put_document` | Create or update a document |
| `delete_document` | Delete a document |
| `compile_documents` | Compile source files |
| `get_server_info` | Server version and namespaces |

## Project Structure

```
src/prism/
├── core/           # Shared infrastructure (config, HTTP, logging, preflight)
├── api/            # Domain-specific HTTP calls (sql, documents, compile, server_info)
├── tools/          # MCP tool wrappers with auto-discovery
└── server.py       # FastMCP server with auto-registration
```

Adding a new tool requires only one file in `tools/` using the `@logged_tool` decorator.

## Tests

```bash
./scripts/test-unit.sh          # No IRIS needed
./scripts/test-integration.sh   # Requires running IRIS
./scripts/test-all.sh           # Everything
```

## Known Issues

### Debug attach to PID not supported on Windows IRIS

The `debug_attach` tool (attaching to an already-running IRIS process by PID) does not work on Windows IRIS. The IRIS XDebug agent drops the WebSocket connection when receiving the `feature_set debug_target PID:<pid>` command. This is a server-side limitation in the Windows build of IRIS's `%Atelier.v1.XDebugAgent` — the VS Code ObjectScript extension has the same behavior.

All other debug tools (`debug_start`, `debug_step`, `debug_inspect`, `debug_variables`, `debug_stack`, `debug_breakpoints`, `debug_stop`) work correctly on Windows.

**Workaround:** Use `debug_start` with breakpoints instead of attaching to a running process.

## Changelog

```bash
./scripts/changelog.sh
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, etc.).

## Client Configuration

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
      "args": ["run", "--directory", "/path/to/prism-mcp", "python", "main.py"]
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
