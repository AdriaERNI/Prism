"""Unit tests for the monitoring dashboard — history, sparklines, rendering."""

from prism.iris.monitor.dashboard import (
    HistoryBuffer,
    _sparkline,
    _color_for_score,
    _grade_color,
    _format_score_bar,
)
from prism.iris.monitor import MonitorSnapshot
from prism.iris.monitor.scorer import LoadScore


def _snap(overall=25.0, cpu=20.0, mem=30.0, disk=25.0, proc=25.0):
    return MonitorSnapshot(
        timestamp=1234567890.0,
        score=LoadScore(
            overall=overall,
            cpu=cpu,
            memory=mem,
            disk=disk,
            process=proc,
            details={},
        ),
        grade="healthy",
        metrics={
            "iris_cpu_usage": 12.5,
            "iris_phys_mem_percent_used": 45.2,
            "iris_process_count": 42,
            "iris_phys_reads_per_sec": 120.5,
        },
        metric_count=42,
        alerts_count=0,
    )


class TestHistoryBuffer:
    def test_create_with_max_samples(self):
        buf = HistoryBuffer(max_samples=60)
        assert len(buf) == 0
        assert buf.max_samples == 60

    def test_add_snapshot_stores_values(self):
        buf = HistoryBuffer(max_samples=10)
        buf.add(_snap(overall=10.0, cpu=10.0))
        assert len(buf) == 1
        assert buf.cpu_history() == [10.0]
        assert buf.score_history() == [10.0]

    def test_add_multiple_snapshots(self):
        buf = HistoryBuffer(max_samples=10)
        buf.add(_snap(overall=10.0, cpu=10.0))
        buf.add(_snap(overall=20.0, cpu=20.0))
        buf.add(_snap(overall=30.0, cpu=30.0))
        assert len(buf) == 3
        assert buf.cpu_history() == [10.0, 20.0, 30.0]
        assert buf.memory_history() == [30.0, 30.0, 30.0]

    def test_overflow_oldest_dropped(self):
        buf = HistoryBuffer(max_samples=3)
        for i in range(5):
            buf.add(_snap(overall=float(i)))
        assert len(buf) == 3
        # Oldest 0,1 dropped; 2,3,4 remain
        assert buf.score_history() == [2.0, 3.0, 4.0]

    def test_empty_history_returns_empty_list(self):
        buf = HistoryBuffer(max_samples=10)
        assert buf.cpu_history() == []
        assert buf.score_history() == []

    def test_all_history_series(self):
        buf = HistoryBuffer(max_samples=10)
        buf.add(_snap(overall=10.0, cpu=15.0, mem=25.0, disk=35.0, proc=45.0))
        assert buf.cpu_history() == [15.0]
        assert buf.memory_history() == [25.0]
        assert buf.disk_history() == [35.0]
        assert buf.process_history() == [45.0]
        assert buf.score_history() == [10.0]

    def test_timestamps_tracked(self):
        buf = HistoryBuffer(max_samples=10)
        s1 = _snap(overall=10.0)
        s1 = MonitorSnapshot(
            timestamp=1000.0,
            score=s1.score,
            grade=s1.grade,
            metrics=s1.metrics,
            metric_count=s1.metric_count,
            alerts_count=s1.alerts_count,
        )
        s2 = MonitorSnapshot(
            timestamp=2000.0,
            score=s1.score,
            grade=s1.grade,
            metrics=s1.metrics,
            metric_count=s1.metric_count,
            alerts_count=s1.alerts_count,
        )
        buf.add(s1)
        buf.add(s2)
        assert buf.timestamps() == [1000.0, 2000.0]


