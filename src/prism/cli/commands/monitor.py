"""`prism monitor` — live IRIS instance resource monitoring dashboard.

Displays a rich terminal dashboard with:

* Real-time CPU, Memory, Disk/IO, and Process load panels
* ASCII sparkline graphs showing the last hour of history
* Colored progress bars for current load
* Summary score + health grade at the bottom

Usage::

    prism monitor              # one-shot dashboard snapshot
    prism monitor --watch 2   # live dashboard, refresh every 2s
    prism monitor --json       # machine-readable JSON output (no dashboard)
    prism monitor --compare    # take two snapshots, compare (JSON)
"""

from __future__ import annotations

import asyncio
import time

import typer

from prism.cli.errors import handle_command_error
from prism.iris.monitor import collect_snapshot
from prism.iris.monitor.dashboard import HistoryBuffer, render_dashboard
from prism.iris.monitor.scorer import compare_snapshots
from prism.output import format_output, get_output_format


def monitor(
    watch: float = typer.Option(
        0,
        "--watch",
        "-w",
        help="Live monitoring mode: refresh every N seconds. "
        "Use 0 (default) for a single snapshot.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON instead of the dashboard UI.",
    ),
    raw: bool = typer.Option(
        False,
        "--raw",
        help="Include all raw metric samples in JSON output (use with --json).",
    ),
    compare: bool = typer.Option(
        False,
        "--compare",
        help="Take two snapshots (5s apart) and compare their load scores (JSON).",
    ),
) -> None:
    """Monitor IRIS instance CPU, RAM, disk I/O, and process load in real time."""
    try:
        if compare:
            _run_compare()
        elif json_output:
            if watch > 0:
                _run_watch_json(watch, raw)
            else:
                _run_json_once(raw)
        else:
            asyncio.run(_run_dashboard(watch))
    except Exception as exc:
        handle_command_error(exc)


# ── Dashboard mode (default — human-readable rich UI) ─────────────────


async def _run_dashboard(watch: float) -> None:
    """Render the rich Live dashboard.

    If *watch* > 0, runs a live-updating dashboard that refreshes every
    *watch* seconds until the user presses Ctrl+C.  If *watch* is 0,
    renders a single snapshot and exits.

    Runs entirely inside a single ``asyncio.run()`` — this is critical
    because the shared ``httpx.AsyncClient`` (in ``prism.iris.sdk.http``)
    is bound to the event loop it was created on.  Calling
    ``asyncio.run()`` multiple times closes the loop, and the next call
    raises ``RuntimeError: Event loop is closed`` when httpx tries to
    clean up connections.
    """
    from rich.console import Console
    from rich.live import Live

    console = Console()
    history = HistoryBuffer()

    # Take the first snapshot
    snapshot = await collect_snapshot()
    history.add(snapshot)

    if watch > 0:
        # Live mode — continuously refresh
        panel = render_dashboard(snapshot, history, console)
        with Live(panel, console=console, refresh_per_second=1) as live:
            try:
                while True:
                    await asyncio.sleep(watch)
                    snapshot = await collect_snapshot()
                    history.add(snapshot)
                    live.update(render_dashboard(snapshot, history, console))
            except KeyboardInterrupt:
                console.print("\n[dim]Monitoring stopped.[/dim]")
    else:
        # Single snapshot — just print once
        panel = render_dashboard(snapshot, history, console)
        console.print(panel)


# ── JSON mode (machine-readable) ──────────────────────────────────────


def _run_json_once(raw: bool) -> None:
    """Single snapshot in JSON format."""
    snapshot = asyncio.run(collect_snapshot())
    result = snapshot.to_dict()
    if raw:
        result["raw_metrics"] = [
            {"name": s.name, "value": s.value, "labels": s.labels}
            for s in snapshot.raw_samples
        ]
    typer.echo(format_output(result, get_output_format()))


def _run_watch_json(interval: float, raw: bool) -> None:
    """Continuously output JSON snapshots at the given interval."""
    typer.echo(
        f"Monitoring IRIS (JSON, refresh every {interval}s). Press Ctrl+C to stop.",
        err=True,
    )
    try:
        asyncio.run(_watch_json_loop(interval, raw))
    except KeyboardInterrupt:
        typer.echo("\nMonitoring stopped.", err=True)


async def _watch_json_loop(interval: float, raw: bool) -> None:
    """Async loop for JSON watch mode — runs in a single event loop."""
    while True:
        snapshot = await collect_snapshot()
        result = snapshot.to_dict()
        if raw:
            result["raw_metrics"] = [
                {"name": s.name, "value": s.value, "labels": s.labels}
                for s in snapshot.raw_samples
            ]
        typer.echo(format_output(result, get_output_format()))
        await asyncio.sleep(interval)


# ── Compare mode ──────────────────────────────────────────────────────


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
