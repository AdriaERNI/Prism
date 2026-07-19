"""Interactive WebSocket terminal session for IRIS.

Provides a persistent WebSocket connection that stays open across multiple
commands, mimicking a real IRIS terminal session. Unlike the one-shot
``execute_command_ws`` which opens a new connection per command, this
session keeps the WebSocket alive so variables and state persist between
commands.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx
import websockets

from prism.iris.api.terminal import (
    TerminalError,
    _clean_text,
    _resolve_namespace,
)
from prism.iris.sdk.http import auth, base_url
from prism.settings import settings


async def _get_session_cookies_and_api_version() -> tuple[dict[str, str], int]:
    """Authenticate and return cookies plus the server's API version.

    The API version is discovered from GET /api/atelier/ response body
    (``result.content.api``). The WebSocket terminal endpoint requires
    ``apiVersion >= 7`` (IRIS 2023.2+). Falls back to the version in
    ``settings.iris_api_prefix`` if the server doesn't report one.
    """
    async with httpx.AsyncClient(auth=auth(), timeout=30.0) as c:
        r = await c.get(f"{base_url()}/api/atelier/")
        r.raise_for_status()
        cookies = dict(r.cookies)
        try:
            data = r.json()
            api_version = data["result"]["content"]["api"]
        except (KeyError, ValueError, TypeError):
            api_version = 0
        return cookies, api_version


def _ws_url_dynamic(api_version: int) -> str:
    """Build the WebSocket URL using the server's API version.

    Falls back to ``settings.iris_api_prefix`` when *api_version* is 0
    or below the minimum (7) for the terminal endpoint.
    """
    url = base_url()
    if url.startswith("https://"):
        url = "wss://" + url[len("https://") :]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://") :]
    if api_version >= 7:
        return f"{url}/api/atelier/v{api_version}/%25SYS/terminal"
    # Fallback: use whatever prefix is configured (default: api/atelier/v8)
    return f"{url}/{settings.iris_api_prefix}/%25SYS/terminal"


class InteractiveWSSession:
    """A persistent WebSocket terminal session to IRIS.

    Opens a WebSocket connection, performs the init/config handshake, and
    keeps the session alive so that variables and namespace state persist
    across multiple commands.

    Usage::

        async with InteractiveWSSession(namespace="USER") as session:
            result = await session.run('set x=42')
            result = await session.run('write x')  # sees x=42
    """

    def __init__(
        self,
        namespace: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._namespace = _resolve_namespace(namespace)
        self._timeout = timeout
        self._ws: websockets.ClientConnection | None = None
        self._current_prompt: str = ""
        # True while the server is evaluating a command (between sending
        # the prompt input and receiving the next prompt message).  The
        # CLI uses this to decide whether Ctrl+C should interrupt the
        # running command or just clear the current input line.
        self._evaluating: bool = False

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def prompt(self) -> str:
        """Return the current prompt text (e.g. ``USER>``)."""
        return self._current_prompt

    @property
    def is_evaluating(self) -> bool:
        """Return True if a command is currently being executed on IRIS."""
        return self._evaluating

    async def interrupt(self) -> None:
        """Send an interrupt message to IRIS.

        This is equivalent to pressing Ctrl+C in a real IRIS terminal.
        The server will stop the running command and send a new prompt.
        Safe to call when not evaluating (no-op in that case).
        """
        if self._ws is None:
            return
        await self._ws.send(json.dumps({"type": "interrupt"}))

    async def __aenter__(self) -> InteractiveWSSession:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Open the WebSocket and perform init/config handshake."""
        cookies, api_version = await _get_session_cookies_and_api_version()
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())

        self._ws = await websockets.connect(
            _ws_url_dynamic(api_version),
            additional_headers={"Cookie": cookie_header},
        )

        # 1. Wait for init message
        raw = await asyncio.wait_for(self._ws.recv(), timeout=self._timeout)
        init_msg = json.loads(raw)
        if init_msg.get("type") != "init":
            raise TerminalError(f"Expected init message, got: {init_msg}")

        # 2. Send config with namespace
        await self._ws.send(
            json.dumps(
                {
                    "type": "config",
                    "namespace": self._namespace,
                    "rawMode": False,
                }
            )
        )

        # 3. Wait for initial prompt
        output_lines, prompt = await self._wait_for_prompt()
        self._current_prompt = prompt

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _wait_for_prompt(
        self,
        on_output: Callable[[str], Awaitable[None]] | None = None,
        on_read: Callable[[str], Awaitable[str]] | None = None,
    ) -> tuple[list[str], str]:
        """Consume messages until a prompt arrives.

        If *on_read* is provided and a ``read`` message arrives, the callback
        is invoked to get user input, which is sent back to IRIS. If *on_read*
        is ``None``, a ``TimeoutError`` will eventually fire (the session blocks).
        """
        if self._ws is None:
            raise TerminalError("Session not connected")

        output_lines: list[str] = []
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=self._timeout)
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "output":
                text = msg.get("text", "")
                output_lines.append(text)
                if on_output is not None:
                    await on_output(text)
            elif msg_type == "prompt":
                # IRIS 2025.3+ includes the current namespace in prompt
                # messages, so we can track zn changes transparently.
                ns = msg.get("ns")
                if ns:
                    self._namespace = ns
                self._evaluating = False
                return output_lines, msg.get("text", "")
            elif msg_type == "error":
                raise TerminalError(f"Server error: {msg.get('text', msg)}")
            elif msg_type == "init":
                raise TerminalError(f"Unexpected init message: {msg}")
            elif msg_type == "read":
                if on_read is not None:
                    # Ask the user for input and send it back
                    user_input = await on_read(msg.get("text", ""))
                    await self._ws.send(
                        json.dumps({"type": "read", "input": user_input})
                    )
                # If no on_read callback, the loop continues and will
                # eventually time out waiting for the next message.
            else:
                pass

    async def run(
        self,
        command: str,
        on_output: Callable[[str], Awaitable[None]] | None = None,
        on_read: Callable[[str], Awaitable[str]] | None = None,
    ) -> dict:
        """Run an ObjectScript command on the persistent session.

        Returns ``{"namespace": ..., "command": ..., "output": ..., "prompt": ...}``.
        Variables set in previous commands persist.

        If *on_read* is provided, it will be called when the server sends a
        ``read`` message (e.g. from the ObjectScript ``read`` command). The
        callback should return the user's input string.
        """
        if self._ws is None:
            raise TerminalError("Session not connected")

        self._evaluating = True
        await self._ws.send(
            json.dumps(
                {
                    "type": "prompt",
                    "input": command,
                }
            )
        )

        output_lines, prompt = await self._wait_for_prompt(on_output, on_read)
        self._current_prompt = prompt

        # Strip a leading blank line from the first output chunk.  IRIS
        # typically sends "\r\n" before the actual output because the
        # prompt already moved to a new line.  Without this, every
        # command result starts with an extra blank line.
        if output_lines:
            first = output_lines[0]
            if first.startswith("\r\n"):
                output_lines[0] = first[2:]
            elif first.startswith("\n"):
                output_lines[0] = first[1:]

        output = _clean_text("\n".join(output_lines))

        max_chars = settings.iris_terminal_max_output_chars
        truncated = False
        omitted = 0
        if max_chars > 0 and len(output) > max_chars:
            omitted = len(output) - max_chars
            output = output[:max_chars]
            truncated = True

        result: dict = {
            "namespace": self._namespace,
            "command": command,
            "output": output,
            "prompt": prompt,
        }
        if truncated:
            result["output_truncated"] = True
            result["output_omitted_chars"] = omitted
        return result
