"""Unit tests for the index API: search, node, refs, impact, path, status.

Mock-based (httpx.MockTransport) — no live IRIS needed. Follows the
``tests/unit/test_index.py`` conventions for the handler/rows pattern.
"""

from unittest.mock import patch

import httpx

from prism.iris.api import index as index_api


def mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _rows_response(request, rows):
    return httpx.Response(
        200,
        json={
            "status": {"errors": [], "summary": ""},
            "console": [],
            "result": {"content": rows},
        },
    )


def _sample_index():
    """A representative index dict with structure + call-graph maps."""
    return {
        "namespace": "USER",
        "classes": [
            {
                "name": "A",
                "super": "%Persistent",
                "class_type": "",
                "sql_table": "",
                "desc": "Class A",
                "methods": {"go": "%Status", "run": "%String"},
                "properties": {"b": "B"},
            },
            {
                "name": "B",
                "super": "",
                "class_type": "",
                "sql_table": "",
                "desc": "",
                "methods": {"run": "%Status"},
                "properties": {},
            },
            {
                "name": "C",
                "super": "B",
                "class_type": "",
                "sql_table": "",
                "desc": "",
                "methods": {"x": "%Integer"},
                "properties": {},
            },
        ],
        "r_edges": {"B": ["A", "C"], "A": ["B"]},
        "edges": {"A": ["B"], "C": ["B"]},
        "degree": {"A": 2, "B": 2, "C": 1},
        "call_graph": {
            "call_edges": {
                "A.go": [{"to": "B.run", "pattern": 1}],
                "B.run": [{"to": "C.x", "pattern": 1}],
            },
            "r_call_edges": {
                "B.run": ["A.go"],
                "C.x": ["B.run"],
            },
            "code_refs": {"A": ["SomeClass"], "B": ["Library.X"]},
            "r_code_refs": {"SomeClass": ["A"], "Library.X": ["B"]},
        },
    }


class TestSearchSymbols:
    """search_symbols — server-side %Dictionary SQL search."""

    async def test_search_class_kind(self):
        rows = [
            {"kind": "class", "symbol": "MyApp.Model", "owner": "", "detail": "", "rnk": 0},
            {"kind": "class", "symbol": "MyApp.ModelView", "owner": "", "detail": "", "rnk": 0},
        ]
        calls = []

        def handler(request):
            calls.append(request)
            return _rows_response(request, rows)

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.search_symbols("MyApp", kind="class", limit=10)

        assert result["count"] == 2
        assert result["results"][0]["symbol"] == "MyApp.Model"
        # The class-kind query must hit ClassDefinition
        assert "ClassDefinition" in calls[0].content.decode()
        # No MethodDefinition for kind=class
        assert "MethodDefinition" not in calls[0].content.decode()

    async def test_search_all_kinds_runs_four(self):
        rows = [{"kind": "method", "symbol": "GetX", "owner": "A", "detail": "", "rnk": 1}]
        calls = []

        def handler(request):
            calls.append(request)
            return _rows_response(request, rows)

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.search_symbols("GetX", limit=5)

        assert result["count"] == 1
        assert result["results"][0]["kind"] == "method"
        assert len(calls) == 4  # class, method, property, table

    async def test_search_rejects_injection(self):
        with patch.object(index_api, "client") as m:
            result = await index_api.search_symbols("'; DROP TABLE x; --")
        assert result["error"]
        assert result["count"] == 0
        m.assert_not_called()

    async def test_search_bad_kind(self):
        with patch.object(index_api, "client") as m:
            result = await index_api.search_symbols("GetX", kind="bogus")
        assert result["error"]
        assert result["count"] == 0
        m.assert_not_called()

    async def test_search_limit_clamped(self):
        rows = [{"kind": "class", "symbol": "A", "owner": "", "detail": "", "rnk": 0}]
        calls = []

        def handler(request):
            calls.append(request)
            return _rows_response(request, rows)

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            await index_api.search_symbols("A", limit=9999)
        # clamped to 200 in the TOP clause
        assert "TOP 200" in calls[0].content.decode()


class TestClassNode:
    """class_node — full picture of one class from an index dict."""

    def test_assembles_full_picture(self):
        node = index_api.class_node(_sample_index(), "A")
        assert node["name"] == "A"
        assert node["super"] == "%Persistent"
        assert node["supers"] == ["%Persistent"]
        assert node["properties"] == {"b": "B"}
        assert node["methods"]["go"]["return_type"] == "%Status"
        assert node["children"] == ["B"]  # via r_edges
        # callers of A.go -> B.run? no: A.go CALLS B.run, so A has no callers
        assert node["callers"] == {}
        # callees: A.go -> B.run
        assert node["callees"] == {"go": ["B.run"]}
        assert node["degree"] == 2
        assert node["out_degree"] == 1

    def test_node_with_callers(self):
        node = index_api.class_node(_sample_index(), "B")
        # B.run is called by A.go
        assert node["callers"] == {"run": ["A.go"]}
        # B.run calls C.x
        assert node["callees"] == {"run": ["C.x"]}

    def test_node_missing_class(self):
        node = index_api.class_node(_sample_index(), "Nope")
        assert "error" in node


class TestClassRefs:
    """class_refs — who references a class in body text."""

    def test_referenced(self):
        out = index_api.class_refs(_sample_index(), "SomeClass")
        assert out["found"] is True
        assert out["count"] == 1
        assert out["referenced_by"] == ["A"]

    def test_unreferenced(self):
        out = index_api.class_refs(_sample_index(), "A")
        assert out["count"] == 0
        assert out["referenced_by"] == []
        assert out["found"] is True  # class exists in the index


