"""MCP tools for interactive ObjectScript debugging via DBGP."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import debugger as debugger_api
from prism.mcp._decorator import logged_tool


@logged_tool
async def debug_list_processes(
    namespace: Annotated[
        str | None,
        Field(
            description="Filter processes by IRIS namespace. Returns all namespaces if omitted."
        ),
    ] = None,
    system: Annotated[
        bool,
        Field(description="Include system processes. Default false."),
    ] = False,
) -> list[dict]:
    """List running IRIS processes (on the IRIS server).

    **Runs on: IRIS server** (remote — queries process table via DBGP/REST API).

    Returns process information including PID, namespace, routine, state,
    and device. Use this to find a process to attach the debugger to.
    """
    processes = await debugger_api.list_processes(system=system)
    if namespace:
        processes = [
            p for p in processes if p.get("namespace", "").upper() == namespace.upper()
        ]
    return processes


@logged_tool
async def debug_attach(
    pid: Annotated[
        int,
        Field(description="Process ID of the IRIS process to attach to."),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace for the debug connection. Uses configured default if omitted."
        ),
    ] = None,
) -> dict:
    """Attach the debugger to a running IRIS process (on the IRIS server).

    **Runs on: IRIS server** (remote — opens a DBGP debug session).

    Pauses the target process and opens an interactive debug session.
    Once attached, use debug_step, debug_inspect, debug_variables,
    debug_stack, and debug_breakpoints to examine and control execution.
    The process resumes when you call debug_stop or the session times out.

    Only one debug session can be active at a time. Call debug_stop to end
    the current session before attaching to a new process.
    """
    return await debugger_api.attach_session(pid=pid, namespace=namespace)


@logged_tool
async def debug_start(
    target: Annotated[
        str,
        Field(
            description=(
                "ObjectScript expression to debug. Examples: "
                "'##class(MyApp.Utils).Calculate(1,2)', 'Main^MyRoutine'. "
                "This is the code that will be executed under the debugger."
            )
        ),
    ],
    stop_on_entry: Annotated[
        bool,
        Field(
            description="If true, break at the first executable line. If false, run until a breakpoint is hit."
        ),
    ] = True,
    breakpoints: Annotated[
        list[dict] | None,
        Field(
            description=(
                "Breakpoints to set before running. Each dict has: "
                "class (str), method (str), offset (int). "
                "Example: [{'class': 'MyApp.Utils', 'method': 'Calculate', 'offset': 3}]. "
                "For conditional breakpoints, add 'condition': 'x > 10'."
            )
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(description="IRIS namespace. Uses configured default if omitted."),
    ] = None,
) -> dict:
    """Start an interactive debug session on an ObjectScript target.

    Opens a DBGP connection to IRIS and begins debugging the specified code.
    Returns a session_id to use with other debug_* tools, along with the
    initial stop location and variable state.

    Only one debug session can be active at a time. Call debug_stop to end
    the current session before starting a new one.
    """
    return await debugger_api.start_session(
        target=target,
        breakpoints=breakpoints,
        stop_on_entry=stop_on_entry,
        namespace=namespace,
    )


@logged_tool
async def debug_step(
    session_id: Annotated[
        str,
        Field(description="Active debug session ID returned by debug_start."),
    ],
    action: Annotated[
        str,
        Field(
            description=(
                "Step action to perform: "
                "'step_into' (enter function calls), "
                "'step_over' (execute current line, skip into calls), "
                "'step_out' (run until current function returns), "
                "'run' (continue to next breakpoint), "
                "'stop' (end the session)."
            )
        ),
    ] = "step_into",
) -> dict:
    """Execute a single debug step and return the new program state.

    Only works when session state is 'break'. Returns the new location
    (file, line), current source context, and all local variables at
    the new position. Use this to walk through code line by line.
    """
    return await debugger_api.step(session_id, action)


@logged_tool
async def debug_inspect(
    session_id: Annotated[
        str,
        Field(description="Active debug session ID."),
    ],
    expression: Annotated[
        str,
        Field(
            description=(
                "Variable name or ObjectScript expression to evaluate. "
                "Examples: 'myVar', 'obj.Property', 'a + b * 2', "
                "'$Length(str)', '##class(Pkg.Cls).Method()'."
            )
        ),
    ],
    stack_level: Annotated[
        int,
        Field(
            description="Stack frame to evaluate in (0 = current frame, 1 = caller, etc.).",
            ge=0,
        ),
    ] = 0,
) -> dict:
    """Evaluate an expression or inspect a variable in the current debug context.

    Only works when session state is 'break'. For simple variable names,
    uses property_get (fast). For expressions, uses eval. Returns the
    value, type, and any child properties for objects and arrays.
    """
    return await debugger_api.inspect_expression(session_id, expression, stack_level)


@logged_tool
async def debug_variables(
    session_id: Annotated[
        str,
        Field(description="Active debug session ID."),
    ],
    context: Annotated[
        str,
        Field(
            description=(
                "Variable scope to retrieve: "
                "'private' (method-local variables), "
                "'public' (process-wide public variables), "
                "'class' (class properties of the current object). "
                "Defaults to 'private'."
            )
        ),
    ] = "private",
    stack_level: Annotated[
        int,
        Field(
            description="Stack frame to inspect (0 = current, 1 = caller, etc.).",
            ge=0,
        ),
    ] = 0,
) -> dict:
    """Get all variables in a specific scope at the current debug position.

    Only works when session state is 'break'. Returns a list of all
    variable names, types, and values in the requested context. Use
    debug_inspect for evaluating expressions or drilling into specific
    variables.
    """
    context_id = {"private": 0, "public": 1, "class": 2}.get(context, 0)
    # stack_level=0 from tool default means "auto-detect" — pass None
    # to let the backend query the correct IRIS stack level
    sl = stack_level if stack_level > 0 else None
    return await debugger_api.get_variables(session_id, context_id, sl)


@logged_tool
async def debug_stack(
    session_id: Annotated[
        str,
        Field(description="Active debug session ID."),
    ],
) -> dict:
    """Get the full call stack of the paused debug session.

    Only works when session state is 'break'. Returns all stack frames
    with file locations and function names, from the current position
    (level 0) up to the entry point.
    """
    return await debugger_api.get_stack(session_id)


@logged_tool
async def debug_breakpoints(
    session_id: Annotated[
        str,
        Field(description="Active debug session ID."),
    ],
    action: Annotated[
        str,
        Field(
            description=(
                "Breakpoint action: 'set' (add new), 'remove' (delete), "
                "'list' (show all), 'enable', 'disable'."
            )
        ),
    ] = "list",
    breakpoint_id: Annotated[
        str | None,
        Field(description="Breakpoint ID (required for remove/enable/disable)."),
    ] = None,
    class_name: Annotated[
        str | None,
        Field(description="Class name for 'set' (e.g. 'MyApp.Utils')."),
    ] = None,
    method: Annotated[
        str | None,
        Field(description="Method name for 'set' (e.g. 'Calculate')."),
    ] = None,
    offset: Annotated[
        int,
        Field(description="Line offset within method for 'set'.", ge=0),
    ] = 0,
    condition: Annotated[
        str | None,
        Field(
            description="Conditional expression for 'set' (e.g. 'x > 10'). Breakpoint only triggers when condition is true."
        ),
    ] = None,
) -> dict:
    """Manage breakpoints in an active debug session.

    Only works when session state is 'break'. Set breakpoints by
    class + method + offset. Use conditional breakpoints to stop only
    when a condition is met. List to see all current breakpoints with
    their IDs.
    """
    return await debugger_api.manage_breakpoints(
        session_id=session_id,
        action=action,
        breakpoint_id=breakpoint_id,
        class_name=class_name,
        method=method,
        offset=offset,
        condition=condition,
    )


@logged_tool
async def debug_stop(
    session_id: Annotated[
        str,
        Field(description="Active debug session ID to stop."),
    ],
) -> dict:
    """Stop a debug session and release all resources.

    Works in any session state. Sends a stop command to IRIS, closes
    the WebSocket connection, and removes the session. The session_id
    becomes invalid after this. Always call this when done debugging.
    """
    return await debugger_api.stop_session(session_id)
