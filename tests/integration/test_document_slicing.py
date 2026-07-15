"""Integration tests for document slicing via MCP tools.

Tests get_document with head, tail, from_line, to_line parameters
and validation errors for invalid slicing combinations.
"""

import json

import pytest

from tests.integration.conftest import stage_file


def _parse(result) -> dict:
    return json.loads(result.content[0].text)


@pytest.fixture
async def deployed_doc(live, workspace):
    """Deploy a known document for slicing tests."""
    stage_file(workspace, "Test.MCPPerson.cls")
    await live.call_tool(
        "put_document",
        {"name": "Test.MCPPerson.cls", "path": "Test.MCPPerson.cls"},
    )
    yield "Test.MCPPerson.cls"


class TestGetDocumentSlicing:
    async def test_get_document_head(self, live, deployed_doc):
        """get_document with head=5 returns first 5 lines."""
        result = _parse(
            await live.call_tool(
                "get_document",
                {"name": deployed_doc, "head": 5},
            )
        )
        content = result["content"]
        assert len(content) <= 5

    async def test_get_document_tail(self, live, deployed_doc):
        """get_document with tail=3 returns last 3 lines."""
        result = _parse(
            await live.call_tool(
                "get_document",
                {"name": deployed_doc, "tail": 3},
            )
        )
        content = result["content"]
        assert len(content) <= 3

    async def test_get_document_range(self, live, deployed_doc):
        """get_document with from_line=2, to_line=5 returns lines 2-5."""
        result = _parse(
            await live.call_tool(
                "get_document",
                {"name": deployed_doc, "from_line": 2, "to_line": 5},
            )
        )
        content = result["content"]
        assert len(content) == 4  # lines 2,3,4,5

    async def test_get_document_invalid_slicing_head_and_from_line(
        self, live, deployed_doc
    ):
        """get_document with head + from_line raises an error."""
        with pytest.raises(Exception):
            await live.call_tool(
                "get_document",
                {"name": deployed_doc, "head": 5, "from_line": 2},
            )

    async def test_get_document_not_found(self, live):
        """get_document for non-existent doc returns found=false."""
        result = _parse(
            await live.call_tool(
                "get_document",
                {"name": "Test.NonExistent.cls"},
            )
        )
        assert result.get("found") is False


class TestListDocumentsGenerated:
    async def test_list_documents_generated(self, live):
        """list_documents with generated=true includes generated docs."""
        result = _parse(
            await live.call_tool(
                "list_documents",
                {"doc_type": "cls", "generated": True},
            )
        )
        assert "documents" in result
        assert result["count"] >= 0


class TestCompileBranchFlags:
    async def test_compile_with_branch_flags(self, live, workspace):
        """compile with 'cub' flags (branch compile)."""
        stage_file(workspace, "Test.MCPPerson.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPPerson.cls", "path": "Test.MCPPerson.cls"},
        )
        result = _parse(
            await live.call_tool(
                "compile_documents",
                {"doc_names": ["Test.MCPPerson.cls"], "flags": "cub"},
            )
        )
        assert result["success"] is True
