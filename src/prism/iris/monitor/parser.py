"""Parse Prometheus/OpenMetrics text exposition format from IRIS /api/monitor.

Format reference: https://prometheus.io/docs/instrumenting/exposition_formats/

Lines:

* ``# HELP <metric> <description>`` — help text
* ``# TYPE <metric> <type>``       — metric type (gauge, counter, histogram...)
* ``# UNIT <metric> <unit>``        — unit comment (optional, IRIS-specific)
* ``<metric>{<labels>} <value>``  — sample line
* ``<metric> <value>``            — sample line without labels

This parser is a zero-dependency hand-rolled scanner — lighter than pulling
in the full ``prometheus-parser`` package, and tailored to the IRIS metric
set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Regex for a metric sample line:
#   name         → starts with letter/underscore, then word chars
#   labels       → optional {...} block
#   value        → float, NaN, +Inf, -Inf, or scientific notation
_SAMPLE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{([^}]*)\})?"
    r"\s+"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[Nn]a[Nn]|[+-]?[Ii]nf)"
    r"(?:\s+\d+)?"  # optional trailing timestamp (Unix epoch ms)
    r"\s*$"
)

# Regex for parsing label key="value" pairs inside the {} block
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


@dataclass(frozen=True)
class MetricSample:
    """A single Prometheus metric sample.

    Attributes:
        name:   Metric name (e.g. ``iris_cpu_usage``).
        value:  Numeric value (``float``; ``NaN`` / ``±Inf`` preserved).
        labels: Dict of label key→value pairs (empty dict if none).
    """

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


def _parse_labels(label_str: str) -> dict[str, str]:
    """Parse the content inside ``{...}`` into a dict.

    Handles escaped quotes (``\\"``), backslashes (``\\\\``), and
    newlines (``\\n``) per the Prometheus exposition format spec.
    """
    labels: dict[str, str] = {}
    for match in _LABEL_RE.finditer(label_str):
        key = match.group(1)
        # Unescape Prometheus label value escapes:
        #   \\  → \   (must be first to avoid double-processing)
        #   \"  → "
        #   \n  → newline
        raw = match.group(2)
        value = raw.replace("\\\\", "\\").replace('\\"', '"').replace("\\n", "\n")
        labels[key] = value
    return labels


def _parse_value(value_str: str) -> float:
    """Convert a Prometheus text value to float.

    Handles ``NaN``, ``+Inf``, ``-Inf`` (case-insensitive), and standard
    float notation.
    """
    lower = value_str.lower()
    if lower == "nan":
        return float("nan")
    if lower in ("+inf", "inf"):
        return float("inf")
    if lower == "-inf":
        return float("-inf")
    return float(value_str)


def parse_prometheus_text(text: str) -> list[MetricSample]:
    """Parse Prometheus exposition-format *text* into a list of samples.

    Skips comment lines (``# HELP``, ``# TYPE``, ``# UNIT``) and blank lines.
    Each metric sample line is converted to a :class:`MetricSample`.

    Args:
        text: Raw Prometheus exposition-format text.

    Returns:
        List of :class:`MetricSample` instances, one per data line.
    """
    samples: list[MetricSample] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        labels_raw = match.group(2)
        value_str = match.group(3)
        labels = _parse_labels(labels_raw) if labels_raw else {}
        samples.append(
            MetricSample(
                name=name,
                value=_parse_value(value_str),
                labels=labels,
            )
        )
    return samples
