"""prism index — build and query a compact index of IRIS source code."""

from __future__ import annotations

import asyncio

import typer

from prism.cli.errors import handle_command_error
from prism.iris.api.index import (
    build_index,
    class_node,
    class_refs,
    get_index,
    index_summary,
    method_impact,
    method_path,
    refresh_index,
    run_index_query,
    search_symbols,
)
from prism.iris.api.index import (
    index_status as api_index_status,
)
from prism.output import format_output, get_output_format


def index(
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace to index."),
    include_system: bool = typer.Option(False, "--system", help="Include system classes."),
    prefix: str = typer.Option("", "--prefix", help="Only index classes with this prefix."),
    summary: bool = typer.Option(False, "--summary", help="Only show counts, no class details."),
    call_graph: bool = typer.Option(
        False,
        "--call-graph",
        help="Also build a method-level call graph by reading every in-index "
        "class's body. Slow (adds ~20s). Adds call_edges, r_call_edges, "
        "code_refs and unresolved-call counts.",
    ),
) -> None:
    """Build a compact index of classes in an IRIS namespace.

    Useful for understanding the structure of large IRIS codebases without
    reading every document. Outputs class hierarchies, methods, properties,
    SQL projections, imports, and dependencies as JSON.
    """
    ns = namespace or None
    prefix_val = prefix or None

    try:
        if summary:
            result = asyncio.run(index_summary(ns))
        else:
            result = asyncio.run(
                build_index(
                    namespace=ns,
                    include_system=include_system,
                    filter_prefix=prefix_val,
                    include_call_graph=call_graph,
                )
            )
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))


# ── index-search ──────────────────────────────────────────────────────────


def index_search(
    query: str = typer.Argument(
        ..., help="Symbol term to search (class/method/property/table name)."
    ),
    kind: str = typer.Option(
        "", "--kind", "-k", help="Restrict to 'class', 'method', 'property' or 'table'."
    ),
    limit: int = typer.Option(
        50, "--limit", "-l", min=1, max=200, help="Maximum results (default 50)."
    ),
    exact: bool = typer.Option(False, "--exact", help="Only exact-name matches (fastest)."),
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace."),
) -> None:
    """Search IRIS symbol names (classes, methods, properties, SQL tables).

    Server-side %Dictionary SQL search. Class names, method names, property
    names and SqlTableName — exact-match and %STARTSWITH prefix.
    """
    try:
        result = asyncio.run(
            search_symbols(
                query,
                kind=kind or None,
                limit=limit,
                exact=exact,
                namespace=namespace or None,
            )
        )
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))


# ── index-node ────────────────────────────────────────────────────────────


def index_node(
    class_name: str = typer.Argument(..., help="Class to assemble the full picture for."),
    prefix: str = typer.Option("", "--prefix", help="Only index classes with this prefix."),
    system: bool = typer.Option(False, "--system", help="Include system classes."),
    refresh: bool = typer.Option(False, "--refresh", help="Rebuild the cached index first."),
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace."),
) -> None:
    """Return the full picture of one class: methods, props, supers, callers, callees."""
    try:
        ns = namespace or None
        pfx = prefix or None
        if refresh:
            index = asyncio.run(
                refresh_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=True
                )
            )
        else:
            index = asyncio.run(
                get_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=True
                )
            )
        result = class_node(index, class_name)
        result["cached"] = index.get("cached", False)
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))


# ── index-refs ────────────────────────────────────────────────────────────


def index_refs(
    class_name: str = typer.Argument(..., help="Class to find body-text references to."),
    prefix: str = typer.Option("", "--prefix", help="Only index classes with this prefix."),
    system: bool = typer.Option(False, "--system", help="Include system classes."),
    refresh: bool = typer.Option(False, "--refresh", help="Rebuild the cached index first."),
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace."),
) -> None:
    """List which classes reference a class in their method bodies."""
    try:
        ns = namespace or None
        pfx = prefix or None
        if refresh:
            index = asyncio.run(
                refresh_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=True
                )
            )
        else:
            index = asyncio.run(
                get_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=True
                )
            )
        result = class_refs(index, class_name)
        result["cached"] = index.get("cached", False)
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))


# ── index-impact ──────────────────────────────────────────────────────────


