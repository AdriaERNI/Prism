"""Unit tests for the index API and MCP tool.

Uses httpx.MockTransport to simulate IRIS Atelier API responses.
No live IRIS needed.
"""

import httpx
from unittest.mock import patch

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

        with patch.object(index_api, "client", lambda: mock_client(handler)):
            result = await index_api.build_index()

        assert result["namespace"] == "USER"
        assert result["statistics"]["classes"] == 2
        assert result["statistics"]["persistent"] == 1
        assert result["statistics"]["methods"] == 2
        assert result["statistics"]["properties"] == 2
        assert result["statistics"]["sql_procedures"] == 1

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

        with patch.object(index_api, "client", lambda: mock_client(handler)):
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

        with patch.object(index_api, "client", lambda: mock_client(handler)):
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

        with patch.object(index_api, "client", lambda: mock_client(handler)):
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

        with patch.object(index_api, "client", lambda: mock_client(handler)):
            result = await index_api.index_summary()

        assert result["namespace"] == "USER"
        assert result["classes"] == 42
        assert result["methods"] == 100
        assert result["properties"] == 50

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

        with patch.object(index_api, "client", lambda: mock_client(handler)):
            result = await index_api.index_summary()

        assert result["classes"] == 0
        assert result["methods"] == 0
        assert result["properties"] == 0


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
            with patch.object(index_api, "client", lambda: mock_client(handler)):
                result = await client.call_tool("index_code", {"summary_only": True})
                import json

                data = json.loads(result.content[0].text)
                assert "classes" in data
                assert "methods" in data
                assert "properties" in data
