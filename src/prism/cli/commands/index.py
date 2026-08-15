"""prism index — build a compact index of IRIS source code."""

from __future__ import annotations

import asyncio

import typer

from prism.cli.errors import handle_command_error
from prism.iris.api.index import build_index, index_summary
from prism.iris.api.index import index_callers as api_index_callers
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


def index_callers(
    method: str = typer.Argument(
        ..., help="Method to query as 'Class.Method' (e.g. 'MyApp.Person.Save')."
    ),
    direction: str = typer.Option(
        "reverse",
        "--direction",
        "-d",
        help="'reverse' = who calls this method (default); 'forward' = what it calls.",
    ),
    max_results: int = typer.Option(
        50,
        "--max",
        "-m",
        min=1,
        max=500,
        help="Maximum number of callers/callees to return.",
    ),
    prefix: str = typer.Option("", "--prefix", help="Only index classes with this prefix."),
    system: bool = typer.Option(False, "--system", help="Include system classes in the index."),
    namespace: str = typer.Option("", "--namespace", "-n", help="IRIS namespace to index."),
) -> None:
    """Answer 'who calls this method?' (reverse) or 'what does this method call?' (forward).

    Builds the method-level call graph (the slow, opt-in Tier 2 pass) and
    returns the focused callers/callees for a single method — the lightweight
    way to ask "who calls X" before changing or deleting a method.
    """
    ns = namespace or None
    prefix_val = prefix or None
    try:
        result = asyncio.run(
            api_index_callers(
                method=method,
                namespace=ns,
                include_system=system,
                filter_prefix=prefix_val,
                direction=direction,
                max_callers=max_results,
            )
        )
    except Exception as exc:
        handle_command_error(exc)

    typer.echo(format_output(result, get_output_format()))
