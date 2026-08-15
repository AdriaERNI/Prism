"""Integration tests for the index_code MCP tool against live IRIS."""

import json


class TestIndexCodeLive:
    """Tests that call index_code against a live IRIS instance."""

    async def test_index_summary(self, live):
        """index_code with summary_only returns counts."""
        result = await live.call_tool("index_code", {"summary_only": True})
        data = json.loads(result.content[0].text)
        assert "namespace" in data
        assert "classes" in data
        assert "methods" in data
        assert "properties" in data
        assert "sql_procedures" in data
        assert isinstance(data["classes"], int)
        assert isinstance(data["methods"], int)
        assert isinstance(data["properties"], int)
        assert isinstance(data["sql_procedures"], int)

    async def test_index_full(self, live):
        """index_code returns full index with classes and dependencies."""
        result = await live.call_tool("index_code", {})
        data = json.loads(result.content[0].text)
        assert "namespace" in data
        assert "statistics" in data
        assert "classes" in data
        assert "dependencies" in data
        # New graph maps (Tier 0)
        assert "edges" in data
        assert "r_edges" in data
        assert "degree" in data

        stats = data["statistics"]
        assert "classes" in stats
        assert "persistent" in stats
        assert "methods" in stats
        assert "properties" in stats
        assert "sql_procedures" in stats
        assert "imports" in stats

    async def test_index_with_prefix(self, live):
        """index_code with filter_prefix returns only matching classes."""
        result = await live.call_tool("index_code", {"filter_prefix": "Test"})
        data = json.loads(result.content[0].text)
        assert data["statistics"]["classes"] >= 0
        for cls in data["classes"]:
            assert cls["name"].startswith("Test")

    async def test_index_compact_representation(self, live):
        """Index classes have compact dict representation."""
        result = await live.call_tool("index_code", {"filter_prefix": "Test"})
        data = json.loads(result.content[0].text)
        for cls in data["classes"]:
            assert "name" in cls
            # Methods should be a dict, not a list
            if "methods" in cls:
                assert isinstance(cls["methods"], dict)
            # Properties should be a dict, not a list
            if "properties" in cls:
                assert isinstance(cls["properties"], dict)

    async def test_index_dependencies_map(self, live):
        """Dependencies map class names to superclasses."""
        result = await live.call_tool("index_code", {"filter_prefix": "Test"})
        data = json.loads(result.content[0].text)
        deps = data["dependencies"]
        # Each dependency should be class_name -> superclass_string
        for cls_name, superclass in deps.items():
            assert isinstance(cls_name, str)
            assert isinstance(superclass, str)

    async def test_index_reachability_live(self, live):
        """index_reachability returns a reachable set from a known class."""
        result = await live.call_tool(
            "index_reachability",
            {"class_name": "Test", "max_hops": 2},
        )
        data = json.loads(result.content[0].text)
        assert data["start"] == "Test"
        assert data["max_hops"] == 2
        assert data["direction"] == "reverse"
        assert isinstance(data["reachable"], list)

    async def test_index_summary_is_smaller_than_full(self, live):
        """Summary output is smaller than full index."""
        summary_result = await live.call_tool("index_code", {"summary_only": True})
        full_result = await live.call_tool("index_code", {"filter_prefix": "Test"})

        summary_size = len(summary_result.content[0].text)
        full_size = len(full_result.content[0].text)
        assert summary_size < full_size

    async def test_index_call_graph(self, live, workspace):
        """index_code with include_call_graph returns method-level call edges."""
        # Create two classes with a real method call, then index them.
        (workspace / "Test.Caller.cls").write_text(
            "Class Test.Caller Extends %RegisteredObject {\n"
            "Method Go() {\n"
            "  Do ##class(Test.Callee).Run()\n"
            "}\n"
            "}\n"
        )
        (workspace / "Test.Callee.cls").write_text(
            "Class Test.Callee Extends %RegisteredObject {\nMethod Run() {\n  Quit $$$OK\n}\n}\n"
        )
        await live.call_tool(
            "put_document",
            {"name": "Test.Caller.cls", "path": "Test.Caller.cls"},
        )
        await live.call_tool(
            "put_document",
            {"name": "Test.Callee.cls", "path": "Test.Callee.cls"},
        )

        result = await live.call_tool(
            "index_code",
            # "Test.Call" indexes BOTH Test.Caller and Test.Callee so the
            # method edge can point at an in-index target class.
            {"filter_prefix": "Test.Call", "include_call_graph": True},
        )
        data = json.loads(result.content[0].text)
        assert "call_graph" in data
        cg = data["call_graph"]
        assert "call_edges" in cg
        assert "r_call_edges" in cg
        edges = cg["call_edges"]
        # Test.Caller.Go calls Test.Callee.Run (pattern 1)
        caller_edges = edges.get("Test.Caller.Go", [])
        assert any(e["to"] == "Test.Callee.Run" and e["pattern"] == 1 for e in caller_edges)
        # reverse: who calls Test.Callee.Run
        assert "Test.Caller.Go" in cg["r_call_edges"].get("Test.Callee.Run", [])

    async def test_index_search_live(self, live, workspace):
        """index_search finds symbols server-side via %Dictionary SQL."""
        # Create a class, then search for it — self-contained (works on any
        # IRIS, including the fresh CI instance).
        (workspace / "Test.SearchTarget.cls").write_text(
            "Class Test.SearchTarget Extends %RegisteredObject {\n"
            "Method Ping() {\n  Quit $$$OK\n}\n"
            "}\n"
        )
        await live.call_tool(
            "put_document",
            {"name": "Test.SearchTarget.cls", "path": "Test.SearchTarget.cls"},
        )

        result = await live.call_tool(
            "index_search", {"query": "Test.SearchTarget", "kind": "class", "limit": 5}
        )
        data = json.loads(result.content[0].text)
        assert data["count"] > 0
        assert any(r["symbol"] == "Test.SearchTarget" for r in data["results"])

    async def test_index_node_live(self, live, workspace):
        """index_node returns the full picture of a class we just created."""
        (workspace / "Test.SearchTarget.cls").write_text(
            "Class Test.SearchTarget Extends %RegisteredObject {\n"
            "Method Ping() {\n  Quit $$$OK\n}\n"
            "Method Run() {\n  Quit $$$OK\n}\n"
            "}\n"
        )
        await live.call_tool(
            "put_document",
            {"name": "Test.SearchTarget.cls", "path": "Test.SearchTarget.cls"},
        )

        result = await live.call_tool("index_node", {"class_name": "Test.SearchTarget"})
        data = json.loads(result.content[0].text)
        assert data["name"] == "Test.SearchTarget"
        # has methods/properties/supers from metadata
        assert "methods" in data
        assert any("Ping" in m for m in data["methods"])
        assert "supers" in data

    async def test_index_status_live(self, live):
        """index_status reports cache state for the USER namespace."""
        result = await live.call_tool("index_status", {})
        data = json.loads(result.content[0].text)
        assert "classes" in data and data["classes"] > 0
        assert "fresh" in data
        assert "cached" in data
