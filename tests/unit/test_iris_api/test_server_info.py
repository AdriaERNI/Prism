"""Unit tests for server_info API."""

from unittest.mock import patch

import httpx
import pytest

from prism.iris.api import server_info as info_api
from tests.unit.test_iris_api.conftest import mock_client, json_response, text_response


class TestGetServerInfo:
    async def test_success(self):
        body = {"result": {"content": {"version": "IRIS 2024.1"}}}

        def handler(request):
            assert "/api/atelier/" in str(request.url)
            return json_response(body)

        with patch.object(info_api, "client", lambda: mock_client(handler)):
            result = await info_api.get_server_info()
        assert result["result"]["content"]["version"] == "IRIS 2024.1"

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(500, text="Internal Server Error")

        with patch.object(info_api, "client", lambda: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await info_api.get_server_info()

    async def test_invalid_json(self):
        def handler(request):
            return text_response("not json", status=200)

        with patch.object(info_api, "client", lambda: mock_client(handler)):
            with pytest.raises(ValueError, match="invalid JSON"):
                await info_api.get_server_info()
