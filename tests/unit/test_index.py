"""Unit tests for the index API and MCP tool.

Uses httpx.MockTransport to simulate IRIS Atelier API responses.
No live IRIS needed.
"""

from unittest.mock import patch

import httpx

from prism.iris.api import index as index_api


def mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestBuildIndex:
    """Tests for build_index() with mocked HTTP."""

    async def test_build_index_returns_structure(self):
        """build_index returns namespace, statistics, classes, dependencies."""
        classes_data = [
            {
                "Name": "MyApp.Model",
                "Super": "%Persistent",
                "ClassType": "",
                "SqlTableName": "MyApp_Model",
                "Description": "A model class.",
            },
            {
                "Name": "MyApp.Util",
                "Super": "%RegisteredObject",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
        ]
        methods_data = [
            {"parent": "MyApp.Model", "Name": "Save", "ReturnType": "%Status"},
            {"parent": "MyApp.Util", "Name": "Helper", "ReturnType": "%String"},
        ]
        props_data = [
            {"parent": "MyApp.Model", "Name": "Name", "Type": "%String"},
            {"parent": "MyApp.Model", "Name": "Age", "Type": "%Integer"},
        ]
        params_data = [
            {"parent": "MyApp.Model", "Name": "MAXVAL", "Default": "100"},
        ]
        sqlprocs_data = [
            {"parent": "MyApp.Model", "Name": "Save"},
        ]
        imports_data = [
            {"parent": "MyApp.Model", "Name": "MyApp.Utils"},
        ]

        call_count = 0

        def handler(request):
            nonlocal call_count
            call_count += 1
            # Return different data based on call order
            datasets = [
                classes_data,
                methods_data,
                props_data,
                params_data,
                sqlprocs_data,
                imports_data,
            ]
            data = datasets[min(call_count - 1, len(datasets) - 1)]
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": data},
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.build_index()

        assert result["namespace"] == "USER"
        assert result["statistics"]["classes"] == 2
        assert result["statistics"]["persistent"] == 1
        assert result["statistics"]["methods"] == 2
        assert result["statistics"]["properties"] == 2
        assert result["statistics"]["sql_procedures"] == 1
        assert result["statistics"]["imports"] == 1

        # Check class entries
        names = [c["name"] for c in result["classes"]]
        assert "MyApp.Model" in names
        assert "MyApp.Util" in names

        # Check compact representation
        model = next(c for c in result["classes"] if c["name"] == "MyApp.Model")
        assert model["super"] == "%Persistent"
        assert model["sql_table"] == "MyApp_Model"
        assert model["properties"] == {"Name": "%String", "Age": "%Integer"}
        assert model["methods"] == {"Save": "%Status"}
        assert model["parameters"] == {"MAXVAL": "100"}
        assert model["sql_procs"] == ["Save"]
        assert model["imports"] == ["MyApp.Utils"]

        # Check dependencies
        assert result["dependencies"]["MyApp.Model"] == "%Persistent"
        assert result["dependencies"]["MyApp.Util"] == "%RegisteredObject"

    async def test_build_index_with_prefix(self):
        """build_index with filter_prefix only returns matching classes."""

        def handler(request):
            # Only return classes matching the prefix
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {
                        "content": [
                            {
                                "Name": "MyApp.Foo",
                                "Super": "",
                                "ClassType": "",
                                "SqlTableName": "",
                                "Description": "",
                            }
                        ]
                    },
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.build_index(filter_prefix="MyApp")

        assert result["statistics"]["classes"] == 1
        assert result["classes"][0]["name"] == "MyApp.Foo"

    async def test_build_index_empty_namespace(self):
        """build_index with no classes returns empty structure."""
        empty = []

        def handler(request):
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": empty},
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.build_index()

        assert result["statistics"]["classes"] == 0
        assert result["classes"] == []
        assert result["dependencies"] == {}

    async def test_build_index_description_truncation(self):
        """Description is truncated to first sentence, max 200 chars."""

        def handler(request):
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {
                        "content": [
                            {
                                "Name": "MyApp.Foo",
                                "Super": "",
                                "ClassType": "",
                                "SqlTableName": "",
                                "Description": "This is a long description. It has multiple sentences. Only the first should appear.",
                            }
                        ]
                    },
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.build_index()

        desc = result["classes"][0].get("desc", "")
        assert "It has multiple sentences" not in desc
        assert "This is a long description" in desc


class TestIndexSummary:
    """Tests for index_summary() with mocked HTTP."""

    async def test_summary_returns_counts(self):
        def handler(request):
            # Return different counts based on the query
            body = request.content.decode()
            if "ClassDefinition" in body:
                content = [{"cnt": 42}]
            elif "SqlProc" in body:
                content = [{"cnt": 5}]
            elif "MethodDefinition" in body:
                content = [{"cnt": 100}]
            elif "PropertyDefinition" in body:
                content = [{"cnt": 50}]
            else:
                content = [{"cnt": 0}]
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": content},
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.index_summary()

        assert result["namespace"] == "USER"
        assert result["classes"] == 42
        assert result["methods"] == 100
        assert result["properties"] == 50
        assert result["sql_procedures"] == 5

    async def test_summary_empty_namespace(self):
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": [{"cnt": 0}]},
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.index_summary()

        assert result["classes"] == 0
        assert result["methods"] == 0
        assert result["properties"] == 0
        assert result["sql_procedures"] == 0


class TestExclusionFilter:
    """Correctness of the system-class exclusion predicate (Part 1 of feedback)."""

    def test_system_exclude_anchors_percent(self):
        """The %-exclusion must be anchored with %STARTSWITH, not LIKE '\\%'."""
        pred = index_api._system_exclude("Name")
        assert "%STARTSWITH" in pred
        assert "NOT LIKE" not in pred
        # The % prefix and SYS./Api. prefixes must all be present, wrapped in
        # NOT (...).  IRIS returns an EMPTY result set for the bare
        # "col NOT %STARTSWITH X" prefix form, so the whole expression must be
        # negated in parentheses.
        assert "NOT (Name %STARTSWITH '%')" in pred
        assert "NOT (Name %STARTSWITH 'SYS.')" in pred
        assert "NOT (Name %STARTSWITH 'Api.')" in pred
        # guard against regressing to the broken prefix form
        assert "Name NOT %STARTSWITH" not in pred

    def test_system_exclude_covers_non_percent_system_packages(self):
        """IRIS ships non-% system packages (Ensemble, CSP dashboard, SQL
        schemas) that must be excluded too — they are not user code."""
        pred = index_api._system_exclude("Name")
        for pkg in (
            "Ens.",
            "EnsLib.",
            "EnsPortal.",
            "Ensemble.",
            "CSPX.",
            "INFORMATION.",
        ):
            assert f"NOT (Name %STARTSWITH '{pkg}')" in pred, pkg
        # all negated forms, not the broken prefix form
        assert "Name NOT %STARTSWITH 'Ens'" not in pred

    def test_system_exclude_covers_library_and_backslash_breakage(self):
        """The old '\\%' row (which matched nothing) is gone; %Library is covered
        by the % prefix rule."""
        pred = index_api._system_exclude("Name")
        # No single backslash that the buggy filter used
        assert "\\%" not in pred
        # %Library.* is excluded because it starts with '%' (the first rule)
        assert "%Library" not in pred  # not needed as a separate clause

    def test_class_filter_include_system_true_leaves_empty(self):
        assert index_api._class_filter(include_system=True, filter_prefix=None) == ""

    def test_class_filter_combines_exclude_and_prefix(self):
        where = index_api._class_filter(include_system=False, filter_prefix="MyApp")
        assert "%STARTSWITH" in where
        assert "%STARTSWITH 'MyApp'" in where
        assert where.startswith("WHERE ")

    def test_class_filter_prefix_only(self):
        where = index_api._class_filter(include_system=True, filter_prefix="App")
        assert where == "WHERE Name %STARTSWITH 'App'"


class TestGraphMaps:
    """Tier 0: forward/reverse edge maps, degree map, BFS reachability."""

    def _class_map(self):
        cm = {}
        a = index_api.ClassInfo(name="A", super="%Persistent")
        a.properties.append({"name": "b", "type": "B"})
        b = index_api.ClassInfo(name="B", super="C")
        c = index_api.ClassInfo(name="C", super="")
        d = index_api.ClassInfo(name="D", super="C")
        cm["A"] = a
        cm["B"] = b
        cm["C"] = c
        cm["D"] = d
        return cm

    def test_edge_maps_superclass_and_property(self):
        cm = self._class_map()
        edges, r_edges, degree = index_api._edge_maps(cm)
        # A -> B via property type AND superclass chain: A super is %Persistent (skipped, system)
        assert "B" in edges["A"]  # property type
        assert "%Persistent" not in edges.get("A", [])  # system super excluded
        # B -> C via superclass
        assert "C" in edges["B"]
        assert "D" not in edges.get("A", [])  # D is independent, no edge from A
        # A -> C? no direct
        # Reverse
        assert "A" in r_edges["B"]
        assert "B" in r_edges["C"]
        assert "D" in r_edges["C"]
        # Degree
        assert degree["C"] == 2  # B and D point here
        assert degree["B"] == 2  # A->B and B->C

    def test_reachable_bfs(self):
        edges = {
            "A": ["B"],
            "B": ["C"],
            "C": [],
        }
        out = index_api.reachable(edges, "A", max_hops=2)
        assert out == {"A": 0, "B": 1, "C": 2}
        out1 = index_api.reachable(edges, "A", max_hops=1)
        assert "C" not in out1
        assert index_api.reachable(edges, "B", max_hops=5) == {"B": 0, "C": 1}

    def test_recursive_inheritance_tree(self):
        # 14k-result case modelled small: a chain
        edges = {f"N{i}": ([f"N{i + 1}"] if i < 99 else []) for i in range(100)}
        out = index_api.reachable(edges, "N0", max_hops=1000)
        assert len(out) == 100

    async def test_build_index_includes_graph_maps(self):
        """build_index returns edges/r_edges/degree alongside dependencies."""
        classes_data = [
            {
                "Name": "MyApp.Base",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
            {
                "Name": "MyApp.Child",
                "Super": "MyApp.Base",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
        ]
        methods_data = [
            {
                "parent": "MyApp.Child",
                "Name": "Run",
                "ReturnType": "%String",
                "FormalSpec": "p As MyApp.Base",
            }
        ]
        datasets = [classes_data, methods_data, [], [], [], []]
        call = 0

        def handler(request):
            nonlocal call
            idx = min(call, len(datasets) - 1)
            call += 1
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": datasets[idx]},
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.build_index()

        assert "edges" in result
        assert "r_edges" in result
        assert "degree" in result
        # Child super = MyApp.Base, and method sig references MyApp.Base (same edge, deduped)
        assert result["edges"]["MyApp.Child"] == ["MyApp.Base"]
        assert result["r_edges"]["MyApp.Base"] == ["MyApp.Child"]
        # Both classes are in the index; only Child has out-edges
        assert result["degree"]["MyApp.Child"] > 0


class TestSignatureTypes:
    """Tier 1: FormalSpec -> non-system type extraction."""

    def test_extract_signature_types(self):
        fs = "pArg1 As %String, pArg2 As MyApp.Model, pArg3 As Other.Thing = 5, pArg4 As %Integer"
        types = index_api._extract_signature_types(fs)
        assert "MyApp.Model" in types
        assert "Other.Thing" in types
        assert "%String" not in types
        assert "%Integer" not in types

    def test_extract_signature_types_empty(self):
        assert index_api._extract_signature_types("") == []
        assert index_api._extract_signature_types("p As %Library.ListOfObjects") == []

    async def test_build_index_signature_edges(self):
        """Signature types become edges in the graph maps."""
        classes_data = [
            {
                "Name": "MyApp.Service",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
            {
                "Name": "MyApp.Repo",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
        ]
        methods_data = [
            {
                "parent": "MyApp.Service",
                "Name": "Load",
                "ReturnType": "%Status",
                "FormalSpec": "r As MyApp.Repo",
            },
        ]
        datasets = [classes_data, methods_data, [], [], [], []]
        call = 0

        def handler(request):
            nonlocal call
            idx = min(call, len(datasets) - 1)
            call += 1
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": datasets[idx]},
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await index_api.build_index()

        assert result["edges"]["MyApp.Service"] == ["MyApp.Repo"]


class TestIndexMCPTool:
    """Tests for the index_code MCP tool registration."""

    async def test_index_code_registered(self):
        """index_code tool is registered in the MCP server."""
        from fastmcp import Client

        from prism.mcp.server import create_mcp

        mcp = create_mcp()
        client = Client(mcp)
        async with client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert "index_code" in names

    async def test_index_reachability_registered(self):
        """index_reachability tool is registered in the MCP server."""
        from fastmcp import Client

        from prism.mcp.server import create_mcp

        mcp = create_mcp()
        client = Client(mcp)
        async with client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert "index_reachability" in names

    async def test_index_reachability_calls_build_and_walks(self):
        """index_reachability builds the index and returns reachable classes."""
        import json

        from fastmcp import Client

        from prism.mcp.server import create_mcp

        classes_data = [
            {
                "Name": "MyApp.Base",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
            {
                "Name": "MyApp.Child",
                "Super": "MyApp.Base",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
        ]
        datasets = [classes_data, [], [], [], [], []]
        call = 0

        def handler(request):
            nonlocal call
            idx = min(call, len(datasets) - 1)
            call += 1
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": datasets[idx]},
                },
            )

        mcp = create_mcp()
        client = Client(mcp)
        async with client:
            with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
                result = await client.call_tool(
                    "index_reachability",
                    {"class_name": "MyApp.Base", "max_hops": 3},
                )
                data = json.loads(result.content[0].text)
                assert data["start"] == "MyApp.Base"
                reachable_list = data["reachable"]
                # MyApp.Base reaches MyApp.Child (1 hop, reverse via superclass)
                names = [r[0] for r in reachable_list]
                assert "MyApp.Child" in names

    async def test_index_code_in_instructions(self):
        """index_code is mentioned in the server instructions sent to clients."""
        from prism.mcp.server import create_mcp

        mcp = create_mcp()
        instructions = mcp.instructions or ""
        assert "index_code" in instructions

    async def test_index_code_summary_only(self):
        """index_code with summary_only=True calls index_summary."""
        from fastmcp import Client

        from prism.mcp.server import create_mcp

        def handler(request):
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": [{"cnt": 5}]},
                },
            )

        mcp = create_mcp()
        client = Client(mcp)
        async with client:
            with patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)):
                result = await client.call_tool("index_code", {"summary_only": True})
                import json

                data = json.loads(result.content[0].text)
                assert "classes" in data
                assert "methods" in data
                assert "properties" in data


class TestCallGraphFlag:
    """include_call_graph=True adds call-graph maps to the index."""

    @staticmethod
    def _make_handler(classes_data, methods_data, bodies):
        """Return a router handler serving SQL (index_api.client) and
        document bodies (documents.client) from the same transport."""
        sql_datasets = [classes_data, methods_data, [], [], [], []]
        sql_call = 0

        def handler(request):
            nonlocal sql_call
            if "/doc/" in request.url.path:
                name = request.url.path.rstrip("/").split("/")[-1]
                body = bodies.get(name, "")
                return httpx.Response(200, json={"result": {"content": body.splitlines()}})
            idx = min(sql_call, len(sql_datasets) - 1)
            sql_call += 1
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "result": {"content": sql_datasets[idx]},
                },
            )

        return handler

    async def test_build_index_call_graph_flag(self):
        """build_index(include_call_graph=True) fetches bodies and adds call_graph."""
        from prism.iris.api import documents

        classes_data = [
            {
                "Name": "MyApp.Service",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
            {
                "Name": "MyApp.Repo",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
        ]
        methods_data = [
            {"parent": "MyApp.Service", "Name": "Go", "ReturnType": "%Status", "FormalSpec": ""},
            {"parent": "MyApp.Repo", "Name": "Run", "ReturnType": "%Status", "FormalSpec": ""},
        ]
        bodies = {
            "MyApp.Service.cls": (
                "Class MyApp.Service Extends %RegisteredObject {\n"
                "Method Go() {\n  Do ##class(MyApp.Repo).Run()\n}\n"
                "}\n"
            ),
            "MyApp.Repo.cls": (
                "Class MyApp.Repo Extends %RegisteredObject {\nMethod Run() {\n  Quit $$$OK\n}\n}\n"
            ),
        }
        handler = self._make_handler(classes_data, methods_data, bodies)

        with (
            patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
            patch.object(documents, "client", lambda *a, **kw: mock_client(handler)),
        ):
            result = await index_api.build_index(include_call_graph=True)
            # default (no flag) should not call documents.client at all
            result_fast = await index_api.build_index()

        cg = result["call_graph"]
        assert "call_edges" in cg
        assert "r_call_edges" in cg
        assert "code_refs" in cg
        assert "stats" in cg
        # MyApp.Service.Go calls MyApp.Repo.Run via pattern 1
        edges = cg["call_edges"]
        service_edges = edges.get("MyApp.Service.Go", [])
        assert any(e["to"] == "MyApp.Repo.Run" and e["pattern"] == 1 for e in service_edges)
        # reverse: who calls MyApp.Repo.Run
        assert "MyApp.Service.Go" in cg["r_call_edges"].get("MyApp.Repo.Run", [])
        # code reference edge
        assert "MyApp.Repo" in cg["code_refs"].get("MyApp.Service", [])
        # fast path has no call graph
        assert "call_graph" not in result_fast

    async def test_index_code_mcp_tool_call_graph_param(self):
        """index_code accepts include_call_graph and returns call-graph maps."""
        import json

        from fastmcp import Client

        from prism.iris.api import documents
        from prism.mcp.server import create_mcp

        classes_data = [
            {
                "Name": "MyApp.Service",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
            {
                "Name": "MyApp.Repo",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
        ]
        methods_data = [
            {"parent": "MyApp.Service", "Name": "Go", "ReturnType": "%Status", "FormalSpec": ""},
            {"parent": "MyApp.Repo", "Name": "Run", "ReturnType": "%Status", "FormalSpec": ""},
        ]
        bodies = {
            "MyApp.Service.cls": (
                "Class MyApp.Service Extends %RegisteredObject {\n"
                "Method Go() {\n  Do ##class(MyApp.Repo).Run()\n}\n"
                "}\n"
            ),
            "MyApp.Repo.cls": (
                "Class MyApp.Repo Extends %RegisteredObject {\nMethod Run() {\n  Quit $$$OK\n}\n}\n"
            ),
        }
        handler = self._make_handler(classes_data, methods_data, bodies)

        mcp = create_mcp()
        client = Client(mcp)
        async with client:
            with (
                patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
                patch.object(documents, "client", lambda *a, **kw: mock_client(handler)),
            ):
                result = await client.call_tool("index_code", {"include_call_graph": True})
                data = json.loads(result.content[0].text)
                assert "call_graph" in data
                cg = data["call_graph"]
                assert "call_edges" in cg
                edges = cg["call_edges"]
                assert any(
                    e["to"] == "MyApp.Repo.Run" and e["pattern"] == 1
                    for e in edges.get("MyApp.Service.Go", [])
                )


class TestIndexCallers:
    """index_callers answers 'who calls method X' (reverse) / 'what it calls' (forward).

    Uses the same mock-handler pattern as TestCallGraphFlag but exercises the
    focused index_callers API + MCP tool.
    """

    @staticmethod
    def _classes_data():
        return [
            {
                "Name": "MyApp.Service",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
            {
                "Name": "MyApp.Repo",
                "Super": "",
                "ClassType": "",
                "SqlTableName": "",
                "Description": "",
            },
        ]

    @staticmethod
    def _methods_data():
        return [
            {"parent": "MyApp.Service", "Name": "Go", "ReturnType": "%Status", "FormalSpec": ""},
            {"parent": "MyApp.Repo", "Name": "Run", "ReturnType": "%Status", "FormalSpec": ""},
        ]

    @staticmethod
    def _bodies():
        return {
            "MyApp.Service.cls": (
                "Class MyApp.Service Extends %RegisteredObject {\n"
                "Method Go() {\n  Do ##class(MyApp.Repo).Run()\n}\n"
                "}\n"
            ),
            "MyApp.Repo.cls": (
                "Class MyApp.Repo Extends %RegisteredObject {\nMethod Run() {\n  Quit $$$OK\n}\n}\n"
            ),
        }

    async def test_index_callers_api_reverse(self):
        """index_callers API returns who calls a method (reverse)."""
        from prism.iris.api import documents

        handler = TestCallGraphFlag._make_handler(
            self._classes_data(), self._methods_data(), self._bodies()
        )
        with (
            patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
            patch.object(documents, "client", lambda *a, **kw: mock_client(handler)),
        ):
            result = await index_api.index_callers("MyApp.Repo.Run")
        assert result["method"] == "MyApp.Repo.Run"
        assert result["direction"] == "reverse"
        assert result["total"] == 1
        assert "MyApp.Service.Go" in result["results"]

    async def test_index_callers_api_forward(self):
        """index_callers API returns what a method calls (forward), with pattern."""
        from prism.iris.api import documents

        handler = TestCallGraphFlag._make_handler(
            self._classes_data(), self._methods_data(), self._bodies()
        )
        with (
            patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
            patch.object(documents, "client", lambda *a, **kw: mock_client(handler)),
        ):
            result = await index_api.index_callers("MyApp.Service.Go", direction="forward")
        assert result["direction"] == "forward"
        assert result["total"] == 1
        assert result["results"][0]["to"] == "MyApp.Repo.Run"
        assert result["results"][0]["pattern"] == 1

    async def test_index_callers_no_callers_returns_empty(self):
        """A method nobody calls returns total 0 with an empty list."""
        from prism.iris.api import documents

        handler = TestCallGraphFlag._make_handler(
            self._classes_data(), self._methods_data(), self._bodies()
        )
        with (
            patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
            patch.object(documents, "client", lambda *a, **kw: mock_client(handler)),
        ):
            result = await index_api.index_callers("MyApp.Repo.Nobody")
        assert result["total"] == 0
        assert result["results"] == []

    async def test_index_callers_registered_as_mcp_tool(self):
        """index_callers is auto-discovered and callable via the MCP client."""
        import json

        from fastmcp import Client

        from prism.iris.api import documents
        from prism.mcp.server import create_mcp

        handler = TestCallGraphFlag._make_handler(
            self._classes_data(), self._methods_data(), self._bodies()
        )
        mcp = create_mcp()
        client = Client(mcp)
        async with client:
            tools = [t.name for t in await client.list_tools()]
            assert "index_callers" in tools
            with (
                patch.object(index_api, "client", lambda *a, **kw: mock_client(handler)),
                patch.object(documents, "client", lambda *a, **kw: mock_client(handler)),
            ):
                result = await client.call_tool(
                    "index_callers",
                    {"method": "MyApp.Repo.Run", "max_results": 5},
                )
                data = json.loads(result.content[0].text)
                assert data["method"] == "MyApp.Repo.Run"
                assert data["total"] == 1
                assert "MyApp.Service.Go" in data["results"]
