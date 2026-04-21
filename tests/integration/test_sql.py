"""Integration tests for SQL queries."""

import json


class TestSQL:
    async def test_select_literal(self, live):
        result = await live.call_tool("execute_sql", {"query": "SELECT 1 AS val"})
        text = result.content[0].text
        assert "1" in text

    async def test_select_expression(self, live):
        result = await live.call_tool("execute_sql", {"query": "SELECT 2 + 3 AS sum"})
        text = result.content[0].text
        assert "5" in text

    async def test_string_functions(self, live):
        result = await live.call_tool(
            "execute_sql",
            {"query": "SELECT UPPER('hello') AS upper_val, LENGTH('hello') AS len_val"},
        )
        text = result.content[0].text
        assert "HELLO" in text
        assert "5" in text

    async def test_date_function(self, live):
        result = await live.call_tool(
            "execute_sql", {"query": "SELECT CURRENT_DATE AS today"}
        )
        text = result.content[0].text
        assert "2026" in text or "today" in text

    async def test_invalid_sql_returns_error(self, live):
        result = await live.call_tool(
            "execute_sql", {"query": "SELECT * FROM NonExistent.Table12345"}
        )
        data = json.loads(result.content[0].text)
        assert "error" in data

    async def test_select_with_namespace(self, live):
        result = await live.call_tool(
            "execute_sql", {"query": "SELECT 42 AS answer", "namespace": "USER"}
        )
        text = result.content[0].text
        assert "42" in text
