"""Unit tests for documents API."""

import json
from unittest.mock import patch

import httpx
import pytest

from prism.iris.api import documents as docs_api
from prism.iris.api.documents import DocumentNotFound, DocumentPutError
from tests.unit.test_iris_api.conftest import json_response, mock_client, text_response


class TestListDocuments:
    async def test_success(self):
        body = {"result": {"content": [{"name": "MyApp.cls"}]}}

        def handler(request):
            assert "/docnames" in str(request.url)
            return json_response(body)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await docs_api.list_documents()
        assert result["result"]["content"][0]["name"] == "MyApp.cls"

    async def test_passes_params(self):
        def handler(request):
            assert "type=cls" in str(request.url)
            assert "generated=1" in str(request.url)
            assert "filter=Test" in str(request.url)
            return json_response({"result": {"content": []}})

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            await docs_api.list_documents(doc_type="cls", generated=True, filter="Test")

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(500)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await docs_api.list_documents()

    async def test_invalid_json(self):
        def handler(request):
            return text_response("{broken", status=200)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(ValueError, match="invalid JSON"):
                await docs_api.list_documents()


class TestGetDocument:
    async def test_success(self):
        body = {"result": {"content": [{"content": "Class MyApp {}"}]}}

        def handler(request):
            assert "/doc/MyApp.cls" in str(request.url)
            return json_response(body)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await docs_api.get_document("MyApp.cls")
        assert result["result"]["content"][0]["content"] == "Class MyApp {}"

    async def test_404_raises_not_found(self):
        def handler(request):
            return httpx.Response(404)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(DocumentNotFound) as exc_info:
                await docs_api.get_document("Missing.cls")
        assert exc_info.value.name == "Missing.cls"

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(500)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await docs_api.get_document("MyApp.cls")

    async def test_invalid_json(self):
        def handler(request):
            return text_response("oops", status=200)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(ValueError, match="invalid JSON"):
                await docs_api.get_document("MyApp.cls")


class TestPutDocument:
    async def test_success(self):
        body = {"result": {"name": "MyApp.cls", "status": "ok"}}

        def handler(request):
            assert request.method == "PUT"
            assert "/doc/MyApp.cls" in str(request.url)
            assert "ignoreConflict=1" in str(request.url)
            return json_response(body)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await docs_api.put_document("MyApp.cls", ["line1"])
        assert result["result"]["name"] == "MyApp.cls"

    async def test_sends_content_payload(self):
        def handler(request):
            payload = json.loads(request.content)
            assert payload["enc"] is False
            assert payload["content"] == ["Class MyApp {", "}"]
            return json_response({"result": {}})

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            await docs_api.put_document("MyApp.cls", ["Class MyApp {", "}"])

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(500)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await docs_api.put_document("MyApp.cls", ["line"])

    async def test_invalid_json(self):
        def handler(request):
            return text_response("bad", status=200)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(ValueError, match="invalid JSON"):
                await docs_api.put_document("MyApp.cls", ["line"])

    async def test_rejected_upload_embedded_status_raises(self):
        """IRIS rejects the PUT but returns HTTP 200 with error in result.status."""
        body = {
            "result": {
                "name": "MyApp.inc",
                "status": "ERROR #16021: Illegal Header Line: #define X",
            }
        }

        def handler(request):
            return json_response(body)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(DocumentPutError, match="ERROR #16021"):
                await docs_api.put_document("MyApp.inc", ["#define X"])

    async def test_rejected_upload_top_level_errors_raises(self):
        """IRIS puts the error in status.errors instead."""
        body = {
            "status": {"errors": [{"error": "ERROR #5001: compile failed"}]},
            "result": {},
        }

        def handler(request):
            return json_response(body)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(DocumentPutError, match="ERROR #5001"):
                await docs_api.put_document("MyApp.cls", ["line"])

    async def test_ok_status_is_not_error(self):
        """A successful put with status 'ok'/'created' must not raise."""
        body = {"result": {"name": "MyApp.cls", "status": "created"}}

        def handler(request):
            return json_response(body)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await docs_api.put_document("MyApp.cls", ["line"])
        assert result["result"]["status"] == "created"


class TestDeleteDocument:
    async def test_success(self):
        body = {"result": {"name": "MyApp.cls", "deleted": True}}

        def handler(request):
            assert request.method == "DELETE"
            return json_response(body)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            result = await docs_api.delete_document("MyApp.cls")
        assert result["result"]["deleted"] is True

    async def test_404_raises_not_found(self):
        def handler(request):
            return httpx.Response(404)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(DocumentNotFound) as exc_info:
                await docs_api.delete_document("Missing.cls")
        assert exc_info.value.name == "Missing.cls"

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(500)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await docs_api.delete_document("MyApp.cls")

    async def test_invalid_json(self):
        def handler(request):
            return text_response("nope", status=200)

        with patch.object(docs_api, "client", lambda *a, **kw: mock_client(handler)):
            with pytest.raises(ValueError, match="invalid JSON"):
                await docs_api.delete_document("MyApp.cls")
