"""Unit tests for terminal WebSocket API."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from prism.config import IRIS_NAMESPACE
from prism.iris.api.terminal import (
    TerminalError,
    _ws_url,
    execute_command,
)


@pytest.fixture(autouse=True)
def _force_ws_method():
    """These tests exercise the WebSocket path — force IRIS_TERMINAL_METHOD=ws."""
    with patch("prism.iris.api.terminal.IRIS_TERMINAL_METHOD", "ws"):
        yield


# ── Helpers ──────────────────────────────────────────────────────────


def _make_ws(messages: list[dict]):
    """Create a mock WebSocket that yields *messages* in order."""
    ws = AsyncMock()
    ws.recv = AsyncMock(side_effect=[json.dumps(m) for m in messages])
    ws.send = AsyncMock()
    return ws


def _standard_messages(output_msgs: list[dict] | None = None, namespace: str = "USER"):
    """Return the standard init → prompt → output… → prompt sequence."""
    msgs = [
        {"type": "init", "protocol": 1, "version": "2024.1"},
        {"type": "prompt", "text": f"{namespace}>"},
    ]
    if output_msgs:
        msgs.extend(output_msgs)
    msgs.append({"type": "prompt", "text": f"{namespace}>"})
    return msgs


def _patch_connect(ws):
    """Patch websockets.connect to return *ws* as an async context manager."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=ws)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch("prism.iris.api.terminal.websockets.connect", return_value=cm)


def _patch_cookies(cookies: dict | None = None):
    """Patch _get_session_cookies to return *cookies*."""
    return patch(
        "prism.iris.api.terminal._get_session_cookies",
        return_value=cookies or {"CSPSESSIONID": "abc123"},
    )


# ── URL building ─────────────────────────────────────────────────────


class TestWsUrl:
    def test_http_to_ws(self):
        with patch(
            "prism.iris.api.terminal.base_url", return_value="http://localhost:52773"
        ):
            assert _ws_url().startswith("ws://")
            assert "/api/atelier/v8/%25SYS/terminal" in _ws_url()

    def test_https_to_wss(self):
        with patch(
            "prism.iris.api.terminal.base_url", return_value="https://iris.example.com"
        ):
            assert _ws_url().startswith("wss://")
            assert "/api/atelier/v8/%25SYS/terminal" in _ws_url()


# ── execute_command ──────────────────────────────────────────────────


class TestExecuteCommand:
    async def test_simple_command(self):
        ws = _make_ws(
            _standard_messages(
                [
                    {"type": "output", "text": "hello"},
                ]
            )
        )

        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command('write "hello"')

        assert result["output"] == "hello"
        assert result["command"] == 'write "hello"'
        assert result["namespace"] == IRIS_NAMESPACE

    async def test_multi_line_output(self):
        ws = _make_ws(
            _standard_messages(
                [
                    {"type": "output", "text": "line1"},
                    {"type": "output", "text": "line2"},
                    {"type": "output", "text": "line3"},
                ]
            )
        )

        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command("test")

        assert result["output"] == "line1\nline2\nline3"

    async def test_output_control_chars_are_sanitized(self):
        ws = _make_ws(
            _standard_messages(
                [
                    {"type": "output", "text": "ok\x00bad\x07"},
                ]
            )
        )

        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command("test")

        assert result["output"] == "okbad"

    async def test_output_is_truncated_when_too_large(self):
        ws = _make_ws(
            _standard_messages(
                [
                    {"type": "output", "text": "A" * 12},
                ]
            )
        )

        with (
            _patch_cookies(),
            _patch_connect(ws),
            patch("prism.iris.api.terminal.IRIS_TERMINAL_MAX_OUTPUT_CHARS", 10),
        ):
            result = await execute_command("test")

        assert result["output"] == "A" * 10
        assert result["output_truncated"] is True
        assert result["output_omitted_chars"] == 2

    async def test_on_output_callback(self):
        """on_output callback is called for each output line."""
        ws = _make_ws(
            _standard_messages(
                [
                    {"type": "output", "text": "line1"},
                    {"type": "output", "text": "line2"},
                ]
            )
        )
        streamed: list[str] = []

        async def on_output(text: str) -> None:
            streamed.append(text)

        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command("test", on_output=on_output)

        # First call is the progress signal (empty string) after auth,
        # followed by the actual output lines from the WebSocket.
        assert streamed == ["", "line1", "line2"]
        assert result["output"] == "line1\nline2"

    async def test_on_output_progress_signal(self):
        """on_output receives a progress signal even without command output."""
        ws = _make_ws(_standard_messages())
        callback = AsyncMock()

        with _patch_cookies(), _patch_connect(ws):
            await execute_command("set x=1", on_output=callback)

        # A single progress signal (empty string) is sent after auth.
        callback.assert_called_once_with("")

    async def test_empty_output(self):
        ws = _make_ws(_standard_messages())

        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command("set x=1")

        assert result["output"] == ""

    async def test_namespace_override(self):
        ws = _make_ws(_standard_messages(namespace="SAMPLES"))

        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command("write 1", namespace="SAMPLES")

        assert result["namespace"] == "SAMPLES"
        # Verify config message was sent with the right namespace
        calls = ws.send.call_args_list
        config_call = json.loads(calls[0][0][0])
        assert config_call["namespace"] == "SAMPLES"

    async def test_namespace_string_null_uses_default(self):
        ws = _make_ws(_standard_messages(namespace=IRIS_NAMESPACE))

        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command("write 1", namespace="null")

        assert result["namespace"] == IRIS_NAMESPACE
        calls = ws.send.call_args_list
        config_call = json.loads(calls[0][0][0])
        assert config_call["namespace"] == IRIS_NAMESPACE

    async def test_namespace_empty_string_uses_default(self):
        ws = _make_ws(_standard_messages(namespace=IRIS_NAMESPACE))

        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command("write 1", namespace="")

        assert result["namespace"] == IRIS_NAMESPACE
        calls = ws.send.call_args_list
        config_call = json.loads(calls[0][0][0])
        assert config_call["namespace"] == IRIS_NAMESPACE

    async def test_unexpected_init_message(self):
        """If an init message arrives where we expect output, raise TerminalError."""
        ws = _make_ws(
            [
                {"type": "init", "protocol": 1, "version": "2024.1"},
                {"type": "prompt", "text": "USER>"},
                # After sending command, server sends another init instead of output
                {"type": "init", "protocol": 1, "version": "2024.1"},
            ]
        )

        with _patch_cookies(), _patch_connect(ws):
            with pytest.raises(TerminalError, match="Unexpected init"):
                await execute_command("test")

    async def test_error_message_from_server(self):
        """Server sends an error message → TerminalError."""
        ws = _make_ws(
            [
                {"type": "init", "protocol": 1, "version": "2024.1"},
                {"type": "prompt", "text": "USER>"},
                {"type": "error", "text": "Something went wrong"},
            ]
        )

        with _patch_cookies(), _patch_connect(ws):
            with pytest.raises(TerminalError, match="Server error"):
                await execute_command("test")

    async def test_bad_init(self):
        """First message is not init → TerminalError."""
        ws = _make_ws(
            [
                {"type": "prompt", "text": "USER>"},
            ]
        )

        with _patch_cookies(), _patch_connect(ws):
            with pytest.raises(TerminalError, match="Expected init"):
                await execute_command("test")
