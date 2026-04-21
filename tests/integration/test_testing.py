"""Integration tests for the unit testing tools."""

import json

from tests.integration.conftest import stage_file


class TestRunTests:
    """Test the run_tests MCP tool against a real IRIS instance."""

    async def test_run_passing_tests(self, live, workspace):
        """Deploy a test class, run it, and verify all pass."""
        stage_file(workspace, "Test.MCPSampleTest.cls")
        await live.call_tool(
            "put_and_compile",
            {"name": "Test.MCPSampleTest.cls", "path": "Test.MCPSampleTest.cls"},
        )

        result = await live.call_tool("run_tests", {"test_class": "Test.MCPSampleTest"})
        data = json.loads(result.content[0].text)

        assert data["class"] == "Test.MCPSampleTest"
        assert data["status"] == "passed"
        assert data["passed"] == 3
        assert data["failed"] == 0
        assert data["skipped"] == 0
        assert len(data["methods"]) == 3

        method_names = {m["name"] for m in data["methods"]}
        assert "TestAddition" in method_names
        assert "TestStringConcat" in method_names
        assert "TestTruth" in method_names

    async def test_run_single_method(self, live, workspace):
        """Run a specific test method instead of all methods."""
        stage_file(workspace, "Test.MCPSampleTest.cls")
        await live.call_tool(
            "put_and_compile",
            {"name": "Test.MCPSampleTest.cls", "path": "Test.MCPSampleTest.cls"},
        )

        result = await live.call_tool(
            "run_tests",
            {"test_class": "Test.MCPSampleTest", "test_method": "TestAddition"},
        )
        data = json.loads(result.content[0].text)

        assert data["status"] == "passed"
        assert data["passed"] >= 1

    async def test_run_failing_tests(self, live, workspace):
        """Run a class with a failing test and verify failure details."""
        stage_file(workspace, "Test.MCPFailingTest.cls")
        await live.call_tool(
            "put_and_compile",
            {"name": "Test.MCPFailingTest.cls", "path": "Test.MCPFailingTest.cls"},
        )

        result = await live.call_tool(
            "run_tests", {"test_class": "Test.MCPFailingTest"}
        )
        data = json.loads(result.content[0].text)

        assert data["class"] == "Test.MCPFailingTest"
        assert data["status"] == "failed"
        assert data["passed"] >= 1
        assert data["failed"] >= 1

        # Find the failing method
        failing = [m for m in data["methods"] if m["status"] == "failed"]
        assert len(failing) >= 1
        assert failing[0]["name"] == "TestWillFail"

    async def test_run_nonexistent_class(self, live):
        """Running tests for a class that doesn't exist returns an error."""
        result = await live.call_tool(
            "run_tests", {"test_class": "Test.NoSuchClass999"}
        )
        data = json.loads(result.content[0].text)

        # The runner should still return a result (not crash)
        assert "class" in data


class TestListTests:
    """Test the list_tests MCP tool."""

    async def test_discover_test_classes(self, live, workspace):
        """After deploying a test class, list_tests should find it."""
        stage_file(workspace, "Test.MCPSampleTest.cls")
        await live.call_tool(
            "put_and_compile",
            {"name": "Test.MCPSampleTest.cls", "path": "Test.MCPSampleTest.cls"},
        )

        result = await live.call_tool("list_tests", {"filter": "Test.MCPSampleTest"})
        data = json.loads(result.content[0].text)

        assert data["count"] >= 1
        class_names = {c["name"] for c in data["classes"]}
        assert "Test.MCPSampleTest" in class_names

        # Verify methods are discovered
        test_cls = next(c for c in data["classes"] if c["name"] == "Test.MCPSampleTest")
        assert "TestAddition" in test_cls["methods"]
        assert "TestStringConcat" in test_cls["methods"]
        assert "TestTruth" in test_cls["methods"]

    async def test_list_with_no_results(self, live):
        """Filtering by a prefix with no matches returns empty."""
        result = await live.call_tool("list_tests", {"filter": "NoSuchPrefix999"})
        data = json.loads(result.content[0].text)
        assert data["count"] == 0
        assert data["classes"] == []


class TestGetTestResults:
    """Test the get_test_results MCP tool."""

    async def test_get_history_after_run(self, live, workspace):
        """After running tests, get_test_results should show the run."""
        stage_file(workspace, "Test.MCPSampleTest.cls")
        await live.call_tool(
            "put_and_compile",
            {"name": "Test.MCPSampleTest.cls", "path": "Test.MCPSampleTest.cls"},
        )
        await live.call_tool("run_tests", {"test_class": "Test.MCPSampleTest"})

        result = await live.call_tool(
            "get_test_results", {"test_class": "Test.MCPSampleTest", "limit": 5}
        )
        data = json.loads(result.content[0].text)

        assert data["count"] >= 1
        assert data["runs"][0]["test_class"] == "Test.MCPSampleTest"
        assert data["runs"][0]["status"] == "passed"

    async def test_get_history_no_results(self, live):
        """Querying history for a class that was never tested returns empty."""
        result = await live.call_tool(
            "get_test_results",
            {"test_class": "Test.NeverTestedClass999", "limit": 5},
        )
        data = json.loads(result.content[0].text)
        assert data["count"] == 0


class TestAutoDeployRunner:
    """Test that the MCP.TestRunner helper class is auto-deployed."""

    async def test_runner_deployed_automatically(self, live, workspace):
        """The first call to run_tests should auto-deploy MCP.TestRunner."""
        # Deploy a test class first
        stage_file(workspace, "Test.MCPSampleTest.cls")
        await live.call_tool(
            "put_and_compile",
            {"name": "Test.MCPSampleTest.cls", "path": "Test.MCPSampleTest.cls"},
        )

        # run_tests should auto-deploy MCP.TestRunner
        await live.call_tool("run_tests", {"test_class": "Test.MCPSampleTest"})

        # Verify the runner was deployed by checking it exists as a document
        doc_result = await live.call_tool(
            "list_documents", {"filter": "MCP.TestRunner", "doc_type": "cls"}
        )
        doc_data = json.loads(doc_result.content[0].text)
        runner_docs = [
            d for d in doc_data["documents"] if d["name"] == "MCP.TestRunner.cls"
        ]
        assert len(runner_docs) == 1
