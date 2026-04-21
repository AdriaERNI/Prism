"""Shared HTTP primitives for the IRIS Atelier REST API."""

from __future__ import annotations

import httpx

from prism.config import (
    IRIS_BASE_URL,
    IRIS_USERNAME,
    IRIS_PASSWORD,
    IRIS_NAMESPACE,
    IRIS_API_PREFIX,
)


def api_url(namespace: str | None = None) -> str:
    ns = namespace or IRIS_NAMESPACE
    # Encode '%' as '%25' for namespaces like %SYS in the URL path
    ns_encoded = ns.replace("%", "%25")
    return f"{IRIS_BASE_URL}/{IRIS_API_PREFIX}/{ns_encoded}"


def base_url() -> str:
    return IRIS_BASE_URL


def auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(IRIS_USERNAME, IRIS_PASSWORD)


_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    """Return a shared AsyncClient with connection pooling."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(auth=auth(), timeout=30.0)
    return _client


def parse_json(response: httpx.Response) -> dict:
    """Parse JSON from an httpx response, raising a clear error on failure."""
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError(
            f"IRIS returned invalid JSON (HTTP {response.status_code} from "
            f"{response.request.method} {response.request.url}): {exc}"
        ) from exc