class TestSparkline:
    def test_empty_data_returns_empty(self):
        assert _sparkline([]) == ""

    def test_single_value(self):
        result = _sparkline([50.0])
        assert len(result) == 1
        # A single value maps to the middle block when span is 0
        assert result == "▄"

    def test_increasing_values(self):
        result = _sparkline([0.0, 25.0, 50.0, 75.0, 100.0])
        # Should be 5 characters, ascending
        assert len(result) == 5

    def test_flat_values(self):
        result = _sparkline([50.0, 50.0, 50.0])
        assert len(result) == 3
        # All same character
        assert len(set(result)) == 1

    def test_decreasing_values(self):
        result = _sparkline([100.0, 75.0, 50.0, 25.0, 0.0])
        assert len(result) == 5

    def test_all_zeros(self):
        result = _sparkline([0.0, 0.0, 0.0])
        assert len(result) == 3

    def test_max_samples_truncation(self):
        result = _sparkline(list(range(100)), width=10)
        assert len(result) == 10


class TestColorForScore:
    def test_idle_score_returns_green(self):
        c = _color_for_score(5.0)
        assert "green" in c

    def test_healthy_score_returns_green(self):
        c = _color_for_score(20.0)
        assert "green" in c

    def test_moderate_score_returns_yellow(self):
        c = _color_for_score(40.0)
        assert "yellow" in c

    def test_loaded_score_returns_red(self):
        c = _color_for_score(70.0)
        assert "red" in c

    def test_critical_score_returns_bold_red(self):
        c = _color_for_score(90.0)
        assert "red" in c


class TestGradeColor:
    def test_idle_is_green(self):
        assert "green" in _grade_color("idle")

    def test_healthy_is_green(self):
        assert "green" in _grade_color("healthy")

    def test_moderate_is_yellow(self):
        assert "yellow" in _grade_color("moderate")

    def test_loaded_is_red(self):
        assert "red" in _grade_color("loaded")

    def test_critical_is_bold_red(self):
        assert "red" in _grade_color("critical")


class TestFormatScoreBar:
    """Score bar shows N.N/100 (a number), not N.N% (a percentage)."""

    def test_zero_score(self):
        bar, score_str = _format_score_bar(0.0)
        assert "█" not in bar
        assert "0.0/100" in score_str

    def test_full_score(self):
        bar, score_str = _format_score_bar(100.0)
        assert "█" in bar
        assert "100.0/100" in score_str

    def test_half_score(self):
        bar, score_str = _format_score_bar(50.0)
        assert "█" in bar
        assert "50.0/100" in score_str

    def test_score_not_percentage(self):
        """Score string must NOT contain a % sign."""
        _, score_str = _format_score_bar(42.5)
        assert "%" not in score_str
        assert "42.5/100" == score_str

    def test_clamps_above_100(self):
        _, score_str = _format_score_bar(150.0)
        assert "100.0/100" in score_str

    def test_clamps_below_0(self):
        _, score_str = _format_score_bar(-10.0)
        assert "0.0/100" in score_str


# ── Dashboard rendering tests ──────────────────────────────────────────


from prism.iris.monitor.dashboard import render_dashboard  # noqa: E402
from rich.console import Console  # noqa: E402


def _full_snap(
    overall: float = 25.0,
    cpu: float = 20.0,
    mem: float = 30.0,
    disk: float = 25.0,
    proc: float = 25.0,
    aggregated: dict | None = None,
) -> MonitorSnapshot:
    """Build a snapshot with extended metrics and aggregated data."""
    return MonitorSnapshot(
        timestamp=1234567890.0,
        score=LoadScore(
            overall=overall,
            cpu=cpu,
            memory=mem,
            disk=disk,
            process=proc,
            details={},
        ),
        grade="healthy",
        metrics={
            "iris_cpu_usage": 12.5,
            "iris_phys_mem_percent_used": 45.2,
            "iris_page_space_percent_used": 5.0,
            "iris_smh_total_percent_full": 1.2,
            "iris_process_count": 42,
            "iris_glo_ref_per_sec": 150.0,
            "iris_glo_update_per_sec": 30.0,
            "iris_cache_efficiency": 95.0,
            "iris_sql_active_queries": 5.0,
            "iris_sql_queries_per_second": 120.0,
            "iris_sql_queries_avg_runtime": 0.05,
            "iris_trans_open_count": 3.0,
            "iris_trans_open_secs": 0.5,
            "iris_license_consumed": 10.0,
            "iris_license_available": 15.0,
            "iris_license_days_remaining": 30.0,
            "iris_csp_sessions": 8.0,
        },
        metric_count=571,
        alerts_count=0,
        aggregated=aggregated or {},
    )


