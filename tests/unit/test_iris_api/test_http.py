"""Tests for the shared HTTP client lifecycle in prism.iris.sdk.http.

Verifies that ``close_client()`` properly closes the shared AsyncClient
singleton and resets the module-level state so a fresh client can be created.
"""

from __future__ import annotations

import httpx
import pytest

from prism.iris.sdk import http as http_sdk


@pytest.fixture(autouse=True)
def _reset_client():
    """Ensure the module-level _client is reset before and after each test."""
    http_sdk._default_client = None
    yield
    # Close any leftover client
    import asyncio

    if http_sdk._default_client is not None and not http_sdk._default_client.is_closed:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(http_sdk._default_client.aclose())
        loop.close()
    http_sdk._default_client = None


class TestClient:
    def test_client_returns_singleton(self):
        """client() returns the same instance on repeated calls."""
        c1 = http_sdk.client()
        c2 = http_sdk.client()
        assert c1 is c2

    def test_client_is_async_client(self):
        assert isinstance(http_sdk.client(), httpx.AsyncClient)

    def test_client_recreated_after_close(self):
        """After close_client(), client() creates a new instance."""
        c1 = http_sdk.client()
        http_sdk._default_client = None  # simulate closed
        c2 = http_sdk.client()
        assert c1 is not c2


class TestCloseClient:
    """close_client() must close the shared client and reset state."""

    async def test_close_client_closes_existing(self):
        c = http_sdk.client()
        assert not c.is_closed
        await http_sdk.close_client()
        assert c.is_closed

    async def test_close_client_resets_module_state(self):
        """After close_client(), _client is None."""
        http_sdk.client()
        assert http_sdk._default_client is not None
        await http_sdk.close_client()
        assert http_sdk._default_client is None

    async def test_close_client_idempotent(self):
        """Calling close_client() when no client exists is a no-op."""
        # No client created yet
        assert http_sdk._default_client is None
        await http_sdk.close_client()  # should not raise
        assert http_sdk._default_client is None

    async def test_close_client_called_twice(self):
        """Calling close_client() twice does not error."""
        http_sdk.client()
        await http_sdk.close_client()
        await http_sdk.close_client()  # second call — no-op
        assert http_sdk._default_client is None

    async def test_client_recreated_after_close(self):
        """A new client can be created after close_client()."""
        c1 = http_sdk.client()
        await http_sdk.close_client()
        c2 = http_sdk.client()
        assert c1 is not c2
        assert not c2.is_closed
        await http_sdk.close_client()


class TestClientIsClosedCheck:
    """client() recreates the client if the existing one was closed externally."""

    async def test_client_recreates_if_closed(self):
        c1 = http_sdk.client()
        await c1.aclose()
        assert c1.is_closed
        # client() should detect the closed state and create a new one
        c2 = http_sdk.client()
        assert c1 is not c2
        assert not c2.is_closed
        await http_sdk.close_client()
