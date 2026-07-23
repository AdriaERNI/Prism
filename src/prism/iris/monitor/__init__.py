"""IRIS monitoring subsystem — Prometheus parser, scorer, collector.

Orchestrates the monitoring pipeline: fetch metrics from IRIS /api/monitor,
parse Prometheus text, compute a load score, and package everything into
a :class:`MonitorSnapshot`.

Usage::

    from prism.iris.monitor import collect_snapshot

    snapshot = await collect_snapshot()
    print(snapshot.grade)      # "healthy"
    print(snapshot.score.overall)  # 23.5
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from prism.iris.api.monitor import get_metrics, get_alerts
from prism.iris.monitor.parser import MetricSample, parse_prometheus_text
from prism.iris.monitor.scorer import (
    LoadScore,
    compare_snapshots,
    compute_load_score,
    get_health_grade,
)

# Curated key metrics to surface in the snapshot for quick human inspection.
# Not exhaustive — the full parsed metrics list is available via `raw_samples`.
KEY_METRICS: list[str] = [
    "iris_cpu_usage",
    "iris_phys_mem_percent_used",
    "iris_page_space_percent_used",
    "iris_smh_total_percent_full",
    "iris_process_count",
    "iris_phys_reads_per_sec",
    "iris_phys_writes_per_sec",
    "iris_glo_ref_per_sec",
    "iris_glo_seize_per_sec",
    "iris_wd_cycle_time",
    "iris_sql_active_queries",
    "iris_cache_efficiency",
    "iris_license_percent_used",
    "iris_license_available",
    "iris_license_consumed",
    "iris_trans_open_count",
    "iris_system_alerts",
    "iris_system_state",
]


@dataclass(frozen=True)
class MonitorSnapshot:
    """A complete monitoring snapshot of an IRIS instance.

    Attributes:
        timestamp:     Unix timestamp (seconds) when the snapshot was taken.
        score:         :class:`LoadScore` with overall + per-category sub-scores.
        grade:         Human-readable health grade (idle/healthy/moderate/loaded/critical).
        metrics:       Curated dict of key metric name → value (single-value metrics only).
        metric_count:  Total number of parsed metric samples.
        alerts_count:  Number of alert metrics parsed from /api/monitor/alerts.
        raw_samples:   Full list of parsed :class:`MetricSample` objects.
    """

    timestamp: float
    score: LoadScore
    grade: str
    metrics: dict[str, float]
    metric_count: int
    alerts_count: int
    raw_samples: list[MetricSample] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a plain dict suitable for JSON serialisation."""
        return {
            "timestamp": self.timestamp,
            "score": {
                "overall": self.score.overall,
                "cpu": self.score.cpu,
                "memory": self.score.memory,
                "disk": self.score.disk,
                "process": self.score.process,
                "details": self.score.details,
            },
            "grade": self.grade,
            "metrics": self.metrics,
            "metric_count": self.metric_count,
            "alerts_count": self.alerts_count,
        }


async def collect_snapshot() -> MonitorSnapshot:
    """Fetch metrics + alerts from IRIS, parse, score, and return a snapshot.

    Makes two HTTP calls in sequence:
    1. ``GET /api/monitor/metrics`` → Prometheus text → parsed into samples
    2. ``GET /api/monitor/alerts``  → Prometheus text → parsed for alert count

    Both calls use the shared HTTP client with connection pooling, so this
    is fast enough for real-time monitoring (typically <200ms on a local
    IRIS instance).
    """
    raw_text = await get_metrics()
    samples = parse_prometheus_text(raw_text)

    # Try to fetch alerts; if it fails, don't let it block the whole snapshot
    try:
        alerts_text = await get_alerts()
        alerts_samples = parse_prometheus_text(alerts_text)
        # Sum the values of alert metrics (each alert may have a value of 1)
        alerts_count = int(
            sum(s.value for s in alerts_samples if s.name == "iris_system_alerts")
        )
    except Exception:
        alerts_count = 0

    # Compute the load score
    score = compute_load_score(samples)
    grade = get_health_grade(score.overall)

    # Extract key metrics for the snapshot
    # For single-value metrics: take the first sample with no labels
    # For labeled metrics: take the first sample with labels (e.g.
    # iris_disk_percent_full{id="USER"} → use the USER value)
    metrics: dict[str, float] = {}
    for key in KEY_METRICS:
        # Prefer unlabeled (single-value) samples, fall back to labeled
        matching = [s for s in samples if s.name == key and not s.labels]
        if matching:
            metrics[key] = matching[0].value
        else:
            labeled = [s for s in samples if s.name == key and s.labels]
            if labeled:
                metrics[key] = labeled[0].value

    return MonitorSnapshot(
        timestamp=time.time(),
        score=score,
        grade=grade,
        metrics=metrics,
        metric_count=len(samples),
        alerts_count=alerts_count,
        raw_samples=samples,
    )


__all__ = [
    "MonitorSnapshot",
    "collect_snapshot",
    "parse_prometheus_text",
    "compute_load_score",
    "get_health_grade",
    "compare_snapshots",
    "MetricSample",
    "LoadScore",
]
