# prism serve

Start the Prism MCP server. This exposes every CLI operation — plus
interactive debugging — as MCP tools that any compatible client
(Claude Code, Claude Desktop, Cursor, VS Code Copilot, GitHub Copilot, etc.) can call.

## Transports

Prism supports two MCP transports:

- **streamable-http** (default): listens on a port, accessible at
  `http://localhost:3000/mcp`. Use for network-accessible setups.
- **stdio**: communicates over stdin/stdout. Use for local MCP clients
  that spawn the server as a subprocess (Claude Code, VS Code Copilot,
  etc.). No port is needed.

## Usage

```
prism serve [OPTIONS]
```

Takes no positional arguments.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--transport`, `-t` | `streamable-http` | MCP transport: `stdio` (stdin/stdout) or `streamable-http` (HTTP server). |
| `--port`, `-p` | `3000` | Port to bind (ignored for stdio). |
| `--skip-preflight` | off | Skip the IRIS connectivity check at startup. |

## Examples

**HTTP transport (default):**

```bash
prism serve
```

Output:

```
Prism ready at http://localhost:3000/mcp | workspace: off
```

**Custom port:**

```bash
prism serve --port 4000
```

**stdio transport (for local MCP clients):**

```bash
prism serve --transport stdio
```

No port is needed — the MCP client (Claude Code, VS Code Copilot, etc.)
spawns this command as a subprocess and communicates over stdin/stdout.

**Skip the preflight check** (useful when starting before IRIS is
reachable, e.g. bootstrapping a Docker compose):

```bash
prism serve --skip-preflight
```

> **Note:** stdio transport automatically skips the preflight check
> since it runs locally without a network connection to verify.

## Preflight

Unless `--skip-preflight` is given (or stdio transport is used), Prism
does an HTTP `GET /api/atelier/` with your credentials before binding the
port. If it fails, Prism exits non-zero with a clear message:

- `Cannot connect to http://…` — network path is broken.
- `Connection to http://… timed out`.
- `IRIS responded with 401` — credentials are wrong.
- `Namespace 'X' not found on server. Available: …` — the configured
  default namespace doesn't exist on this instance.

## MCP tools exposed

12 tools are always registered. With `IRIS_WORKSPACE` set, 5 workspace
tools are added (17 total). With `IRIS_DEBUG_ENABLED=true`, 9 debugger
tools are added (up to 26 total). See [MCP tools](../mcp/tools.md) for
the full reference, and [MCP client setup](setup.md) for how to point
your IDE / AI assistant at this server.

## Workspace mode

If the `IRIS_WORKSPACE` environment variable is set to a directory
path, five extra MCP tools are registered: `put_document`,
`put_and_compile`, `read_file`, `list_files`, and `run_shell`. They
read files from that directory and push them to IRIS, or execute shell
commands locally. The CLI equivalent (`prism put-doc`) takes the file
path directly and does not need `IRIS_WORKSPACE`.

## Debug mode

Setting `IRIS_DEBUG_ENABLED=true` registers nine interactive debugger
tools (`debug_start`, `debug_step`, …). These have no CLI equivalent —
they're only accessible via MCP. See [Interactive
debugging](../mcp/debugging.md).

## Related

- [prism setup](setup.md) — wire up Claude Code, VS Code Copilot,
  Codex, OpenCode, Hermes, etc.
- [MCP tools](../mcp/tools.md) — full tool reference and how each maps
  to a CLI command.
- [Configuration](../getting-started/configuration.md) — environment
  variables that change server behaviour.