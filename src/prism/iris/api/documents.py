"""IRIS document CRUD API calls."""

from __future__ import annotations

from prism.iris.sdk.http import api_url, client, parse_json


class DocumentNotFound(Exception):
    """Raised when a document does not exist on the IRIS server."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Document not found: {name}")


async def list_documents(
    namespace: str | None = None,
    doc_type: str | None = None,
    generated: bool = False,
    filter: str | None = None,
) -> dict:
    """GET /:namespace/docnames — list source code documents."""
    params: dict[str, str] = {}
    if doc_type:
        params["type"] = doc_type
    if generated:
        params["generated"] = "1"
    if filter:
        params["filter"] = filter
    c = client()
    r = await c.get(f"{api_url(namespace)}/docnames", params=params)
    r.raise_for_status()
    return parse_json(r)


async def get_document(name: str, namespace: str | None = None) -> dict:
    """GET /:namespace/doc/:name — retrieve a single document.

    Raises ``DocumentNotFound`` if the server returns 404.
    """
    c = client()
    r = await c.get(f"{api_url(namespace)}/doc/{name}")
    if r.status_code == 404:
        raise DocumentNotFound(name)
    r.raise_for_status()
    return parse_json(r)


async def put_document(
    name: str,
    content: list[str],
    namespace: str | None = None,
) -> dict:
    """PUT /:namespace/doc/:name — create or update a document.

    `content` is a list of lines (the Atelier API expects this format).
    """
    payload = {
        "enc": False,
        "content": content,
    }
    url = f"{api_url(namespace)}/doc/{name}"
    c = client()
    r = await c.put(url, json=payload, params={"ignoreConflict": "1"})
    r.raise_for_status()
    return parse_json(r)


async def delete_document(name: str, namespace: str | None = None) -> dict:
    """DELETE /:namespace/doc/:name — delete a document.

    Raises ``DocumentNotFound`` if the server returns 404.
    """
    c = client()
    r = await c.delete(f"{api_url(namespace)}/doc/{name}")
    if r.status_code == 404:
        raise DocumentNotFound(name)
    r.raise_for_status()
    return parse_json(r)
