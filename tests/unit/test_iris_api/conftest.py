"""Shared helpers for API unit tests."""

import httpx


def mock_client(handler):
    """Return an AsyncClient using a mock transport."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def json_response(data, status=200):
    return httpx.Response(status, json=data)


def text_response(text, status=200):
    return httpx.Response(status, text=text)
