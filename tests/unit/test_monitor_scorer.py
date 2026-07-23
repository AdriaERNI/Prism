"""Unit tests for the monitoring scorer — load score, health grade, comparison."""

from prism.iris.monitor.scorer import (
    compute_load_score,
    get_health_grade,
    compare_snapshots,
    LoadScore,
)


def _make_samples(metrics: dict[str, float | list[tuple[dict, float]]]) -> list:
    """Build a list of MetricSample from a {name: value} or {name: [(labels, value)]} dict."""
    from prism.iris.monitor.parser import MetricSample

    samples = []
    for name, val in metrics.items():
        if isinstance(val, list):
            for labels, v in val:
                samples.append(MetricSample(name=name, value=v, labels=labels))
        else:
            samples.append(MetricSample(name=name, value=val, labels={}))
    return samples


# ── compute_load_score ─────────────────────────────────────────────────


class TestComputeLoadScore:
    """Compute a 0-100 load score from parsed metrics — higher = more loaded."""

    def test_idle_instance_low_score(self):
        """An idle instance with all metrics near zero should score low."""
        samples = _make_samples(
            {
                "iris_cpu_usage": 1.0,
                "iris_phys_mem_percent_used": 10.0,
                "iris_page_space_percent_used": 5.0,
                "iris_smh_total_percent_full": 15.0,
                "iris_process_count": 5,
                "iris_phys_reads_per_sec": 10.0,
                "iris_phys_writes_per_sec": 5.0,
                "iris_glo_seize_per_sec": 0.0,
                "iris_wd_cycle_time": 10.0,
                "iris_sql_active_queries": 0,
                "iris_disk_percent_full": [({}, 20.0)],
                "iris_db_latency": [({}, 1.0)],
            }
        )
        score = compute_load_score(samples)
        assert isinstance(score, LoadScore)
        assert 0 <= score.overall <= 100
        assert score.overall < 25  # idle → low score

    def test_heavily_loaded_instance_high_score(self):
        """A heavily loaded instance with high CPU/mem/disk should score high."""
        samples = _make_samples(
            {
                "iris_cpu_usage": 95.0,
                "iris_phys_mem_percent_used": 90.0,
                "iris_page_space_percent_used": 85.0,
                "iris_smh_total_percent_full": 88.0,
                "iris_process_count": 500,
                "iris_phys_reads_per_sec": 5000.0,
                "iris_phys_writes_per_sec": 3000.0,
                "iris_glo_seize_per_sec": 50.0,
                "iris_wd_cycle_time": 2000.0,
                "iris_sql_active_queries": 100,
                "iris_disk_percent_full": [({}, 95.0)],
                "iris_db_latency": [({}, 50.0)],
            }
        )
        score = compute_load_score(samples)
        assert score.overall > 75  # heavily loaded → high score

    def test_empty_metrics_returns_zero(self):
        """No metrics → zero score with all sub-scores at 0."""
        score = compute_load_score([])
        assert score.overall == 0
        assert score.cpu == 0
        assert score.memory == 0
        assert score.disk == 0
        assert score.process == 0

    def test_partial_metrics_only_cpu(self):
        """Only CPU metrics present → CPU sub-score non-zero, others zero."""
        samples = _make_samples(
            {
                "iris_cpu_usage": 50.0,
            }
        )
        score = compute_load_score(samples)
        assert score.cpu > 0
        assert score.memory == 0
        assert score.disk == 0
        assert score.process == 0

    def test_score_bounded_0_to_100(self):
        """Even with extreme values, score should never exceed 100 or go below 0."""
        samples = _make_samples(
            {
                "iris_cpu_usage": 1000.0,
                "iris_phys_mem_percent_used": 200.0,
                "iris_process_count": 99999,
                "iris_phys_reads_per_sec": 999999.0,
            }
        )
        score = compute_load_score(samples)
        assert 0 <= score.overall <= 100
        assert score.cpu <= 100
        assert score.memory <= 100
        assert score.disk <= 100
        assert score.process <= 100

    def test_sub_scores_sum_to_overall(self):
        """Overall score should be the weighted sum of sub-scores."""
        samples = _make_samples(
            {
                "iris_cpu_usage": 30.0,
                "iris_phys_mem_percent_used": 40.0,
                "iris_process_count": 50,
                "iris_phys_reads_per_sec": 100.0,
            }
        )
        score = compute_load_score(samples)
        # Overall should be a weighted combination
        expected = (
            score.cpu * 0.25
            + score.memory * 0.25
            + score.disk * 0.25
            + score.process * 0.25
        )
        assert abs(score.overall - expected) < 0.01

    def test_load_score_has_detail_breakdown(self):
        """LoadScore should expose individual metric contributions."""
        samples = _make_samples(
            {
                "iris_cpu_usage": 45.0,
            }
        )
        score = compute_load_score(samples)
        assert hasattr(score, "details")
        assert "cpu" in score.details
        assert "iris_cpu_usage" in score.details["cpu"]


