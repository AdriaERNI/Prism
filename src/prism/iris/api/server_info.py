"""IRIS server info API call."""

from __future__ import annotations

from prism.iris.sdk.http import base_url, client, parse_json


async def get_server_info() -> dict:
    """GET /api/atelier/ — server version, namespaces, etc."""
    c = client()
    r = await c.get(f"{base_url()}/api/atelier/")
    r.raise_for_status()
    return parse_json(r)
