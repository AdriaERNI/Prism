"""Unit tests for SQL API."""

import json
from unittest.mock import patch

import httpx
import pytest

from prism.iris.api import sql as sql_api
from tests.unit.test_iris_api.conftest import mock_client, json_response, text_response


class TestExecuteQuery:
    async def test_success(self):
        body = {"result": {"content": [{"ID": 1, "Name": "Alice"}]}}

        def handler(request):
            assert "/action/query" in str(request.url)
            return json_response(body)

        with patch.object(sql_api, "client", lambda: mock_client(handler)):
            result = await sql_api.execute_query("SELECT 1")
        assert result["result"]["content"][0]["Name"] == "Alice"

    async def test_sends_query_payload(self):
        def handler(request):
            payload = json.loads(request.content)
            assert payload["query"] == "SELECT * FROM Test.Person"
            return json_response({"result": {}})

        with patch.object(sql_api, "client", lambda: mock_client(handler)):
            await sql_api.execute_query("SELECT * FROM Test.Person")

    async def test_namespace_override(self):
        def handler(request):
            assert "/SAMPLES/" in str(request.url)
            return json_response({"result": {}})

        with patch.object(sql_api, "client", lambda: mock_client(handler)):
            await sql_api.execute_query("SELECT 1", namespace="SAMPLES")

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(500)

        with patch.object(sql_api, "client", lambda: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await sql_api.execute_query("SELECT 1")

    async def test_invalid_json(self):
        def handler(request):
            return text_response("error", status=200)

        with patch.object(sql_api, "client", lambda: mock_client(handler)):
            with pytest.raises(ValueError, match="invalid JSON"):
                await sql_api.execute_query("SELECT 1")
