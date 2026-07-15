"""High-level debug operations built on the DBGP protocol client.

Orchestrates DBGP commands into coherent debugging workflows: starting
sessions, stepping, inspecting variables, managing breakpoints.
"""

from __future__ import annotations

import asyncio
import base64
import re
from xml.etree.ElementTree import Element

from urllib.parse import quote

from prism.iris.sdk.dbgp import DbgpConnection, DbgpError
from prism.iris.sdk.debug_session import get_session_manager
from prism.iris.sdk.http import api_url, client, parse_json
from prism.settings import settings


# ── Session lifecycle ─────────────────────────────────────────────────


async def start_session(
    target: str,
    breakpoints: list[dict] | None = None,
    stop_on_entry: bool = True,
    namespace: str | None = None,
) -> dict:
    """Start a new debug session targeting an ObjectScript expression.

    Args:
        target: ObjectScript expression to debug, e.g.
            ``##class(MyApp.Utils).Calculate(1,2)`` or ``Main^MyRoutine``.
        breakpoints: Optional list of breakpoints to set before running.
            Each dict: ``{"class": "Pkg.Cls", "method": "Method", "offset": 1}``
            or ``{"routine": "label^routine", "offset": 1}``.
        stop_on_entry: If True, break at the first line. If False, run until
            a breakpoint is hit.
        namespace: IRIS namespace (defaults to configured).

    Returns:
        Session info with id, initial location, and source context.
    """
    conn = await DbgpConnection.connect(namespace)
    session = None
    manager = get_session_manager()

    try:
        # Configure features first, then set the debug target.
        # The target value is base64-encoded (using -v_base64) to avoid
        # DBGP argument parsing issues with special characters like ##, ()
        # in ObjectScript expressions — matches VS Code ObjectScript extension.
        await conn.send_command(
            "feature_set", n="max_data", v=str(settings.iris_debug_max_data)
        )
        await conn.send_command(
            "feature_set", n="max_children", v=str(settings.iris_debug_max_children)
        )
        await conn.send_command(
            "feature_set", n="max_depth", v=str(settings.iris_debug_max_depth)
        )
        await conn.send_command(
            "feature_set",
            n="step_granularity",
            v=settings.iris_debug_step_granularity,
        )
        target_value = f"{_ns_prefix(namespace)}{target}"
        target_b64 = base64.b64encode(target_value.encode("utf-8")).decode("ascii")
        await conn.send_command("feature_set", n="debug_target", v_base64=target_b64)

        # Register the session before running so we can track it
        session = await manager.create(conn, target, namespace)

        # Set breakpoints if provided
        bp_results = []
        if breakpoints:
            for bp in breakpoints:
                bp_result = await _set_breakpoint(conn, bp, namespace)
                bp_results.append(bp_result)

        # When stop_on_entry is requested, set a breakpoint at offset 0 of
        # the target method. IRIS's step_into runs the target to completion
        # for fast methods, so we need an explicit breakpoint + run instead.
        if stop_on_entry:
            entry_bp = _parse_entry_breakpoint(target)
            if entry_bp:
                try:
                    await _set_breakpoint(conn, entry_bp, namespace)
                except DbgpError:
                    pass  # Best effort — fall back to step_into

        # Start execution — always use run; breakpoints will pause us
        resp = await conn.send_command("run")

        session.state = _status_to_state(resp.get("status", ""))

        result = {
            "session_id": session.id,
            "state": session.state,
            "target": target,
        }

        if bp_results:
            result["breakpoints"] = bp_results

        # If we stopped, get current location info
        if session.state == "break":
            location = _parse_location(resp)
            result["location"] = location
            # Auto-fetch variables at break
            try:
                variables = await _get_context_variables(conn)
                result["variables"] = variables
            except DbgpError:
                pass

        return result

    except Exception:
        # Clean up on failure — remove from session manager if registered
        try:
            if session is not None:
                await manager.close(session.id)
            else:
                await conn.close()
        except Exception:
            pass
        raise


