"""IRIS document CRUD API calls."""

from __future__ import annotations

from prism.iris.sdk.http import api_url, client, parse_json


class DocumentNotFound(Exception):
    """Raised when a document does not exist on the IRIS server."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Document not found: {name}")


class DocumentPutError(Exception):
    """Raised when IRIS rejects a document upload (PUT) with an embedded error.

    The Atelier PUT endpoint returns HTTP 200 with the real error inside
    ``result.status`` (e.g. ``ERROR #16021: Illegal Header Line ...``).
    Without this check a rejected upload looks like a success.
    """

    def __init__(self, name: str, iris_status: str) -> None:
        self.name = name
        self.iris_status = iris_status
        super().__init__(f"IRIS rejected upload of {name}: {iris_status}")


def _check_put_status(name: str, data: dict) -> dict:
    """Raise DocumentPutError if the Atelier PUT response embeds an error.

    On success IRIS returns ``result.status`` values like ``"ok"`` or
    ``"created"``; on rejection it embeds ``ERROR #NNNNN: ...`` in the same
    field with HTTP 200. Only ``ERROR`` statuses are failures.
    """
    result = data.get("result") or {}
    iris_status = result.get("status")
    if isinstance(iris_status, str) and iris_status.strip().upper().startswith("ERROR"):
        raise DocumentPutError(name, iris_status.strip())
    errors = (data.get("status") or {}).get("errors") or []
    if errors:
        first = errors[0].get("error", str(errors[0]))
        raise DocumentPutError(name, str(first))
    return data


async def list_documents(
    namespace: str | None = None,
    doc_type: str | None = None,
    generated: bool = False,
    filter: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """GET /:namespace/docnames — list source code documents."""
    params: dict[str, str] = {}
    if doc_type:
        params["type"] = doc_type
    if generated:
        params["generated"] = "1"
    if filter:
        params["filter"] = filter
    c = client(target_host=target_host, target_port=target_port)
    r = await c.get(f"{api_url(namespace, target_host, target_port)}/docnames", params=params)
    r.raise_for_status()
    return parse_json(r)


async def get_document(
    name: str,
    namespace: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """GET /:namespace/doc/:name — retrieve a single document.

    Raises ``DocumentNotFound`` if the server returns 404.
    """
    c = client(target_host=target_host, target_port=target_port)
    r = await c.get(f"{api_url(namespace, target_host, target_port)}/doc/{name}")
    if r.status_code == 404:
        raise DocumentNotFound(name)
    r.raise_for_status()
    return parse_json(r)


async def put_document(
    name: str,
    content: list[str],
    namespace: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """PUT /:namespace/doc/:name — create or update a document.

    `content` is a list of lines (the Atelier API expects this format).
    """
    payload = {
        "enc": False,
        "content": content,
    }
    url = f"{api_url(namespace, target_host, target_port)}/doc/{name}"
    c = client(target_host=target_host, target_port=target_port)
    r = await c.put(url, json=payload, params={"ignoreConflict": "1"})
    r.raise_for_status()
    return _check_put_status(name, parse_json(r))


async def delete_document(
    name: str,
    namespace: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """DELETE /:namespace/doc/:name — delete a document.

    Raises ``DocumentNotFound`` if the server returns 404.
    """
    c = client(target_host=target_host, target_port=target_port)
    r = await c.delete(f"{api_url(namespace, target_host, target_port)}/doc/{name}")
    if r.status_code == 404:
        raise DocumentNotFound(name)
    r.raise_for_status()
    return parse_json(r)
