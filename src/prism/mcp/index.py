"""Index MCP tool — builds a compact, token-efficient index of IRIS code.

Helps AI agents understand large IRIS codebases without reading every file.
Uses %Dictionary SQL metadata to extract class hierarchies, methods,
properties, SQL projections, and dependencies.
"""

from typing import Annotated

from pydantic import Field

from prism.iris.api.index import build_index, index_summary, reachable
from prism.iris.api.index import index_callers as api_index_callers
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
    include_call_graph: Annotated[
        bool,
        Field(
            description="Also read every in-index class's method bodies and build "
            "a method-level call graph. Significantly slower (the ~+20s pass). "
            "Adds call_edges, r_call_edges, call stats, code_refs and unresolved-"
            "call counts to the result. Default: false (fast %Dictionary path only)."
        ),
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

    Return class hierarchies, methods, properties, SQL projections, imports,
    and dependencies — without fetching full source files. Use this to understand
    a large IRIS codebase using a fraction of the tokens needed to read every
    document.

    Set ``include_call_graph=True`` to also build a method-level call graph
    ("who calls this method", "what does this method call"). This is the slow,
    opt-in Tier 2 pass: it fetches every in-index class's body and resolves the
    seven ObjectScript call forms.

    Examples:
        # Index all custom classes in USER namespace
        index_code()

        # Quick overview — just counts
        index_code(summary_only=True)

        # Index only MyApp.* classes
        index_code(filter_prefix="MyApp")

        # Include system classes
        index_code(include_system=True)

        # Also build the method-level call graph (slow)
        index_code(include_call_graph=True)
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
        include_call_graph=include_call_graph,
        target_host=target_host,
        target_port=target_port,
    )


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_reachability(
    class_name: Annotated[
        str,
        Field(
            description="The class name to walk the dependency graph from (e.g. 'MyApp.Model').",
            min_length=1,
            max_length=255,
        ),
    ],
    max_hops: Annotated[
        int,
        Field(
            description="Maximum number of hops to traverse. Default: 3.",
            ge=1,
            le=20,
        ),
    ] = 3,
    direction: Annotated[
        str,
        Field(
            description="Direction of traversal. 'reverse' walks the dependency "
            "graph in the impact direction (what depends on this class — handy for "
            "impact analysis). 'forward' walks what this class depends on. Default: 'reverse'.",
        ),
    ] = "reverse",
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
        Field(description="Include system classes in the index. Default: false."),
    ] = False,
    filter_prefix: Annotated[
        str | None,
        Field(
            description="Only index classes starting with this prefix (e.g. 'MyApp').",
            min_length=1,
            max_length=255,
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
    """Walk the class dependency graph from a starting class.

    **Runs on: IRIS server** (remote — queries IRIS %Dictionary SQL metadata,
    then traverses the built edge map).

    Returns every class reachable from *class_name* within *max_hops* edges,
    with the shortest-path distance for each. Edges are derived from
    superclass links, property types and method-signature types. Use this for
    impact analysis ("what depends on this class"), n-hop reachability and
    shortest-path questions over the codebase. The default ``direction`` is
    ``reverse`` — who depends on this class — which is the impact-analysis
    direction; pass ``direction="forward"`` to list what this class depends on.

    Examples:
        # Who (transitively) depends on MyApp.Model — impact analysis
        index_reachability(class_name="MyApp.Model")

        # Everything MyApp.Core directly depends on (1 hop, forward)
        index_reachability(class_name="MyApp.Core", max_hops=1, direction="forward")
    """
    index = await build_index(
        namespace=namespace,
        include_system=include_system,
        filter_prefix=filter_prefix,
        target_host=target_host,
        target_port=target_port,
    )
    edges = index.get("r_edges", {}) if direction == "reverse" else index.get("edges", {})
    dist = reachable(edges, class_name, max_hops=max_hops)
    return {
        "start": class_name,
        "max_hops": max_hops,
        "direction": direction,
        "reachable": sorted(dist.items(), key=lambda kv: (kv[1], kv[0])),
    }


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_callers(
    method: Annotated[
        str,
        Field(
            description="The method to query as 'Class.method' (e.g. 'MyApp.Person.Save'). "
            "Class must be in the index (see include_system / filter_prefix).",
            min_length=1,
            max_length=255,
        ),
    ],
    direction: Annotated[
        str,
        Field(
            description="Direction of the query. 'reverse' answers 'who calls this method?' "
            "(callers of the method — the impact direction for deleting/renaming it). "
            "'forward' answers 'what does this method call?' (its callees). "
            "Default: 'reverse'.",
        ),
    ] = "reverse",
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of callers/callees to return. Default: 50.",
            ge=1,
            le=500,
        ),
    ] = 50,
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
        Field(description="Include system classes in the index. Default: false."),
    ] = False,
    filter_prefix: Annotated[
        str | None,
        Field(
            description="Only index classes starting with this prefix (e.g. 'MyApp'). "
            "Note: callers are only visible when their class is in the index.",
            min_length=1,
            max_length=255,
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
    """Answer 'who calls this method?' (or 'what does this method call?').

    **Runs on: IRIS server** (remote — builds the method-level call graph by
    reading method bodies, then returns only the focused edges for *method*).

    This is the method-granularity sibling of ``index_reachability`` (which works
    on classes). It builds the call graph (the slow, opt-in Tier 2 pass) and then
    answers one focused question — essential before changing, renaming or
    deleting a method. The default ``direction`` is ``reverse``: who calls this
    method (the impact direction). Pass ``direction=\"forward\"`` for what this
    method itself calls.

    Example:
        # Who calls MyApp.Person.Save? (impact analysis before renaming)
        index_callers(method=\"MyApp.Person.Save\")

        # What does Main.Run call?
        index_callers(method=\"MyApp.Main.Run\", direction=\"forward\")
    """
    return await api_index_callers(
        method=method,
        namespace=namespace,
        include_system=include_system,
        filter_prefix=filter_prefix,
        direction=direction,
        max_callers=max_results,
        target_host=target_host,
        target_port=target_port,
    )
