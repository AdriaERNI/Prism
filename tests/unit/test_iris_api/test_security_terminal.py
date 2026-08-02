"""Regression tests for broad exception swallowing in terminal SDK.

These verify that ``ensure_helper_deployed()`` only swallows
``DocumentNotFound`` (the expected "not yet deployed" signal) and lets
real errors (HTTP failures, auth errors, programming bugs) propagate
instead of being silently masked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from prism.iris.api.documents import DocumentNotFound
from prism.iris.sdk.terminal import ensure_helper_deployed
from prism.settings import settings


class TestEnsureHelperDeployedExceptionHandling:
    """ensure_helper_deployed must not swallow non-DocumentNotFound exceptions."""

    async def test_http_error_propagates(self):
        """An HTTP 500 from get_document must propagate, not be swallowed."""
        import prism.iris.sdk.terminal as mod

        http_err = httpx.HTTPStatusError(
            "Server error",
            request=httpx.Request("GET", "http://x"),
            response=httpx.Response(500, text="Server Error"),
        )
        with patch.object(mod, "_deployed_namespaces", set()):
            with (
                patch(
                    "prism.iris.api.documents.get_document",
                    AsyncMock(side_effect=http_err),
                ),
                patch("prism.iris.api.documents.put_document", AsyncMock()) as mock_put,
                patch("prism.iris.api.compile.compile_documents", AsyncMock()) as mock_compile,
                pytest.raises(httpx.HTTPStatusError, match="Server error"),
            ):
                await ensure_helper_deployed()

            # The HTTP error must NOT trigger a deploy
            mock_put.assert_not_called()
            mock_compile.assert_not_called()

    async def test_auth_error_propagates(self):
        """An HTTP 401 (auth failure) must propagate, not be swallowed."""
        import prism.iris.sdk.terminal as mod

        auth_err = httpx.HTTPStatusError(
            "Unauthorized",
            request=httpx.Request("GET", "http://x"),
            response=httpx.Response(401, text="Unauthorized"),
        )
        with patch.object(mod, "_deployed_namespaces", set()):
            with (
                patch(
                    "prism.iris.api.documents.get_document",
                    AsyncMock(side_effect=auth_err),
                ),
                patch("prism.iris.api.documents.put_document", AsyncMock()) as mock_put,
                pytest.raises(httpx.HTTPStatusError, match="Unauthorized"),
            ):
                await ensure_helper_deployed()

            mock_put.assert_not_called()

    async def test_connection_error_propagates(self):
        """A connection error must propagate, not be swallowed."""
        import prism.iris.sdk.terminal as mod

        with patch.object(mod, "_deployed_namespaces", set()):
            with (
                patch(
                    "prism.iris.api.documents.get_document",
                    AsyncMock(side_effect=httpx.ConnectError("Connection refused")),
                ),
                patch("prism.iris.api.documents.put_document", AsyncMock()) as mock_put,
                pytest.raises(httpx.ConnectError, match="Connection refused"),
            ):
                await ensure_helper_deployed()

            mock_put.assert_not_called()

    async def test_document_not_found_triggers_deploy(self):
        """DocumentNotFound is the expected signal — it should trigger deploy."""
        import prism.iris.sdk.terminal as mod

        with patch.object(mod, "_deployed_namespaces", set()):
            with (
                patch(
                    "prism.iris.api.documents.get_document",
                    AsyncMock(side_effect=DocumentNotFound("MCP.Terminal.cls")),
                ),
                patch("prism.iris.api.documents.put_document", AsyncMock()) as mock_put,
                patch("prism.iris.api.compile.compile_documents", AsyncMock()) as mock_compile,
            ):
                await ensure_helper_deployed()

            mock_put.assert_called_once()
            mock_compile.assert_called_once()
            assert settings.iris_namespace in mod._deployed_namespaces

    async def test_generic_runtime_error_propagates(self):
        """A generic RuntimeError must propagate, not be swallowed."""
        import prism.iris.sdk.terminal as mod

        with patch.object(mod, "_deployed_namespaces", set()):
            with (
                patch(
                    "prism.iris.api.documents.get_document",
                    AsyncMock(side_effect=RuntimeError("unexpected bug")),
                ),
                patch("prism.iris.api.documents.put_document", AsyncMock()) as mock_put,
                pytest.raises(RuntimeError, match="unexpected bug"),
            ):
                await ensure_helper_deployed()

            mock_put.assert_not_called()
