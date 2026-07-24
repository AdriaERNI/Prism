"""Mock IRIS monitor data that changes over time for visual testing.

Run with: PYTHONPATH="" .venv/bin/python scripts/visual_test_monitor.py

This patches collect_snapshot to return oscillating data and runs
prism monitor --watch 1 for 20 seconds, then exits.

Includes realistic data for all extended metrics: database aggregations,
CPU by process type, top processes, CSP connections, SMH, SQL/transactions,
and license/CSP sessions.
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

    # ── Aggregated metrics with realistic data ──
    aggregated = {
        # Database totals — 3 databases with oscillating sizes
        "db_total_size_gb": round(15.5 + 0.5 * math.sin(phase * 0.2), 2),
        "db_total_free_mb": round(2000.0 + 200 * math.sin(phase * 0.3), 1),
        "db_total_max_gb": 50.0,
        "db_avg_latency_ms": round(3.2 + 1.5 * abs(math.sin(phase * 0.8)), 2),
        "db_count": 3,
        # CPU per process type
        "cpu_by_type": {
            "WRTDMN": round(3.2 + 1.5 * abs(math.sin(phase * 1.5)), 2),
            "GARCOL": round(1.1 + 0.5 * abs(math.sin(phase * 0.9)), 2),
            "ECPLAT": round(0.5 + 0.3 * abs(math.sin(phase * 1.1)), 2),
        },
        # Top-5 processes by commands
        "top_processes": [
            {
                "pid": 1234,
                "commands": int(5000 + 200 * math.sin(phase)),
                "routine": "rundown",
                "namespace": "USER",
                "jobtype": "WRTDMN",
            },
            {
                "pid": 5678,
                "commands": int(3000 + 150 * math.sin(phase * 1.3)),
                "routine": "loop",
                "namespace": "DOCDB",
                "jobtype": "GARCOL",
            },
            {
                "pid": 9012,
                "commands": int(1000 + 100 * math.sin(phase * 0.7)),
                "routine": "backup",
                "namespace": "USER",
                "jobtype": "BACKUP",
            },
            {
                "pid": 3456,
                "commands": int(500 + 50 * math.sin(phase * 2.1)),
                "routine": "sqlproc",
                "namespace": "USER",
                "jobtype": "SQL",
            },
            {
                "pid": 7890,
                "commands": int(200 + 30 * math.sin(phase * 1.7)),
                "routine": "clscompile",
                "namespace": "%SYS",
                "jobtype": "OTHER",
            },
        ],
        # CSP connection totals
        "csp_total_connections": round(15 + 5 * abs(math.sin(phase * 0.6)), 1),
        "csp_in_use_connections": round(5 + 3 * abs(math.sin(phase * 0.4)), 1),
        # SMH in GB (metric is in KB)
        "smh_total_gb": 2.0,
    }

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
            # CPU
            "iris_cpu_usage": round(55 + 20 * math.sin(phase * 1.5), 1),
            # Memory
            "iris_phys_mem_percent_used": round(70 + 10 * math.sin(phase * 0.8), 1),
            "iris_page_space_percent_used": round(5 + 3 * math.sin(phase), 1),
            "iris_smh_total_percent_full": 1.2,
            # Process
            "iris_process_count": round(27 + 3 * math.sin(phase * 0.3), 1),
            "iris_glo_ref_per_sec": round(150 + 80 * abs(math.sin(phase * 2)), 1),
            "iris_glo_update_per_sec": round(30 + 20 * abs(math.sin(phase * 1.8)), 1),
            "iris_cache_efficiency": round(95 + 3 * math.sin(phase * 0.5), 1),
            # SQL / Transactions
            "iris_sql_active_queries": round(5 + 3 * abs(math.sin(phase * 1.2)), 1),
            "iris_sql_queries_per_second": round(
                120 + 40 * abs(math.sin(phase * 1.5)), 1
            ),
            "iris_sql_queries_avg_runtime": round(
                0.05 + 0.02 * abs(math.sin(phase * 0.9)), 3
            ),
            "iris_trans_open_count": round(3 + 2 * abs(math.sin(phase * 0.7)), 1),
            "iris_trans_open_secs": round(0.5 + 0.3 * abs(math.sin(phase * 1.1)), 2),
            # License
            "iris_license_consumed": 10.0,
            "iris_license_available": 15.0,
            "iris_license_percent_used": 40.0,
            "iris_license_days_remaining": 30.0,
            # CSP / Web Gateway
            "iris_csp_sessions": 8.0,
            # Disk/IO (still in metrics for scoring)
            "iris_phys_reads_per_sec": round(120 + 80 * abs(math.sin(phase * 2)), 1),
            "iris_phys_writes_per_sec": round(
                45 + 30 * abs(math.sin(phase * 1.8 + 1)), 1
            ),
            "iris_disk_percent_full": 12.0,
        },
        metric_count=571,
        alerts_count=0,
        aggregated=aggregated,
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