def index_impact(
    method: str = typer.Argument(
        ..., help="'Class.method' or bare class to measure blast radius of."
    ),
    max_hops: int | None = typer.Option(
        None, "--max-hops", "-m", min=1, max=20, help="Max transitive hops (default unlimited)."
    ),
    prefix: str = typer.Option("", "--prefix", help="Only index classes with this prefix."),
    system: bool = typer.Option(False, "--system", help="Include system classes."),
    refresh: bool = typer.Option(False, "--refresh", help="Rebuild the cached index first."),
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace."),
) -> None:
    """Measure the blast radius of a method (transitive reverse reachability)."""
    try:
        ns = namespace or None
        pfx = prefix or None
        if refresh:
            index = asyncio.run(
                refresh_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=True
                )
            )
        else:
            index = asyncio.run(
                get_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=True
                )
            )
        result = method_impact(index, method, max_hops=max_hops)
        result["cached"] = index.get("cached", False)
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))


# ── index-path ────────────────────────────────────────────────────────────


def index_path(
    source: str = typer.Argument(..., help="Start 'Class.method' or class name."),
    target: str = typer.Argument(..., help="End 'Class.method' or class name."),
    prefix: str = typer.Option("", "--prefix", help="Only index classes with this prefix."),
    system: bool = typer.Option(False, "--system", help="Include system classes."),
    refresh: bool = typer.Option(False, "--refresh", help="Rebuild the cached index first."),
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace."),
) -> None:
    """Find the shortest method-to-method path in the call graph (BFS)."""
    try:
        ns = namespace or None
        pfx = prefix or None
        if refresh:
            index = asyncio.run(
                refresh_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=True
                )
            )
        else:
            index = asyncio.run(
                get_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=True
                )
            )
        result = method_path(index, source, target)
        result["cached"] = index.get("cached", False)
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))


# ── index-queries ─────────────────────────────────────────────────────────


def index_queries(
    query: str = typer.Argument(
        ...,
        help="Named query: callers_of_method, callers_high_fanin, "
        "method_calls_outbound, class_references, find_path.",
    ),
    method: str = typer.Option(
        "", "--method", "-m", help="'Class.method' for callers_of_method / method_calls_outbound."
    ),
    class_name: str = typer.Option("", "--class", "-c", help="Class for class_references."),
    source: str = typer.Option("", "--source", "-s", help="Start 'Class.method' for find_path."),
    target: str = typer.Option("", "--target", "-t", help="End 'Class.method' for find_path."),
    top_n: int = typer.Option(20, "--top-n", min=1, max=200, help="Top-N for callers_high_fanin."),
    limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        min=1,
        max=1000,
        help="Max results for callers_of_method / method_calls_outbound.",
    ),
    prefix: str = typer.Option("", "--prefix", help="Only index classes with this prefix."),
    system: bool = typer.Option(False, "--system", help="Include system classes."),
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace."),
) -> None:
    """Run one of the five named index queries over the built call graph."""
    try:
        result = asyncio.run(
            run_index_query(
                query,
                method=method or None,
                class_name=class_name or None,
                source=source or None,
                target=target or None,
                top_n=top_n,
                limit=limit,
                namespace=namespace or None,
                include_system=system,
                filter_prefix=prefix or None,
            )
        )
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))


def index_status(
    prefix: str = typer.Option("", "--prefix", help="Only index classes with this prefix."),
    system: bool = typer.Option(False, "--system", help="Include system classes."),
    refresh: bool = typer.Option(False, "--refresh", help="Force a rebuild of the cached index."),
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace."),
) -> None:
    """Report the local index cache status (freshness, counts, age)."""
    try:
        ns = namespace or None
        pfx = prefix or None
        if refresh:
            index = asyncio.run(
                refresh_index(
                    namespace=ns, include_system=system, filter_prefix=pfx, include_call_graph=False
                )
            )
            result = {
                "namespace": ns or "USER",
                "target": index.get("target", f"prefix:{pfx}" if pfx else "all"),
                "classes": len(index.get("classes", [])),
                "fresh": True,
                "cached": True,
                "age_seconds": 0.0,
                "built_at": 0.0,
                "refreshed": True,
            }
        else:
            result = asyncio.run(
                api_index_status(namespace=ns, include_system=system, filter_prefix=pfx)
            )
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))
