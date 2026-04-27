---
name: prism-iris-tools
description: 'Use Prism to interact with InterSystems IRIS databases. Use when: running SQL queries, executing ObjectScript, managing documents/classes, compiling code, running unit tests, or debugging IRIS applications. Covers both CLI (prism command) and MCP tools.'
argument-hint: 'Describe what IRIS operation you need (SQL, compile, test, debug...)'
---

# Prism IRIS Tools

Prism provides two interfaces to InterSystems IRIS: a **CLI** (`prism` command) and an **MCP server** (tools). Use this skill to determine which is available and how to use each tool.

## Detection Procedure

### Step 1: Check CLI Availability

```powershell
prism info
```

- **Success**: Returns JSON with server version and namespaces → CLI is available
- **Command not found**: Prism CLI not installed or not in PATH
- **Connection error**: CLI installed but IRIS unreachable — check connection settings

### Step 2: Check MCP Server Availability

If you have MCP tools available in your context, look for these Prism tools:
- `execute_sql`
- `execute_terminal`
- `get_server_info`
- `list_documents`

If present, the MCP server is running and connected.

### Step 3: Verify IRIS Connection

```powershell
# CLI
prism sql "SELECT 1"

# MCP
execute_sql(query="SELECT 1")
```

Expected: `{"rows": [[1]], "count": 1}` or similar success response.

## When to Use CLI vs MCP

| Scenario | Use |
|----------|-----|
| Running from shell/terminal | CLI |
| AI agent with MCP tools available | MCP |
| Scripting/automation | CLI |
| Interactive debugging session | MCP (debug_* tools have no CLI equivalent) |
| Uploading files from workspace | MCP (`put_document` requires `IRIS_WORKSPACE`) |
| One-off queries | Either |

## Tool Reference

### SQL

| Operation | CLI | MCP |
|-----------|-----|-----|
| Run query | `prism sql "SELECT * FROM Table"` | `execute_sql(query="SELECT * FROM Table")` |
| Target namespace | `prism sql -n SAMPLES "..."` | `execute_sql(query="...", namespace="SAMPLES")` |

### ObjectScript Execution

| Operation | CLI | MCP |
|-----------|-----|-----|
| Run command (native) | `prism terminal "Write 1+1"` | `execute_terminal(command="Write 1+1")` |
| Run command (WebSocket) | `prism ws "Write 1+1"` | `execute_terminal(command="...", method="ws")` |
| With timeout | `prism terminal -t 60 "..."` | `execute_terminal(command="...", timeout=60)` |

### Documents (Classes, Routines, Includes)

| Operation | CLI | MCP |
|-----------|-----|-----|
| List documents | `prism list-docs` | `list_documents()` |
| List with filter | `prism list-docs -f "*.cls"` | `list_documents(filter="*.cls")` |
| Get document | `prism get-doc MyApp.Person.cls` | `get_document(name="MyApp.Person.cls")` |
| Get partial (lines) | N/A | `get_document(name="...", from_line=10, to_line=50)` |
| Upload document | `prism put-doc MyApp.cls ./file.cls` | `put_document(name="MyApp.cls")` (reads from IRIS_WORKSPACE) |
| Delete document | `prism delete-doc MyApp.cls` | `delete_document(name="MyApp.cls")` |

### Compilation

| Operation | CLI | MCP |
|-----------|-----|-----|
| Compile documents | `prism compile MyApp.cls` | `compile_documents(documents=["MyApp.cls"])` |
| Multiple documents | `prism compile A.cls B.cls` | `compile_documents(documents=["A.cls", "B.cls"])` |
| Custom flags | `prism compile --flags cukb A.cls` | `compile_documents(documents=["A.cls"], flags="cukb")` |
| Upload + compile | `prism put-doc X.cls f.cls && prism compile X.cls` | `put_and_compile(name="X.cls")` |

### Testing

| Operation | CLI | MCP |
|-----------|-----|-----|
| List test classes | `prism list-tests` | `list_tests()` |
| Run test class | `prism test MyApp.Tests` | `run_tests(classname="MyApp.Tests")` |
| Run single method | `prism test MyApp.Tests TestMethod` | `run_tests(classname="MyApp.Tests", method="TestMethod")` |
| Get cached results | N/A | `get_test_results()` |

### Server Info

| Operation | CLI | MCP |
|-----------|-----|-----|
| Server version & namespaces | `prism info` | `get_server_info()` |

### Debugging (MCP Only)

These tools require `IRIS_DEBUG_ENABLED=true` and have no CLI equivalent:

