"""MCP tools for running and inspecting ObjectScript unit tests."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import testing as testing_api
from prism.mcp._decorator import logged_tool

_STATUS_MAP = {0: "failed", 1: "passed", 2: "skipped"}


@logged_tool
async def run_tests(
    test_class: Annotated[
        str,
        Field(
            description="Fully qualified ObjectScript class name extending %UnitTest.TestCase. Examples: 'MyApp.Tests.Calculator', 'Test.PersonTests'. The class must already be compiled on the server."
        ),
    ],
    test_method: Annotated[
        str | None,
        Field(
            description="Specific test method to run (e.g. 'TestAddition'). If omitted, all Test* methods in the class are executed."
        ),
    ] = None,
    manager_class: Annotated[
        str | None,
        Field(
            description="Custom %UnitTest.Manager subclass to use for execution (e.g. 'TestCoverage.Manager'). Defaults to IRIS_TEST_MANAGER_CLASS env var ('%UnitTest.Manager')."
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to run tests in. Uses the configured default if omitted."
        ),
    ] = None,
) -> dict:
    """Run ObjectScript unit tests on the IRIS server and return structured results.

    **Runs on: IRIS server** (remote — executes tests via IRIS %UnitTest framework).

    Executes one or all Test* methods in a %UnitTest.TestCase subclass using
    DebugRunTestCase (no file system access needed — the class must already be
    compiled). A helper class is auto-deployed to IRIS on first use.

    Returns ``{"class": "...", "status": "passed|failed", "passed": N,
    "failed": N, "skipped": N, "methods": [...]}`` where each method has
    name, status, duration, and error details for failures.
    """
    # Run the tests via SqlProc
    run_data = await testing_api.run_tests(
        test_class,
        test_method=test_method or "",
        manager_class=manager_class,
        namespace=namespace,
    )

    # Check for SQL-level errors
    errors = run_data.get("status", {}).get("errors", [])
    if errors:
        msg = errors[0].get("error", str(errors[0]))
        return {"class": test_class, "error": msg}

    # Parse the runner result
    rows = run_data.get("result", {}).get("content", [])
    runner_result = rows[0].get("Result", "") if rows else ""

    if runner_result.startswith("ERROR:"):
        return {"class": test_class, "error": runner_result}

    # Fetch structured results from %UnitTest_Result tables
    results_data = await testing_api.get_latest_results(test_class, namespace)
    result_errors = results_data.get("status", {}).get("errors", [])
    if result_errors:
        # Results tables might not be accessible — return basic status
        return {
            "class": test_class,
            "status": "passed" if runner_result == "1" else "unknown",
            "runner_result": runner_result,
        }

    result_rows = results_data.get("result", {}).get("content", [])
    methods = []
    passed = 0
    failed = 0
    skipped = 0

    for row in result_rows:
        status_int = row.get("method_status", -1)
        status_str = _STATUS_MAP.get(status_int, "unknown")
        if status_str == "passed":
            passed += 1
        elif status_str == "failed":
            failed += 1
        elif status_str == "skipped":
            skipped += 1

        method_info: dict = {
            "name": row.get("method_name", ""),
            "status": status_str,
            "duration": row.get("method_duration", 0),
        }
        if status_str == "failed":
            error_desc = row.get("error_description", "")
            error_action = row.get("error_action", "")
            if error_desc:
                method_info["error"] = error_desc
            if error_action:
                method_info["error_action"] = error_action

            # Fetch assertion-level detail for failed methods
            assertions_data = await testing_api.get_assertions(
                test_class, row.get("method_name", ""), namespace
            )
            assertion_rows = assertions_data.get("result", {}).get("content", [])
            if assertion_rows:
                method_info["assertions"] = [
                    {
                        "action": a.get("action", ""),
                        "description": a.get("description", ""),
                        "status": _STATUS_MAP.get(a.get("status", -1), "unknown"),
                    }
                    for a in assertion_rows
                ]

        methods.append(method_info)

    overall = (
        "passed"
        if failed == 0 and passed > 0
        else "failed"
        if failed > 0
        else "unknown"
    )

    return {
        "class": test_class,
        "status": overall,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "methods": methods,
    }


@logged_tool
async def list_tests(
    filter: Annotated[
        str | None,
        Field(
            description="Filter test classes by name prefix. Examples: 'MyApp.Tests' returns all test classes in that package. Omit to list all test classes in the namespace."
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to search for test classes. Uses the configured default if omitted."
        ),
    ] = None,
) -> dict:
    """Discover %UnitTest.TestCase classes and their Test* methods on the IRIS server.

    **Runs on: IRIS server** (remote — queries IRIS %Dictionary tables).

    Queries the %Dictionary tables to find all compiled classes extending
    %UnitTest.TestCase, with their test method names. Use this before
    run_tests to see what tests are available.

    Returns ``{"classes": [{"name": "...", "methods": ["TestX", ...]}, ...],
    "count": N}``.
    """
    data = await testing_api.list_test_classes(filter, namespace)

    errors = data.get("status", {}).get("errors", [])
    if errors:
        msg = errors[0].get("error", str(errors[0]))
        return {"error": msg, "classes": [], "count": 0}

    rows = data.get("result", {}).get("content", [])

    # Group methods by class
    classes: dict[str, list[str]] = {}
    for row in rows:
        cls_name = row.get("class_name", "")
        method_name = row.get("method_name", "")
        if cls_name:
            classes.setdefault(cls_name, []).append(method_name)

    class_list = [
        {"name": name, "methods": methods} for name, methods in classes.items()
    ]
    return {"classes": class_list, "count": len(class_list)}


@logged_tool
async def get_test_results(
    test_class: Annotated[
        str | None,
        Field(
            description="Filter results to a specific test class. Omit to see results across all classes."
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of historical test runs to return.",
            ge=1,
            le=100,
        ),
    ] = 10,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to query results from. Uses the configured default if omitted."
        ),
    ] = None,
) -> dict:
    """Retrieve historical unit test results from the IRIS server.

    **Runs on: IRIS server** (remote — queries %UnitTest_Result tables).

    Returns recent test runs with pass/fail status and timing. Use this to
    check past test results without re-running the tests.

    Returns ``{"runs": [{"run_id": N, "run_time": "...", "test_class": "...",
    "status": "passed|failed", ...}], "count": N}``.
    """
    data = await testing_api.get_test_history(test_class, limit, namespace)

    errors = data.get("status", {}).get("errors", [])
    if errors:
        msg = errors[0].get("error", str(errors[0]))
        return {"error": msg, "runs": [], "count": 0}

    rows = data.get("result", {}).get("content", [])
    runs = [
        {
            "run_id": row.get("run_id", ""),
            "run_time": row.get("run_time", ""),
            "duration": row.get("run_duration", 0),
            "test_class": row.get("test_class", ""),
            "status": _STATUS_MAP.get(row.get("class_status", -1), "unknown"),
        }
        for row in rows
    ]
    return {"runs": runs, "count": len(runs)}
