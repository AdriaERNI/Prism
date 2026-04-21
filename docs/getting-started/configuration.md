# Configuration

Prism reads connection settings and feature flags from three sources, in
this order (highest precedence wins):

1. **Environment variables** — `IRIS_BASE_URL=... prism info` or set in
   the shell session.
2. **`.env` file** — loaded via `python-dotenv` from the current working
   directory.
3. **`settings.json`** — the persistent user settings written by
   `prism config`.

If none of the three provide a value, Prism falls back to the default
shown in the tables below.

## The settings file

`prism config` writes a JSON file under your OS's user config directory:

| OS | Path |
|----|------|
| Windows | `%LOCALAPPDATA%\prism\settings.json` (e.g. `C:\Users\you\AppData\Local\prism\settings.json`) |
| Linux | `~/.config/prism/settings.json` (honours `XDG_CONFIG_HOME`) |

On POSIX the file is `chmod 600`. On Windows it inherits the ACLs of
`%LOCALAPPDATA%`, which is already user-scoped.

### Structure

```json
{
  "url": "http://192.168.1.100:52773",
  "username": "_SYSTEM",
  "password": "SYS",
  "namespace": "USER",
  "superserver_port": 1972
}
```

Only five keys are supported. They map 1:1 to environment variables:

| Settings key | Environment variable |
|--------------|----------------------|
| `url` | `IRIS_BASE_URL` |
| `username` | `IRIS_USERNAME` |
| `password` | `IRIS_PASSWORD` |
| `namespace` | `IRIS_NAMESPACE` |
| `superserver_port` | `IRIS_SUPERSERVER_PORT` |

### Writing with `prism config`

```powershell
prism config _SYSTEM SYS http://192.168.1.100:52773 --namespace USER --superserver-port 1972
```

See [`prism config`](../commands/config.md) for all options.

## Connection

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_BASE_URL` | `http://localhost:52773` | IRIS web server URL |
| `IRIS_USERNAME` | `_SYSTEM` | Authentication username |
| `IRIS_PASSWORD` | `SYS` | Authentication password |
| `IRIS_NAMESPACE` | `USER` | Default namespace for all operations |
| `IRIS_SUPERSERVER_PORT` | `1972` | Port used by `prism terminal` (native driver) |

## Terminal method

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_TERMINAL_METHOD` | `native` | Which backend the MCP `execute_terminal` tool uses: `native` (irisnative via SuperServer, parallel-capable) or `ws` (Atelier WebSocket, useful when only the HTTP port is reachable) |

The CLI bypasses this switch: `prism terminal` always uses the native
driver, `prism ws` always uses the WebSocket.

## API

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_API_PREFIX` | `api/atelier/v8` | Atelier REST API path prefix |
| `IRIS_COMPILE_FLAGS` | `cuk` | Compiler flags: `c` = compile, `u` = skip up-to-date, `k` = keep generated source |

## Workspace (MCP server only)

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_WORKSPACE` | *(empty)* | Local directory for the MCP `put_document` and `put_and_compile` tools. When empty, those tools are not registered |

!!! note
    The CLI `prism put-doc <name> <file>` does not need `IRIS_WORKSPACE` —
    it reads the file path you pass directly. The variable only affects
    the MCP server's workspace-based tools.

## Testing

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_TEST_RUNNER_CLASS` | `MCP.TestRunner` | ObjectScript class that wraps `%UnitTest.Manager` |
| `IRIS_TEST_RUNNER_METHOD` | `RunTests` | SqlProc method name on the runner class |
| `IRIS_TEST_MANAGER_CLASS` | `%UnitTest.Manager` | Underlying IRIS unit test manager class |
| `IRIS_TEST_AUTO_DEPLOY` | `true` | Auto-deploy the test runner helper class to IRIS on first `prism test` run |

## Debugging (MCP server only)

The interactive debugger is only reachable through the MCP server. Debug
tools are hidden until `IRIS_DEBUG_ENABLED=true`.

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_DEBUG_ENABLED` | `false` | Must be `true` to register the `debug_*` MCP tools |
| `IRIS_DEBUG_STEP_GRANULARITY` | `line` | Step granularity for the debugger |
| `IRIS_DEBUG_MAX_DATA` | `8192` | Maximum bytes returned when inspecting a variable |
| `IRIS_DEBUG_MAX_CHILDREN` | `32` | Maximum child elements returned for collections and objects |
| `IRIS_DEBUG_MAX_DEPTH` | `2` | Maximum recursion depth for nested data structures |
| `IRIS_DEBUG_IDLE_TIMEOUT` | `300` | Seconds of inactivity before a debug session is automatically closed |

!!! warning
    Debugging requires a WebSocket connection to the IRIS XDebug
    endpoint. Ensure your IRIS instance has XDebug enabled and that
    port is reachable.