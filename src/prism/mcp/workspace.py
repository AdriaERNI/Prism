"""MCP tools for workspace-based IRIS document I/O."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import documents as docs_api
from prism.iris.api import compile as compile_api
from prism.iris.sdk.workspace import (
    resolve_safe,
    load_content,
    validate_doc_name,
)
from prism.mcp._decorator import logged_tool


@logged_tool
async def put_document(
    name: Annotated[
        str,
        Field(
            description="Full document name including extension. Format: 'Package.ClassName.ext'. Examples: 'MyApp.Person.cls', 'Utils.mac'. For .cls files, this MUST match the class declaration inside the file (e.g. 'Class MyApp.Person' → name 'MyApp.Person.cls')."
        ),
    ],
    path: Annotated[
        str | None,
        Field(
            description="Relative file path within the workspace to read from. Defaults to the document name. The file must already exist in the workspace — write it first before calling this tool."
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to write to. Uses the configured default if omitted."
        ),
    ] = None,
) -> dict:
    """Read a file from the workspace and push it to IRIS.

    The file must already exist in the workspace — write it first, then call
    this tool to upload it. This creates or overwrites the document on the IRIS
    server. After pushing a .cls file, you must compile it with
    compile_documents before it becomes usable (as a SQL table, method target,
    etc.). Use put_and_compile to push and compile in a single step.
    """
    validate_doc_name(name)
    file_path = resolve_safe(path or name)
    content = load_content(file_path)
    await docs_api.put_document(name, content, namespace)
    return {"name": name, "uploaded": True, "lines": len(content)}


@logged_tool
async def put_and_compile(
    name: Annotated[
        str,
        Field(
            description="Full document name including extension. Format: 'Package.ClassName.ext'. Examples: 'MyApp.Person.cls', 'Utils.mac'. For .cls files, this MUST match the class declaration inside the file."
        ),
    ],
    path: Annotated[
        str | None,
        Field(
            description="Relative file path within the workspace to read from. Defaults to the document name. The file must already exist in the workspace."
        ),
    ] = None,
    flags: Annotated[
        str | None,
        Field(
            description="Compiler flags. Defaults to IRIS_COMPILE_FLAGS env var ('cuk'). Flag reference: c=compile, u=skip up-to-date, k=keep generated source, b=include subclasses/dependents, r=compile predecessors, d=display output."
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to write to and compile in. Uses the configured default if omitted."
        ),
    ] = None,
) -> dict:
    """Read a file from the workspace, push it to IRIS, and compile it in one step.

    This is the recommended tool for creating or updating classes. It combines
    put_document + compile_documents into a single call. The file must already
    exist in the workspace. The result includes both the put status and any
    compilation errors or warnings.
    """
    validate_doc_name(name)
    file_path = resolve_safe(path or name)
    content = load_content(file_path)
    await docs_api.put_document(name, content, namespace)
    compile_data = await compile_api.compile_documents([name], namespace, flags)
    status = compile_data.get("status", {})
    errors = [e.get("error", str(e)) for e in status.get("errors", [])]
    console = [line for line in compile_data.get("console", []) if line.strip()]
    return {
        "name": name,
        "uploaded": True,
        "lines": len(content),
        "success": len(errors) == 0,
        "errors": errors,
        "console": console,
    }
