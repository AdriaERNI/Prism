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

    async def test_index_summary_is_smaller_than_full(self, live):
        """Summary output is smaller than full index."""
        summary_result = await live.call_tool("index_code", {"summary_only": True})
        full_result = await live.call_tool("index_code", {"filter_prefix": "Test"})

        summary_size = len(summary_result.content[0].text)
        full_size = len(full_result.content[0].text)
        assert summary_size < full_size