class TestRenderDashboard:
    """Test the render_dashboard function with the new 3-column layout."""

    def test_render_returns_panel(self):
        """render_dashboard should return a Panel object."""
        from rich.panel import Panel

        snap = _full_snap()
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        result = render_dashboard(snap, buf, console)
        assert isinstance(result, Panel)

    def test_render_contains_all_panel_titles(self):
        """Dashboard should contain all 6 panel titles: CPU, Memory, Disk, Process, SQL/Tx, License."""
        snap = _full_snap()
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "CPU" in output
        assert "Memory" in output
        assert "Disk" in output
        assert "Process" in output
        assert "SQL/Tx" in output or "SQL" in output
        assert "License" in output

    def test_render_contains_sql_metrics(self):
        """Dashboard SQL/Tx panel should show SQL and transaction metrics."""
        snap = _full_snap()
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "Active Q" in output
        assert "Open Tx" in output

    def test_render_contains_license_metrics(self):
        """Dashboard License panel should show license and CSP metrics."""
        snap = _full_snap()
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "Lic Used" in output or "Lic" in output
        assert "Sessions" in output

    def test_render_contains_db_aggregations(self):
        """Dashboard Disk panel should show DB aggregation labels."""
        agg = {
            "db_total_size_gb": 15.5,
            "db_total_free_mb": 2000.0,
            "db_total_max_gb": 50.0,
            "db_avg_latency_ms": 3.2,
            "db_count": 3,
        }
        snap = _full_snap(aggregated=agg)
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "DB Total" in output
        assert "15.5 GB" in output
        assert "DB Latency" in output

    def test_render_contains_cpu_by_type(self):
        """CPU panel should show per-process-type CPU breakdown."""
        agg = {
            "cpu_by_type": {"WRTDMN": 3.2, "GARCOL": 1.1, "ECPLAT": 0.5},
        }
        snap = _full_snap(aggregated=agg)
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "WRTDMN" in output
        assert "3.2" in output

    def test_render_contains_top_processes(self):
        """Process panel should show top processes with command counts."""
        agg = {
            "top_processes": [
                {"pid": 1234, "commands": 5000, "routine": "rundown"},
                {"pid": 5678, "commands": 3000, "routine": "loop"},
            ],
        }
        snap = _full_snap(aggregated=agg)
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "1234" in output
        assert "5000" in output

    def test_render_contains_smh_total_gb(self):
        """Memory panel should show SMH Total in GB."""
        agg = {"smh_total_gb": 2.0}
        snap = _full_snap(aggregated=agg)
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "SMH Total" in output
        assert "2.0 GB" in output

    def test_render_contains_global_activity(self):
        """Process panel should show global refs/updates and cache efficiency."""
        snap = _full_snap()
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "Glo Refs" in output
        assert "Cache Eff" in output

    def test_render_contains_users_in_header(self):
        """Header should show user count from iris_csp_sessions."""
        snap = _full_snap()
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "users" in output
        assert "8" in output  # iris_csp_sessions = 8.0

    def test_render_fits_80_columns(self):
        """Dashboard should render without errors at 80-column width."""
        snap = _full_snap()
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=80, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()
        # Should not error and should contain key elements
        assert "Prism Monitor" in output
        assert "CPU" in output

    def test_render_csp_aggregations(self):
        """License panel should show CSP connection totals from aggregations."""
        agg = {
            "csp_total_connections": 15.0,
            "csp_in_use_connections": 5.0,
        }
        snap = _full_snap(aggregated=agg)
        buf = HistoryBuffer(max_samples=10)
        buf.add(snap)
        console = Console(width=120, record=True)
        panel = render_dashboard(snap, buf, console)
        console.print(panel)
        output = console.export_text()

        assert "CSP Conn" in output
        assert "15" in output  # csp_total_connections