class TestMethodImpact:
    """method_impact — transitive blast radius over r_call_edges + r_edges."""

    def _index(self):
        idx = _sample_index()
        # r_call_edges: B.run is CALLED BY A.go, C.x is CALLED BY B.run
        # Starting from C.x, dependents are B.run -> A.go (reverse call chain).
        return idx

    def test_chain(self):
        out = index_api.method_impact(self._index(), "C.x")
        assert out["start"] == "C.x"
        # B.run calls C.x, A.go calls B.run — both are dependents
        assert "B.run" in out["hops"]
        assert "A.go" in out["hops"]
        assert out["count"] >= 2

    def test_class_start(self):
        out = index_api.method_impact(self._index(), "A")
        assert out["start"] == "A"

    def test_max_hops(self):
        out = index_api.method_impact(self._index(), "C.x", max_hops=1)
        # 1 hop: B.run only, A.go is 2 hops away
        hops = out["hops"]
        assert hops.get("B.run") == 1
        assert hops.get("A.go", 99) > 1 or "A.go" not in hops


class TestMethodPath:
    """method_path — shortest BFS path over the merged call graph."""

    def test_found_path(self):
        out = index_api.method_path(_sample_index(), "A.go", "C.x")
        assert out["found"] is True
        assert out["path"] == ["A.go", "B.run", "C.x"]
        assert out["length"] == 2
        assert out["hops"] == "A.go -> B.run -> C.x"

    def test_not_found(self):
        out = index_api.method_path(_sample_index(), "A.go", "Z.m")
        assert out["found"] is False
        assert out["length"] == -1


class TestGetIndexCache:
    """get_index — TimeChanged fingerprint + SQLite cache."""

    async def test_cached_hit(self, tmp_path):
        idx = _sample_index()
        with (
            patch.object(
                index_api, "client", lambda *a, **kw: mock_client(lambda r: _rows_response(r, []))
            ),
            patch(
                "prism.iris.indexing.cache._db_path",
                lambda: tmp_path / "idx.db",
            ),
            patch.object(index_api, "build_index", return_value=idx) as mock_build,
        ):
            first = await index_api.get_index(filter_prefix="A")
            second = await index_api.get_index(filter_prefix="A")

        assert first["cached"] is False
        assert second["cached"] is True
        assert mock_build.call_count == 1  # built once, second served from cache

    async def test_fingerprint_changes_rebuilds(self, tmp_path):
        idx = _sample_index()
        fingerprint_rows_a = [{"Name": "A", "TimeChanged": "1,100"}]
        fingerprint_rows_b = [{"Name": "A", "TimeChanged": "2,200"}]
        state = {"fp": 0}

        def handler(request):
            body = request.content.decode()
            if "TimeChanged" in body:
                rows = fingerprint_rows_a if state["fp"] == 0 else fingerprint_rows_b
                state["fp"] += 1
                return _rows_response(request, rows)
            return _rows_response(request, [])

        with (
            patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
            patch("prism.iris.indexing.cache._db_path", lambda: tmp_path / "idx.db"),
            patch.object(index_api, "build_index", return_value=idx) as mock_build,
        ):
            await index_api.get_index(filter_prefix="A")
            await index_api.get_index(filter_prefix="A")

        assert mock_build.call_count == 2  # fingerprint changed -> rebuilt

    async def test_index_target_key(self):
        assert index_api._index_target() == "all"
        assert index_api._index_target(include_system=True) == "all:system"
        assert index_api._index_target(filter_prefix="MyApp") == "prefix:MyApp"
        assert index_api._index_target(True, "MyApp") == "prefix:MyApp:system"
        # include_call_graph must disambiguate the cache key so a fast (no-callgraph)
        # build cannot serve a Tier-2 query (or vice versa) — they are different
        # payloads and must not collide in the persisted cache.
        assert index_api._index_target(include_call_graph=True) == "all:callgraph"
        assert index_api._index_target(True, "MyApp", True) == "prefix:MyApp:system:callgraph"
        assert index_api._index_target(include_call_graph=True) != index_api._index_target()


class TestIndexStatusAPI:
    """index_status — fingerprint-driven freshness reporting."""

    async def test_status_reports_freshness(self, tmp_path):
        rows = [{"Name": "A", "TimeChanged": "1,100"}]

        def handler(request):
            return _rows_response(request, rows)

        with (
            patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
            patch(
                "prism.iris.indexing.cache._db_path",
                lambda: tmp_path / "idx.db",
            ),
        ):
            # empty cache -> not cached
            status = await index_api.index_status(filter_prefix="A")
            assert status["classes"] == 1
            assert status["fresh"] is False
            assert status["cached"] is False

    async def test_status_sees_cached_entry(self, tmp_path):
        from prism.iris.indexing import cache as cache_mod

        rows = [{"Name": "A", "TimeChanged": "1,100"}]

        def handler(request):
            return _rows_response(request, rows)

        with (
            patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
            patch.object(cache_mod, "_db_path", lambda: tmp_path / "idx.db"),
        ):
            # seed the cache with the matching fingerprint
            cache_mod.cache_put("USER", "prefix:A", index_api._fingerprint(rows), _sample_index())
            status = await index_api.index_status(filter_prefix="A")
            assert status["cached"] is True
            assert status["fresh"] is True
            assert "age_seconds" in status
