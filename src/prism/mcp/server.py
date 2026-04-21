"""Prism server — auto-registers all IRIS tools."""

from fastmcp import FastMCP

from prism.config import IRIS_DEBUG_ENABLED, IRIS_WORKSPACE
from prism.mcp import discover_tools

_BASE_INSTRUCTIONS = """\
MCP server for InterSystems IRIS development via the Atelier REST API.

## Key concepts

- **Documents** are source code files stored in IRIS. The main types are:
  - `.cls` — ObjectScript classes (e.g. `MyApp.Person.cls`)
  - `.mac` — ObjectScript routines
  - `.int` — intermediate routines
  - `.inc` — include files
- **Namespaces** are isolated environments in IRIS. Each tool defaults to the \
configured namespace but can target a different one.
- **Compilation** is required after creating or modifying a `.cls` document \
before the class can be used (e.g. as a SQL table or via method calls).

## ObjectScript class basics

- Classes that extend `%Persistent` auto-project to SQL tables.
- Properties become SQL columns. The package name becomes the SQL schema \
(e.g. `MyApp.Person` → table `MyApp.Person`).
- ClassMethods with the `[SqlProc]` keyword can be called from SQL.
- Document names follow the pattern `Package.ClassName.cls`.

## Terminal access

Use `execute_terminal` for arbitrary ObjectScript that cannot be expressed as \
SQL — method calls, global operations, system utilities ($system), variable \
manipulation, and general-purpose commands. Each call opens a fresh session; \
combine dependent statements in one command (e.g. `set x=1 write x`). \
For SQL queries, prefer `execute_sql` instead.

For long-running commands (data migrations, batch processing, builds), \
`execute_terminal` supports background execution via the MCP task protocol. \
When called as a background task, it returns immediately with a task ID \
while the command runs in its own terminal session. You can continue using \
other tools, check the task status, retrieve output when done, or cancel it. \
Remember to increase the `timeout` parameter for commands that take longer \
than the default 30 seconds (e.g. `timeout=300` for up to 5 minutes).

## Content format

Content is a JSON array of strings, one line per element:
```json
["Class MyApp.Hello Extends %RegisteredObject", "{", "", "ClassMethod Greet() As %String", "{", "  Return \\"Hello\\"", "}", "", "}"]
```

## Unit testing

Use `list_tests` to discover %UnitTest.TestCase classes and their Test* methods. \
Use `run_tests` to execute tests — a helper class is auto-deployed on first use. \
Use `get_test_results` to review historical results without re-running. \
Test classes must extend `%UnitTest.TestCase` and have methods starting with \
`Test` that use `$$$Assert*` macros (e.g. `$$$AssertEquals`, `$$$AssertStatusOK`). \
The test runner is configurable via IRIS_TEST_RUNNER_CLASS, \
IRIS_TEST_MANAGER_CLASS, and IRIS_TEST_RUNNER_METHOD environment variables.
"""

_WORKSPACE_INSTRUCTIONS = """
## Available tools

- **list_documents** — discover what is on the server. Returns a list of \
document names you can pass to the other tools. Filter by type \
(`doc_type="cls"`) or name prefix (`filter="MyApp"`).
- **get_document** — fetch a document from IRIS and return its content \
inline. Supports `head`, `tail`, `from_line`/`to_line` for slicing.
- **put_document** — read a file from the workspace and push it to IRIS.
- **put_and_compile** — push and compile in one step (recommended for `.cls`).
- **compile_documents** — compile one or more documents already on the server.
- **delete_document** — delete a document from IRIS.
- **execute_sql** — run SQL queries (SELECT, INSERT, UPDATE, DELETE, CALL).
- **execute_terminal** — run arbitrary ObjectScript via a terminal session.
- **get_server_info** — check IRIS version and available namespaces.
- **run_tests** — run unit tests for a %UnitTest.TestCase class.
- **list_tests** — discover test classes and their Test* methods.
- **get_test_results** — view historical test results.
{debug_tools}\
## Workspace workflow

A local workspace directory is configured at `{workspace}`.

**To create or modify a class:**
1. Write the `.cls` file to the workspace directory
2. Call **put_and_compile** with the document name — it reads from the \
workspace, pushes to IRIS, and compiles

**To inspect an existing class:**
1. Call **list_documents** to discover document names (e.g. `doc_type="cls"`)
2. Call **get_document** — it returns the source code directly in the response

**To query or manipulate data:**
- Use **execute_sql** for SQL (SELECT, INSERT, UPDATE, CALL)
- Use **execute_terminal** for ObjectScript that cannot be expressed as SQL
"""

_DEBUG_TOOLS_LIST = """\
- **debug_list_processes** — list running IRIS processes (filter by namespace).
- **debug_attach** — attach the debugger to a running process by PID.
- **debug_start** — start an interactive debug session on an ObjectScript target.
- **debug_step** — execute a step (step_into, step_over, step_out, run, stop).
- **debug_inspect** — evaluate an expression or inspect a variable.
- **debug_variables** — get all variables in a scope (private, public, class).
- **debug_stack** — get the full call stack.
- **debug_breakpoints** — set, remove, list, enable, or disable breakpoints.
- **debug_stop** — stop the session and release resources.

"""

