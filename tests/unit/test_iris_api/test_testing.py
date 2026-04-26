"""Unit tests for the testing API layer."""

from unittest.mock import AsyncMock, patch

import pytest

from prism.iris.api import testing as testing_api
from prism.settings import settings


class TestEnsureRunnerDeployed:
    """Tests for auto-deploy logic."""

    async def test_already_exists(self):
        """If the document exists, no PUT or compile is needed."""
        with (
            patch.object(
                testing_api,
                "get_document",
                AsyncMock(return_value={"result": {"content": []}}),
            ) as mock_get,
            patch.object(testing_api, "put_document", AsyncMock()) as mock_put,
        ):
            result = await testing_api.ensure_runner_deployed()
            assert result is True
            mock_get.assert_awaited_once()
            mock_put.assert_not_awaited()

    async def test_deploys_when_missing(self):
        """If the document is not found, it should be PUT and compiled."""
        from prism.iris.api.documents import DocumentNotFound

        with (
            patch.object(
                testing_api,
                "get_document",
                AsyncMock(side_effect=DocumentNotFound("MCP.TestRunner.cls")),
            ),
            patch.object(
                testing_api, "put_document", AsyncMock(return_value={})
            ) as mock_put,
            patch.object(
                testing_api,
                "compile_documents",
                AsyncMock(return_value={"status": {"errors": []}}),
            ) as mock_compile,
        ):
            result = await testing_api.ensure_runner_deployed()
            assert result is True
            mock_put.assert_awaited_once()
            mock_compile.assert_awaited_once()

    async def test_compile_failure_raises(self):
        """If compile fails, RuntimeError is raised."""
        from prism.iris.api.documents import DocumentNotFound

        with (
            patch.object(
                testing_api,
                "get_document",
                AsyncMock(side_effect=DocumentNotFound("MCP.TestRunner.cls")),
            ),
            patch.object(testing_api, "put_document", AsyncMock(return_value={})),
            patch.object(
                testing_api,
                "compile_documents",
                AsyncMock(
                    return_value={"status": {"errors": [{"error": "Syntax error"}]}}
                ),
            ),
        ):
            with pytest.raises(RuntimeError, match="Syntax error"):
                await testing_api.ensure_runner_deployed()

    async def test_skips_when_auto_deploy_disabled(self):
        """When IRIS_TEST_AUTO_DEPLOY is False, skip deployment entirely."""
        with (
            patch.object(settings, "iris_test_auto_deploy", False),
            patch.object(testing_api, "get_document", AsyncMock()) as mock_get,
        ):
            result = await testing_api.ensure_runner_deployed()
            assert result is True
            mock_get.assert_not_awaited()


class TestRunTests:
    """Tests for the run_tests API function."""

    async def test_calls_sql_with_correct_query(self):
        with (
            patch.object(
                testing_api, "ensure_runner_deployed", AsyncMock(return_value=True)
            ),
            patch.object(
                testing_api,
                "execute_query",
                AsyncMock(
                    return_value={
                        "result": {"content": [{"Result": "1"}]},
                        "status": {"errors": []},
                    }
                ),
            ) as mock_sql,
        ):
            await testing_api.run_tests("MyApp.Tests.Calc")
            call_args = mock_sql.call_args
            query = call_args[0][0]
            assert "MCP.TestRunner_RunTests" in query
            assert "MyApp.Tests.Calc" in query

    async def test_passes_custom_manager(self):
        with (
            patch.object(
                testing_api, "ensure_runner_deployed", AsyncMock(return_value=True)
            ),
            patch.object(
                testing_api,
                "execute_query",
                AsyncMock(
                    return_value={
                        "result": {"content": [{"Result": "1"}]},
                        "status": {"errors": []},
                    }
                ),
            ) as mock_sql,
        ):
            await testing_api.run_tests(
                "MyApp.Tests.Calc", manager_class="TestCoverage.Manager"
            )
            query = mock_sql.call_args[0][0]
            assert "TestCoverage.Manager" in query


class TestListTestClasses:
    """Tests for test class discovery."""

    async def test_no_filter(self):
        with patch.object(
            testing_api,
            "execute_query",
            AsyncMock(
                return_value={
                    "result": {
                        "content": [
                            {"class_name": "Test.Calc", "method_name": "TestAdd"},
                        ]
                    },
                    "status": {"errors": []},
                }
            ),
        ) as mock_sql:
            await testing_api.list_test_classes()
            query = mock_sql.call_args[0][0]
            assert "%UnitTest.TestCase" in query
            assert (
                "%STARTSWITH"
                not in query.split("AND md.Name")[0].split("AND cd.Name")[-1]
            )

    async def test_with_filter(self):
        with patch.object(
            testing_api,
            "execute_query",
            AsyncMock(
                return_value={
                    "result": {"content": []},
                    "status": {"errors": []},
                }
            ),
        ) as mock_sql:
            await testing_api.list_test_classes(filter_prefix="MyApp.Tests")
            query = mock_sql.call_args[0][0]
            assert "MyApp.Tests" in query


class TestRunnerSource:
    """Tests for the helper class source content."""

    def test_source_is_valid_list_of_strings(self):
        assert isinstance(testing_api._RUNNER_SOURCE, list)
        assert all(isinstance(line, str) for line in testing_api._RUNNER_SOURCE)

    def test_source_starts_with_class_definition(self):
        assert testing_api._RUNNER_SOURCE[0].startswith("Class MCP.TestRunner")

    def test_source_ends_with_closing_brace(self):
        assert testing_api._RUNNER_SOURCE[-1] == "}"

    def test_source_contains_sqlproc(self):
        joined = "\n".join(testing_api._RUNNER_SOURCE)
        assert "SqlProc" in joined

    def test_source_contains_debug_run_test_case(self):
        joined = "\n".join(testing_api._RUNNER_SOURCE)
        assert "DebugRunTestCase" in joined
