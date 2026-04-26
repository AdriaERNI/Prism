"""IRIS unit test execution and result queries via the Atelier REST API."""

from __future__ import annotations

from prism.iris.api.documents import DocumentNotFound, get_document, put_document
from prism.iris.api.compile import compile_documents
from prism.iris.api.sql import execute_query
from prism.settings import settings

# ── Helper class source ─────────────────────────────────────────────

_RUNNER_DOC_NAME = f"{settings.iris_test_runner_class}.cls"

_RUNNER_SOURCE = [
    f"Class {settings.iris_test_runner_class} Extends %RegisteredObject",
    "{",
    "",
    "/// Run tests for a single class, optionally a specific method.",
    "/// Returns OK on success or ERROR: <message> on failure.",
    f"ClassMethod {settings.iris_test_runner_method}(",
    '    testClass As %String = "",',
    '    testMethod As %String = "",',
    "    managerClass As %String = {..#DEFAULTMANAGER}",
    ") As %String [ SqlProc ]",
    "{",
    '    If testMethod = $Char(0) Set testMethod = ""',
    '    Set root = $System.Util.ManagerDirectory() _ "Temp/UnitTest/"',
    "    Set ^UnitTestRoot = root",
    "    If '##class(%File).DirectoryExists(root) Do ##class(%File).CreateDirectoryChain(root)",
    '    Set qualifiers = "/display=none"',
    '    Set sc = $ClassMethod(managerClass, "DebugRunTestCase", "", testClass, qualifiers, testMethod)',
    "    If $$$ISOK(sc) Return sc",
    '    Return "ERROR: " _ $System.Status.GetErrorText(sc)',
    "}",
    "",
    f'Parameter DEFAULTMANAGER = "{settings.iris_test_manager_class}";',
    "",
    "}",
]


# ── Auto-deploy ──────────────────────────────────────────────────────


async def ensure_runner_deployed(namespace: str | None = None) -> bool:
    """Deploy the test runner helper class if auto-deploy is enabled and it is missing.

    Returns True if the runner is available (either already present or just deployed).
    """
    if not settings.iris_test_auto_deploy:
        return True

    try:
        await get_document(_RUNNER_DOC_NAME, namespace)
        return True
    except DocumentNotFound:
        pass

    await put_document(_RUNNER_DOC_NAME, _RUNNER_SOURCE, namespace)
    result = await compile_documents([_RUNNER_DOC_NAME], namespace)
    errors = result.get("status", {}).get("errors", [])
    if errors:
        msg = errors[0].get("error", str(errors[0]))
        raise RuntimeError(f"Failed to compile test runner: {msg}")
    return True


# ── Test execution ───────────────────────────────────────────────────


async def run_tests(
    test_class: str,
    test_method: str = "",
    manager_class: str | None = None,
    namespace: str | None = None,
) -> dict:
    """Execute unit tests via the deployed SqlProc runner.

    Returns the raw SQL response from the runner method.
    """
    await ensure_runner_deployed(namespace)

    manager = manager_class or settings.iris_test_manager_class
    # SQL function name: Schema.ClassName_MethodName()
    # e.g. MCP.TestRunner → MCP.TestRunner_RunTests()
    runner_sql_name = settings.iris_test_runner_class
    method_sql_name = settings.iris_test_runner_method

    query = (
        f"SELECT {runner_sql_name}_{method_sql_name}"
        f"('{test_class}', '{test_method}', '{manager}') AS Result"
    )
    return await execute_query(query, namespace)


# ── Result queries ───────────────────────────────────────────────────

_LATEST_RESULTS_QUERY = """\
SELECT
    tm.Name AS method_name,
    tm.Status AS method_status,
    tm.Duration AS method_duration,
    tm.ErrorAction AS error_action,
    tm.ErrorDescription AS error_description
FROM %UnitTest_Result.TestMethod tm
JOIN %UnitTest_Result.TestCase tc ON tm.TestCase = tc.ID
JOIN %UnitTest_Result.TestSuite ts ON tc.TestSuite = ts.ID
JOIN %UnitTest_Result.TestInstance ti ON ts.TestInstance = ti.ID
WHERE tc.Name = '{test_class}'
AND ti.InstanceIndex = (
    SELECT MAX(ti2.InstanceIndex)
    FROM %UnitTest_Result.TestInstance ti2
    JOIN %UnitTest_Result.TestSuite ts2 ON ts2.TestInstance = ti2.ID
    JOIN %UnitTest_Result.TestCase tc2 ON tc2.TestSuite = ts2.ID
    WHERE tc2.Name = '{test_class}'
)
ORDER BY tm.Name\
"""

