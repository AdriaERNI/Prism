"""MCP tools for managing IRIS source code documents."""

import json
from typing import Annotated

from pydantic import Field

from prism.iris.api import documents as docs_api
from prism.iris.api.documents import DocumentNotFound
from prism.iris.sdk.http import handle_api_error
from prism.iris.sdk.workspace import validate_doc_name
from prism.mcp._decorator import logged_tool

CHARACTER_LIMIT = 25000


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def get_document(
    name: Annotated[
        str,
        Field(
            description="Full document name including extension. Format: 'Package.ClassName.ext'. Examples: 'MyApp.Person.cls', 'Utils.mac', 'MyInclude.inc'. The name must match exactly as stored in IRIS — use list_documents to discover names.",
            min_length=1,
            max_length=255,
        ),
    ],
    from_line: Annotated[
        int | None,
        Field(
            description="Start line (1-indexed, inclusive). Cannot be combined with head or tail."
        ),
    ] = None,
    to_line: Annotated[
        int | None,
        Field(description="End line (1-indexed, inclusive). Cannot be combined with head or tail."),
    ] = None,
    head: Annotated[
        int | None,
        Field(
            description="Return only the first N lines. Cannot be combined with from_line, to_line, or tail."
        ),
    ] = None,
    tail: Annotated[
        int | None,
        Field(
            description="Return only the last N lines. Cannot be combined with from_line, to_line, or head."
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to read from. Uses the configured default if omitted.",
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
    """Fetch a document from the IRIS server and return its content inline.

    **Runs on: IRIS server** (remote — reads source code stored in IRIS).

    Returns the source code lines directly in the response — no files are
    written to the local workspace. Use the slicing parameters
    (from_line/to_line, head, tail) to navigate large documents without
    retrieving everything.

    If the document does not exist, returns ``found=false``.
    """
    # Validate slicing parameter combinations
    range_params = from_line is not None or to_line is not None
    if range_params and head is not None:
        raise ValueError("from_line/to_line cannot be combined with head")
    if range_params and tail is not None:
        raise ValueError("from_line/to_line cannot be combined with tail")
    if head is not None and tail is not None:
        raise ValueError("head cannot be combined with tail")

    validate_doc_name(name)
    try:
        result = await docs_api.get_document(
            name,
            namespace,
            target_host=target_host,
            target_port=target_port,
        )
    except DocumentNotFound:
        return {"name": name, "found": False}
    except Exception as exc:
        return {"name": name, "found": False, "error": handle_api_error(exc)}

    content = result.get("result", {}).get("content", [])
    if not content:
        return {
            "name": name,
            "found": True,
            "total_lines": 0,
            "from_line": 1,
            "to_line": 0,
            "content": [],
        }

    if not isinstance(content, list):
        raise ValueError(f"Expected content to be a list, got {type(content).__name__}")

    lines: list[str] = []
    for i, item in enumerate(content):
        if isinstance(item, dict):
            lines.append(item.get("content", ""))
        elif isinstance(item, str):
            lines.append(item)
        else:
            raise ValueError(f"Unexpected content item at index {i}: {type(item).__name__}")

    total = len(lines)

    # Apply slicing
    if head is not None:
        n = max(0, head)
        start, end = 1, min(n, total)
    elif tail is not None:
        n = max(0, tail)
        start = max(1, total - n + 1)
        end = total
    else:
        start = max(1, from_line) if from_line is not None else 1
        end = min(to_line, total) if to_line is not None else total

    sliced = lines[start - 1 : end]

    result = {
        "name": name,
        "found": True,
        "total_lines": total,
        "from_line": start,
        "to_line": end,
        "content": sliced,
    }

    # Apply character limit
    result_str = json.dumps(result, default=str)
    if len(result_str) > CHARACTER_LIMIT:
        half = max(1, len(sliced) // 2)
        result["content"] = sliced[:half]
        result["to_line"] = start + half - 1
        result["truncated"] = True
        result["truncation_message"] = (
            f"Document truncated from {len(sliced)} to {half} lines. "
            "Use from_line/to_line to read the rest."
        )
    return result


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def list_documents(
    doc_type: Annotated[
        str | None,
        Field(
            description="Filter by document type. Valid values: 'cls' (classes), 'mac' (routines), 'int' (intermediate code), 'inc' (include files), 'csp' (web pages), 'bpl' (business processes), 'dtl' (data transformations). Omit to list all types.",
            min_length=1,
            max_length=64,
        ),
    ] = None,
    filter: Annotated[
        str | None,
        Field(
            description="Filter documents by name prefix. Examples: 'MyApp' returns all docs starting with 'MyApp' (MyApp.Person.cls, MyApp.Utils.cls, etc.). 'MyApp.Person' narrows to that specific class.",
            min_length=1,
            max_length=255,
        ),
    ] = None,
    generated: Annotated[
        bool,
        Field(
            description="Include system-generated documents (compiler output, internal routines). Default false — only user-authored documents are returned."
        ),
    ] = False,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to list documents from. Uses the configured default if omitted.",
            min_length=1,
            max_length=64,
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results to return. Default 50, max 200.",
            ge=1,
            le=200,
        ),
    ] = 50,
    offset: Annotated[
        int,
        Field(
            description="Number of results to skip for pagination. Default 0.",
            ge=0,
        ),
    ] = 0,
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
    """List source code documents stored on the IRIS server.

    **Runs on: IRIS server** (remote — queries IRIS database metadata).

    Use this to discover existing classes, routines, and other source
    artifacts before reading or modifying them. Results can be filtered by
    type (e.g. 'cls' for classes only) and by name prefix.

    Supports pagination via *limit* and *offset*. The response includes
    ``has_more`` and ``next_offset`` to help navigate large result sets.

    Returns ``{"documents": [...], "count": N, "total": N, "offset": N,
    "has_more": bool, "next_offset": N | None}`` where each document has:
    - **name**: full document name to pass to get_document, put_document,
      delete_document, or compile_documents (e.g. ``MyApp.Person.cls``)
    - **type**: category — CLS (class), MAC (routine), INC (include), INT
      (intermediate), CSP (web page), etc.
    - **modified**: last modification timestamp
    - **database**: IRIS database the document is stored in
    """
    try:
        data = await docs_api.list_documents(
            namespace,
            doc_type,
            generated,
            filter,
            target_host=target_host,
            target_port=target_port,
        )
    except Exception as exc:
        return {"error": handle_api_error(exc), "documents": [], "count": 0}

    content = data.get("result", {}).get("content", [])
    all_docs = [
        {
            "name": item["name"],
            "type": item.get("cat", ""),
            "modified": item.get("ts", ""),
            "database": item.get("db", ""),
        }
        for item in content
    ]

    total = len(all_docs)
    paginated = all_docs[offset : offset + limit]
    has_more = offset + limit < total
    next_offset = offset + limit if has_more else None

    result = {
        "documents": paginated,
        "count": len(paginated),
        "total": total,
        "offset": offset,
        "has_more": has_more,
        "next_offset": next_offset,
    }

    # Apply character limit
    result_str = json.dumps(result, default=str)
    if len(result_str) > CHARACTER_LIMIT:
        half = max(1, len(paginated) // 2)
        result["documents"] = paginated[:half]
        result["count"] = half
        result["truncated"] = True
        result["truncation_message"] = (
            f"Response truncated from {len(paginated)} to {half} items. "
            "Reduce limit or add filters to see more results."
        )
    return result


@logged_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def delete_document(
    name: Annotated[
        str,
        Field(
            description="Full document name including extension. Format: 'Package.ClassName.ext'. Examples: 'MyApp.Person.cls', 'Utils.mac', 'MyInclude.inc'.",
            min_length=1,
            max_length=255,
        ),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to delete from. Uses the configured default if omitted.",
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
    """Delete a source code document from the IRIS server.

    **Runs on: IRIS server** (remote — deletes from the IRIS database).

    WARNING: Deleting a compiled class also removes its SQL table and all data
    stored in it. This cannot be undone. If the document does not exist, returns
    a result indicating it was not found instead of raising an error.
    """
    validate_doc_name(name)
    try:
        await docs_api.delete_document(
            name,
            namespace,
            target_host=target_host,
            target_port=target_port,
        )
        return {"name": name, "deleted": True}
    except DocumentNotFound:
        return {"name": name, "deleted": False, "reason": "not found"}
    except Exception as exc:
        return {"name": name, "deleted": False, "error": handle_api_error(exc)}
