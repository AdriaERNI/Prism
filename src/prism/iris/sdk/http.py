"""Shared HTTP primitives for the IRIS Atelier REST API."""

from __future__ import annotations

import httpx

from prism.settings import settings


def api_url(namespace: str | None = None) -> str:
    ns = namespace or settings.iris_namespace
    # IRIS Atelier API expects %25SYS on the wire (URL-encoded %).
    # httpx passes % through as-is (does NOT re-encode), so we must pre-encode.
    ns_encoded = ns.replace("%", "%25")
    return f"{settings.iris_base_url}/{settings.iris_api_prefix}/{ns_encoded}"


def base_url() -> str:
    return settings.iris_base_url


def auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(settings.iris_username, settings.iris_password)


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
