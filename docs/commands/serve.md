# prism serve

Start the Prism MCP server. This exposes every CLI operation — plus
interactive debugging — as MCP tools that any compatible client
(Claude Code, Claude Desktop, Cursor, GitHub Copilot, etc.) can call.

The server uses **streamable-http** transport and listens at
`http://localhost:3000/mcp` by default.

## Usage

```
prism serve [OPTIONS]
```

Takes no positional arguments.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--port`, `-p` | `3000` | Port to bind. |
| `--skip-preflight` | off | Skip the IRIS connectivity check at startup. |

## Example

```powershell
prism serve
```

Output on a healthy start:

```
Prism ready at http://localhost:3000/mcp | workspace: off
```

The log line is the only output. The server blocks in the foreground —
use your shell's job control (`Ctrl+C`) to stop it.

**Custom port:**

```powershell
prism serve --port 4000
```

**Skip the preflight check** (useful when starting before IRIS is
reachable, e.g. bootstrapping a Docker compose):

```powershell
prism serve --skip-preflight
```

## Preflight

Unless `--skip-preflight` is given, Prism does an HTTP `GET
/api/atelier/` with your credentials before binding the port. If it
fails, Prism exits non-zero with a clear message:

- `Cannot connect to http://…` — network path is broken.
- `Connection to http://… timed out`.
- `IRIS responded with 401` — credentials are wrong.
- `Namespace 'X' not found on server. Available: …` — the configured
  default namespace doesn't exist on this instance.

## MCP tools exposed

10 tools are always registered. With `IRIS_WORKSPACE` set, 2 workspace
tools are added (12 total). With `IRIS_DEBUG_ENABLED=true`, 9 debugger
tools are added (up to 21 total). See [MCP tools](../mcp/tools.md) for
the full reference, and [MCP client setup](../mcp/client-setup.md) for
how to point your IDE / AI assistant at this server.

## Workspace mode

If the `IRIS_WORKSPACE` environment variable is set to a directory
path, two extra MCP tools are registered: `put_document` and
`put_and_compile`. They read files from that directory and push them to
IRIS. The CLI equivalent (`prism put-doc`) takes the file path directly
and does not need `IRIS_WORKSPACE`.

## Debug mode

Setting `IRIS_DEBUG_ENABLED=true` registers nine interactive debugger
tools (`debug_start`, `debug_step`, …). These have no CLI equivalent —
they're only accessible via MCP. See [Interactive
debugging](../mcp/debugging.md).

## Related

- [MCP client setup](../mcp/client-setup.md) — wire up Claude Code,
  Claude Desktop, etc.
- [MCP tools](../mcp/tools.md) — full tool reference and how each maps
  to a CLI command.
- [Configuration](../getting-started/configuration.md) — environment
  variables that change server behaviour.
