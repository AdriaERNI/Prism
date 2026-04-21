"""Unit tests for the irisnative terminal backend."""

import asyncio

from unittest.mock import AsyncMock, patch

import pytest

from prism.config import IRIS_NAMESPACE
from prism.iris.sdk.terminal import (
    _parse_host,
    execute_command,
    ensure_helper_deployed,
)


class TestParseHost:
    def test_http_with_port(self):
        assert _parse_host("http://192.168.1.100:52773") == "192.168.1.100"

    def test_https_with_port(self):
        assert _parse_host("https://iris.example.com:443") == "iris.example.com"

    def test_no_port(self):
        assert _parse_host("http://localhost") == "localhost"

    def test_with_path(self):
        assert _parse_host("http://myhost:52773/some/path") == "myhost"


class TestExecuteCommand:
    async def test_calls_irisnative(self):
        with (
            patch(
                "prism.iris.sdk.terminal.ensure_helper_deployed", new_callable=AsyncMock
            ),
            patch("prism.iris.sdk.terminal._run_command_sync", return_value="hello"),
        ):
            result = await execute_command('Write "hello"')

        assert result["output"] == "hello"
        assert result["command"] == 'Write "hello"'
        assert result["namespace"] == IRIS_NAMESPACE

    async def test_namespace_override(self):
        with (
            patch(
                "prism.iris.sdk.terminal.ensure_helper_deployed", new_callable=AsyncMock
            ),
            patch("prism.iris.sdk.terminal._run_command_sync", return_value=""),
        ):
            result = await execute_command("Write 1", namespace="MYNS")

        assert result["namespace"] == "MYNS"

    async def test_error_propagates(self):
        with (
            patch(
                "prism.iris.sdk.terminal.ensure_helper_deployed", new_callable=AsyncMock
            ),
            patch(
                "prism.iris.sdk.terminal._run_command_sync",
                side_effect=RuntimeError("connection lost"),
            ),
        ):
            with pytest.raises(RuntimeError, match="connection lost"):
                await execute_command("BadCommand")

    async def test_timeout_includes_helper_deploy_time(self):
        async def _slow_deploy():
            await asyncio.sleep(0.05)

        with (
            patch(
                "prism.iris.sdk.terminal.ensure_helper_deployed",
                new=AsyncMock(side_effect=_slow_deploy),
            ),
            patch(
                "prism.iris.sdk.terminal._run_command_sync", return_value="ok"
            ) as run,
        ):
            with pytest.raises(TimeoutError):
                await execute_command('Write "hello"', timeout=0.01)

        run.assert_not_called()


class TestEnsureHelperDeployed:
    async def test_skips_if_already_deployed(self):
        with patch("prism.iris.sdk.terminal._helper_deployed", True):
            # Should return immediately without calling any API
            await ensure_helper_deployed()

    async def test_deploys_when_doc_missing(self):
        import prism.iris.sdk.terminal as mod

        original = mod._helper_deployed
        mod._helper_deployed = False
        try:
            mock_get = AsyncMock(side_effect=Exception("not found"))
            mock_put = AsyncMock()
            mock_compile = AsyncMock()

            with (
                patch("prism.iris.api.documents.get_document", mock_get),
                patch("prism.iris.api.documents.put_document", mock_put),
                patch("prism.iris.api.compile.compile_documents", mock_compile),
            ):
                await ensure_helper_deployed()

            mock_put.assert_called_once()
            mock_compile.assert_called_once()
            assert mod._helper_deployed is True
        finally:
            mod._helper_deployed = original

    async def test_skips_deploy_when_doc_exists(self):
        import prism.iris.sdk.terminal as mod

        original = mod._helper_deployed
        mod._helper_deployed = False
        try:
            mock_get = AsyncMock(return_value={"result": {"content": []}})
            mock_put = AsyncMock()

            with (
                patch("prism.iris.api.documents.get_document", mock_get),
                patch("prism.iris.api.documents.put_document", mock_put),
            ):
                await ensure_helper_deployed()

            mock_put.assert_not_called()
            assert mod._helper_deployed is True
        finally:
            mod._helper_deployed = original
