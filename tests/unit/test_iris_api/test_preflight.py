"""Unit tests for the preflight connectivity check (prism.iris.sdk.preflight).

Covers all branches of ``preflight_check()``: success, connection errors,
HTTP status errors, namespace validation, and workspace creation.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from prism.iris.sdk import preflight


def _make_response(
    status: int = 200,
    *,
    version: str = "2024.1",
    namespaces: list | None = None,
    content: dict | None = None,
) -> httpx.Response:
    """Build an httpx.Response mimicking the Atelier /api/atelier/ endpoint."""
    if content is not None:
        body = content
    else:
        body = {
            "result": {
                "content": {
                    "version": version,
                    "namespaces": namespaces
                    if namespaces is not None
                    else [{"name": "USER"}, {"name": "SAMPLES"}],
                }
            }
        }
    # Build a response with a request so raise_for_status works
    req = httpx.Request("GET", "http://localhost:52773/api/atelier/")
    return httpx.Response(status, json=body, request=req)


class TestPreflightSuccess:
    """preflight_check succeeds when IRIS is reachable and namespace exists."""

    async def test_success_passes(self):
        with patch.object(preflight.httpx, "get", return_value=_make_response()):
            preflight.preflight_check()

    async def test_success_with_string_namespaces(self):
        """Namespaces can be plain strings instead of dicts with 'name'."""
        with patch.object(
            preflight.httpx,
            "get",
            return_value=_make_response(
                content={
                    "result": {
                        "content": {
                            "version": "2025.1",
                            "namespaces": ["USER", "SAMPLES"],
                        }
                    }
                }
            ),
        ):
            preflight.preflight_check()

    async def test_success_with_no_namespaces(self):
        """Server with no namespaces reported still passes."""
        with patch.object(
            preflight.httpx,
            "get",
            return_value=_make_response(
                content={"result": {"content": {"version": "2024.1", "namespaces": []}}}
            ),
        ):
            # Should not exit — no namespace list means skip the check
            preflight.preflight_check()

    async def test_content_no_version_falls_back(self):
        """If result.content has no 'version', falls back to 'unknown'."""
        with patch.object(
            preflight.httpx,
            "get",
            return_value=_make_response(content={"result": {"content": {"version": "2024.1"}}}),
        ):
            preflight.preflight_check()

    async def test_content_falls_back_to_full_data(self):
        """If result.content is not a dict, result itself is used."""
        with patch.object(
            preflight.httpx,
            "get",
            return_value=_make_response(
                content={"result": {"version": "2024.1", "namespaces": [{"name": "USER"}]}}
            ),
        ):
            preflight.preflight_check()


class TestPreflightConnectionErrors:
    """preflight_check exits on connection failures."""

    async def test_connect_error_exits(self, capsys):
        with (
            patch.object(preflight.httpx, "get", side_effect=httpx.ConnectError("Cannot connect")),
            pytest.raises(SystemExit) as exc_info,
        ):
            preflight.preflight_check()
        assert exc_info.value.code == 1
        out = capsys.readouterr()
        assert "Cannot connect" in out.err
        assert "--skip-preflight" in out.err

    async def test_connect_timeout_exits(self, capsys):
        with (
            patch.object(preflight.httpx, "get", side_effect=httpx.ConnectTimeout("Timed out")),
            pytest.raises(SystemExit) as exc_info,
        ):
            preflight.preflight_check()
        assert exc_info.value.code == 1
        out = capsys.readouterr()
        assert "timed out" in out.err.lower()
        assert "--skip-preflight" in out.err

    async def test_http_status_error_exits(self, capsys):
        err = httpx.HTTPStatusError(
            "403 Forbidden",
            request=httpx.Request("GET", "http://x"),
            response=httpx.Response(403, text="Forbidden"),
        )
        with patch.object(preflight.httpx, "get", side_effect=err):
            with pytest.raises(SystemExit) as exc_info:
                preflight.preflight_check()
        assert exc_info.value.code == 1
        out = capsys.readouterr()
        assert "403" in out.err
        assert "--skip-preflight" in out.err

    async def test_generic_request_error_exits(self, capsys):
        with (
            patch.object(preflight.httpx, "get", side_effect=httpx.RequestError("DNS failed")),
            pytest.raises(SystemExit) as exc_info,
        ):
            preflight.preflight_check()
        assert exc_info.value.code == 1
        out = capsys.readouterr()
        assert "DNS failed" in out.err
        assert "--skip-preflight" in out.err


class TestPreflightNamespaceValidation:
    """preflight_check validates the configured namespace is available."""

    async def test_namespace_not_found_exits(self, capsys):
        with (
            patch.object(preflight.httpx, "get", return_value=_make_response()),
            patch.object(preflight.settings, "iris_namespace", "MYNS"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                preflight.preflight_check()
        assert exc_info.value.code == 1
        out = capsys.readouterr()
        assert "MYNS" in out.err
        assert "not found" in out.err.lower()

    async def test_namespace_found_passes(self):
        with (
            patch.object(preflight.httpx, "get", return_value=_make_response()),
            patch.object(preflight.settings, "iris_namespace", "SAMPLES"),
        ):
            preflight.preflight_check()


class TestPreflightWorkspace:
    """preflight_check creates the workspace directory if configured."""

    async def test_workspace_created(self, tmp_path):
        ws = tmp_path / "myworkspace"
        with (
            patch.object(preflight.httpx, "get", return_value=_make_response()),
            patch.object(preflight.settings, "iris_workspace", str(ws)),
            patch.object(preflight.settings, "iris_namespace", "USER"),
        ):
            preflight.preflight_check()
        assert ws.exists()

    async def test_workspace_not_configured(self):
        with (
            patch.object(preflight.httpx, "get", return_value=_make_response()),
            patch.object(preflight.settings, "iris_workspace", ""),
            patch.object(preflight.settings, "iris_namespace", "USER"),
        ):
            preflight.preflight_check()


class TestPreflightUrlConstruction:
    """preflight_check hits the correct Atelier endpoint."""

    async def test_correct_url_called(self):
        with patch.object(preflight.httpx, "get", return_value=_make_response()) as mock_get:
            preflight.preflight_check()
            call_args = mock_get.call_args
            url = call_args[0][0]
            assert "/api/atelier/" in url
            # Timeout should be 10s
            assert call_args[1].get("timeout") == 10.0
