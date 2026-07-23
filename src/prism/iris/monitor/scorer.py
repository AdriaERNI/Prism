"""Compute a weighted load score from IRIS monitoring metrics.

The score is a 0–100 composite index where higher = more loaded. It is
designed for **relative comparison** between snapshots/instances, not
absolute thresholds — though health grades provide rough absolute guidance.

Scoring is built from four equally-weighted categories (25% each):

┌────────────┬───────────────────────────────────────────────────────────┐
│ Category   │ Contributing IRIS metrics                                 │
├────────────┼───────────────────────────────────────────────────────────┤
│ CPU (25%)  │ iris_cpu_usage (OS %), iris_cpu_pct{id=...} (per-process) │
│ Memory     │ iris_phys_mem_percent_used, iris_page_space_percent_used, │
│ (25%)      │ iris_smh_total_percent_full                                │
│ Disk/IO    │ iris_phys_reads_per_sec, iris_phys_writes_per_sec,        │
│ (25%)      │ iris_db_latency, iris_disk_percent_full                   │
│ Process    │ iris_process_count, iris_glo_seize_per_sec,               │
│ (25%)      │ iris_wd_cycle_time, iris_sql_active_queries,              │
│            │ iris_trans_open_count                                      │
└────────────┴───────────────────────────────────────────────────────────┘

Within each category, each metric is **normalised** to 0–100 using a
saturation threshold: a metric at its threshold contributes 100, at zero
contributes 0, and in between scales linearly. Missing metrics are
treated as zero (not penalised).
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field

from prism.iris.monitor.parser import MetricSample

# ── Normalisation thresholds ──────────────────────────────────────────
# Each threshold is the value at which that metric is considered "fully
# loaded" (score 100 for that component). Below the threshold, the
# component scales linearly; above, it clamps to 100.
#
# Percentages (0-100) use a threshold of 100.
# Rates/per-second metrics use empirically reasonable thresholds.

_CPU_THRESHOLDS: dict[str, float] = {
    "iris_cpu_usage": 100.0,  # OS-level CPU % → 100% = max
}

_MEMORY_THRESHOLDS: dict[str, float] = {
    "iris_phys_mem_percent_used": 100.0,
    "iris_page_space_percent_used": 100.0,
    "iris_smh_total_percent_full": 100.0,
}

_DISK_THRESHOLDS: dict[str, float] = {
    "iris_phys_reads_per_sec": 5000.0,  # 5k reads/s = high
    "iris_phys_writes_per_sec": 3000.0,  # 3k writes/s = high
    "iris_db_latency": 50.0,  # 50ms random read = slow
    "iris_disk_percent_full": 100.0,  # 100% = full disk
}

_PROCESS_THRESHOLDS: dict[str, float] = {
    "iris_process_count": 500.0,  # 500 active processes = high
    "iris_glo_seize_per_sec": 50.0,  # 50 global seizes/s = contention
    "iris_wd_cycle_time": 2000.0,  # 2s write-daemon cycle = slow
    "iris_sql_active_queries": 100.0,  # 100 concurrent SQL = busy
    "iris_trans_open_count": 50.0,  # 50 open transactions = high
}

# CPU per-process-type metrics (iris_cpu_pct{id=...}) — sum all and
# normalise against 100% total IRIS CPU.
_CPU_PCT_METRIC = "iris_cpu_pct"

# Category weights — equal weighting for fairness in comparison
_CATEGORY_WEIGHTS = {
    "cpu": 0.25,
    "memory": 0.25,
    "disk": 0.25,
    "process": 0.25,
}


@dataclass(frozen=True)
class LoadScore:
    """Composite load score with per-category breakdown.

    Attributes:
        overall: Weighted 0–100 score (higher = more loaded).
        cpu:     CPU category sub-score (0–100).
        memory:  Memory category sub-score (0–100).
        disk:    Disk/IO category sub-score (0–100).
        process: Process category sub-score (0–100).
        details: Per-metric contribution breakdown, organised by category.
    """

    overall: float
    cpu: float
    memory: float
    disk: float
    process: float
    details: dict[str, dict[str, float]] = field(default_factory=dict)


def _normalise(value: float, threshold: float) -> float:
    """Normalise *value* to a 0–100 scale against *threshold*.

    Returns 0 for value ≤ 0, 100 for value ≥ threshold, linear in between.
    ``NaN`` and ``±Inf`` are treated as 0 (missing/unavailable metric),
    not penalised.
    """
    # NaN and Inf are treated as missing — don't penalise the score
    if math.isnan(value) or math.isinf(value):
        return 0.0
    if threshold <= 0:
        return 100.0 if value > 0 else 0.0
    return max(0.0, min(100.0, (value / threshold) * 100.0))


def _score_category(
    samples: list[MetricSample],
    thresholds: dict[str, float],
    special_metric: str | None = None,
) -> tuple[float, dict[str, float]]:
    """Compute a 0–100 category score from the given metrics.

    If *special_metric* is set, all samples with that name (regardless of
    labels) are summed first and normalised against 100 (used for
    iris_cpu_pct per-process-type aggregation).

    Returns (category_score, details_dict).
    """
    details: dict[str, float] = {}
    component_scores: list[float] = []

    # Handle special aggregated metric (e.g. iris_cpu_pct summing across process types)
    if special_metric:
        special_values = [s.value for s in samples if s.name == special_metric]
        if special_values:
            total = sum(special_values)
            normalised = _normalise(total, 100.0)
            details[special_metric] = normalised
            component_scores.append(normalised)

    # Handle threshold-based metrics
    for name, threshold in thresholds.items():
        matching = [s.value for s in samples if s.name == name]
        if matching:
            # Filter out NaN/Inf values — they're treated as missing
            valid = [v for v in matching if not math.isnan(v) and not math.isinf(v)]
            if not valid:
                continue
            # If multiple samples (e.g. multiple databases), take the max
            # — the most stressed resource is what matters for load.
            max_value = max(valid)
            normalised = _normalise(max_value, threshold)
            details[name] = normalised
            component_scores.append(normalised)

    if not component_scores:
        return 0.0, details

    return min(100.0, sum(component_scores) / len(component_scores)), details


def compute_load_score(samples: list[MetricSample]) -> LoadScore:
    """Compute a composite 0–100 load score from parsed IRIS metrics.

    Args:
        samples: List of :class:`~prism.iris.monitor.parser.MetricSample`
                 from :func:`~prism.iris.monitor.parser.parse_prometheus_text`.

    Returns:
        A :class:`LoadScore` with overall and per-category sub-scores.
    """
    cpu_score, cpu_details = _score_category(
        samples, _CPU_THRESHOLDS, special_metric=_CPU_PCT_METRIC
    )
    mem_score, mem_details = _score_category(samples, _MEMORY_THRESHOLDS)
    disk_score, disk_details = _score_category(samples, _DISK_THRESHOLDS)
    proc_score, proc_details = _score_category(samples, _PROCESS_THRESHOLDS)

    overall = (
        cpu_score * _CATEGORY_WEIGHTS["cpu"]
        + mem_score * _CATEGORY_WEIGHTS["memory"]
        + disk_score * _CATEGORY_WEIGHTS["disk"]
        + proc_score * _CATEGORY_WEIGHTS["process"]
    )

    return LoadScore(
        overall=round(overall, 2),
        cpu=round(cpu_score, 2),
        memory=round(mem_score, 2),
        disk=round(disk_score, 2),
        process=round(proc_score, 2),
        details={
            "cpu": cpu_details,
            "memory": mem_details,
            "disk": disk_details,
            "process": proc_details,
        },
    )


# ── Health grade ───────────────────────────────────────────────────────


def get_health_grade(score: float) -> str:
    """Convert a 0–100 load score to a human-readable health grade.

    Grading scale (higher score = more loaded = worse health):

    * ``idle``      — 0–9   (instance is practically idle)
    * ``healthy``   — 10–29 (normal operation, plenty of headroom)
    * ``moderate``  — 30–59 (noticeable load, monitor closely)
    * ``loaded``    — 60–79  (heavy load, potential performance impact)
    * ``critical``  — 80+   (near saturation, investigate immediately)
    """
    clamped = max(0.0, min(100.0, score))
    if clamped < 10:
        return "idle"
    if clamped < 30:
        return "healthy"
    if clamped < 60:
        return "moderate"
    if clamped < 80:
        return "loaded"
    return "critical"


# ── Snapshot comparison ────────────────────────────────────────────────


def compare_snapshots(
    score_a: LoadScore,
    score_b: LoadScore,
) -> dict:
    """Compare two :class:`LoadScore` snapshots and determine which is less loaded.

    Returns a dict with:

    * ``less_loaded``   — ``"snapshot_a"``, ``"snapshot_b"``, or ``"tie"``
    * ``difference``     — absolute difference in overall scores
    * ``winner_score``   — the lower (better) overall score, or None on tie
    * ``loser_score``    — the higher (worse) overall score, or None on tie
    * ``sub_scores``     — per-category comparison breakdown
    """
    diff = abs(score_a.overall - score_b.overall)

    if score_a.overall < score_b.overall:
        less_loaded = "snapshot_a"
        winner = score_a.overall
        loser = score_b.overall
    elif score_b.overall < score_a.overall:
        less_loaded = "snapshot_b"
        winner = score_b.overall
        loser = score_a.overall
    else:
        less_loaded = "tie"
        winner = None
        loser = None

    categories = ["cpu", "memory", "disk", "process"]
    sub_scores: dict[str, dict[str, float | str]] = {}
    for cat in categories:
        a_val = getattr(score_a, cat)
        b_val = getattr(score_b, cat)
        if a_val < b_val:
            winner_cat = "snapshot_a"
        elif b_val < a_val:
            winner_cat = "snapshot_b"
        else:
            winner_cat = "tie"
        sub_scores[cat] = {
            "snapshot_a": a_val,
            "snapshot_b": b_val,
            "less_loaded": winner_cat,
        }

    return {
        "less_loaded": less_loaded,
        "difference": round(diff, 2),
        "winner_score": winner,
        "loser_score": loser,
        "sub_scores": sub_scores,
    }
