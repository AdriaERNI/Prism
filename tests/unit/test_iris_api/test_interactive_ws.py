"""Unit tests for the InteractiveWSSession class.

Tests the persistent WebSocket session that keeps variables and state
across multiple commands. Mocks the WebSocket layer — no IRIS needed.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from prism.iris.api.interactive_ws import InteractiveWSSession
from prism.iris.api.terminal import TerminalError


# ── Helpers ──────────────────────────────────────────────────────────


def _make_ws(messages: list[dict]):
    """Create a mock WebSocket that yields *messages* in order."""
    ws = AsyncMock()
    ws.recv = AsyncMock(side_effect=[json.dumps(m) for m in messages])
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _init_and_prompt(namespace: str = "USER") -> list[dict]:
    """Return the init + initial prompt messages."""
    return [
        {"type": "init", "protocol": 1, "version": "2024.1"},
        {"type": "prompt", "text": f"\x1b[1m{namespace}>\x1b[0m"},
    ]


def _output_and_prompt(text: str, namespace: str = "USER") -> list[dict]:
    """Return an output message + next prompt."""
    return [
        {"type": "output", "text": text},
        {"type": "prompt", "text": f"\x1b[1m{namespace}>\x1b[0m"},
    ]


def _patch_connect(ws):
    """Patch websockets.connect to return *ws* as an async context manager.

    For InteractiveWSSession, the session calls `await websockets.connect(...)`
    directly (not as a context manager), so we patch the connect coroutine
    to return the ws object.
    """

    async def _connect(*args, **kwargs):
        return ws

    return patch(
        "prism.iris.api.interactive_ws.websockets.connect", side_effect=_connect
    )


def _patch_cookies(cookies: dict | None = None):
    """Patch _get_session_cookies to return *cookies*."""
    return patch(
        "prism.iris.api.interactive_ws._get_session_cookies",
        return_value=cookies or {"CSPSESSIONID": "abc123"},
    )


# ── Connect / handshake ─────────────────────────────────────────────


class TestConnect:
    async def test_connect_handshake(self):
        """connect() performs init/config/prompt handshake."""
        ws = _make_ws(_init_and_prompt())

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession(namespace="USER")
            await session.connect()

        assert session.namespace == "USER"
        assert "USER>" in session.prompt

        # Verify config message was sent
        calls = ws.send.call_args_list
        config_msg = json.loads(calls[0][0][0])
        assert config_msg["type"] == "config"
        assert config_msg["namespace"] == "USER"
        assert config_msg["rawMode"] is False

        await session.close()

    async def test_connect_namespace_override(self):
        """connect() sends the specified namespace."""
        ws = _make_ws(_init_and_prompt(namespace="SAMPLES"))

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession(namespace="SAMPLES")
            await session.connect()

        assert session.namespace == "SAMPLES"

        config_msg = json.loads(ws.send.call_args_list[0][0][0])
        assert config_msg["namespace"] == "SAMPLES"

        await session.close()

    async def test_connect_bad_init(self):
        """First message is not init -> TerminalError."""
        ws = _make_ws([{"type": "prompt", "text": "USER>"}])

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            with pytest.raises(TerminalError, match="Expected init"):
                await session.connect()

    async def test_close(self):
        """close() closes the WebSocket."""
        ws = _make_ws(_init_and_prompt())

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()

        await session.close()
        ws.close.assert_called_once()


# ── Run commands ─────────────────────────────────────────────────────


class TestRun:
    async def test_run_single_command(self):
        """run() sends a command and collects output."""
        messages = _init_and_prompt() + _output_and_prompt("hello")

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            result = await session.run('write "hello"')

        assert result["output"] == "hello"
        assert result["command"] == 'write "hello"'
        assert result["namespace"] == "USER"
        assert "USER>" in result["prompt"]

    async def test_run_multiple_commands_persist(self):
        """Multiple run() calls use the same WebSocket session."""
        messages = (
            _init_and_prompt() + _output_and_prompt("42") + _output_and_prompt("84")
        )

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            r1 = await session.run("write 42")
            r2 = await session.run("write 42*2")

        assert r1["output"] == "42"
        assert r2["output"] == "84"

        # Verify both commands were sent on the same WebSocket
        # First send = config, second = first command, third = second command
        assert ws.send.call_count == 3

        cmd1 = json.loads(ws.send.call_args_list[1][0][0])
        cmd2 = json.loads(ws.send.call_args_list[2][0][0])
        assert cmd1["input"] == "write 42"
        assert cmd2["input"] == "write 42*2"

    async def test_run_multi_line_output(self):
        """run() collects multiple output messages."""
        messages = (
            _init_and_prompt()
            + [
                {"type": "output", "text": "line1"},
                {"type": "output", "text": "line2"},
                {"type": "output", "text": "line3"},
            ]
            + [{"type": "prompt", "text": "\x1b[1mUSER>\x1b[0m"}]
        )

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            result = await session.run("test")

        assert result["output"] == "line1\nline2\nline3"

    async def test_run_empty_output(self):
        """run() with no output messages returns empty string."""
        messages = _init_and_prompt() + [
            {"type": "prompt", "text": "\x1b[1mUSER>\x1b[0m"},
        ]

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            result = await session.run("set x=1")

        assert result["output"] == ""

    async def test_run_updates_prompt(self):
        """run() updates the session's prompt after each command."""
        messages = _init_and_prompt(namespace="USER") + [
            {"type": "output", "text": ""},
            {"type": "prompt", "text": "\x1b[1mSAMPLES>\x1b[0m"},
        ]

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            assert "USER>" in session.prompt
            await session.run('zn "SAMPLES"')
            assert "SAMPLES>" in session.prompt

    async def test_run_on_output_callback(self):
        """run() calls on_output for each output message."""
        messages = (
            _init_and_prompt()
            + [
                {"type": "output", "text": "line1"},
                {"type": "output", "text": "line2"},
            ]
            + [{"type": "prompt", "text": "\x1b[1mUSER>\x1b[0m"}]
        )

        ws = _make_ws(messages)
        streamed: list[str] = []

        async def on_output(text: str) -> None:
            streamed.append(text)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            await session.run("test", on_output=on_output)

        assert streamed == ["line1", "line2"]

    async def test_run_error_message(self):
        """run() raises TerminalError on server error."""
        messages = _init_and_prompt() + [
            {"type": "error", "text": "Something went wrong"}
        ]

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            with pytest.raises(TerminalError, match="Server error"):
                await session.run("test")

    async def test_run_unexpected_init(self):
        """run() raises TerminalError if init arrives mid-session."""
        messages = _init_and_prompt() + [
            {"type": "init", "protocol": 1, "version": "2024.1"}
        ]

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            with pytest.raises(TerminalError, match="Unexpected init"):
                await session.run("test")

    async def test_run_not_connected(self):
        """run() raises TerminalError if session not connected."""
        session = InteractiveWSSession()
        with pytest.raises(TerminalError, match="not connected"):
            await session.run("test")


