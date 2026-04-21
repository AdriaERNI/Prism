"""MCP tool for running ObjectScript commands via the IRIS terminal."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import terminal as terminal_api
from prism.mcp._decorator import logged_tool


@logged_tool(task=True)
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
            "'zwrite ^myGlobal'."
        ),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to run the command in. "
            "Uses the configured default if omitted."
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
) -> dict:
    """Execute an ObjectScript command in the IRIS terminal via WebSocket.

    Use this tool for ObjectScript that cannot be expressed as SQL — method
    calls, global operations, system commands ($system utilities), variable
    manipulation, and any general-purpose ObjectScript code. For SQL queries
    (SELECT, INSERT, UPDATE, DELETE, CALL), prefer execute_sql instead.

    Each invocation opens a fresh terminal session, so variables and state
    do not persist between calls. To run multiple dependent statements,
    combine them in a single command separated by spaces
    (e.g. 'set x=1 write x').

    This tool supports background execution. For long-running commands
    (data migrations, batch processing, builds), call it as a background
    task to avoid blocking. The command runs in its own session while you
    continue using other tools. Increase the timeout for commands that
    take longer than 30 seconds.
    """

    return await terminal_api.execute_command(command, namespace, timeout)
