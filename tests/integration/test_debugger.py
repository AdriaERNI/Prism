"""Integration tests for the interactive debugging tools.

Deploys a test class to IRIS, then exercises the debug_* MCP tools
to simulate real agent debugging workflows: stepping through code,
inspecting variables, setting breakpoints, and attaching to processes.
"""

import asyncio
import json

import pytest

from tests.integration.conftest import write_to_workspace

# ── Test class source ────────────────────────────────────────────────

DEBUG_TARGET_SOURCE = [
    "Class Test.MCPDebugTarget Extends %RegisteredObject",
    "{",
    "",
    "/// Calculate sum and doubled value for debugging tests.",
    "ClassMethod Calculate(a As %Integer, b As %Integer) As %Integer",
    "{",
    "    Set result = a + b",
    "    Set doubled = result * 2",
    "    If doubled > 10 {",
    '        Set status = "big"',
    "    } Else {",
    '        Set status = "small"',
    "    }",
    "    Return doubled",
    "}",
    "",
    "/// Long-running method for attach tests.",
    "ClassMethod LongRunning()",
    "{",
    "    Set x = 42",
    "    Set y = 58",
    "    Set z = x + y",
    "    Hang 30",
    "}",
    "",
    "/// Start LongRunning as a background job. Returns the job PID.",
    "ClassMethod StartLongRunning() As %Integer [ SqlProc ]",
    "{",
    "    Job ..LongRunning()",
    "    Return $ZChild",
    "}",
    "",
    "}",
]


# ── Helpers ──────────────────────────────────────────────────────────


async def _deploy_target(live, workspace):
    """Deploy Test.MCPDebugTarget.cls to IRIS and compile it."""
    write_to_workspace(workspace, "Test.MCPDebugTarget.cls", DEBUG_TARGET_SOURCE)
    await live.call_tool(
        "put_and_compile",
        {"name": "Test.MCPDebugTarget.cls", "path": "Test.MCPDebugTarget.cls"},
    )


@pytest.fixture(autouse=True, scope="module")
async def _cleanup_debug_target():
    """Delete Test.MCPDebugTarget.cls only once after all debugger tests run."""
    yield
    import httpx

    import prism.iris.sdk.http as http_mod
    from prism.config import (
        IRIS_API_PREFIX,
        IRIS_BASE_URL,
        IRIS_PASSWORD,
        IRIS_USERNAME,
    )

    http_mod._client = None
    async with httpx.AsyncClient(
        auth=httpx.BasicAuth(IRIS_USERNAME, IRIS_PASSWORD)
    ) as c:
        url = f"{IRIS_BASE_URL}/{IRIS_API_PREFIX}/USER/doc/Test.MCPDebugTarget.cls"
        await c.delete(url)
        http_mod._client = None


def _parse(result) -> dict | list:
    # FastMCP returns text content for dict returns, structured for lists
    if result.content:
        return json.loads(result.content[0].text)
    # Fallback for structured content (e.g. list[dict] return types)
    if hasattr(result, "structured_content") and result.structured_content is not None:
        sc = result.structured_content
        # Handle pydantic Root wrapper
        if hasattr(sc, "root"):
            return sc.root
        if isinstance(sc, dict):
            return sc.get("result", sc)
        return sc
    raise ValueError(f"Cannot parse result: {result}")


def _var_dict(variables: list[dict]) -> dict[str, str]:
    """Convert a list of variable dicts to {name: value} for easy assertions."""
    return {v["name"]: v.get("value", "") for v in variables}


def _eval_value(inspect_result: dict) -> str:
    """Extract the value from a debug_inspect response.

    IRIS eval returns the value either at the top level or nested
    under children[0] depending on the expression type.
    """
    return inspect_result.get("value") or inspect_result.get("children", [{}])[0].get(
        "value", ""
    )


# ── 1. Smoke test: start and stop ────────────────────────────────────


