"""Integration tests for additional debugger functionality.

Covers: step_into, step_out, public/class variable contexts,
conditional breakpoints, breakpoint enable/disable.
"""

import pytest

from tests.integration.test_debugger import (
    _deploy_target,
    _parse,
    _var_dict,
)


@pytest.fixture
async def debug_session(live, workspace):
    """Start a debug session. Skips if XDebug is unavailable."""
    await _deploy_target(live, workspace)
    try:
        start = _parse(
            await live.call_tool(
                "debug_start",
                {
                    "target": "##class(Test.MCPDebugTarget).Calculate(3,5)",
                    "stop_on_entry": True,
                },
            )
        )
        if "session_id" not in start:
            pytest.skip("XDebug WebSocket not available")
        yield start["session_id"]
        try:
            await live.call_tool("debug_stop", {"session_id": start["session_id"]})
        except Exception:
            pass
    except Exception as e:
        pytest.skip(f"XDebug not available: {e}")


class TestStepInto:
    async def test_step_into_advances_one_line(self, live, debug_session):
        """step_into should advance the debug session by one line."""
        session_id = debug_session

        step1 = _parse(
            await live.call_tool(
                "debug_step",
                {"session_id": session_id, "action": "step_into"},
            )
        )
        assert step1["state"] == "break"

        step2 = _parse(
            await live.call_tool(
                "debug_step",
                {"session_id": session_id, "action": "step_into"},
            )
        )
        assert step2["state"] == "break"


class TestStepOut:
    async def test_step_out_returns_to_caller(self, live, debug_session):
        """step_out should step out of the current method."""
        session_id = debug_session

        await live.call_tool(
            "debug_step",
            {"session_id": session_id, "action": "step_into"},
        )

        out = _parse(
            await live.call_tool(
                "debug_step",
                {"session_id": session_id, "action": "step_out"},
            )
        )
        assert out["state"] in ("break", "ended")


class TestVariableContexts:
    async def test_debug_variables_public(self, live, debug_session):
        """debug_variables with context=public returns public variables."""
        session_id = debug_session

        await live.call_tool(
            "debug_step",
            {"session_id": session_id, "action": "step_over"},
        )
        await live.call_tool(
            "debug_step",
            {"session_id": session_id, "action": "step_over"},
        )

        result = _parse(
            await live.call_tool(
                "debug_variables",
                {"session_id": session_id, "context": "public"},
            )
        )
        assert result["context"] == "public"
        assert "variables" in result

    async def test_debug_variables_class(self, live, debug_session):
        """debug_variables with context=class returns class variables."""
        session_id = debug_session

        await live.call_tool(
            "debug_step",
            {"session_id": session_id, "action": "step_over"},
        )

        result = _parse(
            await live.call_tool(
                "debug_variables",
                {"session_id": session_id, "context": "class"},
            )
        )
        assert result["context"] == "class"
        assert "variables" in result


class TestConditionalBreakpoint:
    async def test_conditional_breakpoint(self, live, workspace):
        """Set a conditional breakpoint and verify it stops when condition is met."""
        await _deploy_target(live, workspace)
        try:
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
                                "offset": 1,
                                "condition": "result=8",
                            }
                        ],
                    },
                )
            )
        except Exception as e:
            pytest.skip(f"XDebug not available: {e}")

        session_id = start["session_id"]
        assert start["state"] == "break"

        vd = _var_dict(start.get("variables", []))
        assert vd.get("result") == "8"

        await live.call_tool("debug_stop", {"session_id": session_id})


class TestBreakpointEnableDisable:
    async def test_enable_disable_breakpoint(self, live, debug_session):
        """Set, disable, enable, and remove a breakpoint."""
        session_id = debug_session

        bp = _parse(
            await live.call_tool(
                "debug_breakpoints",
                {
                    "session_id": session_id,
                    "action": "set",
                    "class_name": "Test.MCPDebugTarget",
                    "method": "Calculate",
                    "offset": 2,
                },
            )
        )
        bp_id = bp["breakpoint"]["id"]
        assert bp_id

        bp_list = _parse(
            await live.call_tool(
                "debug_breakpoints",
                {"session_id": session_id, "action": "list"},
            )
        )
        assert len(bp_list["breakpoints"]) >= 1

        disable = _parse(
            await live.call_tool(
                "debug_breakpoints",
                {
                    "session_id": session_id,
                    "action": "disable",
                    "breakpoint_id": bp_id,
                },
            )
        )
        assert disable["action"] == "disable"

        enable = _parse(
            await live.call_tool(
                "debug_breakpoints",
                {
                    "session_id": session_id,
                    "action": "enable",
                    "breakpoint_id": bp_id,
                },
            )
        )
        assert enable["action"] == "enable"

        remove = _parse(
            await live.call_tool(
                "debug_breakpoints",
                {
                    "session_id": session_id,
                    "action": "remove",
                    "breakpoint_id": bp_id,
                },
            )
        )
        assert remove["action"] == "remove"


class TestInspectWithStackLevel:
    async def test_inspect_with_stack_level(self, live, debug_session):
        """debug_inspect with explicit stack_level parameter."""
        session_id = debug_session

        await live.call_tool(
            "debug_step",
            {"session_id": session_id, "action": "step_over"},
        )

        inspect = _parse(
            await live.call_tool(
                "debug_inspect",
                {
                    "session_id": session_id,
                    "expression": "a",
                    "stack_level": 1,
                },
            )
        )
        assert inspect["expression"] == "a"
