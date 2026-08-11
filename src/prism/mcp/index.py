"""Index MCP tool — builds a compact, token-efficient index of IRIS code.

Helps AI agents understand large IRIS codebases without reading every file.
Uses %Dictionary SQL metadata to extract class hierarchies, methods,
properties, SQL projections, and dependencies.
"""

from typing import Annotated

from pydantic import Field

from prism.iris.api.index import build_index, index_summary
from prism.mcp._decorator import logged_tool


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_code(
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to index. Defaults to configured namespace.",
            min_length=1,
            max_length=64,
        ),
    ] = None,
    include_system: Annotated[
        bool,
        Field(description="Include system classes (%Library, %SYS, etc.). Default: false."),
    ] = False,
    filter_prefix: Annotated[
        str | None,
        Field(
            description="Only index classes starting with this prefix (e.g. 'MyApp').",
            min_length=1,
            max_length=255,
        ),
    ] = None,
    summary_only: Annotated[
        bool,
        Field(description="Return only counts (no class details). Faster for quick overviews."),
    ] = False,
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
    """Build a compact index of all classes in an IRIS namespace.

    **Runs on: IRIS server** (remote — queries IRIS %Dictionary SQL metadata).

    Returns class hierarchies, methods, properties, SQL projections, imports,
    and dependencies — without fetching full source files. Use this to understand
    a large IRIS codebase using a fraction of the tokens needed to read every
    document.

    Examples:
        # Index all custom classes in USER namespace
        index_code()

        # Quick overview — just counts
        index_code(summary_only=True)

        # Index only MyApp.* classes
        index_code(filter_prefix="MyApp")

        # Include system classes
        index_code(include_system=True)
    """
    if summary_only:
        return await index_summary(
            namespace,
            target_host=target_host,
            target_port=target_port,
        )

    return await build_index(
        namespace=namespace,
        include_system=include_system,
        filter_prefix=filter_prefix,
        target_host=target_host,
        target_port=target_port,
    )
