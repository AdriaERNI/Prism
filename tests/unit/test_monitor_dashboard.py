"""Unit tests for the monitoring dashboard — history, sparklines, rendering."""

from prism.iris.monitor.dashboard import (
    HistoryBuffer,
    _sparkline,
    _color_for_score,
    _grade_color,
    _format_bar,
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


class TestFormatBar:
    def test_zero_percent_returns_empty_bar(self):
        bar, pct_str = _format_bar(0.0)
        assert "█" not in bar
        assert "0.0%" in pct_str

    def test_full_bar(self):
        bar, pct_str = _format_bar(100.0)
        assert "█" in bar
        assert "100.0%" in pct_str

    def test_half_bar(self):
        bar, pct_str = _format_bar(50.0)
        assert "█" in bar
        assert "50.0%" in pct_str

    def test_clamps_above_100(self):
        bar, pct_str = _format_bar(150.0)
        assert "100.0%" in pct_str

    def test_clamps_below_0(self):
        bar, pct_str = _format_bar(-10.0)
        assert "0.0%" in pct_str


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
