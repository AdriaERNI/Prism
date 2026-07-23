"""MCP tools for compiling IRIS source code documents."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import compile as compile_api
from prism.iris.sdk.workspace import validate_doc_name
from prism.mcp._decorator import logged_tool


def _parse_compile(data: dict) -> dict:
    """Extract a clean compile result from the raw IRIS response."""
    status = data.get("status", {})
    errors = [e.get("error", str(e)) for e in status.get("errors", [])]
    console = [line for line in data.get("console", []) if line.strip()]
    return {
        "success": len(errors) == 0,
        "errors": errors,
        "console": console,
    }


@logged_tool
async def compile_documents(
    doc_names: Annotated[
        list[str],
        Field(
            description="List of document names to compile. Each name must include the file extension. Examples: ['MyApp.Person.cls'], ['MyApp.Person.cls', 'MyApp.Address.cls']. Use this when multiple classes need compilation together (e.g. classes that reference each other)."
        ),
    ],
    flags: Annotated[
        str | None,
        Field(
            description="Compiler flags. Defaults to IRIS_COMPILE_FLAGS env var ('cuk'). Flag reference: c=compile, u=skip up-to-date, k=keep generated source, b=include subclasses/dependents, r=compile predecessors, d=display output. Use 'ckb' to recompile all subclasses after changing a parent class."
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to compile in. Uses the configured default if omitted."
        ),
    ] = None,
) -> dict:
    """Compile one or more IRIS source code documents on the IRIS server.

    **Runs on: IRIS server** (remote — compiles classes via IRIS compiler).

    Compilation is required after creating or modifying a class with
    put_document — it registers the class with IRIS so it becomes usable as a
    SQL table, its methods can be called, and other classes can reference it.
    If you only need to push and compile a single document, prefer
    put_and_compile instead.

    Returns ``{"success": bool, "errors": [...], "console": [...]}``
    where errors is empty on success and console contains compiler output.
    """
    for doc_name in doc_names:
        validate_doc_name(doc_name)
    data = await compile_api.compile_documents(doc_names, namespace, flags)
    return _parse_compile(data)
