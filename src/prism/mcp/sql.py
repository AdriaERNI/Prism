"""MCP tools for running SQL queries against IRIS."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import sql as sql_api
from prism.mcp._decorator import logged_tool


@logged_tool
async def execute_sql(
    query: Annotated[
        str,
        Field(
            description="InterSystems SQL query. Supports SELECT, INSERT, UPDATE, DELETE, CREATE TABLE, DDL, and CALL for stored procedures ([SqlProc] class methods). Table names map to class names: class MyApp.Person → table MyApp.Person. Use %ID for the auto-generated row ID. Examples: 'SELECT %ID, Name, Age FROM MyApp.Person WHERE Age > 30', 'INSERT INTO MyApp.Person (Name, Age) VALUES (\\'John\\', 30)', 'CALL MyApp.Utils_MyMethod()'."
        ),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to run the query in. Uses the configured default if omitted."
        ),
    ] = None,
) -> dict:
    """Execute an InterSystems SQL query on the IRIS server and return the results.

    **Runs on: IRIS server** (remote, via REST API).

    Returns ``{"rows": [...], "count": N}`` for SELECT queries where each
    row is a dict of column names to values. For INSERT/UPDATE/DELETE returns
    ``{"rows": [], "count": 0}``. On SQL errors returns
    ``{"error": "message", "rows": [], "count": 0}``.

    InterSystems SQL follows standard SQL with extensions: %ID is the
    auto-generated row ID, class properties become columns, and
    package.class names become table names. Classes must be compiled before
    their SQL tables are available. Use CALL to invoke ClassMethods marked
    with [SqlProc] — the SQL name is Package.Class_Method().
    """
    data = await sql_api.execute_query(query, namespace)
    status = data.get("status", {})
    errors = status.get("errors", [])
    if errors:
        msg = errors[0].get("error", str(errors[0])) if errors else ""
        return {"error": msg, "rows": [], "count": 0}
    rows = data.get("result", {}).get("content", [])
    return {"rows": rows, "count": len(rows)}