class TestDebugStartStop:
    """Basic session lifecycle: start a debug session and stop it."""

    async def test_start_and_stop(self, live, workspace):
        """Start a debug session with stop_on_entry and immediately stop it."""
        await _deploy_target(live, workspace)

        result = _parse(
            await live.call_tool(
                "debug_start",
                {
                    "target": "##class(Test.MCPDebugTarget).Calculate(3,5)",
                    "stop_on_entry": True,
                },
            )
        )

        assert "session_id" in result
        assert result["target"] == "##class(Test.MCPDebugTarget).Calculate(3,5)"
        assert result["state"] == "break"
        session_id = result["session_id"]

        # Variables should include the method params
        assert "variables" in result
        vd = _var_dict(result["variables"])
        assert "a" in vd
        assert "b" in vd

        stop = _parse(await live.call_tool("debug_stop", {"session_id": session_id}))
        assert stop["state"] == "ended"


# ── 2. Full stepping workflow ────────────────────────────────────────


class TestFullSteppingWorkflow:
    """Simulate an agent stepping through Calculate(3,5) line by line,
    checking variable values after each step — the most common debug
    workflow an agent would perform."""

    async def test_step_and_verify_variable_values(self, live, workspace):
        """Step through Calculate(3,5) and verify result=8, doubled=16."""
        await _deploy_target(live, workspace)

        start = _parse(
            await live.call_tool(
                "debug_start",
                {
                    "target": "##class(Test.MCPDebugTarget).Calculate(3,5)",
                    "stop_on_entry": True,
                },
            )
        )
        session_id = start["session_id"]
        assert start["state"] == "break"

        # Step 1: execute "Set result = a + b"
        step1 = _parse(
            await live.call_tool(
                "debug_step",
                {"session_id": session_id, "action": "step_over"},
            )
        )
        assert step1["state"] == "break"
        vars1 = _var_dict(step1.get("variables", []))
        assert "result" in vars1
        assert vars1["result"] == "8"

        # Step 2: execute "Set doubled = result * 2"
        step2 = _parse(
            await live.call_tool(
                "debug_step",
                {"session_id": session_id, "action": "step_over"},
            )
        )
        assert step2["state"] == "break"
        vars2 = _var_dict(step2.get("variables", []))
        assert "doubled" in vars2
        assert vars2["doubled"] == "16"

        # Step 3: enters the If branch (doubled=16 > 10)
        step3 = _parse(
            await live.call_tool(
                "debug_step",
                {"session_id": session_id, "action": "step_over"},
            )
        )
        assert step3["state"] == "break"

        # Step 4: executes Set status = "big"
        step4 = _parse(
            await live.call_tool(
                "debug_step",
                {"session_id": session_id, "action": "step_over"},
            )
        )
        if step4["state"] == "break":
            vars4 = _var_dict(step4.get("variables", []))
            if "status" in vars4:
                assert vars4["status"] == "big"

        await live.call_tool("debug_stop", {"session_id": session_id})


# ── 3. Variable inspection by name ──────────────────────────────────


