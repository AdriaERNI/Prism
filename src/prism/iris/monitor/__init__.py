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

import math
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
    # ── Core resource metrics (single-value) ──
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
    # ── Database storage (labeled — aggregation needed) ──
    "iris_db_size_mb",
    "iris_db_free_space",
    "iris_db_max_size_mb",
    "iris_db_latency",
    "iris_db_expansion_size_mb",
    # ── License (additional) ──
    "iris_license_days_remaining",
    # ── CSP / Web Gateway (some labeled by {id="IP:port"}) ──
    "iris_csp_sessions",
    "iris_csp_actual_connections",
    "iris_csp_in_use_connections",
    "iris_csp_gateway_latency",
    "iris_csp_activity",
    # ── SQL (labeled by {id="namespace"}) ──
    "iris_sql_queries_per_second",
    "iris_sql_queries_avg_runtime",
    # ── Transactions (additional) ──
    "iris_trans_open_secs",
    "iris_trans_open_secs_max",
    # ── Shared Memory Heap ──
    "iris_smh_total",  # in KB
    # ── Global activity rates (additional) ──
    "iris_glo_update_per_sec",
    # ── ECP connections ──
    "iris_ecp_conn",
    "iris_ecp_conn_max",
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
        aggregated:    Computed aggregations from labeled metrics (db totals, CPU by
                       type, top processes, CSP connection totals, SMH in GB).
    """

    timestamp: float
    score: LoadScore
    grade: str
    metrics: dict[str, float]
    metric_count: int
    alerts_count: int
    raw_samples: list[MetricSample] = field(default_factory=list)
    aggregated: dict[str, float | list | dict] = field(default_factory=dict)

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
            "aggregated": self.aggregated,
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

    # ── Compute aggregations from labeled metrics ──────────────────────
    # Database totals — sum across all databases (filter NaN/Inf)
    db_sizes = [
        s.value
        for s in samples
        if s.name == "iris_db_size_mb"
        and not math.isnan(s.value)
        and not math.isinf(s.value)
    ]
    db_free = [
        s.value
        for s in samples
        if s.name == "iris_db_free_space"
        and not math.isnan(s.value)
        and not math.isinf(s.value)
    ]
    db_max = [
        s.value
        for s in samples
        if s.name == "iris_db_max_size_mb"
        and not math.isnan(s.value)
        and not math.isinf(s.value)
    ]
    db_latencies = [
        s.value
        for s in samples
        if s.name == "iris_db_latency"
        and not math.isnan(s.value)
        and not math.isinf(s.value)
    ]

    aggregated: dict[str, float | list | dict] = {
        "db_total_size_gb": sum(db_sizes) / 1024 if db_sizes else 0.0,
        "db_total_free_mb": sum(db_free) if db_free else 0.0,
        "db_total_max_gb": sum(db_max) / 1024 if db_max else 0.0,
        "db_avg_latency_ms": (sum(db_latencies) / len(db_latencies))
        if db_latencies
        else 0.0,
        "db_count": len(db_sizes),
    }

    # CPU per process type — extract labeled iris_cpu_pct
    cpu_by_type: dict[str, float] = {}
    for s in samples:
        if s.name == "iris_cpu_pct" and s.labels.get("id"):
            cpu_by_type[s.labels["id"]] = s.value
    aggregated["cpu_by_type"] = cpu_by_type

    # Top-5 processes by commands executed
    # Build PID → labels lookup once (O(n)) to avoid O(n²) inner loop
    proc_labels: dict[str, dict[str, str]] = {}
    for s in samples:
        if s.name == "iris_process" and s.labels.get("id"):
            proc_labels[s.labels["id"]] = s.labels

    process_list: list[dict] = []
    for s in samples:
        if s.name == "iris_process_commands" and s.labels.get("id"):
            pid = s.labels["id"]
            proc_info = proc_labels.get(pid)
            process_list.append(
                {
                    "pid": int(pid),
                    "commands": int(s.value),
                    "routine": proc_info.get("routine", "?") if proc_info else "?",
                    "namespace": proc_info.get("namespace", "?") if proc_info else "?",
                    "jobtype": proc_info.get("jobtype", "?") if proc_info else "?",
                }
            )
    process_list.sort(key=lambda x: x["commands"], reverse=True)
    aggregated["top_processes"] = process_list[:5]

    # CSP connection totals — sum across all IP:port labels (filter NaN/Inf)
    csp_actual = sum(
        s.value
        for s in samples
        if s.name == "iris_csp_actual_connections"
        and not math.isnan(s.value)
        and not math.isinf(s.value)
    )
    csp_in_use = sum(
        s.value
        for s in samples
        if s.name == "iris_csp_in_use_connections"
        and not math.isnan(s.value)
        and not math.isinf(s.value)
    )
    aggregated["csp_total_connections"] = csp_actual
    aggregated["csp_in_use_connections"] = csp_in_use

    # SMH in GB (metric is in KB — filter NaN/Inf)
    smh_total_samples = [
        s.value
        for s in samples
        if s.name == "iris_smh_total"
        and not math.isnan(s.value)
        and not math.isinf(s.value)
    ]
    aggregated["smh_total_gb"] = (
        smh_total_samples[0] / 1024 / 1024 if smh_total_samples else 0.0
    )

    return MonitorSnapshot(
        timestamp=time.time(),
        score=score,
        grade=grade,
        metrics=metrics,
        metric_count=len(samples),
        alerts_count=alerts_count,
        raw_samples=samples,
        aggregated=aggregated,
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
