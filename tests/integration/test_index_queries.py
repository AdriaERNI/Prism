"""Live integration tests for the five named index queries.

Creates three small self-contained classes with real ObjectScript call
relationships, builds the index (Tier-2 call graph), and asserts each named
query returns the exact expected shape/result. Self-contained: works on any
IRIS (including a fresh CI instance) because the classes are created by the
test itself — never relies on pre-loaded namespaces.

Queries under test: callers_of_method, callers_high_fanin,
method_calls_outbound, class_references, find_path.
"""

import json

# Created by these tests; auto-deleted by the conftest ``cleanup`` fixture.
QUERY_TEST_DOCS = [
    "Test.QryCaller.cls",
    "Test.QryMiddle.cls",
    "Test.QryLeaf.cls",
]


def _write(workspace, name: str, body: str) -> None:
    (workspace / name).write_text(body)


def _parse(result) -> dict:
    return json.loads(result.content[0].text)


class TestIndexQueriesLive:
    """Live validation of the 5 named queries on self-created classes.

    Class graph:
        Test.QryCaller.Run   --calls--> Test.QryMiddle.Help  (##class, pattern 1)
        Test.QryCaller.Run   --calls--> Test.QryCaller.Help  (..self, pattern 2)
        Test.QryCaller.Run   --calls--> Test.QryLeaf.Maybe   (##class, pattern 1)
        Test.QryMiddle.Help  --calls--> Test.QryLeaf.Maybe   (##class, pattern 1)
        Test.QryCaller.Boot  --calls--> Test.QryLeaf.Maybe   (##class, pattern 1)

    Expected reverse-degree: Test.QryLeaf.Maybe has 3 distinct callers;
    Test.QryMiddle.Help has 1. class_references of Test.QryLeaf = {Caller,
    Middle}. find_path Caller.Run -> Leaf.Maybe is length 1.
    """

    async def _load(self, live, workspace, client=None):
        """PUT + compile the three test classes, then index the fruit prefix."""
        for name, body in (
            (
                "Test.QryCaller.cls",
                "Class Test.QryCaller Extends %RegisteredObject {\n"
                "Method Run() {\n"
                "  Do ##class(Test.QryMiddle).Help()\n"
                "  Do ..Help()\n"
                "  Do ##class(Test.QryLeaf).Maybe()\n"
                "}\n"
                "Method Help() {\n"
                "  Quit $$$OK\n"
                "}\n"
                "Method Boot() {\n"
                "  Do ##class(Test.QryLeaf).Maybe()\n"
                "  Do ##class(Test.QryLeaf).Maybe()\n"
                "}\n"
                "}\n",
            ),
            (
                "Test.QryMiddle.cls",
                "Class Test.QryMiddle Extends %RegisteredObject {\n"
                "Method Help() {\n"
                "  Do ##class(Test.QryLeaf).Maybe()\n"
                "  Quit $$$OK\n"
                "}\n"
                "}\n",
            ),
            (
                "Test.QryLeaf.cls",
                "Class Test.QryLeaf Extends %RegisteredObject {\n"
                "Method Maybe() {\n"
                "  Quit $$$OK\n"
                "}\n"
                "}\n",
            ),
        ):
            _write(workspace, name, body)
            await live.call_tool("put_document", {"name": name, "path": name})
        await live.call_tool("compile_documents", {"doc_names": QUERY_TEST_DOCS})

    async def test_queries_exact_results(self, live, workspace):
        await self._load(live, workspace)

        # ── callers_of_method ─────────────────────────────────────────────
        data = _parse(
            await live.call_tool(
                "index_queries",
                {
                    "query": "callers_of_method",
                    "method": "Test.QryLeaf.Maybe",
                    "filter_prefix": "Test.Qry",
                },
            )
        )
        assert data["query"] == "callers_of_method"
        assert data["method"] == "Test.QryLeaf.Maybe"
        # Test.QryCaller.Boot calls it twice -> dedup; 3 distinct callers.
        assert data["total"] == 3, data
        assert set(data["callers"]) == {
            "Test.QryCaller.Boot",
            "Test.QryCaller.Run",
            "Test.QryMiddle.Help",
        }

        data = _parse(
            await live.call_tool(
                "index_queries",
                {
                    "query": "callers_of_method",
                    "method": "Test.QryMiddle.Help",
                    "filter_prefix": "Test.Qry",
                },
            )
        )
        assert data["total"] == 1
        assert data["callers"] == ["Test.QryCaller.Run"]

        # ── callers_high_fanin ────────────────────────────────────────────
        data = _parse(
            await live.call_tool(
                "index_queries",
                {"query": "callers_high_fanin", "top_n": 5, "filter_prefix": "Test.Qry"},
            )
        )
        assert data["query"] == "callers_high_fanin"
        top = data["results"][0]
        assert top["method"] == "Test.QryLeaf.Maybe"
        assert top["callers"] == 3  # highest reverse-degree in our graph

        # ── method_calls_outbound ─────────────────────────────────────────
        data = _parse(
            await live.call_tool(
                "index_queries",
                {
                    "query": "method_calls_outbound",
                    "method": "Test.QryCaller.Run",
                    "filter_prefix": "Test.Qry",
                },
            )
        )
        assert data["query"] == "method_calls_outbound"
        assert data["total"] == 3, data
        callees = {c["to"]: c["pattern"] for c in data["callees"]}
        assert callees["Test.QryMiddle.Help"] == 1  # ##class -> pattern 1
        assert callees["Test.QryCaller.Help"] == 2  # ..self -> pattern 2
        assert callees["Test.QryLeaf.Maybe"] == 1

        # ── class_references ──────────────────────────────────────────────
        data = _parse(
            await live.call_tool(
                "index_queries",
                {
                    "query": "class_references",
                    "class_name": "Test.QryLeaf",
                    "filter_prefix": "Test.Qry",
                },
            )
        )
        assert data["query"] == "class_references"
        assert data["class_name"] == "Test.QryLeaf"
        assert data["count"] == 2, data
        assert set(data["referenced_by"]) == {"Test.QryCaller", "Test.QryMiddle"}

        # ── find_path ─────────────────────────────────────────────────────
        data = _parse(
            await live.call_tool(
                "index_queries",
                {
                    "query": "find_path",
                    "source": "Test.QryCaller.Run",
                    "target": "Test.QryLeaf.Maybe",
                    "filter_prefix": "Test.Qry",
                },
            )
        )
        assert data["query"] == "find_path"
        assert data["source"] == "Test.QryCaller.Run"
        assert data["target"] == "Test.QryLeaf.Maybe"
        assert data["found"] is True
        assert data["length"] == 1
        assert data["path"] == ["Test.QryCaller.Run", "Test.QryLeaf.Maybe"]

        # Not-found path: a node with no graph edges at all.
        data = _parse(
            await live.call_tool(
                "index_queries",
                {
                    "query": "find_path",
                    "source": "Test.QryLeaf.Maybe",
                    "target": "Test.QryNone.Isolated",
                    "filter_prefix": "Test.Qry",
                },
            )
        )
        assert data["found"] is False
        assert data["length"] == -1

    async def test_queries_error_paths(self, live):
        """Unknown query and missing required params return an error dict."""
        data = _parse(await live.call_tool("index_queries", {"query": "no_such_query"}))
        assert "error" in data
        assert "callers_of_method" in data["error"]

        data = _parse(await live.call_tool("index_queries", {"query": "callers_of_method"}))
        assert "error" in data
        assert "method" in data["error"]
