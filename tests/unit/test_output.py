"""Tests for the output formatting module and its integration."""

import json
from unittest.mock import patch

import pytest

from prism.output import format_output


class TestFormatOutput:
    """Unit tests for format_output()."""

    def test_json_default(self):
        data = {"key": "value", "num": 42}
        result = format_output(data, "json")
        assert json.loads(result) == data

    def test_json_indent(self):
        data = {"a": 1}
        result = format_output(data, "json")
        assert "\n" in result  # indented

    def test_json_list(self):
        data = [{"id": 1}, {"id": 2}]
        result = format_output(data, "json")
        assert json.loads(result) == data

    def test_toon_import_error(self):
        with patch.dict("sys.modules", {"toons": None}):
            with pytest.raises(RuntimeError, match="toons"):
                format_output({"key": "value"}, "toon")

    def test_toon_with_mock(self):
        """When toons is available, format_output delegates to toons.dumps."""
        import types

        fake_toons = types.ModuleType("toons")
        fake_toons.dumps = lambda data: "name: Alice\nage: 30"

        with patch.dict("sys.modules", {"toons": fake_toons}):
            result = format_output({"name": "Alice", "age": 30}, "toon")
            assert "Alice" in result
            assert "age" in result


class TestDecoratorToonConversion:
    """The @logged_tool decorator converts dict results to TOON when configured."""

    async def test_decorator_returns_dict_by_default(self):
        from prism.mcp._decorator import logged_tool

        @logged_tool
        async def sample_tool() -> dict:
            """Sample."""
            return {"key": "value"}

        with patch("prism.mcp._decorator.PRISM_OUTPUT_FORMAT", "json"):
            result = await sample_tool()
            assert isinstance(result, dict)
            assert result == {"key": "value"}

    async def test_decorator_converts_to_toon(self):
        import types

        from fastmcp.tools.tool import ToolResult
        from mcp.types import TextContent

        from prism.mcp._decorator import logged_tool

        @logged_tool
        async def sample_tool() -> dict:
            """Sample."""
            return {"key": "value"}

        fake_toons = types.ModuleType("toons")
        fake_toons.dumps = lambda data: "key: value"

        with (
            patch("prism.mcp._decorator.PRISM_OUTPUT_FORMAT", "toon"),
            patch.dict("sys.modules", {"toons": fake_toons}),
        ):
            result = await sample_tool()
            assert isinstance(result, ToolResult)
            assert len(result.content) == 1
            assert isinstance(result.content[0], TextContent)
            assert "key" in result.content[0].text