async def list_processes(system: bool = False) -> list[dict]:
    """List IRIS processes via the Atelier jobs API.

    Args:
        system: If True, include system processes.

    Returns:
        List of process dicts with pid, namespace, routine, state, device.
    """
    c = client()
    params = {"system": "1" if system else "0"}
    r = await c.get(f"{api_url('%SYS')}/jobs", params=params)
    r.raise_for_status()
    data = parse_json(r)

    processes = []
    content = data.get("result", {}).get("content", [])
    for item in content:
        processes.append(
            {
                "pid": item.get("pid", 0),
                "namespace": item.get("namespace", ""),
                "routine": item.get("routine", ""),
                "state": item.get("state", ""),
                "device": item.get("device", ""),
            }
        )
    return processes


async def attach_session(
    pid: int,
    namespace: str | None = None,
) -> dict:
    """Attach the debugger to an already-running IRIS process.

    IRIS may drop the WebSocket on first attach if stale debug connections
    exist.  This function retries once on connection-level failures.

    Args:
        pid: Process ID to attach to.
        namespace: IRIS namespace for the DBGP connection (defaults to configured).

    Returns:
        Session info with id, state, target, and location/variables if in break state.
    """
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            return await _do_attach(pid, namespace)
        except (DbgpError, RuntimeError):
            raise  # Protocol / logic errors — don't retry
        except Exception as e:
            last_err = e  # Connection-level failure — IRIS may still be
            # releasing a prior debug agent; back off with increasing delay
            await asyncio.sleep(2 * (attempt + 1))
    raise last_err  # type: ignore[misc]


async def _do_attach(pid: int, namespace: str | None) -> dict:
    conn = await DbgpConnection.connect(namespace)
    session = None
    manager = get_session_manager()
    target = f"PID:{pid}"

    try:
        # Set debug target FIRST — must be sent before other feature_set
        # commands for PID attach on Windows IRIS (matches VS Code extension).
        await conn.send_command("feature_set", n="debug_target", v=target)

        # Then configure session features
        await conn.send_command(
            "feature_set", n="max_data", v=str(settings.iris_debug_max_data)
        )
        await conn.send_command(
            "feature_set", n="max_children", v=str(settings.iris_debug_max_children)
        )
        await conn.send_command(
            "feature_set", n="max_depth", v=str(settings.iris_debug_max_depth)
        )
        await conn.send_command(
            "feature_set",
            n="step_granularity",
            v=settings.iris_debug_step_granularity,
        )

        # Register the session
        session = await manager.create(conn, target, namespace)

        # Attach sequence: IRIS ignores the first "run" for non-CSP PID
        # attach, so send two "run" commands (matches VS Code extension).
        # Then "break" to interrupt the target at the next interruptible point.
        # Finally poll with "step_into" until IRIS confirms status "break".
        timeout = 15
        interval = 1
        elapsed = 0
        resp = None

        # First run — ignored by IRIS, completes the attach handshake
        try:
            resp = await conn.send_command("run")
            if resp.get("status") == "break":
                elapsed = timeout
        except DbgpError:
            pass

        # Second run — actually binds the debugger
        if elapsed < timeout:
            try:
                resp = await conn.send_command("run")
                if resp.get("status") == "break":
                    elapsed = timeout
            except DbgpError:
                pass

        # Send break to interrupt the target process
        if elapsed < timeout:
            try:
                resp = await conn.send_command("break")
                if resp.get("status") == "break":
                    elapsed = timeout
            except DbgpError:
                pass

        # Poll until we get a break status
        while elapsed < timeout:
            try:
                resp = await conn.send_command("step_into")
            except DbgpError as e:
                # Error 6709 = "Target not stopped" — not yet attached, retry
                if e.code == 998 or "6709" in str(e):
                    await asyncio.sleep(interval)
                    elapsed += interval
                    continue
                raise

            status = resp.get("status", "")

            if status == "break":
                break
            elif status in ("stopping", "stopped"):
                raise RuntimeError(
                    f"Attach failed: process {pid} returned status '{status}'. "
                    "The process may have already finished."
                )
            await asyncio.sleep(interval)
            elapsed += interval
        else:
            if resp is None or resp.get("status") != "break":
                raise RuntimeError(
                    f"Attach timed out after {timeout}s: process {pid} did not reach "
                    "'break' state. The process may not be attachable."
                )

        session.state = _status_to_state(resp.get("status", ""))

        result: dict = {
            "session_id": session.id,
            "state": session.state,
            "target": target,
        }

        if session.state == "break":
            location = _parse_location(resp)
            result["location"] = location
            try:
                variables = await _get_context_variables(conn)
                result["variables"] = variables
            except DbgpError:
                pass

        return result

    except Exception:
        try:
            if session is not None:
                await manager.close(session.id)
            else:
                await conn.close()
        except Exception:
            pass
        raise


