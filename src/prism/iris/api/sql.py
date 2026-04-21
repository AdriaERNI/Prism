"""IRIS SQL query API call."""

from __future__ import annotations

from prism.iris.sdk.http import api_url, client, parse_json


async def execute_query(query: str, namespace: str | None = None) -> dict:
    """POST /:namespace/action/query — run an SQL query."""
    c = client()
    r = await c.post(
        f"{api_url(namespace)}/action/query",
        json={"query": query},
    )
    r.raise_for_status()
    return parse_json(r)
