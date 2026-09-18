"""Edge case tests for monitor parser and scorer.

Adds coverage for the few remaining untested branches in
parser.py (line 109: non-matching sample lines) and scorer.py
(lines 112-114: threshold <= 0 edge case in _normalise).
"""

from __future__ import annotations

import math

from prism.iris.monitor.parser import (
    MetricSample,
    _parse_labels,
    _parse_value,
    parse_prometheus_text,
)
from prism.iris.monitor.scorer import (
    LoadScore,
    _normalise,
    _score_category,
    compare_snapshots,
    compute_load_score,
    get_health_grade,
)

# ── Parser edge cases ───────────────────────────────────────────────────


class TestParserMalformedLines:
    """Lines that don't match the Prometheus sample regex should be skipped."""

    def test_malformed_line_no_value(self):
        """A line with a metric name but no value should be skipped."""
        text = "iris_metric_without_value\n"
        metrics = parse_prometheus_text(text)
        assert metrics == []

    def test_malformed_line_invalid_name(self):
        """A line starting with a number (invalid metric name) should be skipped."""
        text = "123bad_metric 42.0\n"
        metrics = parse_prometheus_text(text)
        assert metrics == []

    def test_line_with_only_whitespace_and_name(self):
        """A line with only a name and whitespace (no value) should be skipped."""
        text = "   iris_metric   \n"
        metrics = parse_prometheus_text(text)
        assert metrics == []

    def test_malformed_label_block(self):
        """Malformed label block (missing closing brace) should skip the line."""
        text = 'iris_metric{id="USER" 42.0\n'
        metrics = parse_prometheus_text(text)
        # The regex requires optional {labels} followed by whitespace + value
        # A malformed label block means the line won't match
        assert metrics == []

    def test_mixed_valid_and_invalid_lines(self):
        """Valid and invalid lines mixed — only valid ones parsed."""
        text = (
            "# HELP iris_cpu CPU\n"
            "# TYPE iris_cpu gauge\n"
            "invalid line here\n"
            "iris_cpu 10.0\n"
            "123bad 5.0\n"
            "iris_mem 20.0\n"
        )
        metrics = parse_prometheus_text(text)
        names = [m.name for m in metrics]
        assert "iris_cpu" in names
        assert "iris_mem" in names
        assert "invalid" not in names
        assert len(metrics) == 2

    def test_unit_comment_line(self):
        """# UNIT comment lines should be skipped."""
        text = "# UNIT iris_cpu percent\niris_cpu 10.0\n"
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].name == "iris_cpu"

    def test_comment_only_lines(self):
        """Lines that are just comments (not HELP/TYPE) should be skipped."""
        text = "# This is a comment\n# Another comment\niris_cpu 10.0\n"
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1


class TestParseValueEdgeCases:
    """Edge cases for _parse_value."""

    def test_negative_inf(self):
        assert _parse_value("-Inf") == float("-inf")

    def test_capitalized_inf(self):
        assert _parse_value("+INF") == float("inf")

    def test_capitalized_nan(self):
        assert math.isnan(_parse_value("NaN"))

    def test_zero(self):
        assert _parse_value("0") == 0.0

    def test_negative_zero(self):
        assert _parse_value("-0") == 0.0

    def test_large_scientific(self):
        assert _parse_value("1e10") == 1e10

    def test_negative_scientific(self):
        assert _parse_value("-1.5e-3") == -1.5e-3


class TestParseLabelsEdgeCases:
    """Edge cases for _parse_labels."""

    def test_empty_label_string(self):
        assert _parse_labels("") == {}

    def test_label_with_special_chars(self):
        """Label values with special characters."""
        text = 'metric{id="C:\\Program Files\\IRIS"} 1.0'
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        # The backslash escaping: \\ -> \ in Prometheus
        assert "C:" in metrics[0].labels["id"]

    def test_multiple_labels_same_key_different_values(self):
        """Multiple labels with the same key — the last one wins."""
        text = 'metric{id="A",id="B"} 1.0'
        # This is technically invalid Prometheus, but test the parser behavior
        metrics = parse_prometheus_text(text)
        if metrics:
            # The regex finds all key="value" pairs; last one overwrites
            assert metrics[0].labels.get("id") == "B"


# ── Scorer edge cases ──────────────────────────────────────────────────