async def step(session_id: str, action: str = "step_into") -> dict:
    """Execute a step action in an active debug session.

    Args:
        session_id: The session to step in.
        action: One of ``step_into``, ``step_over``, ``step_out``, ``run``,
            ``break``, ``stop``.

    Returns:
        New state with location, source, and variables.
    """
    valid_actions = {"step_into", "step_over", "step_out", "run", "break", "stop"}
    if action not in valid_actions:
        raise ValueError(f"Invalid action '{action}'. Must be one of: {valid_actions}")

    manager = get_session_manager()
    session = manager.get(session_id)

    if action == "stop":
        await session.conn.send_command("stop")
        await manager.close(session_id)
        return {"session_id": session_id, "state": "ended"}

    resp = await session.conn.send_command(action)
    session.state = _status_to_state(resp.get("status", ""))

    result: dict = {
        "session_id": session_id,
        "state": session.state,
    }

    if session.state == "break":
        result["location"] = _parse_location(resp)
        try:
            result["variables"] = await _get_context_variables(session.conn)
        except DbgpError:
            pass
    elif session.state == "ended":
        await manager.close(session_id)

    return result


# ── Inspection ────────────────────────────────────────────────────────


async def get_variables(
    session_id: str,
    context: int = 0,
    stack_level: int | None = None,
) -> dict:
    """Get all variables in a given context and stack level.

    Args:
        session_id: Active session ID.
        context: 0=PRIVATE, 1=PUBLIC, 2=CLASS.
        stack_level: Stack frame level. None auto-detects from stack_get
            (IRIS levels start at 1, not 0).
    """
    session = get_session_manager().get(session_id)
    variables = await _get_context_variables(session.conn, context, stack_level)
    return {
        "session_id": session_id,
        "context": _context_name(context),
        "stack_level": stack_level,
        "variables": variables,
    }


async def inspect_expression(
    session_id: str,
    expression: str,
    stack_level: int = 0,
) -> dict:
    """Evaluate an expression or get a property value.

    Args:
        session_id: Active session ID.
        expression: Variable name (e.g. ``myVar``) or ObjectScript expression
            (e.g. ``a + b``).
        stack_level: Call stack depth for evaluation context.
    """
    session = get_session_manager().get(session_id)

    # Use eval for all expressions — property_get has argument parsing
    # issues with IRIS's DBGP implementation, while eval works reliably
    # for both variable names and complex expressions.
    encoded = base64.b64encode(expression.encode("utf-8")).decode("ascii")
    resp = await session.conn.send_command("eval", data=encoded)
    return {
        "session_id": session_id,
        "expression": expression,
        **_parse_property(resp),
    }


async def get_stack(session_id: str) -> dict:
    """Get the full call stack for a paused session."""
    session = get_session_manager().get(session_id)
    resp = await session.conn.send_command("stack_get")

    frames = []
    for stack_elem in resp:
        if stack_elem.tag.endswith("stack") or stack_elem.tag == "stack":
            frames.append(
                {
                    "level": int(stack_elem.get("level", "0")),
                    "type": stack_elem.get("type", ""),
                    "filename": stack_elem.get("filename", ""),
                    "lineno": int(stack_elem.get("lineno", "0")),
                    "where": stack_elem.get("where", ""),
                    "cmdbegin": stack_elem.get("cmdbegin", ""),
                }
            )

    return {"session_id": session_id, "frames": frames}


