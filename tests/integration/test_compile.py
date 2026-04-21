"""Integration tests for document compilation."""

import json

from tests.integration.conftest import stage_file


class TestCompile:
    async def test_compile_persistent_class(self, live, workspace):
        stage_file(workspace, "Test.MCPPerson.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPPerson.cls", "path": "Test.MCPPerson.cls"},
        )
        result = await live.call_tool(
            "compile_documents", {"doc_names": ["Test.MCPPerson.cls"]}
        )
        data = json.loads(result.content[0].text)
        assert data["success"] is True

    async def test_compile_abstract_class(self, live, workspace):
        stage_file(workspace, "Test.MCPUtils.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        result = await live.call_tool(
            "compile_documents", {"doc_names": ["Test.MCPUtils.cls"]}
        )
        data = json.loads(result.content[0].text)
        assert data["success"] is True

    async def test_compile_multiple_classes(self, live, workspace):
        stage_file(workspace, "Test.MCPAddress.cls")
        stage_file(workspace, "Test.MCPEmployee.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPAddress.cls", "path": "Test.MCPAddress.cls"},
        )
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPEmployee.cls", "path": "Test.MCPEmployee.cls"},
        )
        result = await live.call_tool(
            "compile_documents",
            {"doc_names": ["Test.MCPAddress.cls", "Test.MCPEmployee.cls"]},
        )
        data = json.loads(result.content[0].text)
        assert data["success"] is True

    async def test_compile_mac_routine(self, live, workspace):
        stage_file(workspace, "Test.MCPRoutine.mac")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPRoutine.mac", "path": "Test.MCPRoutine.mac"},
        )
        result = await live.call_tool(
            "compile_documents", {"doc_names": ["Test.MCPRoutine.mac"]}
        )
        data = json.loads(result.content[0].text)
        assert data["success"] is True

    async def test_compile_nonexistent_class(self, live):
        result = await live.call_tool(
            "compile_documents", {"doc_names": ["Test.NoSuchClass999.cls"]}
        )
        data = json.loads(result.content[0].text)
        assert data["success"] is False
        assert len(data["errors"]) > 0

    async def test_compile_with_custom_flags(self, live, workspace):
        stage_file(workspace, "Test.MCPUtils.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        result = await live.call_tool(
            "compile_documents",
            {"doc_names": ["Test.MCPUtils.cls"], "flags": "ck"},
        )
        data = json.loads(result.content[0].text)
        assert data["success"] is True
