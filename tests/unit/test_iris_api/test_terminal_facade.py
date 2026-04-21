"""Unit tests for the terminal facade dispatch logic."""

from unittest.mock import AsyncMock, patch

from prism.config import IRIS_NAMESPACE


class TestFacadeDispatch:
    async def test_native_method_delegates_to_sdk(self):
        mock_native_exec = AsyncMock(
            return_value={
                "namespace": "USER",
                "command": "Write 1",
                "output": "1",
                "prompt": "",
            }
        )

        with (
            patch("prism.iris.api.terminal.IRIS_TERMINAL_METHOD", "native"),
            patch("prism.iris.sdk.terminal.execute_command", mock_native_exec),
        ):
            from prism.iris.api.terminal import execute_command

            result = await execute_command("Write 1", namespace="USER", timeout=10.0)

        assert result["output"] == "1"
        mock_native_exec.assert_called_once_with("Write 1", "USER", 10.0)

    async def test_native_method_normalizes_null_namespace(self):
        mock_native_exec = AsyncMock(
            return_value={
                "namespace": IRIS_NAMESPACE,
                "command": "Write 1",
                "output": "1",
                "prompt": "",
            }
        )

        with (
            patch("prism.iris.api.terminal.IRIS_TERMINAL_METHOD", "native"),
            patch("prism.iris.sdk.terminal.execute_command", mock_native_exec),
        ):
            from prism.iris.api.terminal import execute_command

            result = await execute_command("Write 1", namespace="null", timeout=10.0)

        assert result["output"] == "1"
        mock_native_exec.assert_called_once_with("Write 1", IRIS_NAMESPACE, 10.0)

    async def test_native_method_sanitizes_output(self):
        mock_native_exec = AsyncMock(
            return_value={
                "namespace": IRIS_NAMESPACE,
                "command": "Write 1",
                "output": "ok\x00bad",
                "prompt": "",
            }
        )

        with (
            patch("prism.iris.api.terminal.IRIS_TERMINAL_METHOD", "native"),
            patch("prism.iris.api.terminal.IRIS_TERMINAL_MAX_OUTPUT_CHARS", 100),
            patch("prism.iris.sdk.terminal.execute_command", mock_native_exec),
        ):
            from prism.iris.api.terminal import execute_command

            result = await execute_command("Write 1", namespace="USER", timeout=10.0)

        assert result["output"] == "okbad"

    async def test_ws_method_uses_websocket(self):
        """When IRIS_TERMINAL_METHOD=ws, the WebSocket path is used (not native)."""
        mock_cookies = AsyncMock(return_value={"CSPSESSIONID": "abc"})
        mock_ws = AsyncMock()

        # Build a mock WebSocket that returns init, then prompt, then output+prompt
        import json

        messages = iter(
            [
                json.dumps({"type": "init"}),
                json.dumps({"type": "prompt", "text": "USER>"}),
                json.dumps({"type": "output", "text": "42"}),
                json.dumps({"type": "prompt", "text": "USER>"}),
            ]
        )
        mock_ws.recv = AsyncMock(side_effect=lambda: next(messages))
        mock_ws.send = AsyncMock()

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("prism.iris.api.terminal.IRIS_TERMINAL_METHOD", "ws"),
            patch("prism.iris.api.terminal._get_session_cookies", mock_cookies),
            patch(
                "prism.iris.api.terminal.websockets.connect", return_value=mock_connect
            ),
        ):
            from prism.iris.api.terminal import execute_command

            result = await execute_command("Write 42")

        assert result["output"] == "42"
        assert result["namespace"] == IRIS_NAMESPACE
