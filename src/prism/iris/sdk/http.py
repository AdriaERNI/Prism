"""Shared HTTP primitives for the IRIS Atelier REST API."""

from __future__ import annotations

import httpx

from prism.iris.sdk.connection import resolve_base_url, resolve_host, resolve_port
from prism.settings import settings


def api_url(
    namespace: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> str:
    """Build the Atelier API URL for *namespace*, optionally on a custom host/port.

    When *target_host* / *target_port* are ``None``, the global settings
    defaults are used (``IRIS_BASE_URL``).
    """
    ns = namespace or settings.iris_namespace
    # IRIS Atelier API expects %25SYS on the wire (URL-encoded %).
    # httpx passes % through as-is (does NOT re-encode), so we must pre-encode.
    ns_encoded = ns.replace("%", "%25")
    base = resolve_base_url(target_host, target_port)
    return f"{base}/{settings.iris_api_prefix}/{ns_encoded}"


def base_url(
    target_host: str | None = None,
    target_port: int | None = None,
) -> str:
    """Return the IRIS base URL, optionally overridden by *target_host*/*target_port*."""
    return resolve_base_url(target_host, target_port)


def auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(settings.iris_username, settings.iris_password)


_default_client: httpx.AsyncClient | None = None
_override_clients: dict[str, httpx.AsyncClient] = {}


def _client_key(host: str, port: int) -> str:
    """Cache key for per-target clients."""
    return f"{host}:{port}"


def client(
    target_host: str | None = None,
    target_port: int | None = None,
) -> httpx.AsyncClient:
    """Return an ``AsyncClient`` with connection pooling.

    For the default target (no overrides), a shared global client is used.
    For custom targets, a per-host:port client is created and cached.
    """
    global _default_client
    if target_host is None and target_port is None:
        if _default_client is None or _default_client.is_closed:
            _default_client = httpx.AsyncClient(auth=auth(), timeout=30.0)
        return _default_client  # type: ignore[return-value]

    host = resolve_host(target_host)
    port = resolve_port(target_port)
    key = _client_key(host, port)
    c = _override_clients.get(key)
    if c is None or c.is_closed:
        c = httpx.AsyncClient(auth=auth(), timeout=30.0)
        _override_clients[key] = c
    return c


async def close_client() -> None:
    """Close all shared ``AsyncClient`` instances and reset module state."""
    global _default_client
    if _default_client is not None and not _default_client.is_closed:
        await _default_client.aclose()
    _default_client = None
    for c in _override_clients.values():
        if not c.is_closed:
            await c.aclose()
    _override_clients.clear()


def parse_json(response: httpx.Response) -> dict:
    """Parse JSON from an httpx response, raising a clear error on failure."""
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError(
            f"IRIS returned invalid JSON (HTTP {response.status_code} from "
            f"{response.request.method} {response.request.url}): {exc}"
        ) from exc


# ── Shared error handling ──────────────────────────────────────────────


def handle_api_error(e: Exception) -> str:
    """Consistent, LLM-friendly error formatting across all tools."""
    if isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code == 404:
            return "Error: Resource not found. Please check the document name or ID is correct."
        elif e.response.status_code == 403:
            return "Error: Permission denied. You don't have access to this resource or namespace."
        elif e.response.status_code == 401:
            return "Error: Authentication failed. Check IRIS_USERNAME and IRIS_PASSWORD."
        elif e.response.status_code == 429:
            return "Error: Rate limit exceeded. Please wait before making more requests."
        return f"Error: IRIS API request failed with status {e.response.status_code}."
    elif isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. The IRIS server may be slow or unresponsive. Try again or increase the timeout."
    elif isinstance(e, httpx.ConnectError):
        return "Error: Could not connect to the IRIS server. Check the host, port, and network connectivity."
    return f"Error: Unexpected error occurred: {type(e).__name__}: {e}"


# ── Shared request helper ─────────────────────────────────────────────


async def make_request(
    method: str,
    endpoint: str,
    *,
    target_host: str | None = None,
    target_port: int | None = None,
    namespace: str | None = None,
    use_base_url: bool = False,
    **kwargs,
) -> dict:
    """Unified API request helper with error handling.

    Args:
        method: HTTP method ("GET", "POST", "PUT", "DELETE").
        endpoint: API path suffix (e.g. "action/query") or full path if *use_base_url*.
        target_host: Override IRIS host (None = settings default).
        target_port: Override IRIS REST port (None = settings default).
        namespace: IRIS namespace for the API URL (ignored if *use_base_url*).
        use_base_url: If True, build URL from ``base_url()`` + endpoint instead of ``api_url()``.
        **kwargs: Passed to httpx (json=, params=, etc.).

    Returns:
        Parsed JSON response dict.

    Raises:
        httpx.HTTPStatusError: On 4xx/5xx responses (callers should catch).
    """
    c = client(target_host=target_host, target_port=target_port)
    if use_base_url:
        url = f"{base_url(target_host, target_port)}/{endpoint}"
    else:
        url = f"{api_url(namespace, target_host, target_port)}/{endpoint}"
    r = await c.request(method, url, **kwargs)
    r.raise_for_status()
    return parse_json(r)
