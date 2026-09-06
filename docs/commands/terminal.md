# Terminal

`prism ws` — run ObjectScript on the IRIS server over the **Atelier
WebSocket terminal**. This is the only terminal command. It does NOT
upload our own ObjectScript helper (MCP.Terminal) and does NOT use the
native SuperServer ("superport") path — no ObjectScript code is uploaded
to IRIS.

| Transport | Endpoint |
|-----------|----------|
| Atelier WebSocket | `/api/atelier/v8/%25SYS/terminal` (same as `IRIS_BASE_URL`, port `52773`) |

The terminal uses the WebSocket terminal exclusively. The MCP
`execute_terminal` tool and the CLI both use the WebSocket terminal; no
ObjectScript helper is uploaded and IRIS_SUPERSERVER_PORT (1972, the
superport) is not used at all.

---

## Usage

```powershell
prism ws ["<COMMAND>"] [OPTIONS]
```

When a `COMMAND` argument is provided, it runs as a single command and
exits. When omitted, `prism ws` enters **interactive mode** — a
persistent REPL session with command history, line editing, and a smart
prompt that mirrors the IRIS namespace.

### Arguments

| Name | Type | Description |
|------|------|-------------|
| `COMMAND` | string (optional) | ObjectScript to execute. If omitted, enters interactive terminal mode. |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |
| `--timeout`, `-t` | `30.0` | Seconds to wait for the command to finish. |
| `--interactive`, `-i` | `false` | Force interactive mode even when a command is provided. The command runs first, then the REPL opens on the same session. |

### Single command example

```powershell
prism ws 'Write $ZVersion'
```

Output includes a trailing ANSI-colored prompt from IRIS:

```json
{
  "namespace": "USER",
  "command": "Write $ZVersion",
  "output": "IRIS for Windows (x86-64) 2025.3 (Build 226U) Thu Nov 13 2025 12:35:14 EST",
  "prompt": "\u001b[1mUSER>\u001b[0m"
}
```

### Interactive mode example

```powershell
prism ws
```

Drops into a terminal-like REPL:

```
Prism 0.2.1-beta2 -- Interactive WebSocket Terminal
Connected to IRIS at http://localhost:52773 in namespace USER
Type 'help' for local commands, 'exit' to quit.

USER> set x=42
USER> write x
42
USER> write $ZVersion
IRIS for Windows (x86-64) 2025.3 (Build 226U) Thu Nov 13 2025 12:35:14 EST
USER> exit
Goodbye.
```

Variables and state persist between commands within the same session,
just like a real IRIS terminal.

### Run a command then enter interactive mode

```powershell
prism ws 'set x=42' --interactive
```

Runs `set x=42` first, then opens the REPL. The variable `x` is
available in subsequent commands:

```
USER> write x
42
```

### Interactive mode local commands

| Command | Description |
|---------|-------------|
| `exit` / `quit` | Exit the terminal |
| `clear` | Clear the screen |
| `help` | Show local commands and usage |
| `history` | Show recent command history |

### Command history

Interactive mode maintains a persistent command history file at:

- Linux: `~/.local/share/prism/ws_history`
- macOS: `~/Library/Application Support/prism/ws_history`
- Windows: `%LOCALAPPDATA%\prism\ws_history`

Use up/down arrows to navigate history. The file persists across
sessions.

### Limitations

- IRIS WebSocket sessions sometimes lose output when many connect
  concurrently from the same credentials.
- Single-command mode opens a new session each time, so variables don't
  persist between calls. Use interactive mode (`prism ws` without a
  command) for stateful sessions.
- **`read` command support**: Interactive mode handles the ObjectScript
  `read` command — when IRIS requests input, you'll be prompted inline.
  In single-command mode, `read` is not supported (use `--interactive`
  with the preceding `read` command instead).
- **Windows headless mode**: When running without a real console (WinRM,
  CI, piped output), `prompt_toolkit` cannot initialize. Prism
  automatically falls back to a basic `input()` loop — history
  navigation (up/down arrows) and advanced line editing are unavailable,
  but all commands work normally.

---

## Common ObjectScript patterns

**Call a class method:**

```powershell
prism ws 'Write ##class(MyApp.Hello).Greet("Prism")'
```

**Inspect a global:**

```powershell
prism ws 'ZWrite ^myGlobal'
```

**System info:**

```powershell
prism ws 'Write $ZVersion'
```

**Combine statements with spaces:**

```powershell
prism ws 'Set x=42 Hang 1 Write "x=",x'
```

## Error handling

ObjectScript errors are returned as `ERROR: <message>` in the `output`
field rather than propagating as exceptions — so a bad command is still
a successful invocation from Prism's perspective (exit code `0`, but
`output` starts with `ERROR:`).

```powershell
prism ws "ZZZNotACommand"
```

```json
{
  "namespace": "USER",
  "command": "ZZZNotACommand",
  "output": "ERROR: <COMMAND>...",
  "prompt": ""
}
```

## Related

- [`prism sql`](sql.md) — preferred when the operation can be expressed
  as SQL (SELECT/INSERT/UPDATE/DELETE/CALL).
- MCP tool: `execute_terminal` — uses the WebSocket terminal. See
  [MCP tools](../mcp/tools.md).
