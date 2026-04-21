# Interactive debugger (MCP only)

Nine MCP tools for interactive ObjectScript debugging via the DBGP
protocol over WebSocket. These tools have **no CLI equivalent** — they
keep a session open across multiple calls, which only fits into a
persistent MCP connection.

To use them, [`prism serve`](../commands/serve.md) must be running with
`IRIS_DEBUG_ENABLED=true`, and an [MCP client](client-setup.md) must be
connected.

!!! warning "Windows IRIS: PID attach not supported"
    The `debug_attach` tool does not work on Windows IRIS. The IRIS
    XDebug agent drops the WebSocket connection when receiving a PID
    attach request. This is a server-side limitation in
    `%Atelier.v1.XDebugAgent` on Windows. Use `debug_start` with
    breakpoints instead. All other debug tools work correctly on
    Windows.

!!! warning "Requires IRIS_DEBUG_ENABLED"
    All debugging tools require `IRIS_DEBUG_ENABLED=true` in the
    environment the server was started in. When debugging is not
    enabled, none of the tools on this page are registered.

## Constraints

- **One concurrent session.** Only a single debug session can be active at a time.
  Call `debug_stop` to end the current session before starting or attaching a new one.
- **Windows limitation.** Process attach via `debug_attach` is not supported on
  Windows-based IRIS instances.
- **Idle timeout.** Sessions are automatically cleaned up after an idle period
  (default 300 seconds, configurable via `IRIS_DEBUG_IDLE_TIMEOUT`).

---

## Session Lifecycle

### 1. debug_list_processes

Find running IRIS processes to attach to, or verify that the target namespace has
active processes.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `namespace` | `str` | No | All namespaces | Filter processes by namespace. |
| `system` | `bool` | No | `false` | Include system processes. |

Returns a list of process entries with PID, namespace, routine, state, and device
information.

---

### 2. debug_start

Start a new debug session by executing an ObjectScript expression under the debugger.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `target` | `str` | Yes | -- | ObjectScript expression to debug (e.g., `##class(MyApp.Utils).Calculate(1,2)` or `Main^MyRoutine`). |
| `stop_on_entry` | `bool` | No | `true` | Break at the first executable line. If `false`, run until a breakpoint is hit. |
| `breakpoints` | `list[dict]` | No | None | Breakpoints to set before running. Each dict: `{"class": "...", "method": "...", "offset": N}`. Add `"condition": "expr"` for conditional breakpoints. |
| `namespace` | `str` | No | Configured default | IRIS namespace for the debug connection. |

Returns a session ID along with the initial stop location, source context, and
variable state.

---

### 3. debug_attach

Attach the debugger to a running IRIS process by PID. The target process is paused
and an interactive debug session is opened.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `pid` | `int` | Yes | -- | Process ID of the IRIS process to attach to. |
| `namespace` | `str` | No | Configured default | IRIS namespace for the debug connection. |

!!! note
    Process attach is not supported on Windows-based IRIS instances.

---

### 4. debug_step

Execute a single debug step and return the new program state. Only works when the
session state is `break` (paused at a line).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | -- | Active debug session ID from `debug_start` or `debug_attach`. |
| `action` | `str` | No | `step_into` | Step action to perform. |

#### Step Actions

| Action | Description |
|--------|-------------|
| `step_into` | Execute the current line. If it contains a function call, enter the called function. |
| `step_over` | Execute the current line. If it contains a function call, run it to completion without entering. |
| `step_out` | Continue execution until the current function returns to its caller. |
| `run` | Continue execution until the next breakpoint is hit or the program ends. |
| `stop` | Terminate the debug target and end the session. |

Returns the new location (file, line number), surrounding source context, and local
variables at the new position.

---

### 5. debug_inspect

Evaluate an expression or inspect a variable in the current debug context.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | -- | Active debug session ID. |
| `expression` | `str` | Yes | -- | Variable name or ObjectScript expression to evaluate. |
| `stack_level` | `int` | No | `0` | Stack frame to evaluate in (0 = current frame, 1 = caller, etc.). |

#### Expression Examples

| Expression | Description |
|------------|-------------|
| `myVar` | Value of a local variable. |
| `obj.Property` | Object property access. |
| `a + b * 2` | Arithmetic expression. |
| `$Length(str)` | Built-in function call. |
| `##class(Pkg.Cls).Method()` | Class method invocation. |

Returns the value, type, and any child properties for objects and arrays.

---

### 6. debug_variables

Retrieve all variables in a specific scope at the current debug position.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | -- | Active debug session ID. |
| `context` | `str` | No | `private` | Variable scope to retrieve. |
| `stack_level` | `int` | No | `0` | Stack frame to inspect (0 = current, 1 = caller, etc.). |

