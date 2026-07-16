"""Index MCP tool — builds a compact, token-efficient index of IRIS code.

Helps AI agents understand large IRIS codebases without reading every file.
Uses %Dictionary SQL metadata to extract class hierarchies, methods,
properties, SQL projections, and dependencies.
"""

from typing import Annotated

from pydantic import Field

from prism.iris.api.index import build_index, index_summary
from prism.mcp._decorator import logged_tool


@logged_tool
async def index_code(
    namespace: Annotated[
        str | None,
        Field(description="IRIS namespace to index. Defaults to configured namespace."),
    ] = None,
    include_system: Annotated[
        bool,
        Field(
            description="Include system classes (%Library, %SYS, etc.). Default: false."
        ),
    ] = False,
    filter_prefix: Annotated[
        str | None,
        Field(
            description="Only index classes starting with this prefix (e.g. 'MyApp')."
        ),
    ] = None,
    summary_only: Annotated[
        bool,
        Field(
            description="Return only counts (no class details). Faster for quick overviews."
        ),
    ] = False,
) -> dict:
    """Build a compact index of all classes in an IRIS namespace.

    Returns class hierarchies, methods, properties, SQL projections, and
    dependencies — without fetching full source files. Use this to understand
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
        return await index_summary(namespace)

    return await build_index(
        namespace=namespace,
        include_system=include_system,
        filter_prefix=filter_prefix,
    )
