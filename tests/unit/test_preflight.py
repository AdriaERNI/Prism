"""Unit tests for iris/sdk/preflight.py — startup connectivity check."""

from __future__ import annotations

import pytest

from prism.iris.sdk import preflight


class TestPreflightSuccess:
    """Successful preflight checks."""

    def test_success_with_namespaces(self, tmp_path, monkeypatch):
        """Successful connection logs version + namespaces, no exit."""
        from unittest.mock import MagicMock, patch

        import httpx

        # Simulate a successful JSON response with version + namespaces
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "content": {
                    "version": "IRIS for Windows (x86-64) 2023.1",
                    "namespaces": ["USER", "SAMPLES"],
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch("prism.iris.sdk.preflight.httpx.get", return_value=mock_response),
            patch("prism.iris.sdk.preflight.settings") as mock_settings,
            patch("prism.iris.sdk.preflight.logger") as mock_logger,
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
        ):
            mock_settings.iris_namespace = "USER"
            mock_settings.iris_workspace = str(tmp_path)
            preflight.preflight_check()

        # Should have logged version + workspace
        logged = " ".join(str(c) for c in mock_logger.info.call_args_list)
        assert "USER" in logged
        mock_logger.info.assert_any_call(f"Workspace: {tmp_path.resolve()}")

    def test_success_namespaces_as_dicts(self, tmp_path, monkeypatch):
        """Namespaces returned as list of dicts should be handled."""
        from unittest.mock import MagicMock, patch

        import httpx

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "content": {
                    "version": "IRIS 2024.1",
                    "namespaces": [
                        {"name": "USER"},
                        {"name": "SAMPLES"},
                    ],
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch("prism.iris.sdk.preflight.httpx.get", return_value=mock_response),
            patch("prism.iris.sdk.preflight.settings") as mock_settings,
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
        ):
            mock_settings.iris_namespace = "USER"
            mock_settings.iris_workspace = ""
            preflight.preflight_check()

    def test_success_no_namespaces(self, tmp_path):
        """Response with no namespaces should not exit."""
        from unittest.mock import MagicMock, patch

        import httpx

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"content": {"version": "IRIS 2023.1", "namespaces": []}}
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch("prism.iris.sdk.preflight.httpx.get", return_value=mock_response),
            patch("prism.iris.sdk.preflight.settings") as mock_settings,
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
        ):
            mock_settings.iris_namespace = "USER"
            mock_settings.iris_workspace = str(tmp_path)
            preflight.preflight_check()

    def test_success_no_workspace_configured(self):
        """No workspace configured should log 'not configured' message."""
        from unittest.mock import MagicMock, patch

        import httpx

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "content": {
                    "version": "IRIS 2023.1",
                    "namespaces": ["USER"],
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch("prism.iris.sdk.preflight.httpx.get", return_value=mock_response),
            patch("prism.iris.sdk.preflight.settings") as mock_settings,
            patch("prism.iris.sdk.preflight.logger") as mock_logger,
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
        ):
            mock_settings.iris_namespace = "USER"
            mock_settings.iris_workspace = ""
            preflight.preflight_check()
            mock_logger.info.assert_any_call(
                "Workspace: not configured (get/put/put_and_compile disabled)"
            )

    def test_result_is_raw_data_when_no_content_key(self):
        """If result.content is absent, the raw result dict is used."""
        from unittest.mock import MagicMock, patch

        import httpx

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"version": "IRIS 2023.1", "namespaces": ["USER"]}
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch("prism.iris.sdk.preflight.httpx.get", return_value=mock_response),
            patch("prism.iris.sdk.preflight.settings") as mock_settings,
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
        ):
            mock_settings.iris_namespace = "USER"
            mock_settings.iris_workspace = ""
            preflight.preflight_check()


