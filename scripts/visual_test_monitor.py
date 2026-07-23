"""Mock IRIS monitor data that changes over time for visual testing.

Run with: PYTHONPATH="" .venv/bin/python scripts/visual_test_monitor.py

This patches collect_snapshot to return oscillating data and runs
prism monitor --watch 1 for 20 seconds, then exits.
"""

import asyncio
import math
import time

# Patch BEFORE importing the CLI


from prism.iris.monitor import MonitorSnapshot
from prism.iris.monitor.scorer import LoadScore

_start_time = time.time()


def _make_snapshot(t: float) -> MonitorSnapshot:
    """Generate a snapshot with values that oscillate over time."""
    phase = t * 0.3
    cpu = 30 + 25 * math.sin(phase)
    mem = 45 + 15 * math.sin(phase * 0.7 + 1)
    disk = 20 + 10 * math.sin(phase * 0.5 + 2)
    proc = 15 + 8 * math.sin(phase * 1.2 + 3)
    overall = (cpu + mem + disk + proc) / 4

    if overall < 10:
        grade = "idle"
    elif overall < 30:
        grade = "healthy"
    elif overall < 60:
        grade = "moderate"
    elif overall < 80:
        grade = "loaded"
    else:
        grade = "critical"

    return MonitorSnapshot(
        timestamp=time.time(),
        score=LoadScore(
            overall=round(overall, 2),
            cpu=round(max(0, cpu), 2),
            memory=round(max(0, mem), 2),
            disk=round(max(0, disk), 2),
            process=round(max(0, proc), 2),
            details={},
        ),
        grade=grade,
        metrics={
            "iris_cpu_usage": round(55 + 20 * math.sin(phase * 1.5), 1),
            "iris_phys_mem_percent_used": round(70 + 10 * math.sin(phase * 0.8), 1),
            "iris_page_space_percent_used": round(5 + 3 * math.sin(phase), 1),
            "iris_smh_total_percent_full": 1.2,
            "iris_phys_reads_per_sec": round(120 + 80 * abs(math.sin(phase * 2)), 1),
            "iris_phys_writes_per_sec": round(
                45 + 30 * abs(math.sin(phase * 1.8 + 1)), 1
            ),
            "iris_disk_percent_full": 12.0,
            "iris_process_count": round(27 + 3 * math.sin(phase * 0.3), 1),
            "iris_glo_seize_per_sec": round(2 + 5 * abs(math.sin(phase * 0.9)), 1),
            "iris_wd_cycle_time": round(13 + 4 * math.sin(phase * 1.1), 1),
        },
        metric_count=571,
        alerts_count=0,
    )


async def mock_collect():
    t = time.time() - _start_time
    return _make_snapshot(t)


async def main():
    """Run the dashboard for 20 seconds, capturing snapshots."""
    from rich.console import Console

    from prism.iris.monitor.dashboard import HistoryBuffer, render_dashboard

    console = Console()
    history = HistoryBuffer()

    # Take 20 snapshots, 1 second apart
    for i in range(20):
        snapshot = await mock_collect()
        history.add(snapshot)
        panel = render_dashboard(snapshot, history, console)

        # Clear and print
        console.print(panel)
        await asyncio.sleep(1)

        if i < 19:
            # Clear screen for next render
            console.print("\033[2J\033[H", end="")


asyncio.run(main())
