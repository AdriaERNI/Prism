"""Unit tests for the five named index queries (index_queries facade).

Covers the pure query handlers in ``prism.iris.api.index`` — correct result
shapes and edge cases, with the call-graph maps supplied directly (no live
IRIS, no HTTP). The async ``run_index_query`` dispatcher is exercised with a
mocked ``get_index``.

Queries under test:

* ``callers_of_method``      — direct callers (r_call_edges)
* ``callers_high_fanin``     — methods ranked by reverse-degree
* ``method_calls_outbound``  — outbound callee edges (call_edges)
* ``class_references``       — who references a class in bodies (r_code_refs)
* ``find_path``              — shortest method-to-method path
"""

from unittest.mock import AsyncMock, patch

from prism.iris.api.index import (
    query_callers_high_fanin,
    query_callers_of_method,
    query_class_references,
    query_find_path,
    query_method_calls_outbound,
)

# A small synthetic index carrying Tier-2 call-graph maps under ``call_graph``,
# mirroring the shape produced by ``build_index(include_call_graph=True)``.
# The handlers take ``(index, **kw)``; every param is passed by keyword.
SAMPLE_INDEX = {
    "classes": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
    "edges": {"B": ["C"]},
    "r_edges": {"C": ["B"]},
    "call_graph": {
        "call_edges": {
            "A.go": [{"to": "B.run", "pattern": 1}, {"to": "C.stop", "pattern": 2}],
            "B.run": [{"to": "C.stop", "pattern": 5}],
        },
        "r_call_edges": {
            "B.run": ["A.go", "A.go", "B.run"],
            "C.stop": ["A.go"],
        },
        "r_code_refs": {
            "C": ["A", "B"],
        },
    },
}


class TestCallersOfMethod:
    def test_direct_callers_deduplicated_and_sorted(self):
        out = query_callers_of_method(SAMPLE_INDEX, method="B.run")
        assert out["query"] == "callers_of_method"
        assert out["method"] == "B.run"
        # A.go appears twice in the map but must be deduplicated.
        assert out["callers"] == ["A.go", "B.run"]
        assert out["total"] == 2

    def test_missing_method_empty(self):
        out = query_callers_of_method(SAMPLE_INDEX, method="Nope.m")
        assert out["callers"] == []
        assert out["total"] == 0

    def test_limit_truncates(self):
        out = query_callers_of_method(SAMPLE_INDEX, method="B.run", limit=1)
        assert out["callers"] == ["A.go"]
        assert out["total"] == 2

    def test_top_level_fallback(self):
        """The map is read from top-level keys when no ``call_graph`` section."""
        flat = {"r_call_edges": {"X.m": ["Y.m"]}}
        out = query_callers_of_method(flat, method="X.m")
        assert out["callers"] == ["Y.m"]


class TestCallersHighFanin:
    def test_ranked_descending_total_callers(self):
        out = query_callers_high_fanin(SAMPLE_INDEX, top_n=10)
        assert out["query"] == "callers_high_fanin"
        # B.run has 2 distinct callers -> ranks first.
        assert out["results"][0] == {"method": "B.run", "callers": 2}
        assert out["results"][1] == {"method": "C.stop", "callers": 1}

    def test_top_n_caps_results(self):
        out = query_callers_high_fanin(SAMPLE_INDEX, top_n=1)
        assert len(out["results"]) == 1
        assert out["top_n"] == 1

    def test_empty_maps(self):
        out = query_callers_high_fanin({}, top_n=5)
        assert out["results"] == []
        out = query_callers_high_fanin({"call_graph": {}}, top_n=5)
        assert out["results"] == []

    def test_bad_top_n_clamped(self):
        out = query_callers_high_fanin(SAMPLE_INDEX, top_n=0)
        assert out["top_n"] == 1


class TestMethodCallsOutbound:
    def test_callees_with_patterns(self):
        out = query_method_calls_outbound(SAMPLE_INDEX, method="A.go")
        assert out["query"] == "method_calls_outbound"
        assert out["total"] == 2
        # Sorted by callee name.
        assert out["callees"] == [
            {"to": "B.run", "pattern": 1},
            {"to": "C.stop", "pattern": 2},
        ]

    def test_missing_method_empty(self):
        out = query_method_calls_outbound(SAMPLE_INDEX, method="Nope.m")
        assert out["callees"] == []
        assert out["total"] == 0

    def test_limit_truncates(self):
        out = query_method_calls_outbound(SAMPLE_INDEX, method="A.go", limit=1)
        assert out["callees"] == [{"to": "B.run", "pattern": 1}]
        assert out["total"] == 2


class TestClassReferences:
    def test_referencing_classes_sorted(self):
        out = query_class_references(SAMPLE_INDEX, class_name="C")
        assert out["query"] == "class_references"
        assert out["class_name"] == "C"
        assert out["referenced_by"] == ["A", "B"]
        assert out["count"] == 2

    def test_missing_class_empty(self):
        out = query_class_references(SAMPLE_INDEX, class_name="Z")
        assert out["referenced_by"] == []
        assert out["count"] == 0


class TestFindPath:
    def test_found_path(self):
        out = query_find_path(SAMPLE_INDEX, source="A.go", target="C.stop")
        assert out["query"] == "find_path"
        assert out["source"] == "A.go"
        assert out["target"] == "C.stop"
        assert out["found"] is True
        assert out["path"] == ["A.go", "C.stop"]
        assert out["length"] == 1

    def test_not_found(self):
        out = query_find_path(SAMPLE_INDEX, source="A.go", target="No.Node")
        assert out["found"] is False
        assert out["path"] == []
        assert out["length"] == -1


class TestRunIndexQueryDispatcher:
    """Async dispatch via ``run_index_query`` with a mocked index."""

    def _index(self, **kw) -> dict:
        idx = {
            "cached": False,
            "classes": [{"name": "A"}],
            "call_graph": SAMPLE_INDEX["call_graph"],
        }
        idx.update(kw)
        return idx

    async def test_unknown_query_returns_error(self):
        from prism.iris.api.index import run_index_query

        with patch(
            "prism.iris.api.index.get_index",
            new=AsyncMock(return_value=self._index()),
        ):
            out = await run_index_query("nope")
        assert "error" in out
        assert "callers_of_method" in out["error"]

    async def test_callers_of_method_requires_method(self):
        from prism.iris.api.index import run_index_query

        with patch(
            "prism.iris.api.index.get_index",
            new=AsyncMock(return_value=self._index()),
        ):
            out = await run_index_query("callers_of_method")
        assert "error" in out
        assert "method" in out["error"]

    async def test_find_path_requires_endpoints(self):
        from prism.iris.api.index import run_index_query

        with patch(
            "prism.iris.api.index.get_index",
            new=AsyncMock(return_value=self._index()),
        ):
            out = await run_index_query("find_path", source="A.go")
        assert "error" in out
        assert "find_path requires" in out["error"]

    async def test_dispatcher_forwards_and_adds_cached(self):
        from prism.iris.api.index import run_index_query

        idx = self._index(cached=True)
        with patch(
            "prism.iris.api.index.get_index",
            new=AsyncMock(return_value=idx),
        ) as gi:
            out = await run_index_query("callers_of_method", method="B.run")
        gi.assert_awaited_once()
        assert out["cached"] is True
        assert out["total"] == 2