class TestNormaliseEdgeCases:
    """Edge cases for _normalise."""

    def test_zero_value(self):
        """Zero value should return 0."""
        assert _normalise(0.0, 100.0) == 0.0

    def test_negative_value(self):
        """Negative value should return 0 (clamped)."""
        assert _normalise(-10.0, 100.0) == 0.0

    def test_at_threshold(self):
        """Value at threshold should return 100."""
        assert _normalise(100.0, 100.0) == 100.0

    def test_above_threshold(self):
        """Value above threshold should clamp to 100."""
        assert _normalise(150.0, 100.0) == 100.0

    def test_nan_value(self):
        """NaN should return 0 (treated as missing)."""
        assert _normalise(float("nan"), 100.0) == 0.0

    def test_positive_inf(self):
        """+Inf should return 0 (treated as missing)."""
        assert _normalise(float("inf"), 100.0) == 0.0

    def test_negative_inf(self):
        """-Inf should return 0 (treated as missing)."""
        assert _normalise(float("-inf"), 100.0) == 0.0

    def test_threshold_zero_with_positive_value(self):
        """threshold=0 with positive value should return 100 (edge case)."""
        assert _normalise(50.0, 0.0) == 100.0

    def test_threshold_zero_with_zero_value(self):
        """threshold=0 with zero value should return 0 (edge case)."""
        assert _normalise(0.0, 0.0) == 0.0

    def test_threshold_negative_with_positive_value(self):
        """Negative threshold with positive value should return 100."""
        assert _normalise(50.0, -10.0) == 100.0

    def test_threshold_negative_with_zero_value(self):
        """Negative threshold with zero value should return 0."""
        assert _normalise(0.0, -10.0) == 0.0


class TestScoreCategoryEdgeCases:
    """Edge cases for _score_category."""

    def test_empty_samples(self):
        """No samples → score 0."""
        score, details = _score_category([], {"iris_cpu": 100.0})
        assert score == 0.0
        assert details == {}

    def test_all_nan_values(self):
        """All NaN values should be filtered out → no score."""
        samples = [MetricSample(name="iris_cpu", value=float("nan"), labels={})]
        score, details = _score_category(samples, {"iris_cpu": 100.0})
        assert score == 0.0

    def test_all_inf_values(self):
        """All Inf values should be filtered out → no score."""
        samples = [MetricSample(name="iris_cpu", value=float("inf"), labels={})]
        score, details = _score_category(samples, {"iris_cpu": 100.0})
        assert score == 0.0

    def test_multiple_samples_same_metric_takes_max(self):
        """Multiple samples with same metric name → max value used."""
        samples = [
            MetricSample(name="iris_db_latency", value=10.0, labels={"id": "DB1"}),
            MetricSample(name="iris_db_latency", value=50.0, labels={"id": "DB2"}),
            MetricSample(name="iris_db_latency", value=20.0, labels={"id": "DB3"}),
        ]
        score, details = _score_category(samples, {"iris_db_latency": 100.0})
        # Max is 50.0, normalised against 100 → 50
        assert details["iris_db_latency"] == 50.0

    def test_special_metric_aggregation(self):
        """Special metric (iris_cpu_pct) should sum across labels."""
        samples = [
            MetricSample(name="iris_cpu_pct", value=30.0, labels={"id": "CSPSRV"}),
            MetricSample(name="iris_cpu_pct", value=20.0, labels={"id": "GARCOL"}),
        ]
        score, details = _score_category(
            samples, {"iris_cpu_usage": 100.0}, special_metric="iris_cpu_pct"
        )
        # Sum = 50, normalised against 100 → 50
        assert "iris_cpu_pct" in details
        assert details["iris_cpu_pct"] == 50.0

    def test_special_metric_with_no_values(self):
        """Special metric with no matching samples → no contribution."""
        samples = [MetricSample(name="iris_cpu_usage", value=50.0, labels={})]
        score, details = _score_category(
            samples, {"iris_cpu_usage": 100.0}, special_metric="iris_cpu_pct"
        )
        # iris_cpu_usage contributes, iris_cpu_pct doesn't
        assert "iris_cpu_pct" not in details
        assert "iris_cpu_usage" in details

    def test_mixed_nan_and_valid(self):
        """Mix of NaN and valid values → only valid ones counted."""
        samples = [
            MetricSample(name="iris_cpu_usage", value=float("nan"), labels={}),
            MetricSample(name="iris_cpu_usage", value=50.0, labels={}),
        ]
        score, details = _score_category(samples, {"iris_cpu_usage": 100.0})
        # NaN filtered out, max of valid = 50
        assert details["iris_cpu_usage"] == 50.0


