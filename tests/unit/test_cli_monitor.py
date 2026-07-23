"""Unit tests for `prism monitor` CLI command."""

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from prism.cli.app import app
from prism.iris.monitor import MonitorSnapshot
from prism.iris.monitor.scorer import LoadScore

runner = CliRunner()


def _make_snapshot(overall: float = 25.0) -> MonitorSnapshot:
    return MonitorSnapshot(
        timestamp=1234567890.0,
        score=LoadScore(
            overall=overall,
            cpu=20.0,
            memory=30.0,
            disk=25.0,
            process=25.0,
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


class TestMonitorDashboard:
    """Tests for the default human-readable dashboard output."""

    def test_monitor_default_renders_dashboard(self):
        """`prism monitor` (no flags) renders a human-readable dashboard."""
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot()
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        # The dashboard should contain resource labels
        assert "CPU" in result.output
        assert "Memory" in result.output
        assert "Disk" in result.output
        assert "Process" in result.output
        assert "Load Score" in result.output
        # Should NOT be raw JSON
        assert not result.output.strip().startswith("{")

    def test_monitor_dashboard_shows_grade(self):
        """Dashboard output includes the health grade."""
        snap = _make_snapshot(overall=5.0)
        # Override grade to match the score
        snap = MonitorSnapshot(
            timestamp=snap.timestamp,
            score=snap.score,
            grade="idle",
            metrics=snap.metrics,
            metric_count=snap.metric_count,
            alerts_count=snap.alerts_count,
        )
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = snap
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        assert "IDLE" in result.output.upper()

    def test_monitor_dashboard_shows_score_bar(self):
        """Dashboard shows a progress bar for the overall score."""
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot(overall=50.0)
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        # Progress bar uses block characters
        assert "█" in result.output or "░" in result.output

    def test_monitor_dashboard_score_shown_as_number_not_percentage(self):
        """Load score must be displayed as a number (N.N/100), not a percentage."""
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot(overall=42.5)
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        # Score should show as "42.5/100" not "42.5%"
        assert "42.5/100" in result.output
        # The Load Score panel should NOT have a % sign on the score value
        # (sub-metrics like "CPU Usage (OS %)" can still have %)
        assert "42.5%" not in result.output

    def test_monitor_dashboard_shows_per_category_numbers(self):
        """Load Score panel must show numeric scores for each category."""
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot(overall=42.5)
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        # Per-category numbers should appear in the Load Score panel
        assert "CPU 20.0" in result.output
        assert "Mem 30.0" in result.output
        assert "Disk 25.0" in result.output
        assert "Proc 25.0" in result.output

    def test_load_score_panel_no_redundant_sparklines(self):
        """Load Score panel should NOT have sparklines — they're in the top panels.

        The top 4 resource panels (CPU, Memory, Disk/IO, Process) each
        have their own sparkline graph.  The Load Score panel is a
        numeric summary only — no duplicate graphs.
        """
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot(overall=42.5)
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        output = result.output
        # Find the Load Score section
        ls_idx = output.index("Load Score")
        load_score_section = output[ls_idx:]
        # Find the end (next outer border or end)
        # Sparkline blocks are ▁▂▃▄▅▆▇ — but █ is also a progress bar char
        # so we check for the non-bar sparkline chars only
        sparkline_chars = set("▁▂▃▄▅▆▇")
        # The Load Score section should only contain █ (bar) not ▁-▇ (sparklines)
        sparkline_found = any(c in load_score_section for c in sparkline_chars)
        assert not sparkline_found, (
            "Load Score panel should not contain sparkline characters "
            "(▁▂▃▄▅▆▇) — those graphs are already shown in the top panels"
        )

    def test_load_score_panel_shows_averages(self):
        """Load Score panel must show SMA + EWMA (1m/5m/15m) + trend arrow."""
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot(overall=42.5)
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        output = result.output
        # The averages line should contain "Avg", "1m", "5m", "15m"
        assert "Avg" in output
        assert "1m" in output
        assert "5m" in output
        assert "15m" in output
        # Trend arrow should be one of ↑ ↓ →
        assert any(arrow in output for arrow in ["↑", "↓", "→"])

    def test_load_score_panel_shows_helpers(self):
        """Load Score panel must show helper text explaining how to read it."""
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot(overall=42.5)
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        output = result.output
        # Helper: "lower=better"
        assert "lower=better" in output
        # Helper: explains the range (0-100)
        assert "0-100" in output
        # Helper: explains the trend arrow
        assert "↓ improving" in output
        assert "→ stable" in output
        assert "↑ worsening" in output


class TestMonitorJson:
    def test_monitor_json_outputs_json(self):
        """`prism monitor --json` outputs JSON with score and metrics."""
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot()
            result = runner.invoke(app, ["monitor", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "score" in data
        assert data["score"]["overall"] == 25.0
        assert "grade" in data
        assert data["grade"] == "healthy"
        assert "metrics" in data

    def test_monitor_json_with_raw_flag(self):
        """`prism monitor --json --raw` includes raw_metrics in output."""
        snapshot = _make_snapshot()
        from prism.iris.monitor.parser import MetricSample

        snapshot = MonitorSnapshot(
            timestamp=snapshot.timestamp,
            score=snapshot.score,
            grade=snapshot.grade,
            metrics=snapshot.metrics,
            metric_count=snapshot.metric_count,
            alerts_count=snapshot.alerts_count,
            raw_samples=[MetricSample(name="iris_cpu_usage", value=12.5, labels={})],
        )
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = snapshot
            result = runner.invoke(app, ["monitor", "--json", "--raw"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "raw_metrics" in data
        assert len(data["raw_metrics"]) == 1


class TestMonitorErrorHandling:
    def test_monitor_error_handling(self):
        """`prism monitor` handles connection errors gracefully."""
        import httpx

        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = httpx.ConnectError("Connection refused")
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 1
        assert "Cannot connect" in result.output or "Error" in result.output


class TestMonitorCompare:
    def test_monitor_compare_with_two_snapshots(self):
        """`prism monitor --compare` takes two snapshots and compares them."""
        snapshot_a = _make_snapshot(overall=20.0)
        snapshot_b = _make_snapshot(overall=60.0)

        with (
            patch(
                "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
            ) as mock,
            patch("prism.cli.commands.monitor.time.sleep"),
        ):
            mock.side_effect = [snapshot_a, snapshot_b]
            result = runner.invoke(app, ["monitor", "--compare"])

        assert result.exit_code == 0
        # Output has stderr progress messages mixed in; extract the JSON block
        output = result.output
        json_start = output.find('{\n  "snapshot_a"')
        assert json_start >= 0, f"JSON block not found in output: {output!r}"
        data = json.loads(output[json_start:])
        assert "comparison" in data
        assert data["comparison"]["less_loaded"] == "snapshot_a"
        assert data["comparison"]["difference"] == 40.0
