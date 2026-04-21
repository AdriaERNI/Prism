# MCP client setup

Start the Prism MCP server, then point your client (Claude Code, Claude
Desktop, Cursor, VS Code Copilot, …) at it.

## Start Prism

```powershell
prism serve
```

```
Prism ready at http://localhost:3000/mcp | workspace: off
```

Leave the terminal open — the server runs in the foreground. Stop with
`Ctrl+C`.

The default URL is `http://localhost:3000/mcp`. Every client example
below assumes that URL; adjust the host/port if you ran
`prism serve --port 4000`.

## Clients

=== "Claude Code"

    Edit `.claude/settings.json` (in your project, or in `%USERPROFILE%`
    for a global config on Windows):

    ```json
    {
      "mcpServers": {
        "prism": {
          "url": "http://localhost:3000/mcp"
        }
      }
    }
    ```

    Claude Code connects over HTTP to the running server — you start
    Prism manually, Claude Code doesn't launch it.

=== "Claude Desktop"

    Edit `claude_desktop_config.json`, located at
    `%APPDATA%\Claude\claude_desktop_config.json`:

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

    Claude Desktop will launch `prism serve` as a child process when it
    starts, and stop it when it exits. Works because `prism.exe` is on
    the system `PATH` after the installer.

=== "Cursor"

    Edit `.cursor/mcp.json` (workspace) or `~/.cursor/mcp.json` (global):

    ```json
    {
      "mcpServers": {
        "prism": {
          "url": "http://localhost:3000/mcp"
        }
      }
    }
    ```

    Same pattern as Claude Code — start `prism serve` yourself.

=== "VS Code / GitHub Copilot"

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

    The server must be running before Copilot connects.

## Enabling the interactive debugger

Debug tools are registered only when `IRIS_DEBUG_ENABLED=true`. Start
Prism with that env var set if you want Claude (or any other client) to
have access to `debug_start`, `debug_step`, etc.:

```powershell
$env:IRIS_DEBUG_ENABLED = "true"
prism serve
```

See [Interactive debugger](debugging.md) for the full workflow.

## Enabling workspace mode

Workspace mode unlocks two additional MCP tools (`put_document`,
`put_and_compile`) that read files from a local directory. Set
`IRIS_WORKSPACE` to the path you want the AI to push code from:

```powershell
$env:IRIS_WORKSPACE = "C:\work\myapp\src"
prism serve
```

Without it, the tools are not registered (and the startup log shows
`workspace: off`).

## Verifying the connection

Ask your client to call `get_server_info` — a zero-argument tool that
returns the IRIS version. Any response means the transport is wired up
correctly. If the AI says the tool isn't available, re-check the client
config file's path and JSON validity.
