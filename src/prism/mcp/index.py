"""Index MCP tool — builds a compact, token-efficient index of IRIS code.

Helps AI agents understand large IRIS codebases without reading every file.
Uses %Dictionary SQL metadata to extract class hierarchies, methods,
properties, SQL projections, and dependencies.
"""

from typing import Annotated

from pydantic import Field

from prism.iris.api.index import (
    _index_target,
    build_index,
    class_node,
    class_refs,
    get_index,
    index_summary,
    method_impact,
    method_path,
    reachable,
    refresh_index,
    run_index_query,
    search_symbols,
)
from prism.iris.api.index import (
    index_status as api_index_status,
)
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


# ── index_search ──────────────────────────────────────────────────────────


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_search(
    query: Annotated[
        str,
        Field(
            description="Term to search for across IRIS symbol names (class, "
            "method, property, SQL table). Exact-name hits rank first, then "
            "%STARTSWITH prefix hits. Letters, digits, '_', '.', '%' only.",
            min_length=1,
            max_length=255,
        ),
    ],
    kind: Annotated[
        str | None,
        Field(
            description="Restrict the search to one symbol kind: 'class', "
            "'method', 'property' or 'table'. Default: search all kinds.",
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of results to return. Default: 50.", ge=1, le=200),
    ] = 50,
    exact: Annotated[
        bool,
        Field(
            description="Only return exact-name matches (the fastest, most "
            "precise path). Default: false."
        ),
    ] = False,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace to search. Defaults to configured namespace.",
            min_length=1,
            max_length=64,
        ),
    ] = None,
    target_host: Annotated[
        str | None,
        Field(description="IRIS server hostname or IP address. Uses the default if omitted."),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Search IRIS symbol names (classes, methods, properties, SQL tables).

    **Runs on: IRIS server** (remote — fast %Dictionary SQL metadata).

    Queries the IRIS ``%Dictionary`` tables server-side for symbol names:
    exact-name matches (fastest), then ``%STARTSWITH`` prefix matches. The
    search spans class names, method names, property names and SQL table
    names, ranking ``class`` first, then ``method``, then ``property``, then
    ``table``. Use this to quickly locate a symbol in a large codebase without
    building a full index.

    Examples:
        # Find the class that defines a method
        index_search(query="GetSystemSetting")

        # Find all HCC classes
        index_search(query="HCC.Interface", kind="class")

        # Exact method lookup (fastest)
        index_search(query="GetUnits", kind="method", exact=True)

        # Property named Patient*
        index_search(query="Patient", kind="property")
    """
    return await search_symbols(
        query,
        kind=kind,
        limit=limit,
        exact=exact,
        namespace=namespace,
        target_host=target_host,
        target_port=target_port,
    )


# ── index_node ────────────────────────────────────────────────────────────


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_node(
    class_name: Annotated[
        str,
        Field(
            description="The class name to assemble the full picture for (e.g. 'MyApp.Model').",
            min_length=1,
            max_length=255,
        ),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace. Defaults to configured namespace.",
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
    refresh: Annotated[
        bool,
        Field(description="Rebuild the cached index before answering. Default: false."),
    ] = False,
    target_host: Annotated[
        str | None,
        Field(description="IRIS server hostname or IP address. Uses the default if omitted."),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Get the focused 'full picture' of one class.

    **Runs on: IRIS server + local cache** (assembles the already-built index).

    Returns a single class's methods and signatures, properties, supers,
    children (classes that reference/extends it), callers (from the reverse
    call graph), callees (from the forward call graph), body code references
    and connectivity degree. Pure assembly of the index — fast once built.

    Examples:
        index_node(class_name="MyApp.Model")

        # Scoped to a prefix
        index_node(class_name="HCC.DocRepository.AllDocs", filter_prefix="HCC")
    """
    if refresh:
        index = await refresh_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=True,
            target_host=target_host,
            target_port=target_port,
        )
    else:
        index = await get_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=True,
            target_host=target_host,
            target_port=target_port,
        )
    node = class_node(index, class_name)
    if isinstance(node.get("error"), str):
        return node
    node["cached"] = index.get("cached", False)
    return node


