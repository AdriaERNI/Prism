# prism setup

Register the Prism MCP server in external AI tools so they can use Prism's
MCP tools (SQL, terminal, documents, testing, code indexing, and more).

## Synopsis

```
prism setup [SERVICE] [OPTIONS]
```

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `SERVICE` | `all` | Which tool to configure: `claude`, `codex`, `opencode`, `hermes`, or `all`. |

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--port` | `-p` | `3000` | Port the Prism MCP server listens on. |
| `--url` | — | `http://localhost:PORT/mcp` | Override the MCP server URL entirely. |
| `--yes` | `-y` | — | Skip the confirmation prompt. |

## Supported services

| Service | Config file | Format |
|---------|------------|--------|
| **Claude Code** | `~/.claude.json` | JSON (`mcpServers.prism`) |
| **Codex CLI** | `~/.codex/config.toml` | TOML (`[mcp_servers.prism]`) |
| **OpenCode** | `~/.config/opencode/opencode.json` (Linux/macOS) or `%APPDATA%\opencode\opencode.json` (Windows) | JSON (`mcp.prism`) |
| **Hermes Agent** | `~/.hermes/config.yaml` | YAML (`mcp_servers.prism`) |

## Examples

### Set up all services

```bash
prism setup
```

Shows a preview of all files that will be created or modified, then asks
for confirmation before writing anything.

### Set up a single service

```bash
prism setup claude       # Claude Code only
prism setup codex        # Codex CLI only
prism setup opencode     # OpenCode only
prism setup hermes       # Hermes Agent only
```

### Custom port

```bash
prism setup --port 8080
```

Uses `http://localhost:8080/mcp` as the MCP URL.

### Custom URL

```bash
prism setup --url https://prism.example.com/mcp
```

Overrides the URL entirely (e.g. for a remote Prism instance).

### Skip confirmation

```bash
prism setup --yes
```

Writes the config files immediately without asking.

## What it does

For each target service, `prism setup`:

1. **Reads** the existing config file (if any).
2. **Shows** a preview of the file path, the action (`CREATE` or `MODIFY`),
   and the exact content that will be written.
3. **Asks** for confirmation (unless `--yes`).
4. **Writes** the config, preserving any existing settings and other MCP
   servers already registered.

The operation is **idempotent** — running it twice does not create duplicate
entries. If Prism is already registered, the URL is updated in place.

## After setup

Start the Prism MCP server:

```bash
prism serve
```

Then restart the target tool (Claude Code, Codex, OpenCode, or Hermes) so it
picks up the new MCP server configuration.
