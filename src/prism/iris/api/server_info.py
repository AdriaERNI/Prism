"""IRIS server info API call."""

from __future__ import annotations

from prism.iris.sdk.http import base_url, client, parse_json


async def get_server_info(
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """GET /api/atelier/ — server version, namespaces, etc."""
    c = client(target_host=target_host, target_port=target_port)
    r = await c.get(f"{base_url(target_host, target_port)}/api/atelier/")
    r.raise_for_status()
    return parse_json(r)
