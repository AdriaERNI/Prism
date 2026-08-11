"""Unit tests for per-call IRIS connection target overrides."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from prism.iris.sdk.connection import (
    resolve_base_url,
    resolve_host,
    resolve_port,
)
from prism.settings import settings

# ── resolve_base_url ────────────────────────────────────────────────


class TestResolveBaseUrl:
    def test_no_override_returns_settings_url(self):
        """When no target is provided, the settings base URL is used."""
        result = resolve_base_url(None, None)
        assert result == settings.iris_base_url.rstrip("/")

    def test_host_override_replaces_host(self):
        """When target_host is provided, only the host changes."""
        result = resolve_base_url("10.0.0.50", None)
        assert "10.0.0.50" in result
        # Port should still come from settings
        from urllib.parse import urlparse

        parsed = urlparse(result)
        # settings.iris_base_url may or may not have a port
        # but the host should be overridden
        assert parsed.hostname == "10.0.0.50"

    def test_port_override_replaces_port(self):
        """When target_port is provided, only the port changes."""
        result = resolve_base_url(None, 8080)
        from urllib.parse import urlparse

        parsed = urlparse(result)
        assert parsed.port == 8080

    def test_both_override_replaces_both(self):
        """When both host and port are provided, both are overridden."""
        result = resolve_base_url("192.168.1.100", 52774)
        from urllib.parse import urlparse

        parsed = urlparse(result)
        assert parsed.hostname == "192.168.1.100"
        assert parsed.port == 52774

    def test_preserves_scheme(self):
        """The scheme (http/https) is preserved from settings."""
        result = resolve_base_url("10.0.0.50", 8080)
        from urllib.parse import urlparse

        original = urlparse(settings.iris_base_url)
        parsed = urlparse(result)
        assert parsed.scheme == original.scheme

    def test_strips_trailing_slash(self):
        """The result has no trailing slash."""
        result = resolve_base_url("10.0.0.50", 8080)
        assert not result.endswith("/")


# ── resolve_host ────────────────────────────────────────────────────


class TestResolveHost:
    def test_no_override_returns_settings_host(self):
        result = resolve_host(None)
        from urllib.parse import urlparse

        expected = urlparse(settings.iris_base_url).hostname
        assert result == expected

    def test_override_returns_target_host(self):
        result = resolve_host("10.0.0.50")
        assert result == "10.0.0.50"

    def test_override_strips_whitespace(self):
        result = resolve_host("  10.0.0.50  ")
        assert result == "10.0.0.50"

    def test_empty_string_falls_back_to_settings(self):
        result = resolve_host("")
        from urllib.parse import urlparse

        expected = urlparse(settings.iris_base_url).hostname
        assert result == expected

    def test_none_falls_back_to_settings(self):
        result = resolve_host(None)
        from urllib.parse import urlparse

        expected = urlparse(settings.iris_base_url).hostname
        assert result == expected


# ── resolve_port ────────────────────────────────────────────────────


class TestResolvePort:
    def test_no_override_returns_settings_port(self):
        result = resolve_port(None)
        # settings.iris_base_url typically has a port
        from urllib.parse import urlparse

        expected = urlparse(settings.iris_base_url).port
        if expected is None:
            # If no port in URL, default to 80/443 based on scheme
            assert result in (80, 443)
        else:
            assert result == expected

    def test_override_returns_target_port(self):
        result = resolve_port(8080)
        assert result == 8080


# ── api_url with target ─────────────────────────────────────────────


class TestApiUrlWithTarget:
    def test_api_url_uses_override_host(self):
        from prism.iris.sdk.http import api_url

        url = api_url("USER", target_host="10.0.0.50")
        assert "10.0.0.50" in url

    def test_api_url_uses_override_port(self):
        from prism.iris.sdk.http import api_url

        url = api_url("USER", target_port=8080)
        assert ":8080" in url

    def test_api_url_no_override_matches_original(self):
        from prism.iris.sdk.http import api_url

        url = api_url("USER")
        # Should contain the settings base URL
        assert settings.iris_base_url.rstrip("/") in url

    def test_api_url_namespace_encoding_preserved(self):
        """%SYS namespace should still be encoded to %25SYS."""
        from prism.iris.sdk.http import api_url

        url = api_url("%SYS", target_host="10.0.0.50")
        assert "%25SYS" in url


# ── base_url with target ────────────────────────────────────────────


class TestBaseUrlWithTarget:
    def test_base_url_uses_override(self):
        from prism.iris.sdk.http import base_url

        result = base_url(target_host="10.0.0.50", target_port=8080)
        assert "10.0.0.50" in result
        assert ":8080" in result

    def test_base_url_no_override_matches_settings(self):
        from prism.iris.sdk.http import base_url

        result = base_url()
        assert result == settings.iris_base_url.rstrip("/")


# ── client() with target ───────────────────────────────────────────


class TestClientWithTarget:
    def test_client_no_override_returns_default_client(self):
        """Without overrides, the shared default client is returned."""
        from prism.iris.sdk.http import client

        c1 = client()
        c2 = client()
        assert c1 is c2

    def test_client_with_override_returns_different_client(self):
        """With overrides, a separate cached client is returned."""
        from prism.iris.sdk.http import client

        default = client()
        targeted = client(target_host="10.0.0.50", target_port=8080)
        assert targeted is not default

    def test_client_same_target_returns_cached_client(self):
        """Same host:port returns the same cached client."""
        from prism.iris.sdk.http import client

        c1 = client(target_host="10.0.0.50", target_port=8080)
        c2 = client(target_host="10.0.0.50", target_port=8080)
        assert c1 is c2

    def test_client_different_targets_return_different_clients(self):
        """Different targets return different clients."""
        from prism.iris.sdk.http import client

        c1 = client(target_host="10.0.0.50", target_port=8080)
        c2 = client(target_host="10.0.0.51", target_port=8080)
        assert c1 is not c2


# ── SQL tool with target ────────────────────────────────────────────


class TestSqlToolWithTarget:
    async def test_execute_sql_passes_target_to_api(self):
        """execute_sql passes target_host/target_port to the API layer."""
        from prism.iris.api import sql as sql_api

        def handler(request):
            return httpx.Response(
                200,
                json={
                    "status": {"errors": []},
                    "result": {"content": [{"col1": "val1"}]},
                    "console": [],
                },
            )

        captured_kwargs = {}

        async def mock_execute(query, namespace=None, **kwargs):
            captured_kwargs.update(kwargs)
            return {
                "status": {"errors": []},
                "result": {"content": [{"col1": "val1"}]},
                "console": [],
            }

        with patch.object(sql_api, "execute_query", mock_execute):
            from prism.mcp.sql import execute_sql

            await execute_sql(
                "SELECT 1",
                target_host="10.0.0.50",
                target_port=8080,
            )

        assert captured_kwargs.get("target_host") == "10.0.0.50"
        assert captured_kwargs.get("target_port") == 8080


# ─– Server info tool with target ────────────────────────────────────


class TestServerInfoWithTarget:
    async def test_get_server_info_passes_target_to_api(self):
        """get_server_info passes target_host/target_port to the API layer."""
        captured_kwargs = {}
        from prism.iris.api import server_info as info_api

        async def mock_get_server_info(**kwargs):
            captured_kwargs.update(kwargs)
            return {"result": {"content": {"version": "2025.1", "api": 6, "namespaces": ["USER"]}}}

        with patch.object(info_api, "get_server_info", mock_get_server_info):
            from prism.mcp.server_info import get_server_info

            result = await get_server_info(
                target_host="10.0.0.50",
                target_port=52774,
            )

        assert captured_kwargs.get("target_host") == "10.0.0.50"
        assert captured_kwargs.get("target_port") == 52774
        assert result["version"] == "2025.1"


# ── Decorator annotations ──────────────────────────────────────────


class TestLoggedToolAnnotations:
    def test_annotations_stored_in_mcp_tool_kwargs(self):
        """@logged_tool(annotations={...}) stores annotations for FastMCP registration."""
        from prism.mcp._decorator import logged_tool

        @logged_tool(annotations={"readOnlyHint": True, "destructiveHint": False})
        async def my_tool() -> dict:
            """test"""
            return {"ok": True}

        assert hasattr(my_tool, "_mcp_tool_kwargs")
        assert "annotations" in my_tool._mcp_tool_kwargs
        assert my_tool._mcp_tool_kwargs["annotations"]["readOnlyHint"] is True

    def test_no_annotations_does_not_set_key(self):
        """@logged_tool without annotations doesn't add annotations key."""
        from prism.mcp._decorator import logged_tool

        @logged_tool
        async def my_tool() -> dict:
            """test"""
            return {"ok": True}

        assert hasattr(my_tool, "_mcp_tool_kwargs")
        assert "annotations" not in my_tool._mcp_tool_kwargs

    def test_task_and_annotations_combined(self):
        """@logged_tool(task=True, annotations={...}) stores both."""
        from prism.mcp._decorator import logged_tool

        @logged_tool(task=True, annotations={"readOnlyHint": False})
        async def my_tool() -> dict:
            """test"""
            return {"ok": True}

        assert my_tool._mcp_tool_kwargs.get("task") is True
        assert "annotations" in my_tool._mcp_tool_kwargs


