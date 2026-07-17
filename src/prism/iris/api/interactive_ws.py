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
    _ws_url,
)
from prism.iris.sdk.http import auth, base_url
from prism.settings import settings


async def _get_session_cookies() -> dict[str, str]:
    """Authenticate via GET /api/atelier/ and return session cookies."""
    async with httpx.AsyncClient(auth=auth(), timeout=30.0) as c:
        r = await c.get(f"{base_url()}/api/atelier/")
        r.raise_for_status()
        return dict(r.cookies)


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

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def prompt(self) -> str:
        """Return the current prompt text (e.g. ``USER>``)."""
        return self._current_prompt

    async def __aenter__(self) -> InteractiveWSSession:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Open the WebSocket and perform init/config handshake."""
        cookies = await _get_session_cookies()
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())

        self._ws = await websockets.connect(
            _ws_url(),
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
    ) -> tuple[list[str], str]:
        """Consume messages until a prompt arrives."""
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
                return output_lines, msg.get("text", "")
            elif msg_type == "error":
                raise TerminalError(f"Server error: {msg.get('text', msg)}")
            elif msg_type == "init":
                raise TerminalError(f"Unexpected init message: {msg}")
            else:
                pass

    async def run(
        self,
        command: str,
        on_output: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict:
        """Run an ObjectScript command on the persistent session.

        Returns ``{"namespace": ..., "command": ..., "output": ..., "prompt": ...}``.
        Variables set in previous commands persist.
        """
        if self._ws is None:
            raise TerminalError("Session not connected")

        await self._ws.send(
            json.dumps(
                {
                    "type": "prompt",
                    "input": command,
                }
            )
        )

        output_lines, prompt = await self._wait_for_prompt(on_output)
        self._current_prompt = prompt

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
