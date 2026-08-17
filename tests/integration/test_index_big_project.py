"""Big-project index validation against a large loaded namespace (e.g. hcc).

The full `prism index` surface — every index tool plus the five named
queries — is exercised against whatever large project is loaded in the
namespace, with correctness spot-checks and timing reports.

This is the CI-amenable wrapper over ``scripts/index_big_bench.py``: it runs
the same assertions but as a pytest test, and **skips gracefully** when hcc
is not present (a bare IRIS has no big project, so there is nothing to
validate). The CI workflow (``.github/workflows/index-validation.yml``)
loads hcc via ``scripts/hcc_loader.py`` first, so in CI this test always
runs in earnest.

Markers:
* ``@pytest.mark.bigproject`` — excluded from the fast integration suite;
  run explicitly via ``pytest -m bigproject``.
"""

import asyncio

import pytest

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
from prism.settings import settings

# hcc is a ~2,344-class project; a bare IRIS has far fewer user classes.
_MIN_BIG_PROJECT_CLASSES = 1000

# Spot-check facts verified against a real hcc load in the USER namespace.
SPOT_CHECKS = {
    "callers_of_method": ("HCC.SQL.Tools.TestTreatmentPlanGenerate", 27),
    "class_references_header": ("HCC.SQL.Document.Header", 2),
    "openid_callers": ("HCC.SQL.Document.Header.%OpenId", 2),
}


async def _index_is_big(namespace: str) -> bool:
    """True when the namespace holds a big project (hcc-sized)."""
    s = await index_summary(namespace)
    return isinstance(s.get("classes"), int) and s["classes"] >= _MIN_BIG_PROJECT_CLASSES


pytestmark = pytest.mark.bigproject


@pytest.fixture(scope="module")
def big_index():
    """Return the cached Tier-2 index once hcc is confirmed loaded, else skip."""
    namespace = settings.iris_namespace
    loop = asyncio.new_event_loop()
    try:
        if not loop.run_until_complete(_index_is_big(namespace)):
            pytest.skip("no big project loaded in namespace (expected in bare IRIS)")
        return loop.run_until_complete(get_index(namespace, include_call_graph=True))
    finally:
        loop.close()


def _ns() -> str:
    return settings.iris_namespace


class TestBigProjectIndex:
    """Every index tool + the 5 queries against the loaded big project."""

    async def test_index_summary_shows_big_scope(self):
        s = await index_summary(_ns())
        assert s["classes"] >= _MIN_BIG_PROJECT_CLASSES
        assert s["methods"] > 0

    async def test_index_callgraph_has_edges(self, big_index):
        cg = big_index.get("call_graph", {})
        assert cg.get("stats", {}).get("call_edges", 0) > 0
        assert cg.get("r_call_edges")
        assert cg.get("unresolved") is not None

    async def test_reachability_big(self, big_index):
        edges = big_index.get("edges", {})
        out = reachable(edges, "HCC.SQL.Document.Header", max_hops=2)
        assert "HCC.SQL.Document.Header" in out

    async def test_search_finds_hcc_symbol(self):
        r = await search_symbols("HCC.SQL.Document.Header", kind="class", limit=5, namespace=_ns())
        assert r["count"] >= 1
        assert any(x["symbol"] == "HCC.SQL.Document.Header" for x in r["results"])

    async def test_node_full_picture(self, big_index):
        node = class_node(big_index, "HCC.SQL.Document.Header")
        assert node["name"] == "HCC.SQL.Document.Header"
        assert isinstance(node["methods"], dict)

    async def test_refs_spot_check(self, big_index):
        refs = class_refs(big_index, "HCC.SQL.Document.Header")
        assert refs["count"] == SPOT_CHECKS["class_references_header"][1]

    async def test_impact_has_dependents(self, big_index):
        imp = method_impact(big_index, "HCC.SQL.Tools.TestTreatmentPlanGenerate")
        assert imp["count"] >= 1

    async def test_path_between_real_methods(self, big_index):
        path = method_path(
            big_index,
            "HCC.SQL.Tools.GenSampleFor10",
            "HCC.SQL.Tools.TestTreatmentPlanGenerate",
        )
        assert path["found"] is True
        assert path["length"] >= 1

    async def test_status_reports_big_scope(self):
        st = await index_status(_ns())
        assert st["classes"] >= _MIN_BIG_PROJECT_CLASSES

    # ── the five named queries ────────────────────────────────────────────

    async def test_query_callers_of_method_spot_check(self):
        method, expected = SPOT_CHECKS["callers_of_method"]
        r = await run_index_query("callers_of_method", method=method, namespace=_ns())
        assert r["total"] == expected, r

    async def test_query_callers_high_fanin_ranked(self):
        r = await run_index_query("callers_high_fanin", top_n=10, namespace=_ns())
        assert r["results"]
        counts = [x["callers"] for x in r["results"]]
        assert counts == sorted(counts, reverse=True), "must be ranked descending"

    async def test_query_method_calls_outbound(self):
        r = await run_index_query(
            "method_calls_outbound",
            method="HCC.SQL.Tools.GenSampleFor10",
            namespace=_ns(),
        )
        assert r["total"] >= 1
        assert all("to" in c and "pattern" in c for c in r["callees"])

    async def test_query_class_references_spot_check(self):
        cls, expected = SPOT_CHECKS["class_references_header"]
        r = await run_index_query("class_references", class_name=cls, namespace=_ns())
        assert r["count"] == expected, r

    async def test_query_find_path_spot_check(self):
        r = await run_index_query(
            "find_path",
            source="HCC.SQL.Tools.GenSampleFor10",
            target="HCC.SQL.Tools.TestTreatmentPlanGenerate",
            namespace=_ns(),
        )
        assert r["found"] is True