class TestPreflightNamespaceValidation:
    """Namespace validation logic."""

    def test_namespace_not_found_exits(self):
        """If configured namespace not in server's list, exit(1)."""
        from unittest.mock import MagicMock, patch

        import httpx

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "content": {
                    "version": "IRIS 2023.1",
                    "namespaces": ["USER", "SAMPLES"],
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch("prism.iris.sdk.preflight.httpx.get", return_value=mock_response),
            patch("prism.iris.sdk.preflight.settings") as mock_settings,
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
            patch("prism.iris.sdk.preflight.typer.echo") as mock_echo,
            patch("prism.iris.sdk.preflight.sys.exit") as mock_exit,
        ):
            mock_settings.iris_namespace = "NONEXISTENT"
            mock_settings.iris_workspace = ""
            preflight.preflight_check()
            mock_exit.assert_called_once_with(1)
            # Should echo an error about the namespace
            echo_args = " ".join(str(c) for c in mock_echo.call_args)
            assert "NONEXISTENT" in echo_args


class TestPreflightErrorPaths:
    """Error handling — each error type should exit(1).

    preflight_check() calls sys.exit(1) which raises SystemExit. We let
    the real sys.exit raise and assert on the SystemExit instead of mocking
    it, because mocking sys.exit would cause execution to fall through to
    r.json() where ``r`` is unbound.
    """

    def test_connect_error_exits(self):
        from unittest.mock import patch

        import httpx

        with (
            patch(
                "prism.iris.sdk.preflight.httpx.get",
                side_effect=httpx.ConnectError("Connection refused"),
            ),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.typer.echo") as mock_echo,
        ):
            with pytest.raises(SystemExit) as exc_info:
                preflight.preflight_check()
            assert exc_info.value.code == 1
            echo_text = " ".join(str(c) for c in mock_echo.call_args)
            assert "Cannot connect" in echo_text

    def test_connect_timeout_exits(self):
        from unittest.mock import patch

        import httpx

        with (
            patch(
                "prism.iris.sdk.preflight.httpx.get",
                side_effect=httpx.ConnectTimeout("Timed out"),
            ),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.typer.echo") as mock_echo,
        ):
            with pytest.raises(SystemExit) as exc_info:
                preflight.preflight_check()
            assert exc_info.value.code == 1
            echo_text = " ".join(str(c) for c in mock_echo.call_args)
            assert "timed out" in echo_text.lower()

    def test_http_status_error_exits(self):
        from unittest.mock import MagicMock, patch

        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        exc = httpx.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=mock_resp)

        with (
            patch(
                "prism.iris.sdk.preflight.httpx.get",
                side_effect=exc,
            ),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.typer.echo") as mock_echo,
        ):
            with pytest.raises(SystemExit) as exc_info:
                preflight.preflight_check()
            assert exc_info.value.code == 1
            echo_text = " ".join(str(c) for c in mock_echo.call_args)
            assert "401" in echo_text

    def test_generic_request_error_exits(self):
        from unittest.mock import patch

        import httpx

        with (
            patch(
                "prism.iris.sdk.preflight.httpx.get",
                side_effect=httpx.RequestError("Some error"),
            ),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.typer.echo") as mock_echo,
        ):
            with pytest.raises(SystemExit) as exc_info:
                preflight.preflight_check()
            assert exc_info.value.code == 1
            echo_text = " ".join(str(c) for c in mock_echo.call_args)
            assert "Failed to connect" in echo_text


class TestPreflightWorkspaceCreation:
    """Workspace directory creation logic."""

    def test_workspace_dir_created(self, tmp_path):
        """If workspace path doesn't exist, it should be created."""
        from unittest.mock import MagicMock, patch

        import httpx

        ws_path = tmp_path / "subdir" / "workspace"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"content": {"version": "IRIS 2023.1", "namespaces": ["USER"]}}
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch("prism.iris.sdk.preflight.httpx.get", return_value=mock_response),
            patch("prism.iris.sdk.preflight.settings") as mock_settings,
            patch("prism.iris.sdk.preflight.logger"),
            patch("prism.iris.sdk.preflight.base_url", return_value="http://iris:52773"),
            patch("prism.iris.sdk.preflight.auth", return_value=httpx.BasicAuth("u", "p")),
        ):
            mock_settings.iris_namespace = "USER"
            mock_settings.iris_workspace = str(ws_path)
            preflight.preflight_check()

        assert ws_path.exists()
        assert ws_path.is_dir()