# ── CHARACTER_LIMIT ────────────────────────────────────────────────


class TestCharacterLimit:
    def test_sql_module_has_character_limit(self):
        from prism.mcp.sql import CHARACTER_LIMIT

        assert CHARACTER_LIMIT == 25000

    def test_documents_module_has_character_limit(self):
        from prism.mcp.documents import CHARACTER_LIMIT

        assert CHARACTER_LIMIT == 25000


# ── Pagination on list_documents ───────────────────────────────────


class TestListDocumentsPagination:
    async def test_pagination_returns_has_more_and_next_offset(self):
        """list_documents returns pagination metadata."""
        from prism.iris.api import documents as docs_api

        # Generate 100 fake documents
        fake_content = [
            {"name": f"App.Class{i}.cls", "cat": "CLS", "ts": "2024-01-01", "db": "USER"}
            for i in range(100)
        ]

        async def mock_list_documents(*args, **kwargs):
            return {"result": {"content": fake_content}}

        with patch.object(docs_api, "list_documents", mock_list_documents):
            from prism.mcp.documents import list_documents

            result = await list_documents(limit=10, offset=0)

        assert result["count"] == 10
        assert result["total"] == 100
        assert result["offset"] == 0
        assert result["has_more"] is True
        assert result["next_offset"] == 10

    async def test_pagination_at_end_returns_has_more_false(self):
        """When all results are exhausted, has_more is False and next_offset is None."""
        from prism.iris.api import documents as docs_api

        fake_content = [
            {"name": f"App.Class{i}.cls", "cat": "CLS", "ts": "2024-01-01", "db": "USER"}
            for i in range(15)
        ]

        async def mock_list_documents(*args, **kwargs):
            return {"result": {"content": fake_content}}

        with patch.object(docs_api, "list_documents", mock_list_documents):
            from prism.mcp.documents import list_documents

            result = await list_documents(limit=10, offset=10)

        assert result["count"] == 5
        assert result["total"] == 15
        assert result["offset"] == 10
        assert result["has_more"] is False
        assert result["next_offset"] is None
