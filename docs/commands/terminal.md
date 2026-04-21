# Terminal

Two commands for running ObjectScript on the server. They produce the
same output shape — they differ only in how they reach IRIS.

| Command | Transport | Port | Parallel-safe |
|---------|-----------|------|---------------|
| [`prism terminal`](#native) | irisnative (SuperServer) | `1972` (`IRIS_SUPERSERVER_PORT`) | ✅ |
| [`prism ws`](#websocket) | Atelier WebSocket | same as `IRIS_BASE_URL` (`52773`) | ⚠️ see notes |

The native variant is faster, supports parallel execution, and captures
`Write` output reliably. The WebSocket variant is the fallback when you
can only reach the HTTP port (corporate networks, cloud IRIS instances
behind an HTTPS proxy, etc.).

The MCP `execute_terminal` tool switches between the two based on the
`IRIS_TERMINAL_METHOD` environment variable. The CLI bypasses that
switch — `prism terminal` is always native, `prism ws` is always
WebSocket.

---

## native

`prism terminal` — native driver via SuperServer.

### Usage

```
prism terminal "<COMMAND>" [OPTIONS]
```

### Arguments

| Name | Type | Description |
|------|------|-------------|
| `COMMAND` | string | ObjectScript to execute (e.g. `Write 42`). Multiple statements can be combined on one line with spaces: `Set x=1 Write x`. |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |
| `--timeout`, `-t` | `30.0` | Seconds to wait for the command to finish. |

### Example

```powershell
prism terminal 'Write "hello"'
```

Output:

```json
{
  "namespace": "USER",
  "command": "Write \"hello\"",
  "output": "hello",
  "prompt": ""
}
```

### How it works

First time you run `prism terminal`, Prism uploads a small helper class
called `MCP.Terminal` (uses `%Device.ReDirectIO` to capture `Write`
output from `XECUTE`), then invokes it via the `intersystems-irispython`
native driver over the SuperServer port. Each invocation opens a fresh
SuperServer session, which is why this mode can run many commands in
parallel.

The helper class is idempotent; subsequent runs reuse it. You can safely
`prism delete-doc MCP.Terminal.cls` — the next `prism terminal` call
will redeploy it.

---

## websocket

`prism ws` — same operation, but via the Atelier WebSocket terminal
endpoint (`/api/atelier/v8/%25SYS/terminal`) rather than SuperServer.
Use this when the SuperServer port is firewalled.

### Usage

```
prism ws "<COMMAND>" [OPTIONS]
```

### Arguments and options

Identical to `prism terminal`.

### Example

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

### Limitations

- IRIS WebSocket sessions sometimes lose output when many connect
  concurrently from the same credentials. If you need to run commands
  in parallel, prefer `prism terminal`.
- Each call opens a new session, so variables don't persist between
  calls: run dependent statements in a single command
  (`Set x=1 Write x`).

---

## Common ObjectScript patterns

**Call a class method:**

```powershell
prism terminal 'Write ##class(MyApp.Hello).Greet("Prism")'
```

**Inspect a global:**

```powershell
prism terminal 'ZWrite ^myGlobal'
```

**System info:**

```powershell
prism terminal 'Write $ZVersion'
```

**Combine statements with spaces:**

```powershell
prism terminal 'Set x=42 Hang 1 Write "x=",x'
```

## Error handling

The `MCP.Terminal` helper wraps `XECUTE` in a `Try/Catch`. ObjectScript
errors come back as `ERROR: <message>` strings in `output` rather than
propagating as exceptions — so a bad command is still a successful
invocation from Prism's perspective (exit code `0`, but `output` starts
with `ERROR:`).

```powershell
prism terminal "ZZZNotACommand"
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
- MCP tool: `execute_terminal` — uses whichever backend
  `IRIS_TERMINAL_METHOD` selects. See [MCP tools](../mcp/tools.md).
