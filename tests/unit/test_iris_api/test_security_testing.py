"""Regression tests for SQL injection vulnerabilities in testing.py.

These tests verify that user-supplied values (test class names, method names,
filter prefixes, limits) are validated/sanitised before being interpolated
into SQL queries sent to the IRIS Atelier API.

The Atelier /action/query endpoint accepts a single SQL string and does NOT
support bind parameters, so inputs must be validated against an allowlist of
safe identifier characters.
"""

from __future__ import annotations

import pytest

from prism.iris.api import testing as testing_api

# ── Helpers ──────────────────────────────────────────────────────────────────


def _extract_query(mock_sql) -> str:
    """Extract the SQL query string from a mocked execute_query call."""
    return mock_sql.call_args[0][0]


# ── Identifier validation ────────────────────────────────────────────────────


class TestIdentifierValidation:
    """Test the _validate_identifier / _validate_class_name helpers."""

    @pytest.mark.parametrize(
        "name",
        [
            "MyApp.Tests.Calc",
            "Test.MCPSampleTest",
            "MCP.TestRunner",
            "Simple",
            "A",
            "Package.SubPackage.Class123",
        ],
    )
    def test_valid_class_names_accepted(self, name):
        assert testing_api._validate_class_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "TestAddition",
            "TestMethod",
            "Test_Method_123",
            "Run",
        ],
    )
    def test_valid_method_names_accepted(self, name):
        assert testing_api._validate_identifier(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "MyApp'; DROP TABLE %UnitTest_Result.TestMethod;--",
            "x' OR '1'='1",
            'test";--',
            "bad\x00null",
            "line\nbreak",
            "tab\there",
            "back`tick",
            "semi;colon",
        ],
    )
    def test_malicious_class_names_rejected(self, name):
        with pytest.raises(ValueError, match="invalid"):
            testing_api._validate_class_name(name)

    @pytest.mark.parametrize(
        "name",
        [
            "x' OR '1'='1",
            'test";--',
            "bad\x00null",
            "semi;colon",
        ],
    )
    def test_malicious_method_names_rejected(self, name):
        with pytest.raises(ValueError, match="invalid"):
            testing_api._validate_identifier(name)


# ── run_tests SQL injection ──────────────────────────────────────────────────


class TestRunTestsInjection:
    """run_tests must reject SQL-injection payloads in test_class/test_method."""

    async def test_malicious_test_class_rejected(self):
        from unittest.mock import AsyncMock, patch

        with (
            patch.object(testing_api, "ensure_runner_deployed", AsyncMock(return_value=True)),
            patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql,
        ):
            with pytest.raises(ValueError):
                await testing_api.run_tests("x'; DROP TABLE foo;--")
            mock_sql.assert_not_awaited()

    async def test_malicious_test_method_rejected(self):
        from unittest.mock import AsyncMock, patch

        with (
            patch.object(testing_api, "ensure_runner_deployed", AsyncMock(return_value=True)),
            patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql,
        ):
            with pytest.raises(ValueError):
                await testing_api.run_tests(
                    "MyApp.Tests.Calc",
                    test_method="x'); DROP TABLE foo;--",
                )
            mock_sql.assert_not_awaited()

    async def test_malicious_manager_class_rejected(self):
        from unittest.mock import AsyncMock, patch

        with (
            patch.object(testing_api, "ensure_runner_deployed", AsyncMock(return_value=True)),
            patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql,
        ):
            with pytest.raises(ValueError):
                await testing_api.run_tests(
                    "MyApp.Tests.Calc",
                    manager_class="x'; DROP TABLE foo;--",
                )
            mock_sql.assert_not_awaited()

    async def test_valid_class_still_works(self):
        from unittest.mock import AsyncMock, patch

        with (
            patch.object(testing_api, "ensure_runner_deployed", AsyncMock(return_value=True)),
            patch.object(
                testing_api,
                "execute_query",
                AsyncMock(return_value={"result": {"content": [{"Result": "1"}]}}),
            ) as mock_sql,
        ):
            await testing_api.run_tests("MyApp.Tests.Calc")
            query = _extract_query(mock_sql)
            assert "MyApp.Tests.Calc" in query
            # Ensure no injection artefacts
            assert "DROP" not in query.upper()
            assert "--" not in query


# ── get_latest_results SQL injection ─────────────────────────────────────────


class TestGetLatestResultsInjection:
    """get_latest_results must reject injection in test_class."""

    async def test_malicious_class_rejected(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql:
            with pytest.raises(ValueError):
                await testing_api.get_latest_results("x' OR '1'='1")
            mock_sql.assert_not_awaited()

    async def test_valid_class_still_works(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(
            testing_api,
            "execute_query",
            AsyncMock(return_value={"result": {"content": []}}),
        ) as mock_sql:
            await testing_api.get_latest_results("MyApp.Tests.Calc")
            query = _extract_query(mock_sql)
            assert "MyApp.Tests.Calc" in query
            # No injection artefacts leaked
            assert " OR " not in query.upper()
            assert "--" not in query


# ── get_assertions SQL injection ─────────────────────────────────────────────


class TestGetAssertionsInjection:
    """get_assertions must reject injection in test_class and test_method."""

    async def test_malicious_class_rejected(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql:
            with pytest.raises(ValueError):
                await testing_api.get_assertions("x'; DROP TABLE foo;--", "TestMethod")
            mock_sql.assert_not_awaited()

    async def test_malicious_method_rejected(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql:
            with pytest.raises(ValueError):
                await testing_api.get_assertions("MyApp.Tests.Calc", "x'; DROP TABLE foo;--")
            mock_sql.assert_not_awaited()


# ── get_test_history SQL injection ──────────────────────────────────────────


class TestGetTestHistoryInjection:
    """get_test_history must reject injection in test_class."""

    async def test_malicious_class_rejected(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql:
            with pytest.raises(ValueError):
                await testing_api.get_test_history("x' OR '1'='1")
            mock_sql.assert_not_awaited()

    async def test_valid_class_still_works(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(
            testing_api,
            "execute_query",
            AsyncMock(return_value={"result": {"content": []}}),
        ) as mock_sql:
            await testing_api.get_test_history("MyApp.Tests.Calc")
            query = _extract_query(mock_sql)
            assert "MyApp.Tests.Calc" in query

    async def test_limit_must_be_int(self):
        """limit must be an integer, not a string injection vector."""
        from unittest.mock import AsyncMock, patch

        with patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql:
            with pytest.raises((ValueError, TypeError)):
                await testing_api.get_test_history(limit="10; DROP TABLE foo")  # type: ignore[arg-type]
            mock_sql.assert_not_awaited()


# ── list_test_classes SQL injection ──────────────────────────────────────────


class TestListTestClassesInjection:
    """list_test_classes must reject injection in filter_prefix."""

    async def test_malicious_prefix_rejected(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(testing_api, "execute_query", AsyncMock()) as mock_sql:
            with pytest.raises(ValueError):
                await testing_api.list_test_classes(filter_prefix="x'; DROP TABLE--")
            mock_sql.assert_not_awaited()

    async def test_valid_prefix_still_works(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(
            testing_api,
            "execute_query",
            AsyncMock(return_value={"result": {"content": []}}),
        ) as mock_sql:
            await testing_api.list_test_classes(filter_prefix="MyApp.Tests")
            query = _extract_query(mock_sql)
            assert "MyApp.Tests" in query
