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
| `SERVICE` | `all` | Which tool to configure: `claude`, `codex`, `opencode`, `vscode`, `hermes`, or `all`. |

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--transport` | `-t` | `http` | Transport type: `http` (requires `prism serve` running) or `stdio` (spawns `prism serve --transport stdio` as a subprocess). |
| `--port` | `-p` | `3000` | Port the Prism MCP server listens on (HTTP transport only). |
| `--url` | — | `http://localhost:PORT/mcp` | Override the MCP server URL entirely (HTTP transport only). |
| `--yes` | `-y` | — | Skip the confirmation prompt. |

## Supported services

| Service | Config file | Format |
|---------|------------|--------|
| **Claude Code** | `~/.claude.json` | JSON (`mcpServers.prism`) |
| **Codex CLI** | `~/.codex/config.toml` | TOML (`[mcp_servers.prism]`) |
| **OpenCode** | `~/.config/opencode/opencode.json` (Linux/macOS) or `%APPDATA%\opencode\opencode.json` (Windows) | JSON (`mcp.prism`) |
| **VS Code Copilot** | `~/.config/Code/User/settings.json` (Linux) or `~/Library/Application Support/Code/User/settings.json` (macOS) or `%APPDATA%\Code\User\settings.json` (Windows) | JSON (`chat.mcp.servers.prism`) |
| **Hermes Agent** | `~/.hermes/config.yaml` | YAML (`mcp_servers.prism`) |

## Transport modes

### HTTP (default)

Registers Prism as an HTTP MCP server. You must start `prism serve`
manually before the AI tool can connect.

```bash
prism setup --transport http
prism serve --port 3000
```

### stdio

Registers Prism as a stdio MCP server. The AI tool spawns
`prism serve --transport stdio` as a subprocess automatically — no port
needed, no manual `prism serve` required.

```bash
prism setup --transport stdio
```

## Examples

### Set up all services (HTTP)

```bash
prism setup
```

Shows a preview of all files that will be created or modified, then asks
for confirmation before writing anything.

### Set up all services (stdio)

```bash
prism setup --transport stdio
```

Configures all services to spawn Prism as a stdio subprocess. No
`prism serve` needed — the AI tool handles it.

### Set up a single service

```bash
prism setup claude       # Claude Code only
prism setup codex        # Codex CLI only
prism setup opencode     # OpenCode only
prism setup vscode       # VS Code Copilot only
prism setup hermes       # Hermes Agent only
```

### Custom port (HTTP)

```bash
prism setup --port 8080
```

Uses `http://localhost:8080/mcp` as the MCP URL.

### Custom URL (HTTP)

```bash
prism setup --url https://prism.example.com/mcp
```

Overrides the URL entirely (e.g. for a remote Prism instance).

### VS Code Copilot with stdio

```bash
prism setup vscode --transport stdio --yes
```

Writes the Prism MCP server config to VS Code's `settings.json` with
stdio transport. VS Code Copilot will spawn `prism serve --transport stdio`
automatically when you use Copilot Chat.

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
entries. If Prism is already registered, the URL or command is updated in place.

## After setup

### HTTP transport

Start the Prism MCP server:

```bash
prism serve
```

Then restart the target tool (Claude Code, Codex, OpenCode, VS Code, or
Hermes) so it picks up the new MCP server configuration.

### stdio transport

No manual server start needed. The AI tool spawns
`prism serve --transport stdio` automatically. Just restart the target
tool after running `prism setup`.