# ── Context manager ──────────────────────────────────────────────────


class TestContextManager:
    async def test_context_manager(self):
        """InteractiveWSSession works as an async context manager."""
        messages = _init_and_prompt() + _output_and_prompt("ok")

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            async with InteractiveWSSession(namespace="USER") as session:
                result = await session.run("write 1")

        assert result["output"] == "ok"
        ws.close.assert_called_once()

    async def test_context_manager_namespace(self):
        """Context manager uses the provided namespace."""
        messages = _init_and_prompt(namespace="SAMPLES")

        ws = _make_ws(messages[:2])  # only init + prompt

        with _patch_cookies(), _patch_connect(ws):
            async with InteractiveWSSession(namespace="SAMPLES") as session:
                assert session.namespace == "SAMPLES"


# ── Output truncation ────────────────────────────────────────────────


class TestOutputTruncation:
    async def test_output_truncated(self):
        """Output is truncated when exceeding max_output_chars."""
        messages = _init_and_prompt() + _output_and_prompt("A" * 200)

        ws = _make_ws(messages)

        with (
            _patch_cookies(),
            _patch_connect(ws),
            patch(
                "prism.iris.api.interactive_ws.settings.iris_terminal_max_output_chars",
                50,
            ),
        ):
            session = InteractiveWSSession()
            await session.connect()
            result = await session.run("test")

        assert len(result["output"]) == 50
        assert result["output_truncated"] is True
        assert result["output_omitted_chars"] == 150


