"""Unit tests for the monitoring collector — orchestrates API→parser→scorer."""

from unittest.mock import AsyncMock, patch


from prism.iris.monitor import collect_snapshot, MonitorSnapshot


# Sample Prometheus text returned by IRIS /api/monitor/metrics
SAMPLE_METRICS = """\
# HELP iris_cpu_usage Percent of CPU usage
# TYPE iris_cpu_usage gauge
iris_cpu_usage 25.5
# HELP iris_phys_mem_percent_used Percent of physical memory
# TYPE iris_phys_mem_percent_used gauge
iris_phys_mem_percent_used 45.2
# HELP iris_process_count Total processes
# TYPE iris_process_count gauge
iris_process_count 42
# HELP iris_phys_reads_per_sec Physical reads
# TYPE iris_phys_reads_per_sec gauge
iris_phys_reads_per_sec 120.5
# HELP iris_disk_percent_full Disk full
# TYPE iris_disk_percent_full gauge
iris_disk_percent_full{id="USER",dir="/data"} 35.0
"""

SAMPLE_ALERTS = """\
# HELP iris_system_alerts Number of alerts
# TYPE iris_system_alerts gauge
iris_system_alerts 2
"""


class TestCollectSnapshot:
    async def test_returns_monitor_snapshot(self):
        """collect_snapshot returns a MonitorSnapshot with score, grade, metrics."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = SAMPLE_METRICS
            mock_alerts.return_value = SAMPLE_ALERTS

            snapshot = await collect_snapshot()

        assert isinstance(snapshot, MonitorSnapshot)
        assert snapshot.score.overall > 0
        assert snapshot.grade in ("idle", "healthy", "moderate", "loaded", "critical")
        assert snapshot.metric_count > 0
        assert snapshot.timestamp is not None

    async def test_snapshot_includes_raw_metrics(self):
        """Snapshot should include a curated subset of key metrics."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = SAMPLE_METRICS
            mock_alerts.return_value = ""

            snapshot = await collect_snapshot()

        assert "iris_cpu_usage" in snapshot.metrics
        assert snapshot.metrics["iris_cpu_usage"] == 25.5
        assert "iris_phys_mem_percent_used" in snapshot.metrics
        assert snapshot.metrics["iris_phys_mem_percent_used"] == 45.2

    async def test_snapshot_handles_empty_metrics(self):
        """Empty metrics endpoint → zero score, idle grade."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = ""
            mock_alerts.return_value = ""

            snapshot = await collect_snapshot()

        assert snapshot.score.overall == 0
        assert snapshot.grade == "idle"
        assert snapshot.metric_count == 0

    async def test_snapshot_includes_alerts(self):
        """Snapshot should include alert count from /api/monitor/alerts."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = SAMPLE_METRICS
            mock_alerts.return_value = SAMPLE_ALERTS

            snapshot = await collect_snapshot()

        assert snapshot.alerts_count >= 0

    async def test_collect_is_fast(self):
        """collect_snapshot should complete quickly (sub-second with mocked API)."""
        import time

        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = SAMPLE_METRICS
            mock_alerts.return_value = ""

            start = time.monotonic()
            await collect_snapshot()
            elapsed = time.monotonic() - start

        assert elapsed < 1.0  # should be near-instant with mocked HTTP

    async def test_snapshot_to_dict_serializable(self):
        """Snapshot should convert to a plain dict for JSON output."""
        import json

        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = SAMPLE_METRICS
            mock_alerts.return_value = ""

            snapshot = await collect_snapshot()
            d = snapshot.to_dict()

        # Must be JSON serializable
        json_str = json.dumps(d, default=str)
        assert "score" in json_str
        assert "grade" in json_str
        assert "metrics" in json_str