_DEBUG_INSTRUCTIONS = """
## Interactive debugging

The debug tools provide interactive ObjectScript debugging via the DBGP \
protocol over WebSocket. Debugging is enabled when `IRIS_DEBUG_ENABLED=true`.

### Workflow

1. **Start** — call `debug_start` with a target expression \
(e.g. `##class(MyApp.Utils).Calculate(1,2)`). Set `stop_on_entry=true` to \
pause at the first line, or set breakpoints and use `stop_on_entry=false`. \
You receive a `session_id` and the initial stop location.
2. **Step and inspect** — use `debug_step` to advance execution, and \
`debug_inspect` / `debug_variables` / `debug_stack` to examine state. \
After each step, variables at the current position are returned automatically.
3. **Stop** — call `debug_stop` when finished. Always do this to release the \
WebSocket connection. Do not leave sessions hanging.

### Session states

- `"break"` — paused and ready for inspection. You can only call step, \
inspect, variables, stack, and breakpoint tools when the session is in this \
state.
- `"running"` — the target is still executing (e.g. between a `run` command \
and the next breakpoint). Wait for it to reach `"break"` before inspecting.
- `"ended"` — the target finished executing or was stopped. Call `debug_stop` \
to clean up.

### Session lifecycle

- Only **one session** can be active at a time. Call `debug_stop` before \
starting a new one.
- Sessions have an idle timeout (default 5 minutes). Each tool call resets \
the timer. If you do not interact, the session expires automatically.

### Stepping strategy

- `step_over` — execute the current line without entering function calls. \
Use this for line-by-line debugging.
- `step_into` — enter function/method calls to debug their internals.
- `step_out` — run until the current function returns to its caller.
- `run` — continue execution until the next breakpoint is hit.

### Inspecting state

- After each `debug_step`, the response includes local variables at the new \
position automatically.
- Use `debug_inspect` to evaluate arbitrary ObjectScript expressions \
(e.g. `$Length(str)`, `obj.Property`, `a + b`).
- Use `debug_variables` to get all variables in a scope: `private` \
(method-local), `public` (process-wide), or `class` (object properties).

### Breakpoints

- Breakpoints can be set at `debug_start` time via the `breakpoints` \
parameter, or during the session with `debug_breakpoints`.
- Specify `class_name`, `method`, and `offset` (line offset within the method).
- Conditional breakpoints are supported — add a `condition` expression that \
must evaluate to true for the breakpoint to trigger.

### Attaching to running processes

Instead of launching a new debug target, you can attach to an already-running \
IRIS process:

1. **List processes** — call `debug_list_processes` to see what IRIS processes \
are running. Filter by `namespace` to narrow results and exclude system \
processes (the default).
2. **Find your target** — look for the process running the routine or class \
you want to debug. Note its `pid`.
3. **Attach** — call `debug_attach` with the `pid`. The debugger pauses the \
process and returns a `session_id` along with the current stop location and \
variables.
4. **Inspect and step** — once attached, use `debug_step`, `debug_inspect`, \
`debug_variables`, `debug_stack`, and `debug_breakpoints` exactly as you \
would after `debug_start`.
5. **Detach** — call `debug_stop` when finished. The attached process resumes \
execution. If the session times out due to inactivity, the process also \
resumes automatically.

Typical workflow: `debug_list_processes` → identify the PID → `debug_attach` → \
inspect state → `debug_stop`.

### Source context tip

The debugger returns line numbers but not full source code. Use \
`get_document` to read the source of the class being debugged if you need \
to see surrounding code.
"""

_NO_WORKSPACE_INSTRUCTIONS = """
## Available tools

- **list_documents** — discover what is on the server. Returns a list of \
document names. Filter by type (`doc_type="cls"`) or name prefix \
(`filter="MyApp"`).
- **get_document** — fetch a document from IRIS and return its content \
inline. Supports `head`, `tail`, `from_line`/`to_line` for slicing.
- **compile_documents** — compile one or more documents on the server.
- **delete_document** — delete a document from IRIS.
- **execute_sql** — run SQL queries (SELECT, INSERT, UPDATE, DELETE, CALL).
- **execute_terminal** — run arbitrary ObjectScript via a terminal session.
- **get_server_info** — check IRIS version and available namespaces.
- **run_tests** — run unit tests for a %UnitTest.TestCase class.
- **list_tests** — discover test classes and their Test* methods.
- **get_test_results** — view historical test results.
{debug_tools}\
Note: put_document and put_and_compile are disabled because \
IRIS_WORKSPACE is not configured. Set the IRIS_WORKSPACE environment variable \
to a local directory path to enable file-based document I/O.
"""


def create_mcp() -> FastMCP:
    """Build and return a fully configured FastMCP instance."""
    debug_tools = _DEBUG_TOOLS_LIST if IRIS_DEBUG_ENABLED else ""
    if IRIS_WORKSPACE:
        instructions = _BASE_INSTRUCTIONS + _WORKSPACE_INSTRUCTIONS.format(
            workspace=IRIS_WORKSPACE,
            debug_tools=debug_tools,
        )
    else:
        instructions = _BASE_INSTRUCTIONS + _NO_WORKSPACE_INSTRUCTIONS.format(
            debug_tools=debug_tools,
        )

    if IRIS_DEBUG_ENABLED:
        instructions += _DEBUG_INSTRUCTIONS

    server = FastMCP("Prism", instructions=instructions)

    for tool_fn in discover_tools():
        extra = getattr(tool_fn, "_mcp_tool_kwargs", {})
        server.tool(tool_fn, **extra)

    return server


mcp = create_mcp()
