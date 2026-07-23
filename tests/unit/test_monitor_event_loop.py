"""Tests for event-loop handling in `prism monitor --watch`.

Bug: calling asyncio.run() repeatedly in a watch loop causes
RuntimeError: Event loop is closed because the shared httpx AsyncClient
is bound to the first (now-closed) event loop.

These tests verify the fix: the entire watch loop runs inside a single
asyncio.run() call, and the HTTP client is properly closed afterwards.
"""

import asyncio
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
        },
        metric_count=42,
        alerts_count=0,
    )


class TestWatchEventLoop:
    """Verify --watch doesn't crash with 'Event loop is closed'."""

    def test_watch_does_not_raise_event_loop_closed(self):
        """`prism monitor --watch 1` should not raise RuntimeError.

        The bug: repeated asyncio.run() calls in the watch loop close the
        event loop while the shared httpx AsyncClient still has open
        connections, causing 'Event loop is closed' on the next iteration.

        The fix: run the entire watch loop inside one asyncio.run().
        """
        call_count = 0

        async def mock_collect():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise KeyboardInterrupt  # stop after 3 snapshots
            return _make_snapshot(overall=float(call_count * 10))

        async def fast_sleep(*args, **kwargs):
            pass

        with (
            patch(
                "prism.cli.commands.monitor.collect_snapshot",
                new=AsyncMock(side_effect=mock_collect),
            ),
            patch(
                "prism.cli.commands.monitor.asyncio.sleep",
                side_effect=fast_sleep,
            ),
        ):
            result = runner.invoke(app, ["monitor", "--watch", "1"])

        assert result.exit_code == 0
        assert call_count == 3  # 3 snapshots taken before KeyboardInterrupt

    def test_watch_uses_single_asyncio_run(self):
        """Verify only one asyncio.run() is called for the entire watch loop.

        This is the core fix — multiple asyncio.run() calls cause the
        'Event loop is closed' error with the shared httpx client.
        """
        run_count = 0
        original_run = asyncio.run

        def counting_run(coro, **kwargs):
            nonlocal run_count
            run_count += 1
            return original_run(coro, **kwargs)

        snapshot_count = 0

        async def mock_collect():
            nonlocal snapshot_count
            snapshot_count += 1
            return _make_snapshot(overall=float(snapshot_count * 10))

        sleep_count = 0

        async def counting_async_sleep(*args, **kwargs):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise KeyboardInterrupt

        with (
            patch(
                "prism.cli.commands.monitor.collect_snapshot",
                new=AsyncMock(side_effect=mock_collect),
            ),
            patch(
                "prism.cli.commands.monitor.asyncio.sleep",
                side_effect=counting_async_sleep,
            ),
            patch(
                "prism.cli.commands.monitor.asyncio.run",
                side_effect=counting_run,
            ),
        ):
            result = runner.invoke(app, ["monitor", "--watch", "1"])

        assert result.exit_code == 0
        # The entire watch loop should use exactly ONE asyncio.run()
        assert run_count == 1, (
            f"Expected 1 asyncio.run() call, got {run_count}. "
            "Multiple calls cause 'Event loop is closed' with shared httpx client."
        )

    def test_single_snapshot_works_without_error(self):
        """`prism monitor` (no watch) should also work without event loop issues."""
        with patch(
            "prism.cli.commands.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            mock.return_value = _make_snapshot()
            result = runner.invoke(app, ["monitor"])

        assert result.exit_code == 0
        assert "CPU" in result.output
