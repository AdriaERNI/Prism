"""Unit tests for error handling in MCP tool functions."""

from unittest.mock import patch, AsyncMock

import pytest

from prism.iris.api.documents import DocumentNotFound


class TestGetDocumentErrors:
    """Error paths in tools/documents.py get_document."""

    async def test_404_returns_not_found(self):
        from prism.mcp import documents as doc_tools

        mock_get = AsyncMock(side_effect=DocumentNotFound("Missing.cls"))
        with patch.object(doc_tools, "docs_api") as api:
            api.get_document = mock_get
            result = await doc_tools.get_document.__wrapped__("Missing.cls")
        assert result == {"name": "Missing.cls", "found": False}

    async def test_content_not_a_list(self):
        from prism.mcp import documents as doc_tools

        mock_get = AsyncMock(return_value={"result": {"content": "not a list"}})
        with patch.object(doc_tools, "docs_api") as api:
            api.get_document = mock_get
            with pytest.raises(ValueError, match="Expected content to be a list"):
                await doc_tools.get_document.__wrapped__("Bad.cls")

    async def test_content_item_unexpected_type(self):
        from prism.mcp import documents as doc_tools

        mock_get = AsyncMock(return_value={"result": {"content": [123, 456]}})
        with patch.object(doc_tools, "docs_api") as api:
            api.get_document = mock_get
            with pytest.raises(ValueError, match="Unexpected content item at index 0"):
                await doc_tools.get_document.__wrapped__("Bad.cls")


class TestGetDocumentSlicing:
    """Slicing parameters for get_document."""

    def _mock_api(self, lines: list[str]):
        return AsyncMock(return_value={"result": {"content": lines}})

    async def _call(self, lines, **kwargs):
        from prism.mcp import documents as doc_tools

        mock_get = self._mock_api(lines)
        with patch.object(doc_tools, "docs_api") as api:
            api.get_document = mock_get
            return await doc_tools.get_document.__wrapped__("Test.cls", **kwargs)

    async def test_head(self):
        lines = ["a", "b", "c", "d", "e"]
        result = await self._call(lines, head=3)
        assert result["content"] == ["a", "b", "c"]
        assert result["total_lines"] == 5
        assert result["from_line"] == 1
        assert result["to_line"] == 3

    async def test_tail(self):
        lines = ["a", "b", "c", "d", "e"]
        result = await self._call(lines, tail=2)
        assert result["content"] == ["d", "e"]
        assert result["from_line"] == 4
        assert result["to_line"] == 5

    async def test_from_to(self):
        lines = ["a", "b", "c", "d", "e"]
        result = await self._call(lines, from_line=2, to_line=4)
        assert result["content"] == ["b", "c", "d"]
        assert result["from_line"] == 2
        assert result["to_line"] == 4

    async def test_from_line_only(self):
        lines = ["a", "b", "c", "d", "e"]
        result = await self._call(lines, from_line=3)
        assert result["content"] == ["c", "d", "e"]
        assert result["from_line"] == 3
        assert result["to_line"] == 5

    async def test_to_line_only(self):
        lines = ["a", "b", "c", "d", "e"]
        result = await self._call(lines, to_line=2)
        assert result["content"] == ["a", "b"]
        assert result["from_line"] == 1
        assert result["to_line"] == 2

    async def test_no_slicing_returns_all(self):
        lines = ["a", "b", "c"]
        result = await self._call(lines)
        assert result["content"] == ["a", "b", "c"]
        assert result["from_line"] == 1
        assert result["to_line"] == 3
        assert result["total_lines"] == 3

    async def test_head_exceeds_total(self):
        lines = ["a", "b"]
        result = await self._call(lines, head=100)
        assert result["content"] == ["a", "b"]
        assert result["to_line"] == 2

    async def test_tail_exceeds_total(self):
        lines = ["a", "b"]
        result = await self._call(lines, tail=100)
        assert result["content"] == ["a", "b"]
        assert result["from_line"] == 1

    async def test_out_of_range_from_line_clamped(self):
        lines = ["a", "b", "c"]
        result = await self._call(lines, from_line=0)
        assert result["from_line"] == 1
        assert result["content"] == ["a", "b", "c"]

    async def test_out_of_range_to_line_clamped(self):
        lines = ["a", "b", "c"]
        result = await self._call(lines, to_line=999)
        assert result["to_line"] == 3
        assert result["content"] == ["a", "b", "c"]

    async def test_empty_document(self):
        from prism.mcp import documents as doc_tools

        mock_get = AsyncMock(return_value={"result": {"content": []}})
        with patch.object(doc_tools, "docs_api") as api:
            api.get_document = mock_get
            result = await doc_tools.get_document.__wrapped__("Empty.cls")
        assert result["found"] is True
        assert result["total_lines"] == 0
        assert result["content"] == []

    async def test_conflict_from_line_with_head(self):
        from prism.mcp import documents as doc_tools

        with pytest.raises(
            ValueError, match="from_line/to_line cannot be combined with head"
        ):
            await doc_tools.get_document.__wrapped__("X.cls", from_line=1, head=5)

    async def test_conflict_to_line_with_tail(self):
        from prism.mcp import documents as doc_tools

        with pytest.raises(
            ValueError, match="from_line/to_line cannot be combined with tail"
        ):
            await doc_tools.get_document.__wrapped__("X.cls", to_line=5, tail=3)

    async def test_conflict_head_with_tail(self):
        from prism.mcp import documents as doc_tools

        with pytest.raises(ValueError, match="head cannot be combined with tail"):
            await doc_tools.get_document.__wrapped__("X.cls", head=5, tail=3)

    async def test_head_zero(self):
        lines = ["a", "b", "c"]
        result = await self._call(lines, head=0)
        assert result["content"] == []
        assert result["from_line"] == 1
        assert result["to_line"] == 0

    async def test_tail_zero(self):
        lines = ["a", "b", "c"]
        result = await self._call(lines, tail=0)
        assert result["content"] == []
        assert result["from_line"] == 4
        assert result["to_line"] == 3


