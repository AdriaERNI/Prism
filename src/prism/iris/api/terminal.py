"""IRIS terminal via WebSocket — run arbitrary ObjectScript commands."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx
import websockets

from prism.config import (
    IRIS_API_PREFIX,
    IRIS_NAMESPACE,
    IRIS_TERMINAL_METHOD,
    IRIS_TERMINAL_MAX_OUTPUT_CHARS,
)
from prism.iris.sdk.http import auth, base_url


class TerminalError(Exception):
    """Raised when the terminal WebSocket session fails."""


def _resolve_namespace(namespace: str | None) -> str:
    """Normalize namespace input and apply the configured default.

    Some clients send null-like string values (for example "null") instead of
    omitting the field. Treat those as unset so terminal execution remains
    deterministic.
    """
    if namespace is None:
        return IRIS_NAMESPACE

    cleaned = namespace.strip()
    if not cleaned or cleaned.lower() in {"null", "none"}:
        return IRIS_NAMESPACE
    return cleaned


def _clean_text(value: str) -> str:
    """Remove control characters that can break downstream tool transports."""
    return "".join(
        ch for ch in value if ch in "\n\r\t" or (ord(ch) >= 32 and ch != "\x7f")
    )


def _finalize_result(result: dict) -> dict:
    """Sanitize and bound output payload size for robust MCP delivery."""
    output = result.get("output", "")
    if not isinstance(output, str):
        output = str(output)
    output = _clean_text(output)

    max_chars = IRIS_TERMINAL_MAX_OUTPUT_CHARS
    if max_chars > 0 and len(output) > max_chars:
        omitted = len(output) - max_chars
        output = output[:max_chars]
        return {
            **result,
            "output": output,
            "output_truncated": True,
            "output_omitted_chars": omitted,
        }

    return {
        **result,
        "output": output,
    }


async def _get_session_cookies() -> dict[str, str]:
    """Authenticate via GET /api/atelier/ and return a fresh session cookie.

    Uses a one-shot client so concurrent calls each get their own
    IRIS session — sharing a session across WebSocket connections causes
    output to be lost.
    """
    async with httpx.AsyncClient(auth=auth(), timeout=30.0) as c:
        r = await c.get(f"{base_url()}/api/atelier/")
        r.raise_for_status()
        return dict(r.cookies)


def _ws_url() -> str:
    """Build the WebSocket URL for the IRIS terminal endpoint."""
    url = base_url()
    if url.startswith("https://"):
        url = "wss://" + url[len("https://") :]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://") :]
    return f"{url}/{IRIS_API_PREFIX}/%25SYS/terminal"


async def _wait_for_prompt(
    ws: websockets.ClientConnection,
    timeout: float,
    on_output: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[list[str], str]:
    """Consume messages until a prompt arrives.

    Returns (output_lines, prompt_text).
    Raises ``TerminalError`` on error messages or unexpected protocol.
    """
    output_lines: list[str] = []
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
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
            # Ignore unknown message types (e.g. read, readchar)
            pass


async def execute_command_ws(
    command: str,
    namespace: str | None = None,
    timeout: float = 30.0,
    on_output: Callable[[str], Awaitable[None]] | None = None,
) -> dict:
    """Run an ObjectScript command over the Atelier WebSocket terminal."""
    ns = _resolve_namespace(namespace)
    cookies = await _get_session_cookies()

    # Signal progress after auth so the MCP transport knows we're alive.
    if on_output is not None:
        await on_output("")

    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())

    async with websockets.connect(
        _ws_url(),
        additional_headers={"Cookie": cookie_header},
    ) as ws:
        # 1. Wait for init
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        init_msg = json.loads(raw)
        if init_msg.get("type") != "init":
            raise TerminalError(f"Expected init message, got: {init_msg}")

        # 2. Send config
        await ws.send(
            json.dumps(
                {
                    "type": "config",
                    "namespace": ns,
                    "rawMode": False,
                }
            )
        )

        # 3. Wait for initial prompt
        await _wait_for_prompt(ws, timeout)

        # 4. Send command
        await ws.send(
            json.dumps(
                {
                    "type": "prompt",
                    "input": command,
                }
            )
        )

        # 5. Collect output until next prompt
        output_lines, prompt = await _wait_for_prompt(ws, timeout, on_output)

    return _finalize_result(
        {
            "namespace": ns,
            "command": command,
            "output": "\n".join(output_lines),
            "prompt": prompt,
        }
    )


async def execute_command(
    command: str,
    namespace: str | None = None,
    timeout: float = 30.0,
    on_output: Callable[[str], Awaitable[None]] | None = None,
) -> dict:
    """Run an ObjectScript command, dispatching based on IRIS_TERMINAL_METHOD.

    When ``native``, uses irisnative via SuperServer (parallel-capable).
    When ``ws``, uses the Atelier WebSocket terminal.

    Returns ``{"namespace": ..., "command": ..., "output": ..., "prompt": ...}``.
    """
    ns = _resolve_namespace(namespace)

    if IRIS_TERMINAL_METHOD == "native":
        from prism.iris.sdk import terminal as native_terminal

        # Signal progress before blocking executor call so the MCP transport
        # keeps the response stream alive while irisnative is working.
        if on_output is not None:
            await on_output("")

        result = await native_terminal.execute_command(command, ns, timeout)
        return _finalize_result(result)

    return await execute_command_ws(command, ns, timeout, on_output)
