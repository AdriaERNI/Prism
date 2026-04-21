"""Integration tests for document CRUD."""

import json

from tests.integration.conftest import stage_file


class TestDocuments:
    async def test_put_and_get_cls(self, live, workspace):
        stage_file(workspace, "Test.MCPUtils.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        result = await live.call_tool("get_document", {"name": "Test.MCPUtils.cls"})
        data = json.loads(result.content[0].text)
        assert data["found"] is True
        assert data["total_lines"] > 0
        content = "\n".join(data["content"])
        assert "MCPUtils" in content
        assert "Greet" in content

    async def test_put_and_get_mac(self, live, workspace):
        stage_file(workspace, "Test.MCPRoutine.mac")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPRoutine.mac", "path": "Test.MCPRoutine.mac"},
        )
        result = await live.call_tool("get_document", {"name": "Test.MCPRoutine.mac"})
        text = result.content[0].text
        assert "MCPRoutine" in text or "Hello" in text

    async def test_put_and_get_inc(self, live, workspace):
        stage_file(workspace, "Test.MCPHeader.inc")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPHeader.inc", "path": "Test.MCPHeader.inc"},
        )
        result = await live.call_tool("get_document", {"name": "Test.MCPHeader.inc"})
        text = result.content[0].text
        assert "AppName" in text or "MCP" in text

    async def test_put_overwrite(self, live, workspace):
        stage_file(workspace, "Test.MCPUtils.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        # Overwrite with modified content
        original = (workspace / "Test.MCPUtils.cls").read_text()
        (workspace / "Test.MCPUtils.cls").write_text(
            original.replace("Greet", "SayHello")
        )
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        result = await live.call_tool("get_document", {"name": "Test.MCPUtils.cls"})
        data = json.loads(result.content[0].text)
        content = "\n".join(data["content"])
        assert "SayHello" in content

    async def test_delete_document(self, live, workspace):
        stage_file(workspace, "Test.MCPUtils.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        result = await live.call_tool("delete_document", {"name": "Test.MCPUtils.cls"})
        data = json.loads(result.content[0].text)
        assert data["deleted"] is True

    async def test_get_nonexistent_document(self, live):
        result = await live.call_tool(
            "get_document", {"name": "Test.DoesNotExist99999.cls"}
        )
        data = json.loads(result.content[0].text)
        assert data["found"] is False

    async def test_list_documents_unfiltered(self, live):
        result = await live.call_tool("list_documents")
        data = json.loads(result.content[0].text)
        assert "documents" in data
        assert data["count"] >= 0

    async def test_list_documents_filter_by_type(self, live):
        result = await live.call_tool("list_documents", {"doc_type": "cls"})
        data = json.loads(result.content[0].text)
        assert data["count"] > 0
        # IRIS may include related includes; verify CLS documents are present
        cls_docs = [d for d in data["documents"] if d["name"].endswith(".cls")]
        assert len(cls_docs) > 0

    async def test_list_documents_with_filter_string(self, live, workspace):
        stage_file(workspace, "Test.MCPUtils.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        result = await live.call_tool(
            "list_documents", {"doc_type": "cls", "filter": "Test.MCPUtils"}
        )
        data = json.loads(result.content[0].text)
        names = [doc["name"] for doc in data["documents"]]
        assert any("MCPUtils" in n for n in names)
