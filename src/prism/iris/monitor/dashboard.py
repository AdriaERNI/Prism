"""Rich-based live dashboard for IRIS monitoring.

Renders a real-time terminal dashboard with:

* A header showing instance info and uptime
* Four resource panels (CPU, Memory, Disk/IO, Process) each with:
  - Current value as a colored progress bar
  - Historical sparkline graph (ASCII) showing the last hour
  - Key sub-metrics in a compact table
* A summary score panel at the bottom with overall grade

Uses the ``rich`` library (already a project dependency) for terminal
rendering — no extra packages required.

History is kept in a ring buffer (default: 360 samples = 1 hour at
10s intervals, or 60 at 1s intervals).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prism.iris.monitor import MonitorSnapshot

# ── Sparkline blocks (Unicode block elements) ────────────────────────
# Ordered from low to high.  8 levels of resolution.
_SPARK_BLOCKS = " ▁▂▃▄▅▆▇█"

# Default history capacity — 360 samples covers 1 hour at 10s intervals.
_DEFAULT_MAX_SAMPLES = 360


# ── History ring buffer ───────────────────────────────────────────────


@dataclass
class _HistoryEntry:
    timestamp: float
    overall: float
    cpu: float
    memory: float
    disk: float
    process: float


class HistoryBuffer:
    """Fixed-capacity ring buffer storing per-category time-series.

    When full, the oldest entry is dropped (FIFO).  This is intentionally
    lightweight — each entry is 6 floats — so even 3600 samples (1 hour
    at 1s resolution) use negligible memory.
    """

    def __init__(self, max_samples: int = _DEFAULT_MAX_SAMPLES) -> None:
        self.max_samples = max_samples
        self._entries: deque[_HistoryEntry] = deque(maxlen=max_samples)

    def add(self, snapshot: MonitorSnapshot) -> None:
        """Record a snapshot into history."""
        self._entries.append(
            _HistoryEntry(
                timestamp=snapshot.timestamp,
                overall=snapshot.score.overall,
                cpu=snapshot.score.cpu,
                memory=snapshot.score.memory,
                disk=snapshot.score.disk,
                process=snapshot.score.process,
            )
        )

    def __len__(self) -> int:
        return len(self._entries)

    def cpu_history(self) -> list[float]:
        return [e.cpu for e in self._entries]

    def memory_history(self) -> list[float]:
        return [e.memory for e in self._entries]

    def disk_history(self) -> list[float]:
        return [e.disk for e in self._entries]

    def process_history(self) -> list[float]:
        return [e.process for e in self._entries]

    def score_history(self) -> list[float]:
        return [e.overall for e in self._entries]

    def timestamps(self) -> list[float]:
        return [e.timestamp for e in self._entries]

    # ── Averages ──────────────────────────────────────────────────

    def sma(self) -> float:
        """Simple moving average of overall scores."""
        return _sma(self.score_history())

    def ewma_1m(self, interval_s: float = 1.0) -> float:
        """1-minute exponentially weighted moving average."""
        return _ewma(self.score_history(), window_s=60.0, interval_s=interval_s)

    def ewma_5m(self, interval_s: float = 1.0) -> float:
        """5-minute exponentially weighted moving average."""
        return _ewma(self.score_history(), window_s=300.0, interval_s=interval_s)

    def ewma_15m(self, interval_s: float = 1.0) -> float:
        """15-minute exponentially weighted moving average."""
        return _ewma(self.score_history(), window_s=900.0, interval_s=interval_s)

    def trend(self, interval_s: float = 1.0) -> str:
        """Trend arrow comparing 1m EWMA vs 5m EWMA.

        Returns ``↑`` (rising), ``→`` (stable), or ``↓`` (falling).
        """
        return _trend_arrow(self.ewma_1m(interval_s), self.ewma_5m(interval_s))


# ── Sparkline renderer ────────────────────────────────────────────────


def _sparkline(data: list[float], width: int = 40) -> str:
    """Render *data* as an ASCII sparkline using Unicode block characters.

    The output is at most *width* characters long.  If ``len(data) >
    width``, the most recent *width* values are used (right-aligned, so
    the graph shows the latest trend).
    """
    if not data:
        return ""

    # Truncate to most recent `width` values
    if len(data) > width:
        data = data[-width:]

    lo = min(data)
    hi = max(data)
    span = hi - lo

    chars: list[str] = []
    for v in data:
        if span == 0:
            # All values identical — show a flat line in the middle
            idx = len(_SPARK_BLOCKS) // 2
        else:
            # Normalise to 0..(len-1) block indices
            normalized = (v - lo) / span
            idx = int(round(normalized * (len(_SPARK_BLOCKS) - 1)))
            idx = max(0, min(len(_SPARK_BLOCKS) - 1, idx))
        chars.append(_SPARK_BLOCKS[idx])

    return "".join(chars)


# ── Averages: SMA + EWMA ──────────────────────────────────────────────


def _sma(data: list[float]) -> float:
    """Simple moving average — arithmetic mean of all values.

    Returns 0.0 for empty data.
    """
    if not data:
        return 0.0
    return sum(data) / len(data)


def _ewma(
    data: list[float],
    window_s: float,
    interval_s: float,
) -> float:
    """Exponentially weighted moving average (EWMA).

    Follows the Linux load-average model: recent samples weigh more
    than old ones, decaying exponentially with a time constant of
    *window_s* seconds.

    Args:
        data:        Time-series of values (oldest first).
        window_s:    EWMA window in seconds (e.g. 60 for 1-min avg).
        interval_s:  Time between samples in seconds.

    Returns 0.0 for empty data.
    """
    if not data:
        return 0.0

    # Decay factor per sample: α = 1 - e^(-Δt / window)
    alpha = 1.0 - math.exp(-interval_s / window_s)

    result = data[0]
    for value in data[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _trend_arrow(current: float, baseline: float, threshold: float = 2.0) -> str:
    """Compare current (1m EWMA) vs baseline (5m EWMA) and return an arrow.

    ↑  current > baseline + threshold  → load rising
    →  |current - baseline| ≤ threshold → load stable
    ↓  current < baseline - threshold  → load falling
    """
    diff = current - baseline
    if diff > threshold:
        return "↑"
    if diff < -threshold:
        return "↓"
    return "→"


# ── Color helpers ─────────────────────────────────────────────────────


def _color_for_score(score: float) -> str:
    """Return a rich color name based on the load score."""
    if score < 10:
        return "green"
    if score < 30:
        return "green"
    if score < 60:
        return "yellow"
    if score < 80:
        return "red"
    return "bold red"


def _grade_color(grade: str) -> str:
    """Return a rich color name based on the health grade."""
    colors = {
        "idle": "green",
        "healthy": "green",
        "moderate": "yellow",
        "loaded": "red",
        "critical": "bold red",
    }
    return colors.get(grade, "white")


# ── Progress bar renderer ──────────────────────────────────────────────


_BAR_WIDTH = 20


def _format_bar(value: float, width: int = _BAR_WIDTH) -> tuple[str, str]:
    """Render a textual progress bar for *value* (0–100 percentage).

    Returns (bar_string, percentage_string).
    The bar uses ``█`` for filled and ``░`` for empty.
    """
    clamped = max(0.0, min(100.0, value))
    filled = int(round(clamped / 100.0 * width))
    bar = "█" * filled + "░" * (width - filled)
    pct_str = f"{clamped:.1f}%"
    return bar, pct_str


def _format_score_bar(value: float, width: int = _BAR_WIDTH) -> tuple[str, str]:
    """Render a progress bar for a 0–100 load score index (not a percentage).

    Returns (bar_string, score_string) where score_string is ``N.N/100``.
    """
    clamped = max(0.0, min(100.0, value))
    filled = int(round(clamped / 100.0 * width))
    bar = "█" * filled + "░" * (width - filled)
    score_str = f"{clamped:.1f}/100"
    return bar, score_str


# ── Dashboard renderer ────────────────────────────────────────────────


def _metric_table(
    title: str,
    score_value: float,
    history: list[float],
    sub_metrics: dict[str, float],
    color: str,
) -> Panel:
    """Build a resource panel with bar, sparkline, and sub-metric table.

    The *score_value* is a 0–100 load index (not a percentage), so the
    bar uses :func:`_format_score_bar` to show ``N.N/100``.
    """
    bar, score_str = _format_score_bar(score_value)
    spark = _sparkline(history)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column(style=color, justify="right")

    # Sub-metrics
    for name, val in sub_metrics.items():
        table.add_row(name, f"{val:.1f}")

    content = Group(
        Text(f"{bar} {score_str}", style=color),
        Text(f"  {spark}", style="dim"),
        table,
    )

    return Panel(content, title=title, border_style=color, padding=(0, 1))


def render_dashboard(
    snapshot: MonitorSnapshot,
    history: HistoryBuffer,
    console: Console | None = None,
) -> Panel:
    """Render the full monitoring dashboard as a single rich Panel.

    Returns a Panel suitable for use with ``rich.live.Live``.
    """
    console = console or Console()

    score = snapshot.score

    # ── Header ──────────────────────────────────────────────────────
    from datetime import datetime

    ts = datetime.fromtimestamp(snapshot.timestamp).strftime("%H:%M:%S")
    header = Text.assemble(
        ("IRIS Monitor  ", "bold cyan"),
        (f"  {ts}", "dim"),
        (f"  │  {snapshot.metric_count} metrics", "dim"),
        (f"  │  {snapshot.alerts_count} alerts", "dim"),
    )

    # ── Resource panels ─────────────────────────────────────────────
    cpu_color = _color_for_score(score.cpu)
    mem_color = _color_for_score(score.memory)
    disk_color = _color_for_score(score.disk)
    proc_color = _color_for_score(score.process)

    # Extract sub-metrics from snapshot
    m = snapshot.metrics
    cpu_sub = {
        "CPU Usage (OS %)": m.get("iris_cpu_usage", 0.0),
    }
    mem_sub = {
        "Memory Used %": m.get("iris_phys_mem_percent_used", 0.0),
        "Page Space %": m.get("iris_page_space_percent_used", 0.0),
        "SMH Full %": m.get("iris_smh_total_percent_full", 0.0),
    }
    disk_sub = {
        "Reads/s": m.get("iris_phys_reads_per_sec", 0.0),
        "Writes/s": m.get("iris_phys_writes_per_sec", 0.0),
        "Disk Full %": m.get("iris_disk_percent_full", 0.0)
        if hasattr(m, "get")
        else 0.0,
    }
    proc_sub = {
        "Processes": m.get("iris_process_count", 0.0),
        "Glo Seize/s": m.get("iris_glo_seize_per_sec", 0.0),
        "WD Cycle ms": m.get("iris_wd_cycle_time", 0.0),
    }

    cpu_panel = _metric_table(
        "CPU", score.cpu, history.cpu_history(), cpu_sub, cpu_color
    )
    mem_panel = _metric_table(
        "Memory", score.memory, history.memory_history(), mem_sub, mem_color
    )
    disk_panel = _metric_table(
        "Disk/IO", score.disk, history.disk_history(), disk_sub, disk_color
    )
    proc_panel = _metric_table(
        "Process", score.process, history.process_history(), proc_sub, proc_color
    )

    # ── Score summary (bottom) ──────────────────────────────────────
    grade_col = _grade_color(snapshot.grade)
    bar, score_str = _format_score_bar(score.overall)

    # Per-category score numbers (compact, one line)
    # No sparklines here — the top 4 panels already show per-category
    # sparklines.  The Load Score panel is a numeric summary only.
    score_numbers = Text.assemble(
        ("CPU ", "dim"),
        (f"{score.cpu:.1f}", cpu_color),
        ("   ", "dim"),
        ("Mem ", "dim"),
        (f"{score.memory:.1f}", mem_color),
        ("   ", "dim"),
        ("Disk ", "dim"),
        (f"{score.disk:.1f}", disk_color),
        ("   ", "dim"),
        ("Proc ", "dim"),
        (f"{score.process:.1f}", proc_color),
    )

    # Averages line: SMA + EWMA (1m/5m/15m) + trend arrow
    # Uses default 1s interval; if --watch uses a different interval the
    # values are still meaningful as relative trend indicators.
    avg = history.sma()
    e1 = history.ewma_1m()
    e5 = history.ewma_5m()
    e15 = history.ewma_15m()
    arrow = history.trend()

    # Color the trend arrow
    if arrow == "↑":
        arrow_col = "red"
    elif arrow == "↓":
        arrow_col = "green"
    else:
        arrow_col = "dim"

    averages = Text.assemble(
        ("Avg ", "dim"),
        (f"{avg:.1f}", "white"),
        ("  │  ", "dim"),
        ("1m ", "dim"),
        (f"{e1:.1f}", "white"),
        ("  ", "dim"),
        ("5m ", "dim"),
        (f"{e5:.1f}", "white"),
        ("  ", "dim"),
        ("15m ", "dim"),
        (f"{e15:.1f}", "white"),
        ("  ", "dim"),
        (arrow, arrow_col),
    )

    # Helper text so users know how to read the numbers
    # Keep under ~70 chars to fit in the Load Score panel at 80-col terminals
    helpers = Text.assemble(
        (
            "Score: lower=better (0-100)  |  Trend: ↓ improving → stable ↑ worsening",
            "dim",
        ),
    )

    summary = Panel(
        Group(
            Text(
                f"{bar} {score_str}  │  Grade: {snapshot.grade.upper()}",
                style=grade_col,
            ),
            score_numbers,
            averages,
            helpers,
        ),
        title="Load Score",
        border_style=grade_col,
    )

    # ── Layout: header → 2×2 grid → summary ─────────────────────────
    # rich Table can be used as a grid layout
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column()
    grid.add_row(cpu_panel, mem_panel)
    grid.add_row(disk_panel, proc_panel)

    full = Group(
        Align.center(header),
        grid,
        summary,
    )

    return Panel(full, border_style="cyan", title="Prism Monitor", padding=(0, 1))
