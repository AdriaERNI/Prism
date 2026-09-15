"""MCP tool for running ObjectScript commands via the IRIS terminal."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import terminal as terminal_api
from prism.iris.sdk.http import handle_api_error
from prism.mcp._decorator import logged_tool


@logged_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def execute_terminal(
    command: Annotated[
        str,
        Field(
            description="ObjectScript command to execute in the IRIS terminal. "
            "Supports any valid ObjectScript: variable assignment, method calls, "
            "global manipulation, system utilities, etc. Examples: "
            "'write \"hello world\"', "
            "'set x=42 write x', "
            "'write ##class(MyApp.Utils).Greet(\"Alice\")', "
            "'zwrite ^myGlobal'.",
            min_length=1,
            max_length=10000,
        ),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to run the command in. "
            "Uses the configured default if omitted.",
            min_length=1,
            max_length=64,
        ),
    ] = None,
    timeout: Annotated[
        float,
        Field(
            description="Timeout in seconds for the WebSocket session. "
            "Increase for long-running commands.",
            gt=0,
        ),
    ] = 30.0,
    target_host: Annotated[
        str | None,
        Field(description="IRIS server host or IP. Uses the configured default if omitted."),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the configured default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Execute an ObjectScript command on the IRIS server via the WebSocket terminal.

    **Runs on: IRIS server** (remote). Use for ObjectScript beyond SQL —
    method calls, globals, $system utilities, variable manipulation. Each call
    opens a fresh session, so combine dependent statements in one command
    (e.g. 'set x=1 write x'). For SQL prefer execute_sql.

    Returns ``{"namespace", "command", "output", "prompt"}``; server errors
    appear as ``ERROR: <message>`` in output. Long commands support background
    execution (call as a task, raise `timeout`, default 30s). Use
    target_host/target_port for another IRIS instance.
    """
    try:
        return await terminal_api.execute_command(
            command,
            namespace,
            timeout,
            target_host=target_host,
            target_port=target_port,
        )
    except Exception as exc:
        return {"error": handle_api_error(exc), "output": ""}
