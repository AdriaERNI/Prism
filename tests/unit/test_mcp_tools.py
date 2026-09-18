"""Unit tests for MCP tool layer — testing.py, sql.py, debugger.py.

These tests mock the iris.api layer to verify the MCP tools' parsing,
error handling, and return-value shaping logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from prism.mcp import debugger as debugger_mcp
from prism.mcp import sql as sql_mcp
from prism.mcp import testing as testing_mcp

# ── MCP testing.py: run_tests ──────────────────────────────────────────


class TestMcpRunTests:
    """Tests for the MCP run_tests tool."""

    async def test_run_tests_all_pass(self):
        """All test methods pass → status 'passed'."""
        run_data = {
            "status": {"errors": []},
            "result": {"content": [{"Result": "1"}]},
        }
        results_data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {"method_name": "TestAdd", "method_status": 1, "method_duration": 0.1},
                    {"method_name": "TestSub", "method_status": 1, "method_duration": 0.2},
                ]
            },
        }
        with (
            patch.object(testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)),
            patch.object(
                testing_mcp.testing_api, "get_latest_results", AsyncMock(return_value=results_data)
            ),
            patch.object(
                testing_mcp.testing_api,
                "get_assertions",
                AsyncMock(return_value={"result": {"content": []}}),
            ),
        ):
            result = await testing_mcp.run_tests("MyApp.Tests.Calc")

        assert result["status"] == "passed"
        assert result["passed"] == 2
        assert result["failed"] == 0
        assert result["skipped"] == 0
        assert len(result["methods"]) == 2
        assert result["methods"][0]["name"] == "TestAdd"

    async def test_run_tests_with_failures(self):
        """Failed test method → status 'failed', with error details + assertions."""
        run_data = {
            "status": {"errors": []},
            "result": {"content": [{"Result": "0"}]},
        }
        results_data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {"method_name": "TestAdd", "method_status": 1, "method_duration": 0.1},
                    {
                        "method_name": "TestFail",
                        "method_status": 0,
                        "method_duration": 0.5,
                        "error_description": "Expected 5, got 3",
                        "error_action": "AssertEquals",
                    },
                ]
            },
        }
        assertions_data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {"action": "AssertEquals", "description": "5 == result", "status": 0},
                    {"action": "LogMessage", "description": "setup", "status": 1},
                ]
            },
        }
        with (
            patch.object(testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)),
            patch.object(
                testing_mcp.testing_api, "get_latest_results", AsyncMock(return_value=results_data)
            ),
            patch.object(
                testing_mcp.testing_api, "get_assertions", AsyncMock(return_value=assertions_data)
            ),
        ):
            result = await testing_mcp.run_tests("MyApp.Tests.Calc")

        assert result["status"] == "failed"
        assert result["failed"] == 1
        assert result["passed"] == 1
        # The failed method should have error and assertions
        failed_method = [m for m in result["methods"] if m["status"] == "failed"][0]
        assert failed_method["error"] == "Expected 5, got 3"
        assert failed_method["error_action"] == "AssertEquals"
        assert "assertions" in failed_method
        assert len(failed_method["assertions"]) == 2

    async def test_run_tests_skipped_method(self):
        """Skipped test method → status 'skipped'."""
        run_data = {
            "status": {"errors": []},
            "result": {"content": [{"Result": "1"}]},
        }
        results_data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {"method_name": "TestSkip", "method_status": 2, "method_duration": 0.0},
                ]
            },
        }
        with (
            patch.object(testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)),
            patch.object(
                testing_mcp.testing_api, "get_latest_results", AsyncMock(return_value=results_data)
            ),
        ):
            result = await testing_mcp.run_tests("MyApp.Tests.Calc")

        assert result["skipped"] == 1
        assert result["passed"] == 0
        assert result["failed"] == 0
        assert result["status"] == "unknown"

    async def test_run_tests_sql_error(self):
        """SQL-level error → returns error dict."""
        run_data = {
            "status": {"errors": [{"error": "SQL syntax error"}]},
            "result": {"content": []},
        }
        with patch.object(testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)):
            result = await testing_mcp.run_tests("MyApp.Tests.Calc")

        assert "error" in result
        assert "SQL syntax error" in result["error"]

    async def test_run_tests_runner_error(self):
        """Runner returns ERROR: prefix → returns error dict."""
        run_data = {
            "status": {"errors": []},
            "result": {"content": [{"Result": "ERROR: Class not found"}]},
        }
        with patch.object(testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)):
            result = await testing_mcp.run_tests("MyApp.Tests.Calc")

        assert "error" in result
        assert "ERROR: Class not found" in result["error"]

    async def test_run_tests_empty_result_rows(self):
        """Runner returns no rows → empty Result string."""
        run_data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        results_data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with (
            patch.object(testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)),
            patch.object(
                testing_mcp.testing_api, "get_latest_results", AsyncMock(return_value=results_data)
            ),
        ):
            result = await testing_mcp.run_tests("MyApp.Tests.Calc")

        assert result["status"] == "unknown"
        assert result["passed"] == 0

    async def test_run_tests_results_table_error(self):
        """Results tables inaccessible → returns basic status."""
        run_data = {
            "status": {"errors": []},
            "result": {"content": [{"Result": "1"}]},
        }
        results_data = {
            "status": {"errors": [{"error": "Table not found"}]},
            "result": {"content": []},
        }
        with (
            patch.object(testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)),
            patch.object(
                testing_mcp.testing_api, "get_latest_results", AsyncMock(return_value=results_data)
            ),
        ):
            result = await testing_mcp.run_tests("MyApp.Tests.Calc")

        assert result["status"] == "passed"
        assert result["runner_result"] == "1"

    async def test_run_tests_with_test_method(self):
        """Running a specific test method passes it to the API."""
        run_data = {
            "status": {"errors": []},
            "result": {"content": [{"Result": "1"}]},
        }
        results_data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with (
            patch.object(
                testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)
            ) as mock_run,
            patch.object(
                testing_mcp.testing_api, "get_latest_results", AsyncMock(return_value=results_data)
            ),
        ):
            await testing_mcp.run_tests("MyApp.Tests.Calc", test_method="TestAdd")

        mock_run.assert_awaited_once()
        args = mock_run.call_args
        assert args[0][0] == "MyApp.Tests.Calc"
        assert args[1]["test_method"] == "TestAdd"

    async def test_run_tests_unknown_status_int(self):
        """method_status not in {0,1,2} → 'unknown'."""
        run_data = {
            "status": {"errors": []},
            "result": {"content": [{"Result": "1"}]},
        }
        results_data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {"method_name": "TestX", "method_status": 99, "method_duration": 0.1},
                ]
            },
        }
        with (
            patch.object(testing_mcp.testing_api, "run_tests", AsyncMock(return_value=run_data)),
            patch.object(
                testing_mcp.testing_api, "get_latest_results", AsyncMock(return_value=results_data)
            ),
        ):
            result = await testing_mcp.run_tests("MyApp.Tests.Calc")

        assert result["methods"][0]["status"] == "unknown"


# ── MCP testing.py: list_tests ──────────────────────────────────────────


class TestMcpListTests:
    """Tests for the MCP list_tests tool."""

    async def test_list_tests_success(self):
        """List tests groups methods by class."""
        data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {"class_name": "MyApp.Tests.Calc", "method_name": "TestAdd"},
                    {"class_name": "MyApp.Tests.Calc", "method_name": "TestSub"},
                    {"class_name": "MyApp.Tests.Utils", "method_name": "TestHelper"},
                ]
            },
        }
        with patch.object(
            testing_mcp.testing_api, "list_test_classes", AsyncMock(return_value=data)
        ):
            result = await testing_mcp.list_tests()

        assert result["count"] == 2
        names = [c["name"] for c in result["classes"]]
        assert "MyApp.Tests.Calc" in names
        assert "MyApp.Tests.Utils" in names
        calc = [c for c in result["classes"] if c["name"] == "MyApp.Tests.Calc"][0]
        assert "TestAdd" in calc["methods"]
        assert "TestSub" in calc["methods"]

    async def test_list_tests_empty(self):
        """No test classes → empty result."""
        data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with patch.object(
            testing_mcp.testing_api, "list_test_classes", AsyncMock(return_value=data)
        ):
            result = await testing_mcp.list_tests()

        assert result["count"] == 0
        assert result["classes"] == []

    async def test_list_tests_error(self):
        """API error → returns error dict."""
        data = {
            "status": {"errors": [{"error": "Connection failed"}]},
            "result": {"content": []},
        }
        with patch.object(
            testing_mcp.testing_api, "list_test_classes", AsyncMock(return_value=data)
        ):
            result = await testing_mcp.list_tests()

        assert "error" in result
        assert result["count"] == 0

    async def test_list_tests_with_filter(self):
        """Filter prefix is passed through."""
        data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with patch.object(
            testing_mcp.testing_api, "list_test_classes", AsyncMock(return_value=data)
        ) as mock_list:
            await testing_mcp.list_tests(filter="MyApp.Tests")

        mock_list.assert_awaited_once()
        assert mock_list.call_args[0][0] == "MyApp.Tests"

    async def test_list_tests_empty_class_name_ignored(self):
        """Rows with empty class_name are ignored."""
        data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {"class_name": "", "method_name": "Orphan"},
                    {"class_name": "Real.Test", "method_name": "TestOne"},
                ]
            },
        }
        with patch.object(
            testing_mcp.testing_api, "list_test_classes", AsyncMock(return_value=data)
        ):
            result = await testing_mcp.list_tests()

        assert result["count"] == 1
        assert result["classes"][0]["name"] == "Real.Test"


# ── MCP testing.py: get_test_results ────────────────────────────────────


class TestMcpGetTestResults:
    """Tests for the MCP get_test_results tool."""

    async def test_get_test_results_success(self):
        data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {
                        "run_id": 1,
                        "run_time": "2024-01-01 10:00",
                        "run_duration": 5.0,
                        "test_class": "MyApp.Tests.Calc",
                        "class_status": 1,
                    },
                    {
                        "run_id": 2,
                        "run_time": "2024-01-02 10:00",
                        "run_duration": 3.0,
                        "test_class": "MyApp.Tests.Calc",
                        "class_status": 0,
                    },
                ]
            },
        }
        with patch.object(
            testing_mcp.testing_api, "get_test_history", AsyncMock(return_value=data)
        ):
            result = await testing_mcp.get_test_results()

        assert result["count"] == 2
        assert result["runs"][0]["status"] == "passed"
        assert result["runs"][1]["status"] == "failed"

    async def test_get_test_results_empty(self):
        data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with patch.object(
            testing_mcp.testing_api, "get_test_history", AsyncMock(return_value=data)
        ):
            result = await testing_mcp.get_test_results()

        assert result["count"] == 0
        assert result["runs"] == []

    async def test_get_test_results_error(self):
        data = {
            "status": {"errors": [{"error": "Permission denied"}]},
            "result": {"content": []},
        }
        with patch.object(
            testing_mcp.testing_api, "get_test_history", AsyncMock(return_value=data)
        ):
            result = await testing_mcp.get_test_results()

        assert "error" in result
        assert result["count"] == 0

    async def test_get_test_results_with_class_filter(self):
        data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with patch.object(
            testing_mcp.testing_api, "get_test_history", AsyncMock(return_value=data)
        ) as mock_hist:
            await testing_mcp.get_test_results(test_class="MyApp.Tests.Calc", limit=5)

        mock_hist.assert_awaited_once()
        assert mock_hist.call_args[0][0] == "MyApp.Tests.Calc"
        assert mock_hist.call_args[0][1] == 5

    async def test_get_test_results_unknown_status(self):
        """class_status not in {0,1,2} → 'unknown'."""
        data = {
            "status": {"errors": []},
            "result": {
                "content": [
                    {
                        "run_id": 1,
                        "run_time": "",
                        "run_duration": 0,
                        "test_class": "X",
                        "class_status": -1,
                    }
                ]
            },
        }
        with patch.object(
            testing_mcp.testing_api, "get_test_history", AsyncMock(return_value=data)
        ):
            result = await testing_mcp.get_test_results()

        assert result["runs"][0]["status"] == "unknown"


# ── MCP sql.py: execute_sql ─────────────────────────────────────────────


class TestMcpExecuteSql:
    """Tests for the MCP execute_sql tool."""

    async def test_execute_sql_success(self):
        """Successful SELECT → rows + count."""
        data = {
            "status": {"errors": []},
            "result": {"content": [{"ID": 1, "Name": "Alice"}, {"ID": 2, "Name": "Bob"}]},
        }
        with patch.object(sql_mcp.sql_api, "execute_query", AsyncMock(return_value=data)):
            result = await sql_mcp.execute_sql("SELECT * FROM Users")

        assert result["count"] == 2
        assert result["rows"][0]["Name"] == "Alice"

    async def test_execute_sql_no_rows(self):
        """DML with no rows returned → count 0."""
        data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with patch.object(sql_mcp.sql_api, "execute_query", AsyncMock(return_value=data)):
            result = await sql_mcp.execute_sql("INSERT INTO Users VALUES (1)")

        assert result["count"] == 0
        assert result["rows"] == []

    async def test_execute_sql_error(self):
        """SQL error → error dict."""
        data = {
            "status": {"errors": [{"error": "Table not found"}]},
            "result": {"content": []},
        }
        with patch.object(sql_mcp.sql_api, "execute_query", AsyncMock(return_value=data)):
            result = await sql_mcp.execute_sql("SELECT * FROM Nonexistent")

        assert "error" in result
        assert "Table not found" in result["error"]
        assert result["count"] == 0

    async def test_execute_sql_empty_error_list(self):
        """Empty error list in status → no error key."""
        data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with patch.object(sql_mcp.sql_api, "execute_query", AsyncMock(return_value=data)):
            result = await sql_mcp.execute_sql("SELECT 1")

        assert "error" not in result

    async def test_execute_sql_with_namespace(self):
        """Namespace is passed through to the API."""
        data = {
            "status": {"errors": []},
            "result": {"content": []},
        }
        with patch.object(sql_mcp.sql_api, "execute_query", AsyncMock(return_value=data)) as mock:
            await sql_mcp.execute_sql("SELECT 1", namespace="SAMPLES")

        mock.assert_awaited_once()
        assert mock.call_args[0][1] == "SAMPLES"

    async def test_execute_sql_error_missing_error_key(self):
        """Error dict missing 'error' key → uses str() of the dict."""
        data = {
            "status": {"errors": [{"code": 500, "msg": "unknown"}]},
            "result": {"content": []},
        }
        with patch.object(sql_mcp.sql_api, "execute_query", AsyncMock(return_value=data)):
            result = await sql_mcp.execute_sql("SELECT 1")

        assert "error" in result
        # The error should be the string repr of the error dict
        assert "code" in result["error"] or "msg" in result["error"]


# ── MCP debugger.py: debug_list_processes ────────────────────────────────


class TestMcpDebugListProcesses:
    """Tests for the MCP debug_list_processes tool."""

    async def test_list_all_processes(self):
        """List all processes without namespace filter."""
        processes = [
            {"pid": 1, "namespace": "USER", "routine": "Main"},
            {"pid": 2, "namespace": "SAMPLES", "routine": "Test"},
        ]
        with patch.object(
            debugger_mcp.debugger_api, "list_processes", AsyncMock(return_value=processes)
        ):
            result = await debugger_mcp.debug_list_processes()

        assert len(result) == 2
        assert result[0]["pid"] == 1

    async def test_list_processes_with_namespace_filter(self):
        """Namespace filter should filter processes case-insensitively."""
        processes = [
            {"pid": 1, "namespace": "USER", "routine": "Main"},
            {"pid": 2, "namespace": "SAMPLES", "routine": "Test"},
            {"pid": 3, "namespace": "user", "routine": "Other"},
        ]
        with patch.object(
            debugger_mcp.debugger_api, "list_processes", AsyncMock(return_value=processes)
        ):
            result = await debugger_mcp.debug_list_processes(namespace="user")

        assert len(result) == 2
        pids = [p["pid"] for p in result]
        assert 1 in pids
        assert 3 in pids

    async def test_list_processes_empty(self):
        """No processes → empty list."""
        with patch.object(debugger_mcp.debugger_api, "list_processes", AsyncMock(return_value=[])):
            result = await debugger_mcp.debug_list_processes()

        assert result == []

    async def test_list_processes_no_namespace_key(self):
        """Processes missing 'namespace' key should not crash."""
        processes = [
            {"pid": 1, "routine": "Main"},
            {"pid": 2, "namespace": "USER", "routine": "Test"},
        ]
        with patch.object(
            debugger_mcp.debugger_api, "list_processes", AsyncMock(return_value=processes)
        ):
            result = await debugger_mcp.debug_list_processes(namespace="USER")

        # Only the process with namespace="USER" matches
        assert len(result) == 1
        assert result[0]["pid"] == 2


# ── MCP debugger.py: debug_attach / debug_start ──────────────────────────


class TestMcpDebugAttach:
    async def test_attach_success(self):
        with patch.object(
            debugger_mcp.debugger_api,
            "attach_session",
            AsyncMock(return_value={"session_id": "abc"}),
        ):
            result = await debugger_mcp.debug_attach(pid=1234)

        assert result["session_id"] == "abc"

    async def test_attach_with_namespace(self):
        with patch.object(
            debugger_mcp.debugger_api,
            "attach_session",
            AsyncMock(return_value={"session_id": "abc"}),
        ) as mock:
            await debugger_mcp.debug_attach(pid=1234, namespace="USER")

        mock.assert_awaited_once()
        assert mock.call_args[1]["pid"] == 1234
        assert mock.call_args[1]["namespace"] == "USER"


class TestMcpDebugStart:
    async def test_start_success(self):
        with patch.object(
            debugger_mcp.debugger_api, "start_session", AsyncMock(return_value={"session_id": "s1"})
        ):
            result = await debugger_mcp.debug_start(target="##class(App).Run()")

        assert result["session_id"] == "s1"

    async def test_start_with_breakpoints(self):
        bps = [{"class": "App", "method": "Run", "offset": 5}]
        with patch.object(
            debugger_mcp.debugger_api, "start_session", AsyncMock(return_value={"session_id": "s1"})
        ) as mock:
            await debugger_mcp.debug_start(target="target", breakpoints=bps, stop_on_entry=False)

        mock.assert_awaited_once()
        assert mock.call_args[1]["breakpoints"] == bps
        assert mock.call_args[1]["stop_on_entry"] is False


# ── MCP debugger.py: debug_step / debug_inspect / debug_variables ─────────


class TestMcpDebugStep:
    async def test_step_into(self):
        with patch.object(
            debugger_mcp.debugger_api, "step", AsyncMock(return_value={"state": "break"})
        ) as mock:
            result = await debugger_mcp.debug_step("sess1", action="step_into")

        assert result["state"] == "break"
        mock.assert_awaited_once()
        assert mock.call_args[0][0] == "sess1"
        assert mock.call_args[0][1] == "step_into"

    async def test_step_run(self):
        with patch.object(
            debugger_mcp.debugger_api, "step", AsyncMock(return_value={"state": "running"})
        ):
            result = await debugger_mcp.debug_step("sess1", action="run")

        assert result["state"] == "running"


class TestMcpDebugInspect:
    async def test_inspect_default_level(self):
        with patch.object(
            debugger_mcp.debugger_api, "inspect_expression", AsyncMock(return_value={"value": "42"})
        ) as mock:
            result = await debugger_mcp.debug_inspect("sess1", "myVar")

        assert result["value"] == "42"
        assert mock.call_args[0][2] == 0

    async def test_inspect_custom_level(self):
        with patch.object(
            debugger_mcp.debugger_api, "inspect_expression", AsyncMock(return_value={"value": "x"})
        ) as mock:
            await debugger_mcp.debug_inspect("sess1", "obj.prop", stack_level=2)

        assert mock.call_args[0][2] == 2


class TestMcpDebugVariables:
    async def test_variables_private(self):
        with patch.object(
            debugger_mcp.debugger_api, "get_variables", AsyncMock(return_value={"vars": []})
        ) as mock:
            await debugger_mcp.debug_variables("sess1", context="private")

        assert mock.call_args[0][1] == 0  # private = 0

    async def test_variables_public(self):
        with patch.object(
            debugger_mcp.debugger_api, "get_variables", AsyncMock(return_value={"vars": []})
        ) as mock:
            await debugger_mcp.debug_variables("sess1", context="public")

        assert mock.call_args[0][1] == 1  # public = 1

    async def test_variables_class(self):
        with patch.object(
            debugger_mcp.debugger_api, "get_variables", AsyncMock(return_value={"vars": []})
        ) as mock:
            await debugger_mcp.debug_variables("sess1", context="class")

        assert mock.call_args[0][1] == 2  # class = 2

    async def test_variables_unknown_context_defaults_private(self):
        with patch.object(
            debugger_mcp.debugger_api, "get_variables", AsyncMock(return_value={"vars": []})
        ) as mock:
            await debugger_mcp.debug_variables("sess1", context="unknown")

        assert mock.call_args[0][1] == 0  # unknown → default 0

    async def test_variables_stack_level_zero_passes_none(self):
        """stack_level=0 should pass None to API (auto-detect)."""
        with patch.object(
            debugger_mcp.debugger_api, "get_variables", AsyncMock(return_value={"vars": []})
        ) as mock:
            await debugger_mcp.debug_variables("sess1", stack_level=0)

        assert mock.call_args[0][2] is None

    async def test_variables_stack_level_nonzero_passes_value(self):
        with patch.object(
            debugger_mcp.debugger_api, "get_variables", AsyncMock(return_value={"vars": []})
        ) as mock:
            await debugger_mcp.debug_variables("sess1", stack_level=3)

        assert mock.call_args[0][2] == 3


class TestMcpDebugStack:
    async def test_get_stack(self):
        with patch.object(
            debugger_mcp.debugger_api, "get_stack", AsyncMock(return_value={"frames": []})
        ):
            result = await debugger_mcp.debug_stack("sess1")

        assert "frames" in result


class TestMcpDebugBreakpoints:
    async def test_list_breakpoints(self):
        with patch.object(
            debugger_mcp.debugger_api, "manage_breakpoints", AsyncMock(return_value={"bps": []})
        ) as mock:
            result = await debugger_mcp.debug_breakpoints("sess1", action="list")

        mock.assert_awaited_once()
        assert mock.call_args[1]["action"] == "list"
        assert result == {"bps": []}

    async def test_set_breakpoint(self):
        with patch.object(
            debugger_mcp.debugger_api, "manage_breakpoints", AsyncMock(return_value={})
        ) as mock:
            await debugger_mcp.debug_breakpoints(
                "sess1",
                action="set",
                class_name="App.Cls",
                method="Run",
                offset=10,
                condition="x > 5",
            )

        assert mock.call_args[1]["class_name"] == "App.Cls"
        assert mock.call_args[1]["condition"] == "x > 5"

    async def test_remove_breakpoint(self):
        with patch.object(
            debugger_mcp.debugger_api, "manage_breakpoints", AsyncMock(return_value={})
        ) as mock:
            await debugger_mcp.debug_breakpoints("sess1", action="remove", breakpoint_id="bp1")

        assert mock.call_args[1]["breakpoint_id"] == "bp1"


class TestMcpDebugStop:
    async def test_stop_session(self):
        with patch.object(
            debugger_mcp.debugger_api, "stop_session", AsyncMock(return_value={"status": "stopped"})
        ):
            result = await debugger_mcp.debug_stop("sess1")

        assert result["status"] == "stopped"