_LATEST_ASSERTIONS_QUERY = """\
SELECT
    ta.Action AS action,
    ta.Description AS description,
    ta.Status AS status
FROM %UnitTest_Result.TestAssert ta
JOIN %UnitTest_Result.TestMethod tm ON ta.TestMethod = tm.ID
JOIN %UnitTest_Result.TestCase tc ON tm.TestCase = tc.ID
JOIN %UnitTest_Result.TestSuite ts ON tc.TestSuite = ts.ID
JOIN %UnitTest_Result.TestInstance ti ON ts.TestInstance = ti.ID
WHERE tc.Name = '{test_class}'
AND tm.Name = '{test_method}'
AND ti.InstanceIndex = (
    SELECT MAX(ti2.InstanceIndex)
    FROM %UnitTest_Result.TestInstance ti2
    JOIN %UnitTest_Result.TestSuite ts2 ON ts2.TestInstance = ti2.ID
    JOIN %UnitTest_Result.TestCase tc2 ON tc2.TestSuite = ts2.ID
    WHERE tc2.Name = '{test_class}'
)
ORDER BY ta.Counter\
"""

_HISTORY_QUERY = """\
SELECT TOP {limit}
    ti.InstanceIndex AS run_id,
    ti.DateTime AS run_time,
    ti.Duration AS run_duration,
    tc.Name AS test_class,
    tc.Status AS class_status
FROM %UnitTest_Result.TestCase tc
JOIN %UnitTest_Result.TestSuite ts ON tc.TestSuite = ts.ID
JOIN %UnitTest_Result.TestInstance ti ON ts.TestInstance = ti.ID
{where_clause}
ORDER BY ti.DateTime DESC\
"""

_LIST_TESTS_QUERY = """\
SELECT
    cd.Name AS class_name,
    md.Name AS method_name
FROM %Dictionary.MethodDefinition md
JOIN %Dictionary.ClassDefinition cd ON md.parent = cd.Name
WHERE cd.Super [ '%UnitTest.TestCase'
AND md.Name %STARTSWITH 'Test'
{filter_clause}
ORDER BY cd.Name, md.Name\
"""


async def get_latest_results(
    test_class: str,
    namespace: str | None = None,
) -> dict:
    """Query the %UnitTest_Result tables for the latest run of a test class."""
    query = _LATEST_RESULTS_QUERY.format(test_class=test_class)
    return await execute_query(query, namespace)


async def get_assertions(
    test_class: str,
    test_method: str,
    namespace: str | None = None,
) -> dict:
    """Query assertion details for a specific test method in the latest run."""
    query = _LATEST_ASSERTIONS_QUERY.format(
        test_class=test_class, test_method=test_method
    )
    return await execute_query(query, namespace)


async def get_test_history(
    test_class: str | None = None,
    limit: int = 10,
    namespace: str | None = None,
) -> dict:
    """Query historical test runs, optionally filtered by class."""
    where_clause = ""
    if test_class:
        where_clause = f"WHERE tc.Name = '{test_class}'"
    query = _HISTORY_QUERY.format(limit=limit, where_clause=where_clause)
    return await execute_query(query, namespace)


async def list_test_classes(
    filter_prefix: str | None = None,
    namespace: str | None = None,
) -> dict:
    """Discover test classes and their Test* methods via %Dictionary."""
    filter_clause = ""
    if filter_prefix:
        filter_clause = f"AND cd.Name %STARTSWITH '{filter_prefix}'"
    query = _LIST_TESTS_QUERY.format(filter_clause=filter_clause)
    return await execute_query(query, namespace)