#### Variable Contexts

| Context | Description |
|---------|-------------|
| `private` | Method-local variables (the default scope for most debugging). |
| `public` | Process-wide public variables. |
| `class` | Class properties of the current object instance. |

Returns a list of all variable names, types, and values in the requested scope. For
inspecting a specific variable or evaluating an expression, use `debug_inspect`
instead.

---

### 7. debug_stack

View the full call stack of the paused debug session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | -- | Active debug session ID. |

Returns all stack frames with file locations and function names, from the current
position (level 0) up to the entry point.

---

### 8. debug_breakpoints

Manage breakpoints in an active debug session. Breakpoints are identified by class
name, method name, and line offset within the method.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | -- | Active debug session ID. |
| `action` | `str` | No | `list` | Breakpoint action to perform. |
| `breakpoint_id` | `str` | No | None | Breakpoint ID (required for `remove`, `enable`, `disable`). |
| `class_name` | `str` | No | None | Class name for `set` (e.g., `MyApp.Utils`). |
| `method` | `str` | No | None | Method name for `set` (e.g., `Calculate`). |
| `offset` | `int` | No | `0` | Line offset within the method for `set`. |
| `condition` | `str` | No | None | Conditional expression for `set` (e.g., `x > 10`). |

#### Breakpoint Actions

| Action | Required Parameters | Description |
|--------|-------------------|-------------|
| `set` | `class_name`, `method` | Add a new breakpoint at the specified location. |
| `remove` | `breakpoint_id` | Delete a breakpoint. |
| `list` | None | Show all current breakpoints with their IDs and states. |
| `enable` | `breakpoint_id` | Re-enable a disabled breakpoint. |
| `disable` | `breakpoint_id` | Temporarily disable a breakpoint without removing it. |

Conditional breakpoints accept an ObjectScript expression. The breakpoint only
triggers when the condition evaluates to true, allowing you to skip over iterations
or states that are not relevant to the problem being investigated.

---

### 9. debug_stop

End a debug session and release all resources. Works in any session state.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | `str` | Yes | -- | Active debug session ID to stop. |

Sends a stop command to IRIS, closes the WebSocket connection, and removes the
session from the session manager. The `session_id` becomes invalid after this call.
Always call this when you are finished debugging.

---

## Complete Workflow Example

The following sequence demonstrates a full debugging session from start to finish.

### Step 1: Start a Session

Start debugging a method with `stop_on_entry` enabled and an initial breakpoint:

```
debug_start(
    target="##class(MyApp.Utils).Calculate(10, 5)",
    stop_on_entry=true,
    breakpoints=[
        {"class": "MyApp.Utils", "method": "Calculate", "offset": 3}
    ]
)
```

The response includes a `session_id` and the initial stop location.

### Step 2: Examine the Current State

View local variables at the entry point:

```
debug_variables(session_id="abc123", context="private")
```

Check the call stack:

```
debug_stack(session_id="abc123")
```

### Step 3: Step Through Code

Step into the next line:

```
debug_step(session_id="abc123", action="step_into")
```

Step over a function call without entering it:

```
debug_step(session_id="abc123", action="step_over")
```

### Step 4: Inspect Values

Evaluate an expression at the current position:

```
debug_inspect(session_id="abc123", expression="a + b")
```

Check a specific variable:

```
debug_inspect(session_id="abc123", expression="result")
```

### Step 5: Manage Breakpoints Mid-Session

Add a conditional breakpoint:

```
debug_breakpoints(
    session_id="abc123",
    action="set",
    class_name="MyApp.Utils",
    method="Calculate",
    offset=8,
    condition="result > 100"
)
```

List all active breakpoints:

```
debug_breakpoints(session_id="abc123", action="list")
```

### Step 6: Continue and Stop

Run to the next breakpoint:

```
debug_step(session_id="abc123", action="run")
```

End the session:

```
debug_stop(session_id="abc123")
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `IRIS_DEBUG_ENABLED` | `false` | Enable debugging tools. Must be `true` to register any debug tool. |
| `IRIS_DEBUG_STEP_GRANULARITY` | `line` | Step granularity for the DBGP protocol. |
| `IRIS_DEBUG_MAX_DATA` | `8192` | Maximum data size (bytes) for variable values. |
| `IRIS_DEBUG_MAX_CHILDREN` | `32` | Maximum number of child properties returned for objects. |
| `IRIS_DEBUG_MAX_DEPTH` | `2` | Maximum depth for nested object inspection. |
| `IRIS_DEBUG_IDLE_TIMEOUT` | `300` | Seconds of inactivity before a session is automatically cleaned up. |