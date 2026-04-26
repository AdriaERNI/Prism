"""Unit tests for compile API."""

import json
from unittest.mock import patch

import httpx
import pytest

from prism.iris.api import compile as compile_api
from prism.settings import settings
from tests.unit.test_iris_api.conftest import mock_client, json_response, text_response


class TestCompileDocuments:
    async def test_success(self):
        body = {"result": {"content": "compiled successfully"}}

        def handler(request):
            assert "/action/compile" in str(request.url)
            assert "flags=cuk" in str(request.url)
            return json_response(body)

        with patch.object(compile_api, "client", lambda: mock_client(handler)):
            result = await compile_api.compile_documents(["MyApp.cls"])
        assert "successfully" in str(result)

    async def test_custom_flags(self):
        def handler(request):
            assert "flags=ck" in str(request.url)
            return json_response({"result": {}})

        with patch.object(compile_api, "client", lambda: mock_client(handler)):
            await compile_api.compile_documents(["MyApp.cls"], flags="ck")

    async def test_default_flags_from_env(self):
        def handler(request):
            assert "flags=bck" in str(request.url)
            return json_response({"result": {}})

        with (
            patch.object(compile_api, "client", lambda: mock_client(handler)),
            patch.object(settings, "iris_compile_flags", "bck"),
        ):
            await compile_api.compile_documents(["MyApp.cls"])

    async def test_sends_doc_names_as_json_body(self):
        def handler(request):
            payload = json.loads(request.content)
            assert payload == ["A.cls", "B.cls"]
            return json_response({"result": {}})

        with patch.object(compile_api, "client", lambda: mock_client(handler)):
            await compile_api.compile_documents(["A.cls", "B.cls"])

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(500)

        with patch.object(compile_api, "client", lambda: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await compile_api.compile_documents(["MyApp.cls"])

    async def test_invalid_json(self):
        def handler(request):
            return text_response("nah", status=200)

        with patch.object(compile_api, "client", lambda: mock_client(handler)):
            with pytest.raises(ValueError, match="invalid JSON"):
                await compile_api.compile_documents(["MyApp.cls"])