# ── Read message handling ──────────────────────────────────────────


class TestReadMessage:
    """Verify that ``read`` messages from IRIS are handled correctly."""

    async def test_read_message_triggers_callback(self):
        """When a ``read`` message arrives, the on_read callback is invoked."""
        messages = _init_and_prompt() + [
            {"type": "read", "text": "Enter name: "},
            {"type": "output", "text": "Hello, Alice"},
            {"type": "prompt", "text": "USER>"},
        ]

        ws = _make_ws(messages)

        callback_called = False
        callback_text = ""

        async def on_read(text: str) -> str:
            nonlocal callback_called, callback_text
            callback_called = True
            callback_text = text
            return "Alice"

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            result = await session.run("read name", on_read=on_read)

        assert callback_called is True
        assert "Enter name" in callback_text
        assert "Hello, Alice" in result["output"]

    async def test_read_message_sends_input_back(self):
        """The callback's return value is sent back as a ``read`` message."""
        messages = _init_and_prompt() + [
            {"type": "read", "text": ""},
            {"type": "output", "text": "42"},
            {"type": "prompt", "text": "USER>"},
        ]

        ws = _make_ws(messages)

        async def on_read(text: str) -> str:
            return "42"

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            await session.run("read x", on_read=on_read)

        # Verify a read message was sent back
        sent_messages = [json.loads(call.args[0]) for call in ws.send.call_args_list]
        read_msgs = [m for m in sent_messages if m.get("type") == "read"]
        assert len(read_msgs) == 1
        assert read_msgs[0]["input"] == "42"

    async def test_read_message_without_callback_times_out(self):
        """Without on_read callback, a read message is silently skipped
        and the session continues waiting (may timeout)."""
        messages = _init_and_prompt() + [
            {"type": "read", "text": "Enter: "},
            {"type": "prompt", "text": "USER>"},
        ]

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession(timeout=2.0)
            await session.connect()
            # Should not raise — read message is skipped, next prompt is consumed
            result = await session.run("read x")

        assert result["prompt"] == "USER>"

    async def test_read_message_empty_text(self):
        """Read message with empty text still triggers callback."""
        messages = _init_and_prompt() + [
            {"type": "read", "text": ""},
            {"type": "output", "text": "ok"},
            {"type": "prompt", "text": "USER>"},
        ]

        ws = _make_ws(messages)

        called_with = None

        async def on_read(text: str) -> str:
            nonlocal called_with
            called_with = text
            return "input"

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            result = await session.run("read x", on_read=on_read)

        assert called_with == ""
        assert "ok" in result["output"]


# ── Color message handling ──────────────────────────────────────────


class TestColorMessage:
    """``color`` messages from IRIS should be silently ignored."""

    async def test_color_message_ignored(self):
        """Color messages do not interfere with normal output."""
        messages = _init_and_prompt() + [
            {"type": "color", "text": "\x1b[32m"},
            {"type": "output", "text": "hello"},
            {"type": "color", "text": "\x1b[0m"},
            {"type": "prompt", "text": "USER>"},
        ]

        ws = _make_ws(messages)

        with _patch_cookies(), _patch_connect(ws):
            session = InteractiveWSSession()
            await session.connect()
            result = await session.run('w "hello"')

        assert "hello" in result["output"]
        assert result["prompt"] == "USER>"
