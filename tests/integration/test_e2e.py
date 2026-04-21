"""End-to-end workflow tests combining multiple IRIS operations."""

import json

from tests.integration.conftest import stage_file, write_to_workspace


class TestEndToEnd:
    async def test_create_compile_insert_select(self, live, workspace):
        """Full lifecycle: create class -> compile -> INSERT -> SELECT."""
        stage_file(workspace, "Test.MCPPerson.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPPerson.cls", "path": "Test.MCPPerson.cls"},
        )
        compile_result = await live.call_tool(
            "compile_documents", {"doc_names": ["Test.MCPPerson.cls"]}
        )
        data = json.loads(compile_result.content[0].text)
        assert data["success"] is True

        await live.call_tool(
            "execute_sql",
            {
                "query": "INSERT INTO Test.MCPPerson (Name, Age, Email) VALUES ('Alice', 30, 'alice@test.com')"
            },
        )
        await live.call_tool(
            "execute_sql",
            {
                "query": "INSERT INTO Test.MCPPerson (Name, Age, Email) VALUES ('Bob', 25, 'bob@test.com')"
            },
        )

        result = await live.call_tool(
            "execute_sql", {"query": "SELECT * FROM Test.MCPPerson ORDER BY Name"}
        )
        text = result.content[0].text
        assert "Alice" in text
        assert "Bob" in text

        result = await live.call_tool(
            "execute_sql", {"query": "SELECT COUNT(*) AS total FROM Test.MCPPerson"}
        )
        assert "2" in result.content[0].text

        await live.call_tool("execute_sql", {"query": "DELETE FROM Test.MCPPerson"})

    async def test_sql_update_and_verify(self, live, workspace):
        """INSERT -> UPDATE -> verify change."""
        stage_file(workspace, "Test.MCPPerson.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPPerson.cls", "path": "Test.MCPPerson.cls"},
        )
        await live.call_tool("compile_documents", {"doc_names": ["Test.MCPPerson.cls"]})

        await live.call_tool(
            "execute_sql",
            {"query": "INSERT INTO Test.MCPPerson (Name, Age) VALUES ('Charlie', 40)"},
        )
        await live.call_tool(
            "execute_sql",
            {"query": "UPDATE Test.MCPPerson SET Age = 41 WHERE Name = 'Charlie'"},
        )
        result = await live.call_tool(
            "execute_sql",
            {"query": "SELECT Age FROM Test.MCPPerson WHERE Name = 'Charlie'"},
        )
        assert "41" in result.content[0].text

        await live.call_tool("execute_sql", {"query": "DELETE FROM Test.MCPPerson"})

    async def test_sql_aggregates(self, live, workspace):
        """Test SUM, AVG, MIN, MAX on persistent data."""
        stage_file(workspace, "Test.MCPPerson.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPPerson.cls", "path": "Test.MCPPerson.cls"},
        )
        await live.call_tool("compile_documents", {"doc_names": ["Test.MCPPerson.cls"]})

        for name, age in [("A", 20), ("B", 30), ("C", 40)]:
            await live.call_tool(
                "execute_sql",
                {
                    "query": f"INSERT INTO Test.MCPPerson (Name, Age) VALUES ('{name}', {age})"
                },
            )

        result = await live.call_tool(
            "execute_sql",
            {
                "query": "SELECT SUM(Age) AS s, AVG(Age) AS a, MIN(Age) AS mn, MAX(Age) AS mx FROM Test.MCPPerson"
            },
        )
        text = result.content[0].text
        assert "90" in text  # sum
        assert "30" in text  # avg
        assert "20" in text  # min
        assert "40" in text  # max

        await live.call_tool("execute_sql", {"query": "DELETE FROM Test.MCPPerson"})

    async def test_call_sqlproc_via_sql(self, live, workspace):
        """Call a ClassMethod marked [SqlProc] from SQL."""
        stage_file(workspace, "Test.MCPPerson.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPPerson.cls", "path": "Test.MCPPerson.cls"},
        )
        await live.call_tool("compile_documents", {"doc_names": ["Test.MCPPerson.cls"]})

        result = await live.call_tool(
            "execute_sql",
            {"query": "SELECT Test.MCPPerson_Hello() AS greeting"},
        )
        assert "Hello from MCP" in result.content[0].text

        result = await live.call_tool(
            "execute_sql",
            {"query": "SELECT Test.MCPPerson_Add(10, 20) AS total"},
        )
        assert "30" in result.content[0].text

    async def test_serial_embedded_object(self, live, workspace):
        """Create class with embedded serial object, insert, query."""
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

        await live.call_tool(
            "execute_sql",
            {
                "query": "INSERT INTO Test.MCPEmployee (FullName, Address_Street, Address_City, Address_Zip, Salary) VALUES ('Dana', '123 Main St', 'Springfield', '62704', 75000.50)"
            },
        )
        result = await live.call_tool(
            "execute_sql",
            {"query": "SELECT FullName, Address_City, Salary FROM Test.MCPEmployee"},
        )
        text = result.content[0].text
        assert "Dana" in text
        assert "Springfield" in text

        await live.call_tool("execute_sql", {"query": "DELETE FROM Test.MCPEmployee"})

    async def test_document_roundtrip(self, live, workspace):
        """Put -> Get -> verify content matches -> Delete -> verify gone."""
        stage_file(workspace, "Test.MCPUtils.cls")
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )

        result = await live.call_tool("get_document", {"name": "Test.MCPUtils.cls"})
        data = json.loads(result.content[0].text)
        assert data["found"] is True
        content = "\n".join(data["content"])
        assert "MCPUtils" in content
        assert "Greet" in content
        assert "Timestamp" in content

        await live.call_tool("delete_document", {"name": "Test.MCPUtils.cls"})

        result = await live.call_tool("list_documents", {"filter": "Test.MCPUtils*"})
        data = json.loads(result.content[0].text)
        assert data["count"] == 0

    async def test_modify_class_recompile(self, live, workspace):
        """Create class -> compile -> modify -> recompile -> verify new behavior."""
        v1 = [
            "Class Test.MCPUtils",
            "{",
            "ClassMethod Version() As %String [ SqlProc ]",
            "{",
            '  Return "v1"',
            "}",
            "}",
        ]
        write_to_workspace(workspace, "Test.MCPUtils.cls", v1)
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        await live.call_tool("compile_documents", {"doc_names": ["Test.MCPUtils.cls"]})
        result = await live.call_tool(
            "execute_sql", {"query": "SELECT Test.MCPUtils_Version() AS ver"}
        )
        assert "v1" in result.content[0].text

        v2 = [line.replace("v1", "v2") for line in v1]
        write_to_workspace(workspace, "Test.MCPUtils.cls", v2)
        await live.call_tool(
            "put_document",
            {"name": "Test.MCPUtils.cls", "path": "Test.MCPUtils.cls"},
        )
        await live.call_tool("compile_documents", {"doc_names": ["Test.MCPUtils.cls"]})
        result = await live.call_tool(
            "execute_sql", {"query": "SELECT Test.MCPUtils_Version() AS ver"}
        )
        assert "v2" in result.content[0].text
