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
        # aggregated must be present in to_dict output
        assert "aggregated" in d
        assert "aggregated" in json_str


# ── Aggregated metrics tests ────────────────────────────────────────────


# Sample Prometheus text with labeled metrics for aggregation tests
LABELED_METRICS = """\
# HELP iris_cpu_usage Percent of CPU usage
# TYPE iris_cpu_usage gauge
iris_cpu_usage 25.5
# HELP iris_phys_mem_percent_used Percent of physical memory
# TYPE iris_phys_mem_percent_used gauge
iris_phys_mem_percent_used 45.2
# HELP iris_process_count Total processes
# TYPE iris_process_count gauge
iris_process_count 42
# HELP iris_db_size_mb Database size in MB
# TYPE iris_db_size_mb gauge
iris_db_size_mb{id="USER",dir="/data/user"} 5120
iris_db_size_mb{id="DOCDB",dir="/data/docdb"} 3072
# HELP iris_db_free_space Free space in MB
# TYPE iris_db_free_space gauge
iris_db_free_space{id="USER"} 1024
iris_db_free_space{id="DOCDB"} 2048
# HELP iris_db_max_size_mb Max size in MB
# TYPE iris_db_max_size_mb gauge
iris_db_max_size_mb{id="USER"} 10240
iris_db_max_size_mb{id="DOCDB"} 8192
# HELP iris_db_latency Random read latency in ms
# TYPE iris_db_latency gauge
iris_db_latency{id="USER"} 2.5
iris_db_latency{id="DOCDB"} 5.5
# HELP iris_cpu_pct CPU percent by process type
# TYPE iris_cpu_pct gauge
iris_cpu_pct{id="WRTDMN"} 3.2
iris_cpu_pct{id="GARCOL"} 1.1
iris_cpu_pct{id="ECPLAT"} 0.5
# HELP iris_process_commands Commands executed by process
# TYPE iris_process_commands gauge
iris_process_commands{id="1234"} 5000
iris_process_commands{id="5678"} 3000
iris_process_commands{id="9012"} 1000
# HELP iris_process Process info
# TYPE iris_process gauge
iris_process{id="1234",routine="rundown",namespace="USER",jobtype="WRTDMN"} 1
iris_process{id="5678",routine="loop",namespace="DOCDB",jobtype="GARCOL"} 1
iris_process{id="9012",routine="backup",namespace="USER",jobtype="BACKUP"} 1
# HELP iris_csp_actual_connections CSP actual connections
# TYPE iris_csp_actual_connections gauge
iris_csp_actual_connections{id="127.0.0.1:52773"} 10
iris_csp_actual_connections{id="192.168.1.1:52773"} 5
# HELP iris_csp_in_use_connections CSP in-use connections
# TYPE iris_csp_in_use_connections gauge
iris_csp_in_use_connections{id="127.0.0.1:52773"} 3
iris_csp_in_use_connections{id="192.168.1.1:52773"} 2
# HELP iris_smh_total Shared memory heap total in KB
# TYPE iris_smh_total gauge
iris_smh_total 2097152
"""


class TestAggregatedMetrics:
    """Test that collect_snapshot computes aggregated metrics from labeled samples."""

    async def test_aggregated_dict_present(self):
        """Snapshot should have a non-None aggregated dict."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        assert snapshot.aggregated is not None
        assert isinstance(snapshot.aggregated, dict)

    async def test_db_total_size_gb(self):
        """db_total_size_gb should sum all iris_db_size_mb values and convert to GB."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        # 5120 + 3072 = 8192 MB → 8.0 GB
        assert snapshot.aggregated["db_total_size_gb"] == 8.0

    async def test_db_total_free_mb(self):
        """db_total_free_mb should sum all iris_db_free_space values."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        # 1024 + 2048 = 3072 MB
        assert snapshot.aggregated["db_total_free_mb"] == 3072.0

    async def test_db_total_max_gb(self):
        """db_total_max_gb should sum all iris_db_max_size_mb values and convert to GB."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        # 10240 + 8192 = 18432 MB → 18.0 GB
        assert snapshot.aggregated["db_total_max_gb"] == 18.0

    async def test_db_avg_latency_ms(self):
        """db_avg_latency_ms should average all iris_db_latency values."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        # (2.5 + 5.5) / 2 = 4.0
        assert snapshot.aggregated["db_avg_latency_ms"] == 4.0

    async def test_db_count(self):
        """db_count should equal the number of iris_db_size_mb samples."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        assert snapshot.aggregated["db_count"] == 2

    async def test_cpu_by_type(self):
        """cpu_by_type should map process type → CPU % from labeled iris_cpu_pct."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        cpu_by_type = snapshot.aggregated["cpu_by_type"]
        assert isinstance(cpu_by_type, dict)
        assert cpu_by_type["WRTDMN"] == 3.2
        assert cpu_by_type["GARCOL"] == 1.1
        assert cpu_by_type["ECPLAT"] == 0.5

    async def test_top_processes_sorted(self):
        """top_processes should be sorted by commands descending, max 5 entries."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        top = snapshot.aggregated["top_processes"]
        assert isinstance(top, list)
        assert len(top) <= 5
        # First entry should have the most commands
        assert top[0]["commands"] == 5000
        assert top[0]["pid"] == 1234
        assert top[0]["routine"] == "rundown"
        assert top[1]["commands"] == 3000

    async def test_csp_total_connections(self):
        """csp_total_connections should sum all iris_csp_actual_connections."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        # 10 + 5 = 15
        assert snapshot.aggregated["csp_total_connections"] == 15.0

    async def test_csp_in_use_connections(self):
        """csp_in_use_connections should sum all iris_csp_in_use_connections."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        # 3 + 2 = 5
        assert snapshot.aggregated["csp_in_use_connections"] == 5.0

    async def test_smh_total_gb(self):
        """smh_total_gb should convert KB to GB (divide by 1024*1024)."""
        with (
            patch(
                "prism.iris.monitor.get_metrics", new_callable=AsyncMock
            ) as mock_metrics,
            patch(
                "prism.iris.monitor.get_alerts", new_callable=AsyncMock
            ) as mock_alerts,
        ):
            mock_metrics.return_value = LABELED_METRICS
            mock_alerts.return_value = ""
            snapshot = await collect_snapshot()

        # 2097152 KB / 1024 / 1024 = 2.0 GB
        assert snapshot.aggregated["smh_total_gb"] == 2.0

    async def test_aggregated_empty_when_no_labeled_metrics(self):
        """Aggregated metrics should default to zeros when no labeled metrics present."""
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

        agg = snapshot.aggregated
        assert agg["db_total_size_gb"] == 0.0
        assert agg["db_count"] == 0
        assert agg["csp_total_connections"] == 0.0
        assert agg["smh_total_gb"] == 0.0
        assert agg["cpu_by_type"] == {}
        assert agg["top_processes"] == []