class TestInspectVariables:
    """Agent inspects specific variables and evaluates expressions
    using values from the running code — not just literals."""

    async def test_inspect_variable_by_name(self, live, workspace):
        """Use debug_inspect to read a specific variable's value."""
        await _deploy_target(live, workspace)

        start = _parse(
            await live.call_tool(
                "debug_start",
                {
                    "target": "##class(Test.MCPDebugTarget).Calculate(3,5)",
                    "stop_on_entry": True,
                },
            )
        )
        session_id = start["session_id"]
        assert start["state"] == "break"

        # Step past "Set result = a + b"
        await live.call_tool(
            "debug_step",
            {"session_id": session_id, "action": "step_over"},
        )

        # Inspect the variable 'result' by name
        inspect = _parse(
            await live.call_tool(
                "debug_inspect",
                {"session_id": session_id, "expression": "result"},
            )
        )
        assert inspect["expression"] == "result"
        assert _eval_value(inspect) == "8"

        # Evaluate an expression using a variable from the running code
        inspect2 = _parse(
            await live.call_tool(
                "debug_inspect",
                {"session_id": session_id, "expression": "result * 3"},
            )
        )
        assert _eval_value(inspect2) == "24"

        await live.call_tool("debug_stop", {"session_id": session_id})

    async def test_get_variables_returns_all_locals(self, live, workspace):
        """debug_variables returns all local variables with correct values."""
        await _deploy_target(live, workspace)

        start = _parse(
            await live.call_tool(
                "debug_start",
                {
                    "target": "##class(Test.MCPDebugTarget).Calculate(3,5)",
                    "stop_on_entry": True,
                },
            )
        )
        session_id = start["session_id"]

        # Step twice: past "Set result" and "Set doubled"
        await live.call_tool(
            "debug_step",
            {"session_id": session_id, "action": "step_over"},
        )
        await live.call_tool(
            "debug_step",
            {"session_id": session_id, "action": "step_over"},
        )

        # Explicitly fetch private variables
        vars_result = _parse(
            await live.call_tool(
                "debug_variables",
                {"session_id": session_id, "context": "private"},
            )
        )

        assert vars_result["context"] == "private"
        vd = _var_dict(vars_result["variables"])
        # Method params and locals should all be visible
        assert "a" in vd
        assert "b" in vd
        assert "result" in vd
        assert "doubled" in vd
        assert vd["a"] == "3"
        assert vd["b"] == "5"
        assert vd["result"] == "8"
        assert vd["doubled"] == "16"

        await live.call_tool("debug_stop", {"session_id": session_id})


# ── 4. Stack inspection ─────────────────────────────────────────────


class TestStackInspection:
    """Agent examines the call stack to understand execution context."""

    async def test_stack_shows_method_name(self, live, workspace):
        """The call stack should show the method being debugged."""
        await _deploy_target(live, workspace)

        start = _parse(
            await live.call_tool(
                "debug_start",
                {
                    "target": "##class(Test.MCPDebugTarget).Calculate(3,5)",
                    "stop_on_entry": True,
                },
            )
        )
        session_id = start["session_id"]
        assert start["state"] == "break"

        stack = _parse(await live.call_tool("debug_stack", {"session_id": session_id}))

        assert "frames" in stack
        assert len(stack["frames"]) >= 1

        # At least one frame should reference our class or method
        frame_text = " ".join(
            f.get("where", "") + f.get("filename", "") for f in stack["frames"]
        )
        assert "Calculate" in frame_text or "MCPDebugTarget" in frame_text

        await live.call_tool("debug_stop", {"session_id": session_id})


# ── 5. Breakpoints ──────────────────────────────────────────────────


class TestBreakpoints:
    """Agent sets breakpoints and runs to them — skipping lines
    instead of stepping one by one."""

    async def test_set_breakpoint_and_run_to_it(self, live, workspace):
        """Set a breakpoint at offset 2, run to it, and verify
        'result' is already set when we stop."""
        await _deploy_target(live, workspace)

        # Start with stop_on_entry=false and a breakpoint at offset 2.
        # IRIS offsets within Calculate:
        #   0: Set result = a + b
        #   1: Set doubled = result * 2
        #   2: If doubled > 10 {
        # Breakpoint at offset 2 should stop after result and doubled are set.
        start = _parse(
            await live.call_tool(
                "debug_start",
                {
                    "target": "##class(Test.MCPDebugTarget).Calculate(3,5)",
                    "stop_on_entry": False,
                    "breakpoints": [
                        {
                            "class": "Test.MCPDebugTarget",
                            "method": "Calculate",
                            "offset": 2,
                        }
                    ],
                },
            )
        )
        session_id = start["session_id"]
        assert start["state"] == "break"

        # At this point, result and doubled should be set
        vars_at_bp = _var_dict(start.get("variables", []))
        assert "result" in vars_at_bp
        assert vars_at_bp["result"] == "8"

        await live.call_tool("debug_stop", {"session_id": session_id})

    async def test_set_breakpoint_during_session(self, live, workspace):
        """Start with stop_on_entry, add a breakpoint mid-session, then run to it."""
        await _deploy_target(live, workspace)

        start = _parse(
            await live.call_tool(
                "debug_start",
                {
                    "target": "##class(Test.MCPDebugTarget).Calculate(3,5)",
                    "stop_on_entry": True,
                },
            )
        )
        session_id = start["session_id"]
        assert start["state"] == "break"

        # Set a breakpoint further into the method (offset 3)
        # so we can verify running to it skips intermediate lines.
        bp_result = _parse(
            await live.call_tool(
                "debug_breakpoints",
                {
                    "session_id": session_id,
                    "action": "set",
                    "class_name": "Test.MCPDebugTarget",
                    "method": "Calculate",
                    "offset": 3,
                },
            )
        )
        assert "breakpoint" in bp_result
        assert bp_result["breakpoint"]["id"]

        # List breakpoints — should include ours
        bp_list = _parse(
            await live.call_tool(
                "debug_breakpoints",
                {"session_id": session_id, "action": "list"},
            )
        )
        assert len(bp_list["breakpoints"]) >= 1

        # Run to the breakpoint (skip stepping)
        run_result = _parse(
            await live.call_tool(
                "debug_step",
                {"session_id": session_id, "action": "run"},
            )
        )
        assert run_result["state"] == "break"

        # result should be set after running past it
        vd = _var_dict(run_result.get("variables", []))
        assert "result" in vd
        assert vd["result"] == "8"

        await live.call_tool("debug_stop", {"session_id": session_id})