| Tool | Purpose |
|------|---------|
| `debug_list_processes` | List running IRIS processes |
| `debug_start` | Start debug session with breakpoints |
| `debug_attach` | Attach to running process (not supported on Windows IRIS) |
| `debug_step` | Step into/over/out |
| `debug_inspect` | Evaluate expression in current context |
| `debug_variables` | List variables in scope |
| `debug_stack` | Show call stack |
| `debug_breakpoints` | Add/remove/list breakpoints |
| `debug_stop` | End debug session |

## Common Patterns

### Pattern 1: Query and Process Results

```powershell
# CLI — pipe to jq for processing
prism sql "SELECT Name, Age FROM MyApp.Person" | jq '.rows'
```

```python
# MCP
result = execute_sql(query="SELECT Name, Age FROM MyApp.Person")
# result["rows"] contains [[name, age], ...]
```

### Pattern 2: Edit and Compile Cycle

```powershell
# CLI
prism put-doc MyApp.Handler.cls ./src/MyApp.Handler.cls
prism compile MyApp.Handler.cls
```

```python
# MCP (file must be in IRIS_WORKSPACE)
put_and_compile(name="MyApp.Handler.cls")
```

### Pattern 3: Run Unit Tests After Changes

```powershell
# CLI
prism compile MyApp.cls
prism test MyApp.Tests
```

```python
# MCP
compile_documents(documents=["MyApp.cls"])
run_tests(classname="MyApp.Tests")
```

### Pattern 4: Debug a Method

```python
# MCP only — start debug session
debug_start(
    classname="MyApp.Service",
    method="ProcessOrder",
    arguments="orderId",
    breakpoints=[{"classname": "MyApp.Service", "line": 42}]
)
# Then use debug_step, debug_variables, debug_inspect as needed
debug_stop()
```

## Configuration

Connection settings (in order of precedence):

1. Environment variables: `IRIS_BASE_URL`, `IRIS_USERNAME`, `IRIS_PASSWORD`, `IRIS_NAMESPACE`
2. `.env` file in current directory
3. User settings: `prism config` writes to `~/.local/share/prism/config.json` (Linux) or `%LOCALAPPDATA%\prism\config.json` (Windows)

### Quick Setup

```powershell
prism config -u _SYSTEM -p SYS -U http://localhost:52773 -n USER
```

### Enable Workspace Tools

Set `IRIS_WORKSPACE` to enable `put_document` and `put_and_compile` MCP tools:

```powershell
$env:IRIS_WORKSPACE = "D:\myproject\src"
```

### Enable Debug Tools

```powershell
$env:IRIS_DEBUG_ENABLED = "true"
```

## PowerShell Quoting (CLI)

When running `prism terminal` or `prism ws` from PowerShell, be aware of two quoting pitfalls:

### 1. Dollar signs (`$`) are interpolated in double quotes

PowerShell expands `$ZVersion`, `$Namespace`, etc. as its own variables (empty), so the command arrives mangled.

```powershell
# WRONG — PowerShell expands $ZVersion to empty string
prism terminal "Write $ZVersion"

# CORRECT — single quotes prevent interpolation
prism terminal 'Write $ZVersion'
```

### 2. Inner double quotes are stripped

PowerShell removes double quotes inside a single-quoted string when passing to native executables. Use backslash-escaped quotes (`\"`) instead.

```powershell
# WRONG — quotes stripped, IRIS sees: Write hello → <UNDEFINED> error
prism terminal 'Write "hello"'

# CORRECT — backslash escapes survive to the executable
prism terminal 'Write \"hello\"'

# Also works for complex expressions
prism terminal 'For i=1:1:3 Write i,\" \"'
```

### Quick reference

| ObjectScript | PowerShell CLI command |
|---|---|
| `Write 1+1` | `prism terminal 'Write 1+1'` |
| `Write "hello"` | `prism terminal 'Write \"hello\"'` |
| `Write $ZVersion` | `prism terminal 'Write $ZVersion'` |
| `Set x="abc" Write x` | `prism terminal 'Set x=\"abc\" Write x'` |

> **MCP tools are not affected** — `execute_terminal(command='Write "hello"')` works as-is because there is no shell in the middle.

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| Connection refused | IRIS not running or wrong URL | Check `IRIS_BASE_URL`, verify IRIS is running |
| 401 Unauthorized | Wrong credentials | Check `IRIS_USERNAME` and `IRIS_PASSWORD` |
| Namespace not found | Invalid namespace | Use `prism info` or `get_server_info()` to list valid namespaces |
| Document not found | Wrong document name | Use `prism list-docs` or `list_documents()` to find correct name |
| Compilation error | Code has errors | Check the `console` and `status.errors` fields in response |

## Documentation Links

- [CLI Commands](../../docs/commands/index.md)
- [MCP Tools Reference](../../docs/mcp/tools.md)
- [Configuration](../../docs/getting-started/configuration.md)
- [Debugging Guide](../../docs/mcp/debugging.md)
