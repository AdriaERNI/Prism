"""Unit tests for IRIS monitoring API — /api/monitor/metrics and /alerts."""

from unittest.mock import patch

import httpx
import pytest

from prism.iris.api import monitor as monitor_api
from tests.unit.test_iris_api.conftest import mock_client

# ── /api/monitor/metrics ──────────────────────────────────────────────


class TestGetMetrics:
    async def test_returns_prometheus_text(self):
        body = (
            "# HELP iris_cpu_usage Percent of CPU usage\n"
            "# TYPE iris_cpu_usage gauge\n"
            "iris_cpu_usage 12.5\n"
            "# HELP iris_phys_mem_percent_used Percent of physical memory\n"
            "# TYPE iris_phys_mem_percent_used gauge\n"
            "iris_phys_mem_percent_used 45.2\n"
        )

        def handler(request):
            assert "/api/monitor/metrics" in str(request.url)
            return httpx.Response(
                200, text=body, headers={"Content-Type": "text/plain"}
            )

        with patch.object(monitor_api, "client", lambda: mock_client(handler)):
            result = await monitor_api.get_metrics()
        assert isinstance(result, str)
        assert "iris_cpu_usage" in result
        assert "iris_phys_mem_percent_used" in result

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(500, text="Internal Server Error")

        with patch.object(monitor_api, "client", lambda: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await monitor_api.get_metrics()

    async def test_empty_response(self):
        def handler(request):
            return httpx.Response(200, text="", headers={"Content-Type": "text/plain"})

        with patch.object(monitor_api, "client", lambda: mock_client(handler)):
            result = await monitor_api.get_metrics()
        assert result == ""

    async def test_connection_error(self):
        def handler(request):
            raise httpx.ConnectError("Connection refused")

        with patch.object(monitor_api, "client", lambda: mock_client(handler)):
            with pytest.raises(httpx.ConnectError):
                await monitor_api.get_metrics()


# ── /api/monitor/alerts ───────────────────────────────────────────────


class TestGetAlerts:
    async def test_returns_alerts_text(self):
        body = (
            "# HELP iris_system_alerts Number of alerts\n"
            "# TYPE iris_system_alerts gauge\n"
            'iris_system_alerts{application="App1"} 3\n'
        )

        def handler(request):
            assert "/api/monitor/alerts" in str(request.url)
            return httpx.Response(
                200, text=body, headers={"Content-Type": "text/plain"}
            )

        with patch.object(monitor_api, "client", lambda: mock_client(handler)):
            result = await monitor_api.get_alerts()
        assert isinstance(result, str)
        assert "iris_system_alerts" in result

    async def test_http_error(self):
        def handler(request):
            return httpx.Response(404, text="Not Found")

        with patch.object(monitor_api, "client", lambda: mock_client(handler)):
            with pytest.raises(httpx.HTTPStatusError):
                await monitor_api.get_alerts()

    async def test_empty_alerts(self):
        def handler(request):
            return httpx.Response(200, text="", headers={"Content-Type": "text/plain"})

        with patch.object(monitor_api, "client", lambda: mock_client(handler)):
            result = await monitor_api.get_alerts()
        assert result == ""