# ── get_health_grade ──────────────────────────────────────────────────


class TestGetHealthGrade:
    """Convert a 0-100 load score to a human-readable grade."""

    def test_grade_idle(self):
        assert get_health_grade(5) == "idle"

    def test_grade_healthy(self):
        assert get_health_grade(20) == "healthy"

    def test_grade_moderate(self):
        assert get_health_grade(45) == "moderate"

    def test_grade_loaded(self):
        assert get_health_grade(65) == "loaded"

    def test_grade_critical(self):
        assert get_health_grade(85) == "critical"

    def test_grade_boundaries(self):
        """Test boundary values between grades."""
        assert get_health_grade(0) == "idle"
        assert get_health_grade(10) == "healthy"  # 10 is boundary
        assert get_health_grade(30) == "moderate"  # 30 is boundary
        assert get_health_grade(60) == "loaded"  # 60 is boundary
        assert get_health_grade(80) == "critical"

    def test_grade_clamps_out_of_range(self):
        assert get_health_grade(-5) == "idle"
        assert get_health_grade(150) == "critical"


# ── compare_snapshots ─────────────────────────────────────────────────


class TestCompareSnapshots:
    """Compare two monitoring snapshots and determine which is less loaded."""

    def test_first_less_loaded(self):
        """Snapshot A has lower scores → A is less loaded."""
        score_a = LoadScore(
            overall=20, cpu=15, memory=20, disk=25, process=20, details={}
        )
        score_b = LoadScore(
            overall=60, cpu=50, memory=65, disk=70, process=55, details={}
        )
        result = compare_snapshots(score_a, score_b)
        assert result["less_loaded"] == "snapshot_a"
        assert result["difference"] == 40
        assert result["winner_score"] == 20

    def test_second_less_loaded(self):
        score_a = LoadScore(
            overall=70, cpu=65, memory=70, disk=75, process=70, details={}
        )
        score_b = LoadScore(
            overall=25, cpu=20, memory=25, disk=30, process=25, details={}
        )
        result = compare_snapshots(score_a, score_b)
        assert result["less_loaded"] == "snapshot_b"
        assert result["difference"] == 45

    def test_equal_scores(self):
        score_a = LoadScore(
            overall=50, cpu=50, memory=50, disk=50, process=50, details={}
        )
        score_b = LoadScore(
            overall=50, cpu=50, memory=50, disk=50, process=50, details={}
        )
        result = compare_snapshots(score_a, score_b)
        assert result["less_loaded"] == "tie"
        assert result["difference"] == 0

    def test_comparison_includes_sub_scores(self):
        """Comparison should include per-category breakdown."""
        score_a = LoadScore(
            overall=30, cpu=10, memory=20, disk=40, process=50, details={}
        )
        score_b = LoadScore(
            overall=60, cpu=50, memory=60, disk=70, process=60, details={}
        )
        result = compare_snapshots(score_a, score_b)
        assert "sub_scores" in result
        assert "cpu" in result["sub_scores"]
        assert result["sub_scores"]["cpu"]["snapshot_a"] == 10
        assert result["sub_scores"]["cpu"]["snapshot_b"] == 50
