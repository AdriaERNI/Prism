"""IRIS document compilation API call."""

from __future__ import annotations

from prism.iris.sdk.http import api_url, client, parse_json
from prism.settings import settings


async def compile_documents(
    doc_names: list[str],
    namespace: str | None = None,
    flags: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """POST /:namespace/action/compile — compile one or more documents."""
    c = client(target_host=target_host, target_port=target_port)
    r = await c.post(
        f"{api_url(namespace, target_host, target_port)}/action/compile",
        json=doc_names,
        params={"flags": flags or settings.iris_compile_flags},
    )
    r.raise_for_status()
    return parse_json(r)