# ── 6. Process discovery and attach ─────────────────────────────────


class TestProcessDiscovery:
    """Agent lists running IRIS processes."""

    async def test_list_processes_returns_pids(self, live, workspace):
        """debug_list_processes returns running IRIS processes with PIDs."""
        result = _parse(await live.call_tool("debug_list_processes", {"system": True}))

        assert isinstance(result, list)
        assert len(result) > 0
        proc = result[0]
        assert "pid" in proc
        assert "namespace" in proc
        assert "routine" in proc
        assert "state" in proc


class TestAttachToProcess:
    """Agent finds a running process, attaches, inspects state, and detaches.

    PID attach via XDebug WebSocket drops the connection on Windows IRIS
    (the server closes the socket when receiving `feature_set debug_target PID:x`).
    The VS Code ObjectScript extension has the same limitation — it only
    supports PID attach on Linux/macOS IRIS. This test skips on platforms
    where PID attach is not supported.
    """

    async def test_attach_inspect_and_detach(self, live, workspace):
        """Full attach workflow: job → attach → inspect variables → eval → stop."""
        await _deploy_target(live, workspace)

        # Start a background job via SqlProc — returns the child PID directly
        job_result = _parse(
            await live.call_tool(
                "execute_sql",
                {"query": "SELECT Test.MCPDebugTarget_StartLongRunning() AS pid"},
            )
        )

        pid = int(job_result["rows"][0]["pid"])
        assert pid > 0

        # Give IRIS a moment to start the job
        await asyncio.sleep(2)

        try:
            attach_result = _parse(await live.call_tool("debug_attach", {"pid": pid}))
        except Exception as e:
            if "close frame" in str(e) or "ConnectionClosed" in type(e).__name__:
                pytest.skip(f"PID attach not supported on this IRIS platform: {e}")
            raise

        assert "session_id" in attach_result
        assert attach_result["state"] == "break"
        session_id = attach_result["session_id"]

        # LongRunning sets x=42, y=58, z=100 before Hang 30
        vd = _var_dict(attach_result.get("variables", []))
        assert vd.get("x") == "42"
        assert vd.get("y") == "58"
        assert vd.get("z") == "100"

        # Explicitly fetch variables via debug_variables
        vars_result = _parse(
            await live.call_tool(
                "debug_variables",
                {"session_id": session_id, "context": "private"},
            )
        )
        vars_vd = _var_dict(vars_result["variables"])
        assert vars_vd.get("x") == "42"

        # Evaluate an expression in the attached context
        inspect = _parse(
            await live.call_tool(
                "debug_inspect",
                {"session_id": session_id, "expression": "x + y"},
            )
        )
        assert _eval_value(inspect) == "100"

        # Detach — process resumes
        stop = _parse(await live.call_tool("debug_stop", {"session_id": session_id}))
        assert stop["state"] == "ended"