# ── Breakpoints ───────────────────────────────────────────────────────


async def manage_breakpoints(
    session_id: str,
    action: str,
    breakpoint_id: str | None = None,
    class_name: str | None = None,
    method: str | None = None,
    offset: int = 0,
    condition: str | None = None,
) -> dict:
    """Manage breakpoints in an active session.

    Args:
        action: ``set``, ``remove``, ``list``, ``enable``, ``disable``.
        breakpoint_id: Required for remove/enable/disable.
        class_name: Class for set (e.g. ``MyApp.Utils``).
        method: Method name for set.
        offset: Line offset within method for set.
        condition: Optional conditional expression for set.
    """
    session = get_session_manager().get(session_id)

    if action == "list":
        resp = await session.conn.send_command("breakpoint_list")
        bps = _parse_breakpoint_list(resp)
        return {"session_id": session_id, "breakpoints": bps}

    if action == "set":
        bp_def: dict = {}
        if class_name and method:
            bp_def = {
                "class": class_name,
                "method": method,
                "offset": offset,
            }
            if condition:
                bp_def["condition"] = condition
        bp_result = await _set_breakpoint(session.conn, bp_def)
        return {"session_id": session_id, "breakpoint": bp_result}

    if action in ("remove", "enable", "disable"):
        if not breakpoint_id:
            raise ValueError(f"breakpoint_id is required for '{action}'")
        if action == "remove":
            await session.conn.send_command("breakpoint_remove", d=breakpoint_id)
        else:
            state = "enabled" if action == "enable" else "disabled"
            await session.conn.send_command(
                "breakpoint_update", d=breakpoint_id, s=state
            )
        return {
            "session_id": session_id,
            "action": action,
            "breakpoint_id": breakpoint_id,
        }

    raise ValueError(f"Invalid breakpoint action: {action}")


async def stop_session(session_id: str) -> dict:
    """Stop a debug session and clean up."""
    manager = get_session_manager()
    session = manager.get(session_id)

    try:
        await session.conn.send_command("stop")
    except (DbgpError, Exception):
        pass

    await manager.close(session_id)
    return {"session_id": session_id, "state": "ended"}


# ── Internal helpers ──────────────────────────────────────────────────


def _ns_prefix(namespace: str | None) -> str:
    """Build the namespace prefix for debug_target feature.

    IRIS debug_target requires ``NAMESPACE:expression`` format.
    Falls back to the configured default namespace.
    """
    ns = namespace or settings.iris_namespace
    return f"{ns}:"


def _status_to_state(status: str) -> str:
    """Map DBGP status attribute to our session state."""
    if status == "break":
        return "break"
    if status in ("stopping", "stopped"):
        return "ended"
    if status == "running":
        return "running"
    return status or "unknown"


def _parse_location(resp: Element) -> dict:
    """Extract location info from a step/run response."""
    # The response itself may have filename/lineno, or a child <xdebug:message>
    location: dict = {}

    filename = resp.get("filename", "")
    lineno = resp.get("lineno", "")
    if not filename:
        # Look for message child element
        for child in resp:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "message":
                filename = child.get("filename", "")
                lineno = child.get("lineno", "")
                break

    if filename:
        location["filename"] = filename
    if lineno:
        location["line"] = int(lineno)

    return location


async def _get_context_variables(
    conn: DbgpConnection,
    context: int = 0,
    stack_level: int | None = None,
) -> list[dict]:
    """Fetch all variables in a given context.

    If *stack_level* is None, auto-detects the correct level by querying
    ``stack_get`` first — IRIS stack levels start at 1, not 0.
    """
    if stack_level is None:
        stack_level = await _get_current_stack_level(conn)
    resp = await conn.send_command("context_get", c=str(context), d=str(stack_level))
    variables = []
    for prop in resp:
        tag = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
        if tag == "property":
            variables.append(_parse_property(prop))
    return variables


