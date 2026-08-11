"""Regression tests for SQL injection in the code index API.

These tests verify that user-supplied ``filter_prefix`` values passed to
``build_index()`` are validated before being interpolated into the SQL
``LIKE`` clause, preventing SQL injection.

The Atelier /action/query endpoint accepts a single SQL string and does NOT
support bind parameters, so inputs must be validated against an allowlist
of safe identifier characters.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from prism.iris.api import index as index_api


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestBuildIndexPrefixValidation:
    """build_index must reject injection in filter_prefix."""

    async def test_malicious_prefix_rejected(self):
        """A filter_prefix containing SQL metacharacters is rejected."""
        with (
            patch.object(
                index_api,
                "client",
                lambda *a, **kw: _mock_client(
                    lambda r: httpx.Response(200, json={"result": {"content": []}})
                ),
            ),
            pytest.raises(ValueError, match="invalid"),
        ):
            await index_api.build_index(filter_prefix="x' OR '1'='1")

    async def test_prefix_with_semicolon_rejected(self):
        with (
            patch.object(
                index_api,
                "client",
                lambda *a, **kw: _mock_client(
                    lambda r: httpx.Response(200, json={"result": {"content": []}})
                ),
            ),
            pytest.raises(ValueError, match="invalid"),
        ):
            await index_api.build_index(filter_prefix="x; DROP TABLE--")

    async def test_prefix_with_control_chars_rejected(self):
        with (
            patch.object(
                index_api,
                "client",
                lambda *a, **kw: _mock_client(
                    lambda r: httpx.Response(200, json={"result": {"content": []}})
                ),
            ),
            pytest.raises(ValueError, match="invalid"),
        ):
            await index_api.build_index(filter_prefix="bad\x00null")

    async def test_valid_prefix_still_works(self):
        """A valid prefix like 'MyApp' is accepted and appears in the query."""

        captured_queries: list[str] = []

        def handler(request):
            body = request.content.decode()
            captured_queries.append(body)
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": []},
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: _mock_client(handler)):
            result = await index_api.build_index(filter_prefix="MyApp")

        assert result["statistics"]["classes"] == 0
        # The valid prefix should appear in at least one of the queries
        assert any("MyApp" in q for q in captured_queries)
        # No injection artefacts
        assert not any(" OR " in q.upper() for q in captured_queries)
        assert not any("--" in q for q in captured_queries)

    async def test_prefix_with_underscore_allowed(self):
        """Underscores are valid in IRIS class names and should be accepted."""

        def handler(request):
            return httpx.Response(
                200,
                json={
                    "status": {"errors": [], "summary": ""},
                    "console": [],
                    "result": {"content": []},
                },
            )

        with patch.object(index_api, "client", lambda *a, **kw: _mock_client(handler)):
            result = await index_api.build_index(filter_prefix="My_App")

        assert result["statistics"]["classes"] == 0

    async def test_prefix_with_percent_injection_rejected(self):
        """A prefix trying to exploit LIKE wildcards with quotes is rejected."""

        def handler(request):
            return httpx.Response(200, json={"result": {"content": []}})

        with patch.object(index_api, "client", lambda *a, **kw: _mock_client(handler)):
            with pytest.raises(ValueError, match="invalid"):
                await index_api.build_index(filter_prefix="%' OR '1'='1")