class TestComputeLoadScoreEdgeCases:
    """Edge cases for compute_load_score."""

    def test_cpu_pct_aggregation(self):
        """iris_cpu_pct values should be summed across process types."""
        samples = [
            MetricSample(name="iris_cpu_pct", value=40.0, labels={"id": "CSPSRV"}),
            MetricSample(name="iris_cpu_pct", value=30.0, labels={"id": "GARCOL"}),
        ]
        score = compute_load_score(samples)
        # CPU = (40+30) / 100 * weight 0.25 = 17.5
        assert score.cpu > 0
        assert score.details["cpu"]["iris_cpu_pct"] == 70.0

    def test_all_metrics_present(self):
        """All metric categories populated → meaningful overall score."""
        samples = [
            MetricSample(name="iris_cpu_usage", value=50.0, labels={}),
            MetricSample(name="iris_phys_mem_percent_used", value=60.0, labels={}),
            MetricSample(name="iris_phys_reads_per_sec", value=2500.0, labels={}),
            MetricSample(name="iris_process_count", value=250.0, labels={}),
        ]
        score = compute_load_score(samples)
        assert 0 < score.overall < 100
        assert score.cpu > 0
        assert score.memory > 0
        assert score.disk > 0
        assert score.process > 0

    def test_score_is_rounded(self):
        """Overall score should be rounded to 2 decimal places."""
        samples = [MetricSample(name="iris_cpu_usage", value=33.333, labels={})]
        score = compute_load_score(samples)
        # Should be rounded
        assert score.overall == round(score.overall, 2)

    def test_details_structure(self):
        """Details should have all 4 categories."""
        score = compute_load_score([])
        assert "cpu" in score.details
        assert "memory" in score.details
        assert "disk" in score.details
        assert "process" in score.details


class TestCompareSnapshotsEdgeCases:
    """Edge cases for compare_snapshots."""

    def test_tie_in_sub_scores(self):
        """Equal sub-scores in a category → 'tie' for that category."""
        score_a = LoadScore(overall=50, cpu=30, memory=30, disk=50, process=50, details={})
        score_b = LoadScore(overall=50, cpu=30, memory=30, disk=50, process=50, details={})
        result = compare_snapshots(score_a, score_b)
        assert result["sub_scores"]["cpu"]["less_loaded"] == "tie"

    def test_mixed_winners_in_sub_scores(self):
        """Different categories have different winners."""
        score_a = LoadScore(overall=40, cpu=10, memory=70, disk=20, process=60, details={})
        score_b = LoadScore(overall=60, cpu=50, memory=30, disk=80, process=40, details={})
        result = compare_snapshots(score_a, score_b)
        assert result["sub_scores"]["cpu"]["less_loaded"] == "snapshot_a"
        assert result["sub_scores"]["memory"]["less_loaded"] == "snapshot_b"
        assert result["sub_scores"]["disk"]["less_loaded"] == "snapshot_a"
        assert result["sub_scores"]["process"]["less_loaded"] == "snapshot_b"

    def test_loser_score_correct(self):
        """Loser score should be the higher overall."""
        score_a = LoadScore(overall=30, cpu=30, memory=30, disk=30, process=30, details={})
        score_b = LoadScore(overall=70, cpu=70, memory=70, disk=70, process=70, details={})
        result = compare_snapshots(score_a, score_b)
        assert result["winner_score"] == 30
        assert result["loser_score"] == 70


class TestHealthGradeEdgeCases:
    """Additional edge cases for get_health_grade."""

    def test_grade_just_below_idle(self):
        assert get_health_grade(9.99) == "idle"

    def test_grade_just_above_critical(self):
        assert get_health_grade(80.0) == "critical"

    def test_grade_just_below_critical(self):
        assert get_health_grade(79.99) == "loaded"

    def test_grade_exactly_100(self):
        assert get_health_grade(100.0) == "critical"

    def test_grade_exactly_0(self):
        assert get_health_grade(0.0) == "idle"
