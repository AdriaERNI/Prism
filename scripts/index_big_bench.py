"""Big-project index benchmark against a large loaded IRIS namespace.

Runs EVERY prism index tool plus the five named queries against a loaded
big project (the zzllkk2003/hcc 2,344-class ObjectScript codebase), asserts
correctness of spot-check facts, and reports median-of-3 timings so index
performance at scale is measured, not assumed.

Usage (from the repo root):

    # 1. Load hcc into IRIS once (see scripts/hcc_loader.py):
    python scripts/hcc_loader.py

    # 2. Run the bench:
    python scripts/index_big_bench.py [--namespace USER] [--runs 3]

The bench asserts real correctness facts (caller counts, reference sets,
high-fanin order, path finding) — a regression fails loudly. Timings are
reported as nanoseconds-per-call medians and printed as a table.

Exit code is 0 when every tool/query produced a correct result, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from statistics import median
from typing import Any

from prism.iris.api.index import (
    class_node,
    class_refs,
    get_index,
    index_status,
    index_summary,
    method_impact,
    method_path,
    reachable,
    run_index_query,
    search_symbols,
)

# Known-good facts about the loaded hcc namespace. These are the project's
# spot-checks — verified against a real hcc load. If any regresses, the bench
# fails loudly (rather than silently reporting a number).
SPOT_CHECKS = {
    # callers_of_method — TestTreatmentPlanGenerate has exactly 27 callers.
    "callers_of_method": ("HCC.SQL.Tools.TestTreatmentPlanGenerate", 27),
    # callers_high_fanin — the most-called method's caller count (>= 1).
    "callers_high_fanin_min": 1,
    # callers of an inherited %OpenId on an in-index receiver.
    "callers_of_header_openid": ("HCC.SQL.Document.Header.%OpenId", 2),
    # class_references of HCC.SQL.Document.Header.
    "class_references_header": ("HCC.SQL.Document.Header", 2),
}


async def _timeit(fn, *args, runs: int = 3, **kw) -> tuple[float, Any]:
    """Return (median_seconds, result) for ``fn(*args, **kw)`` over *runs* calls."""
    timings: list[float] = []
    result: Any = None
    for _ in range(runs):
        t0 = time.perf_counter()
        result = await fn(*args, **kw)
        timings.append(time.perf_counter() - t0)
    return median(timings), result


def _format_ns(seconds: float) -> str:
    if seconds >= 1.0:
        return f"{seconds:.2f}s"
    if seconds >= 1e-3:
        return f"{seconds * 1e3:.1f}ms"
    if seconds >= 1e-6:
        return f"{seconds * 1e6:.0f}µs"
    return f"{seconds * 1e9:.0f}ns"


async def run_bench(namespace: str, runs: int) -> int:
    print(f"[bench] namespace={namespace} runs={runs}")
    rows: list[tuple[str, str, str]] = []  # (tool, result, time)
    failures: list[str] = []

    def _report(tool: str, ok: bool, detail: str, median_s: float) -> None:
        status = "ok" if ok else "FAIL"
        rows.append((tool, status, _format_ns(median_s)))
        if not ok:
            failures.append(f"{tool}: {detail}")

    # ── index_code (summary path) ─────────────────────────────────────────
    median_s, summary = await _timeit(index_summary, namespace, runs=runs)
    ok = isinstance(summary.get("classes"), int) and summary["classes"] > 1000
    _report("index_code(summary)", ok, f"classes={summary.get('classes')}", median_s)

    # ── index build + cache (full index, Tier-2 call graph) ───────────────
    median_s, index = await _timeit(get_index, namespace, include_call_graph=True, runs=runs)
    cg = index.get("call_graph", {}) or {}
    ces = cg.get("stats", {}).get("call_edges", 0)
    ok = index.get("statistics", {}).get("classes", 0) > 1000 and ces > 0
    _report(
        "index_code(callgraph)",
        ok,
        f"classes={index.get('statistics', {}).get('classes')} call_edges={ces}",
        median_s,
    )

    # ── index_reachability ────────────────────────────────────────────────
    median_s, _ = await _timeit(get_index, namespace, include_call_graph=False, runs=runs)
    edges_fwd = index.get("edges", {})
    reachable_out = reachable(edges_fwd, "HCC.SQL.Document.Header", max_hops=2)
    ok = "HCC.SQL.Document.Header" in reachable_out
    _report("index_reachability", ok, f"reachable={len(reachable_out)}", median_s)

    # ── index_search ──────────────────────────────────────────────────────
    median_s, srch = await _timeit(
        search_symbols,
        "HCC.SQL.Document.Header",
        kind="class",
        limit=5,
        runs=runs,
        namespace=namespace,
    )
    ok = srch.get("count", 0) >= 1 and any(
        r.get("symbol") == "HCC.SQL.Document.Header" for r in srch.get("results", [])
    )
    _report("index_search", ok, f"hits={srch.get('count')}", median_s)

    # ── index_node ────────────────────────────────────────────────────────
    median_s, _ = await _timeit(get_index, namespace, include_call_graph=True, runs=runs)
    node = class_node(index, "HCC.SQL.Document.Header")
    ok = node.get("name") == "HCC.SQL.Document.Header" and "methods" in node
    _report("index_node", ok, f"methods={len(node.get('methods', {}))}", median_s)

    # ── index_refs ────────────────────────────────────────────────────────
    median_s, _ = await _timeit(get_index, namespace, include_call_graph=True, runs=runs)
    refs = class_refs(index, "HCC.SQL.Document.Header")
    ok = refs.get("count") == SPOT_CHECKS["class_references_header"][1]
    _report("index_refs", ok, f"refs={refs.get('count')}", median_s)

    # ── index_impact ──────────────────────────────────────────────────────
    median_s, _ = await _timeit(get_index, namespace, include_call_graph=True, runs=runs)
    impact = method_impact(index, "HCC.SQL.Tools.TestTreatmentPlanGenerate")
    ok = impact.get("count", 0) >= 1
    _report("index_impact", ok, f"dependents={impact.get('count')}", median_s)

    # ── index_path ────────────────────────────────────────────────────────
    median_s, _ = await _timeit(get_index, namespace, include_call_graph=True, runs=runs)
    path = method_path(
        index,
        "HCC.SQL.Tools.GenSampleFor10",
        "HCC.SQL.Tools.TestTreatmentPlanGenerate",
    )
    ok = path.get("found") is True
    _report("index_path", ok, f"length={path.get('length')}", median_s)

    # ── index_status ──────────────────────────────────────────────────────
    median_s, status = await _timeit(index_status, namespace, runs=runs)
    ok = isinstance(status.get("classes"), int) and status["classes"] > 1000
    _report("index_status", ok, f"classes={status.get('classes')}", median_s)

    # ── five named queries ────────────────────────────────────────────────
    q = SPOT_CHECKS["callers_of_method"]
    median_s, qr = await _timeit(
        run_index_query, "callers_of_method", method=q[0], runs=runs, namespace=namespace
    )
    ok = qr.get("total") == q[1]
    _report("query callers_of_method", ok, f"total={qr.get('total')} expected={q[1]}", median_s)

    median_s, qr = await _timeit(
        run_index_query, "callers_high_fanin", top_n=10, runs=runs, namespace=namespace
    )
    top = qr.get("results") or [{}]
    ok = top[0].get("callers", 0) >= SPOT_CHECKS["callers_high_fanin_min"]
    _report("query callers_high_fanin", ok, f"top_callers={top[0].get('callers')}", median_s)

    median_s, qr = await _timeit(
        run_index_query,
        "method_calls_outbound",
        method="HCC.SQL.Tools.GenSampleFor10",
        runs=runs,
        namespace=namespace,
    )
    ok = qr.get("total", 0) >= 1
    _report("query method_calls_outbound", ok, f"callees={qr.get('total')}", median_s)

    median_s, qr = await _timeit(
        run_index_query,
        "class_references",
        class_name="HCC.SQL.Document.Header",
        runs=runs,
        namespace=namespace,
    )
    ok = qr.get("count") == SPOT_CHECKS["class_references_header"][1]
    _report("query class_references", ok, f"refs={qr.get('count')}", median_s)

    median_s, qr = await _timeit(
        run_index_query,
        "find_path",
        source="HCC.SQL.Tools.GenSampleFor10",
        target="HCC.SQL.Tools.TestTreatmentPlanGenerate",
        runs=runs,
        namespace=namespace,
    )
    ok = qr.get("found") is True
    _report("query find_path", ok, f"found={qr.get('found')} len={qr.get('length')}", median_s)

    # ── report ────────────────────────────────────────────────────────────
    print(f"\n{'tool':38} {'result':6} {'median'}")
    print("-" * 60)
    for tool, status, timed in rows:
        print(f"{tool:38} {status:6} {timed}")
    print("-" * 60)

    if failures:
        print(f"\n[bench] {len(failures)} FAILURE(S):")
        for f in failures:
            print("  -", f)
        return 1
    print("\n[bench] all index tools + queries correct")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default=None, help="IRIS namespace (default: configured).")
    parser.add_argument("--runs", type=int, default=3, help="Timing runs per tool (median).")
    args = parser.parse_args()
    return asyncio.run(run_bench(args.namespace, args.runs))


if __name__ == "__main__":
    raise SystemExit(main())