def _parse_property(elem: Element) -> dict:
    """Parse a DBGP <property> element into a dict."""
    result: dict = {
        "name": elem.get("fullname") or elem.get("name", ""),
        "type": elem.get("type", ""),
    }

    encoding = elem.get("encoding", "")
    if elem.text:
        if encoding == "base64":
            try:
                result["value"] = base64.b64decode(elem.text).decode("utf-8")
            except Exception:
                result["value"] = elem.text
        else:
            result["value"] = elem.text

    # Parse children (nested properties for objects/arrays)
    children = []
    for child in elem:
        child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if child_tag == "property":
            children.append(_parse_property(child))
    if children:
        result["children"] = children

    num_children = elem.get("numchildren")
    if num_children is not None:
        result["num_children"] = int(num_children)

    return result


def _parse_breakpoint_list(resp: Element) -> list[dict]:
    """Parse a breakpoint_list response into a list of dicts."""
    bps = []
    for child in resp:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "breakpoint":
            bps.append(
                {
                    "id": child.get("id", ""),
                    "type": child.get("type", ""),
                    "state": child.get("state", ""),
                    "filename": child.get("filename", ""),
                    "lineno": int(child.get("lineno", "0")),
                    "method": child.get("function", ""),
                    "hit_count": int(child.get("hit_count", "0")),
                }
            )
    return bps


async def _set_breakpoint(
    conn: DbgpConnection, bp: dict, namespace: str | None = None
) -> dict:
    """Set a single breakpoint from a breakpoint definition dict.

    IRIS expects file URIs in ``dbgp://|NAMESPACE|FileName.cls`` format
    and method offsets counted from the opening ``{`` of the method body.
    """
    args: dict[str, str] = {"t": "line", "s": "enabled"}

    cls = bp.get("class", "")
    method = bp.get("method", "")
    offset = bp.get("offset", 0)
    routine = bp.get("routine", "")
    condition = bp.get("condition", "")
    ns = namespace or settings.iris_namespace

    if cls and method:
        file_uri = f"dbgp://|{quote(ns)}|{quote(cls + '.cls')}"
        args["f"] = file_uri
        args["m"] = method
        args["n"] = str(offset)
    elif routine:
        file_uri = f"dbgp://|{quote(ns)}|{quote(routine)}"
        args["f"] = file_uri
        args["n"] = str(offset)

    if condition:
        args["t"] = "conditional"
        encoded = base64.b64encode(condition.encode("utf-8")).decode("ascii")
        # condition is sent as the data payload
        resp = await conn.send_command("breakpoint_set", data=encoded, **args)
    else:
        resp = await conn.send_command("breakpoint_set", **args)

    return {
        "id": resp.get("id", ""),
        "state": resp.get("state", "enabled"),
        **{k: v for k, v in bp.items() if v},
    }


def _parse_entry_breakpoint(target: str) -> dict | None:
    """Extract class and method from a target expression for an entry breakpoint.

    Parses ``##class(Pkg.Cls).Method(args)`` into
    ``{"class": "Pkg.Cls", "method": "Method", "offset": 0}``.
    Returns None if the target format is not recognized.
    """
    match = re.match(r"##class\(([^)]+)\)\.(\w+)", target)
    if match:
        return {"class": match.group(1), "method": match.group(2), "offset": 0}
    return None


async def _get_current_stack_level(conn: DbgpConnection) -> int:
    """Query the stack and return the lowest (most recent) frame level.

    IRIS stack levels start at 1 for user code, not 0.
    """
    resp = await conn.send_command("stack_get")
    min_level = 1  # default fallback
    for child in resp:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "stack":
            level = int(child.get("level", "1"))
            min_level = min(min_level, level)
    return min_level


def _context_name(context_id: int) -> str:
    return {0: "private", 1: "public", 2: "class"}.get(
        context_id, f"context_{context_id}"
    )