class TestDeleteDocumentErrors:
    """Error paths in tools/documents.py delete_document."""

    async def test_404_returns_not_found(self):
        from prism.mcp import documents as doc_tools

        mock_del = AsyncMock(side_effect=DocumentNotFound("Gone.cls"))
        with patch.object(doc_tools, "docs_api") as api:
            api.delete_document = mock_del
            result = await doc_tools.delete_document.__wrapped__("Gone.cls")
        assert result == {"name": "Gone.cls", "deleted": False, "reason": "not found"}


class TestPutDocumentErrors:
    """Error paths in tools/workspace.py put_document."""

    async def test_file_missing_in_workspace(self, tmp_path):
        from prism.mcp import workspace as ws_tools

        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", str(tmp_path)):
            with pytest.raises(FileNotFoundError, match="Write the file"):
                await ws_tools.put_document.__wrapped__("NoSuch.cls")

    async def test_path_traversal_blocked(self, tmp_path):
        from prism.mcp import workspace as ws_tools

        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", str(tmp_path)):
            with pytest.raises(ValueError, match="escapes workspace"):
                await ws_tools.put_document.__wrapped__(
                    "Hack.cls", path="../../../etc/passwd"
                )


class TestPutAndCompileErrors:
    """Error paths in tools/workspace.py put_and_compile."""

    async def test_file_missing_in_workspace(self, tmp_path):
        from prism.mcp import workspace as ws_tools

        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", str(tmp_path)):
            with pytest.raises(FileNotFoundError, match="Write the file"):
                await ws_tools.put_and_compile.__wrapped__("NoSuch.cls")


class TestDocNameValidationInTools:
    """Verify every tool that accepts a name rejects invalid ones."""

    async def test_get_document_rejects_invalid_name(self):
        from prism.mcp import documents as doc_tools

        with pytest.raises(ValueError, match="Invalid document name"):
            await doc_tools.get_document.__wrapped__("no-extension")

    async def test_put_document_rejects_invalid_name(self):
        from prism.mcp import workspace as ws_tools

        with pytest.raises(ValueError, match="Invalid document name"):
            await ws_tools.put_document.__wrapped__("../evil")

    async def test_put_and_compile_rejects_invalid_name(self):
        from prism.mcp import workspace as ws_tools

        with pytest.raises(ValueError, match="Invalid document name"):
            await ws_tools.put_and_compile.__wrapped__("bad name.cls")

    async def test_delete_document_rejects_invalid_name(self):
        from prism.mcp import documents as doc_tools

        with pytest.raises(ValueError, match="Invalid document name"):
            await doc_tools.delete_document.__wrapped__("")

    async def test_compile_documents_rejects_invalid_name(self):
        from prism.mcp import compile as compile_tools

        with pytest.raises(ValueError, match="Invalid document name"):
            await compile_tools.compile_documents.__wrapped__(["valid.cls", "bad!name"])