# ── index_refs ────────────────────────────────────────────────────────────


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_refs(
    class_name: Annotated[
        str,
        Field(
            description="The class name to find body-text references to (e.g. 'MyApp.Model').",
            min_length=1,
            max_length=255,
        ),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace. Defaults to configured namespace.",
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
    refresh: Annotated[
        bool,
        Field(description="Rebuild the cached index before answering. Default: false."),
    ] = False,
    target_host: Annotated[
        str | None,
        Field(description="IRIS server hostname or IP address. Uses the default if omitted."),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Find which classes reference a class in their method bodies.

    **Runs on: IRIS server + local cache** (reads the already-computed reverse
    code-reference map).

    Searches the built call-graph's ``r_code_refs`` map (every ``##class(X)``
    class reference seen in body text). Returns the referencing classes and a
    count. Requires the index to have been built with ``include_call_graph``.

    Examples:
        index_refs(class_name="MyApp.Model", filter_prefix="MyApp")
    """
    if refresh:
        index = await refresh_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=True,
            target_host=target_host,
            target_port=target_port,
        )
    else:
        index = await get_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=True,
            target_host=target_host,
            target_port=target_port,
        )
    refs = class_refs(index, class_name)
    refs["cached"] = index.get("cached", False)
    return refs


# ── index_impact ──────────────────────────────────────────────────────────


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_impact(
    method: Annotated[
        str,
        Field(
            description="The method to measure the blast radius of, as "
            "'Class.method' (e.g. 'MyApp.Service.Run'), or a bare class name "
            "'MyApp.Service' for class-level impact.",
            min_length=1,
            max_length=255,
        ),
    ],
    max_hops: Annotated[
        int | None,
        Field(
            description="Maximum transitive hops to traverse. Default: unlimited.",
            ge=1,
            le=20,
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace. Defaults to configured namespace.",
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
    refresh: Annotated[
        bool,
        Field(description="Rebuild the cached index before answering. Default: false."),
    ] = False,
    target_host: Annotated[
        str | None,
        Field(description="IRIS server hostname or IP address. Uses the default if omitted."),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Measure the blast radius of a method (transitive reverse reachability).

    **Runs on: IRIS server + local cache** (traverses ``r_call_edges`` +
    ``r_edges``).

    Walks the reverse call graph from *method* — who calls it, who calls the
    callers, and so on — plus the structural reverse edges, to compute the
    full set of transitive dependents (the "who breaks if I change this"
    answer). Returns ``hops`` (each dependent with its distance), ``count``
    and ``truncated``.

    Examples:
        # Who transitively depends on HCC.DocRepository.Patient
        index_impact(method="HCC.DocRepository.Patient")

        # Method-level with a hop ceiling
        index_impact(method="MyApp.Service.Run", max_hops=3)
    """
    if refresh:
        index = await refresh_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=True,
            target_host=target_host,
            target_port=target_port,
        )
    else:
        index = await get_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=True,
            target_host=target_host,
            target_port=target_port,
        )
    imp = method_impact(index, method, max_hops=max_hops)
    imp["cached"] = index.get("cached", False)
    return imp


