"""DBGP protocol client over WebSocket for IRIS XDEBUG debugging.

Implements the DBGP (Xdebug) protocol used by IRIS's %Atelier.v1.XDebugAgent.
Commands are sent as newline-terminated text strings over WebSocket.
Responses arrive as ``length|base64(xml)`` framed messages.

References:
- DBGP spec: https://xdebug.org/docs/dbgp
- IRIS endpoint: /api/atelier/{version}/%25SYS/debug
"""

from __future__ import annotations

import asyncio
import base64
import itertools
import ssl
from xml.etree.ElementTree import Element, fromstring as parse_xml

import websockets
import websockets.asyncio.client

from prism.config import (
    IRIS_BASE_URL,
    IRIS_USERNAME,
    IRIS_PASSWORD,
    IRIS_API_PREFIX,
)


class DbgpError(Exception):
    """Raised when DBGP returns an error response."""

    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(f"DBGP error {code}: {message}")


class DbgpConnection:
    """Low-level DBGP protocol client over a WebSocket connection.

    Usage::

        async with DbgpConnection.connect() as conn:
            await conn.send_command("feature_set", n="max_data", v="8192")
            resp = await conn.send_command("step_into")
    """

    def __init__(
        self, ws: websockets.asyncio.client.ClientConnection, init_elem: Element
    ):
        self._ws = ws
        self._tx_id = itertools.count(1)
        self.init = init_elem
        self.app_id = init_elem.get("appid", "")
        self.ide_key = init_elem.get("idekey", "")
        self.language = init_elem.get("language", "ObjectScript")

    @classmethod
    async def connect(cls, namespace: str | None = None) -> DbgpConnection:
        """Open a WebSocket to the IRIS DBGP debug endpoint and read the init packet."""
        ns = namespace or "%SYS"
        encoded_ns = ns.replace("%", "%25")

        base = IRIS_BASE_URL.rstrip("/")
        scheme = "wss" if base.startswith("https") else "ws"
        http_base = base.split("://", 1)[1] if "://" in base else base
        uri = f"{scheme}://{http_base}/{IRIS_API_PREFIX}/{encoded_ns}/debug"

        # Basic auth header
        credentials = base64.b64encode(
            f"{IRIS_USERNAME}:{IRIS_PASSWORD}".encode()
        ).decode()

        ssl_ctx: ssl.SSLContext | None = None
        if scheme == "wss":
            ssl_ctx = ssl.create_default_context()

        ws = await websockets.asyncio.client.connect(
            uri,
            additional_headers={"Authorization": f"Basic {credentials}"},
            ssl=ssl_ctx,
        )

        try:
            init_data = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(init_data, bytes):
                init_data = init_data.decode("utf-8")
            init_xml = _parse_dbgp_response(init_data)
            return cls(ws, init_xml)
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            raise

    async def send_command(
        self, command: str, data: str | None = None, **args: str
    ) -> Element:
        """Send a DBGP command and return the parsed XML response.

        Args:
            command: DBGP command name (e.g. "step_into", "breakpoint_set").
            data: Optional base64-encoded data payload (for eval, stdin, etc.).
            **args: Command arguments as key=value (e.g. n="max_data", v="8192").

        Returns:
            The parsed XML Element of the response.

        Raises:
            DbgpError: If the response contains an <error> element.
        """
        tx_id = next(self._tx_id)
        parts = [command, f"-i {tx_id}"]
        for key, value in args.items():
            # Support -v_base64 flag: sent as the arg key with underscore
            # so it arrives as a kwarg (v_base64="...") and gets formatted
            # as "-v_base64 ..." on the wire.
            parts.append(f"-{key} {value}")
        if data is not None:
            parts.append(f"-- {data}")

        message = " ".join(parts) + "\n"
        await self._ws.send(message)

        raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        elem = _parse_dbgp_response(raw)
        _check_error(elem)
        return elem

    async def close(self) -> None:
        """Close the underlying WebSocket connection."""
        await self._ws.close()

    @property
    def closed(self) -> bool:
        return (
            self._ws.protocol.state.name == "CLOSED"
            if hasattr(self._ws, "protocol")
            else True
        )


def _parse_dbgp_response(raw: str) -> Element:
    """Parse an IRIS DBGP response in ``length|base64(xml)`` framing.

    IRIS sends WebSocket messages as ``<length>|<base64-encoded-xml>``.
    Falls back to plain XML parsing if no pipe-framing is detected.
    """
    text = raw.strip()
    if "|" in text:
        _, b64_payload = text.split("|", 1)
        xml_str = base64.b64decode(b64_payload).decode("iso-8859-1")
        return parse_xml(xml_str)
    # Fallback: plain XML (for testing / non-IRIS implementations)
    return parse_xml(text)


def _check_error(elem: Element) -> None:
    """Raise DbgpError if the response element contains an error child."""
    # Error responses have an <error> child with code attribute
    err = elem.find("{urn:debugger_protocol_v1}error")
    if err is None:
        err = elem.find("error")
    if err is not None:
        code = int(err.get("code", "0"))
        msg_elem = err.find("{urn:debugger_protocol_v1}message")
        if msg_elem is None:
            msg_elem = err.find("message")
        message = (
            msg_elem.text if msg_elem is not None and msg_elem.text else "Unknown error"
        )
        raise DbgpError(code, message)
