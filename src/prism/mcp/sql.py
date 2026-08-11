"""MCP tools for running SQL queries against IRIS."""

import json
from typing import Annotated

from pydantic import Field

from prism.iris.api import sql as sql_api
from prism.iris.sdk.http import handle_api_error
from prism.mcp._decorator import logged_tool

CHARACTER_LIMIT = 25000


@logged_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def execute_sql(
    query: Annotated[
        str,
        Field(
            description="InterSystems SQL query. Supports SELECT, INSERT, UPDATE, DELETE, CREATE TABLE, DDL, and CALL for stored procedures ([SqlProc] class methods). Table names map to class names: class MyApp.Person → table MyApp.Person. Use %ID for the auto-generated row ID. Examples: 'SELECT %ID, Name, Age FROM MyApp.Person WHERE Age > 30', 'INSERT INTO MyApp.Person (Name, Age) VALUES (\\'John\\', 30)', 'CALL MyApp.Utils_MyMethod()'.",
            min_length=1,
            max_length=10000,
        ),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to run the query in. Uses the configured default if omitted.",
            min_length=1,
            max_length=64,
        ),
    ] = None,
    target_host: Annotated[
        str | None,
        Field(
            description="IRIS server hostname or IP address (e.g. '192.168.1.100'). "
            "Uses the configured default if omitted."
        ),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port (e.g. 52773). Uses the configured default if omitted.",
            ge=1,
            le=65535,
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
    try:
        data = await sql_api.execute_query(
            query,
            namespace,
            target_host=target_host,
            target_port=target_port,
        )
    except Exception as exc:
        return {"error": handle_api_error(exc), "rows": [], "count": 0}

    status = data.get("status", {})
    errors = status.get("errors", [])
    if errors:
        msg = errors[0].get("error", str(errors[0])) if errors else ""
        return {"error": msg, "rows": [], "count": 0}
    rows = data.get("result", {}).get("content", [])

    # Apply character limit truncation
    result = {"rows": rows, "count": len(rows)}
    result_str = json.dumps(result, default=str)
    if len(result_str) > CHARACTER_LIMIT:
        half = max(1, len(rows) // 2)
        truncated = rows[:half]
        result = {
            "rows": truncated,
            "count": len(truncated),
            "truncated": True,
            "truncation_message": (
                f"Response truncated from {len(rows)} to {len(truncated)} rows. "
                "Add WHERE clauses or LIMIT to reduce results."
            ),
        }
    return result