# ── index_path ────────────────────────────────────────────────────────────


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_path(
    source: Annotated[
        str,
        Field(
            description="The start method, as 'Class.method' (e.g. 'MyApp.Service.Run') "
            "or a bare class name.",
            min_length=1,
            max_length=255,
        ),
    ],
    target: Annotated[
        str,
        Field(
            description="The end method, as 'Class.method' (e.g. 'MyApp.Repo.Save') "
            "or a bare class name.",
            min_length=1,
            max_length=255,
        ),
    ],
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace. Defaults to configured namespace.",
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
    refresh: Annotated[
        bool,
        Field(description="Rebuild the cached index before answering. Default: false."),
    ] = False,
    target_host: Annotated[
        str | None,
        Field(description="IRIS server hostname or IP address. Uses the default if omitted."),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Find the shortest method-to-method path in the call graph.

    **Runs on: IRIS server + local cache** (BFS over the built call graph).

    Computes a shortest path from *source* to *target* using breadth-first
    search with predecessor tracking, over the merged call edges, reverse
    call edges and structural edges. Returns ``found``, ``path`` (the node
    list), ``length`` (edge count) and ``hops`` (a display string).

    Examples:
        index_path(source="HCC.Demo", target="HCC.Interface.Setting")
    """
    if refresh:
        index = await refresh_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=True,
            target_host=target_host,
            target_port=target_port,
        )
    else:
        index = await get_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=True,
            target_host=target_host,
            target_port=target_port,
        )
    path = method_path(index, source, target)
    path["cached"] = index.get("cached", False)
    return path


# ── index_status ──────────────────────────────────────────────────────────


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_status(
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace. Defaults to configured namespace.",
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
    refresh: Annotated[
        bool,
        Field(
            description="Force a rebuild of the (possibly stale) cached index. Default: false.",
        ),
    ] = False,
    target_host: Annotated[
        str | None,
        Field(description="IRIS server hostname or IP address. Uses the default if omitted."),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Report the cache status for an index scope.

    **Runs on: IRIS server + local cache** (one fast fingerprint SQL query).

    Returns the class count in the scope, whether a cached index exists, its
    age in seconds, and whether it is fresh (the ``%Dictionary``
    ``TimeChanged`` fingerprint matches). Pass ``refresh=True`` to force a
    rebuild when a cached index has gone stale.

    Examples:
        index_status(filter_prefix="MyApp")

        # Force a rebuild for a changed namespace
        index_status(refresh=True)
    """
    if refresh:
        index = await refresh_index(
            namespace=namespace,
            include_system=include_system,
            filter_prefix=filter_prefix,
            include_call_graph=False,
            target_host=target_host,
            target_port=target_port,
        )
        return {
            "namespace": namespace or "USER",
            "target": index.get("target", _index_target(include_system, filter_prefix)),
            "classes": len(index.get("classes", [])),
            "fresh": True,
            "cached": True,
            "age_seconds": 0.0,
            "built_at": 0.0,
            "refreshed": True,
        }

    return await api_index_status(
        namespace=namespace,
        include_system=include_system,
        filter_prefix=filter_prefix,
        target_host=target_host,
        target_port=target_port,
    )


# ── index_queries ─────────────────────────────────────────────────────────


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def index_queries(
    query: Annotated[
        str,
        Field(
            description="Which named query to run: 'callers_of_method', "
            "'callers_high_fanin', 'method_calls_outbound', 'class_references' "
            "or 'find_path'.",
            min_length=1,
            max_length=64,
        ),
    ],
    method: Annotated[
        str | None,
        Field(
            description="For callers_of_method / method_calls_outbound: the "
            "method key as 'Class.Method' (e.g. 'MyApp.Service.Run').",
            min_length=1,
            max_length=255,
        ),
    ] = None,
    class_name: Annotated[
        str | None,
        Field(
            description="For class_references: the class name to find body "
            "references to (e.g. 'MyApp.Model').",
            min_length=1,
            max_length=255,
        ),
    ] = None,
    source: Annotated[
        str | None,
        Field(
            description="For find_path: the start 'Class.method' or class name.",
            min_length=1,
            max_length=255,
        ),
    ] = None,
    target: Annotated[
        str | None,
        Field(
            description="For find_path: the end 'Class.method' or class name.",
            min_length=1,
            max_length=255,
        ),
    ] = None,
    top_n: Annotated[
        int,
        Field(
            description="For callers_high_fanin: how many top methods to return. Default: 20.",
            ge=1,
            le=200,
        ),
    ] = 20,
    limit: Annotated[
        int,
        Field(
            description="For callers_of_method / method_calls_outbound: maximum "
            "number of results. Default: 100.",
            ge=1,
            le=1000,
        ),
    ] = 100,
    namespace: Annotated[
        str | None,
        Field(
            description="IRIS namespace. Defaults to configured namespace.",
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
        Field(description="IRIS server hostname or IP address. Uses the default if omitted."),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Run one of the five named index queries.

    **Runs on: IRIS server + local cache** (reads the already-built index; the
    call-graph maps come from the cached Tier-2 build).

    The five named queries, all over the built method-level call graph:

    * ``callers_of_method`` — list the methods that call ``Class.method``
      (direct callers, from the reverse call map).
    * ``callers_high_fanin`` — the methods with the most callers (top-N).
    * ``method_calls_outbound`` — what ``Class.method`` calls (direct callees,
      each with its call-form ``pattern`` 1-7).
    * ``class_references`` — which classes reference a class in method bodies.
    * ``find_path`` — the shortest method-to-method path (BFS).

    These are stable, focused, single-hop query shapes; the heavier transitive
    tools (``index_impact``, ``index_path``) remain available for blast-radius
    and path questions.

    Note: callers/callees are only visible when the *caller class* is inside
    the indexed scope — a ``filter_prefix`` that excludes a calling class will
    hide its edges.

    Examples:
        # Who calls HCC.DocRepository.Patient.Load?
        index_queries(query="callers_of_method", method="HCC.DocRepository.Patient.Load")

        # The 10 methods with the most callers
        index_queries(query="callers_high_fanin", top_n=10)

        # What HCC.SQL.Tools.BuildPyConfig calls
        index_queries(query="method_calls_outbound", method="HCC.SQL.Tools.BuildPyConfig.Run")

        # Which classes reference HCC.Interface.Setting
        index_queries(query="class_references", class_name="HCC.Interface.Setting")

        # Shortest path between two methods
        index_queries(query="find_path", source="HCC.Demo", target="HCC.Interface.Setting")
    """
    return await run_index_query(
        query=query,
        method=method,
        class_name=class_name,
        source=source,
        target=target,
        top_n=top_n,
        limit=limit,
        namespace=namespace,
        include_system=include_system,
        filter_prefix=filter_prefix,
        target_host=target_host,
        target_port=target_port,
    )
