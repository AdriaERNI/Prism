"""Unit tests for the terminal facade dispatch.

The terminal now always routes to the Atelier WebSocket terminal
(``execute_command_ws``). It does NOT upload our own ObjectScript helper
(MCP.Terminal) and does NOT use the native SuperServer ("superport") path.
"""

import json
from unittest.mock import AsyncMock, patch

from prism.iris.api.terminal import execute_command
from prism.settings import settings


def _make_ws(messages: list[dict]):
    """Create a mock WebSocket that yields *messages* in order."""
    ws = AsyncMock()
    ws.recv = AsyncMock(side_effect=[json.dumps(m) for m in messages])
    ws.send = AsyncMock()
    return ws


def _standard_messages(output_msgs: list[dict] | None = None, namespace: str = "USER"):
    """Return the standard init -> prompt -> output... -> prompt sequence."""
    msgs = [
        {"type": "init", "protocol": 1, "version": "2024.1"},
        {"type": "prompt", "text": f"{namespace}>"},
    ]
    if output_msgs:
        msgs.extend(output_msgs)
    msgs.append({"type": "prompt", "text": f"{namespace}>"})
    return msgs


def _patch_connect(ws):
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=ws)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch("prism.iris.api.terminal.websockets.connect", return_value=cm)


def _patch_cookies(cookies: dict | None = None):
    return patch(
        "prism.iris.api.terminal._get_session_cookies",
        return_value=cookies or {"CSPSESSIONID": "abc123"},
    )


class TestFacadeDispatch:
    async def test_always_routes_to_websocket(self):
        """The facade always uses the WebSocket terminal — no native/superport.

        Regardless of what ``iris_terminal_method`` is set to, execution
        goes through ``execute_command_ws`` (the Atelier WebSocket terminal),
        which never uploads our own ObjectScript and never uses the superport.
        """
        ws = _make_ws(_standard_messages([{"type": "output", "text": "hello"}]))
        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command('write "hello"')

        assert result["output"] == "hello"
        assert result["command"] == 'write "hello"'
        assert result["namespace"] == settings.iris_namespace

    async def test_ws_method_uses_websocket(self):
        """With IRIS_TERMINAL_METHOD=ws, the WebSocket path is used."""
        mock_cookies = AsyncMock(return_value={"CSPSESSIONID": "abc"})
        messages = iter(
            [
                json.dumps({"type": "init"}),
                json.dumps({"type": "prompt", "text": "USER>"}),
                json.dumps({"type": "output", "text": "42"}),
                json.dumps({"type": "prompt", "text": "USER>"}),
            ]
        )
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=lambda: next(messages))
        mock_ws.send = AsyncMock()

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(settings, "iris_terminal_method", "ws"),
            patch("prism.iris.api.terminal._get_session_cookies", mock_cookies),
            patch("prism.iris.api.terminal.websockets.connect", return_value=mock_connect),
        ):
            result = await execute_command("Write 42")

        assert result["output"] == "42"
        assert result["namespace"] == settings.iris_namespace

    async def test_ws_method_sanitizes_output(self):
        """Output control chars/ANSI are sanitized via the WebSocket path."""
        ws = _make_ws(_standard_messages([{"type": "output", "text": "ok\x00bad\x07"}]))
        with _patch_cookies(), _patch_connect(ws):
            result = await execute_command("test")

        assert result["output"] == "okbad"
