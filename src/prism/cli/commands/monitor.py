"""`prism monitor` — live IRIS instance resource monitoring.

Fetches metrics from the IRIS /api/monitor REST endpoint, computes a
weighted load score (CPU, memory, disk/IO, process load), and reports a
health grade. Supports ``--compare`` to take two snapshots and determine
which is less loaded.

Usage::

    prism monitor              # one-shot snapshot
    prism monitor --raw        # include all raw metrics
    prism monitor --compare    # take two snapshots, compare them
    prism monitor --watch 2    # continuous monitoring, refresh every 2s
"""

from __future__ import annotations

import asyncio
import time

import typer

from prism.cli.errors import handle_command_error
from prism.iris.monitor import collect_snapshot
from prism.iris.monitor.scorer import compare_snapshots
from prism.output import format_output, get_output_format


def monitor(
    raw: bool = typer.Option(
        False,
        "--raw",
        help="Include all raw metric samples in the output.",
    ),
    compare: bool = typer.Option(
        False,
        "--compare",
        help="Take two snapshots with a 5-second interval and compare them.",
    ),
    watch: float = typer.Option(
        0,
        "--watch",
        "-w",
        help="Continuous monitoring mode: refresh every N seconds. "
        "Use 0 (default) for a single snapshot.",
    ),
) -> None:
    """Monitor IRIS instance CPU, RAM, disk I/O, and process load in real time."""
    try:
        if compare:
            _run_compare()
        elif watch > 0:
            _run_watch(watch, raw)
        else:
            snapshot = asyncio.run(collect_snapshot())
            result = snapshot.to_dict()
            if raw:
                result["raw_metrics"] = [
                    {"name": s.name, "value": s.value, "labels": s.labels}
                    for s in snapshot.raw_samples
                ]
            typer.echo(format_output(result, get_output_format()))
    except Exception as exc:
        handle_command_error(exc)


def _run_compare() -> None:
    """Take two snapshots (5s apart) and compare their load scores."""
    typer.echo("Taking snapshot A...", err=True)
    snapshot_a = asyncio.run(collect_snapshot())
    typer.echo(f"  Score: {snapshot_a.score.overall} ({snapshot_a.grade})", err=True)

    typer.echo("Waiting 5 seconds for second snapshot...", err=True)
    time.sleep(5)

    typer.echo("Taking snapshot B...", err=True)
    snapshot_b = asyncio.run(collect_snapshot())
    typer.echo(f"  Score: {snapshot_b.score.overall} ({snapshot_b.grade})", err=True)

    comparison = compare_snapshots(snapshot_a.score, snapshot_b.score)
    result = {
        "snapshot_a": snapshot_a.to_dict(),
        "snapshot_b": snapshot_b.to_dict(),
        "comparison": comparison,
    }
    typer.echo(format_output(result, get_output_format()))


def _run_watch(interval: float, raw: bool) -> None:
    """Continuously monitor and print snapshots at the given interval."""
    typer.echo(
        f"Monitoring IRIS (refresh every {interval}s). Press Ctrl+C to stop.",
        err=True,
    )
    try:
        while True:
            snapshot = asyncio.run(collect_snapshot())
            result = snapshot.to_dict()
            if raw:
                result["raw_metrics"] = [
                    {"name": s.name, "value": s.value, "labels": s.labels}
                    for s in snapshot.raw_samples
                ]
            # Clear screen for live status (ANSI escape)
            typer.echo("\033[2J\033[H", nl=False)
            typer.echo(format_output(result, get_output_format()))
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\nMonitoring stopped.", err=True)
