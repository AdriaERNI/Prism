"""MCP tools for workspace-based IRIS document I/O."""

from typing import Annotated

from pydantic import Field

from prism.iris.api import compile as compile_api
from prism.iris.api import documents as docs_api
from prism.iris.sdk.workspace import (
    load_content,
    resolve_safe,
    validate_doc_name,
)
from prism.mcp._decorator import logged_tool


@logged_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def put_document(
    name: Annotated[
        str,
        Field(
            description="Full document name including extension. Format: 'Package.ClassName.ext'. Examples: 'MyApp.Person.cls', 'Utils.mac'. For .cls files, this MUST match the class declaration inside the file (e.g. 'Class MyApp.Person' → name 'MyApp.Person.cls').",
            min_length=1,
            max_length=255,
        ),
    ],
    path: Annotated[
        str | None,
        Field(
            description="Relative file path within the workspace to read from. Defaults to the document name. The file must already exist in the workspace — write it first before calling this tool.",
            min_length=1,
            max_length=1024,
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to write to. Uses the configured default if omitted.",
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
    """Read a file from the local workspace and push it to the IRIS server.

    **Runs on: local → IRIS** (reads a local file, writes to the remote IRIS server).

    The file must already exist in the local workspace — write it first, then call
    this tool to upload it. This creates or overwrites the document on the IRIS
    server. After pushing a .cls file, you must compile it with
    compile_documents before it becomes usable (as a SQL table, method target,
    etc.). Use put_and_compile to push and compile in a single step.
    """
    validate_doc_name(name)
    file_path = resolve_safe(path or name)
    content = load_content(file_path)
    await docs_api.put_document(
        name, content, namespace, target_host=target_host, target_port=target_port
    )
    return {"name": name, "uploaded": True, "lines": len(content)}


@logged_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def put_and_compile(
    name: Annotated[
        str,
        Field(
            description="Full document name including extension. Format: 'Package.ClassName.ext'. Examples: 'MyApp.Person.cls', 'Utils.mac'. For .cls files, this MUST match the class declaration inside the file.",
            min_length=1,
            max_length=255,
        ),
    ],
    path: Annotated[
        str | None,
        Field(
            description="Relative file path within the workspace to read from. Defaults to the document name. The file must already exist in the workspace.",
            min_length=1,
            max_length=1024,
        ),
    ] = None,
    flags: Annotated[
        str | None,
        Field(
            description="Compiler flags. Defaults to IRIS_COMPILE_FLAGS env var ('cuk'). Flag reference: c=compile, u=skip up-to-date, k=keep generated source, b=include subclasses/dependents, r=compile predecessors, d=display output.",
            min_length=1,
            max_length=64,
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to write to and compile in. Uses the configured default if omitted.",
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
    """Read a file from the local workspace, push it to IRIS, and compile it in one step.

    **Runs on: local → IRIS** (reads a local file, writes and compiles on the remote IRIS server).

    This is the recommended tool for creating or updating classes. It combines
    put_document + compile_documents into a single call. The file must already
    exist in the local workspace. The result includes both the put status and any
    compilation errors or warnings.
    """
    validate_doc_name(name)
    file_path = resolve_safe(path or name)
    content = load_content(file_path)
    await docs_api.put_document(
        name, content, namespace, target_host=target_host, target_port=target_port
    )
    compile_data = await compile_api.compile_documents(
        [name], namespace, flags, target_host=target_host, target_port=target_port
    )
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
