"""Unit tests for Prometheus exposition-format parser."""

import math


from prism.iris.monitor.parser import parse_prometheus_text, MetricSample


class TestParseBasic:
    """Basic metric parsing — no labels, simple gauge values."""

    def test_simple_gauge(self):
        text = (
            "# HELP iris_cpu_usage Percent of CPU usage\n"
            "# TYPE iris_cpu_usage gauge\n"
            "iris_cpu_usage 12.5\n"
        )
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].name == "iris_cpu_usage"
        assert metrics[0].value == 12.5
        assert metrics[0].labels == {}

    def test_counter_type(self):
        text = (
            "# HELP iris_wd_pass Number of write daemon cycles\n"
            "# TYPE iris_wd_pass counter\n"
            "iris_wd_pass 42\n"
        )
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].name == "iris_wd_pass"
        assert metrics[0].value == 42.0

    def test_multiple_metrics(self):
        text = (
            "# HELP iris_cpu_usage CPU usage\n"
            "# TYPE iris_cpu_usage gauge\n"
            "iris_cpu_usage 12.5\n"
            "# HELP iris_phys_mem_percent_used Memory\n"
            "# TYPE iris_phys_mem_percent_used gauge\n"
            "iris_phys_mem_percent_used 45.2\n"
        )
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 2
        names = [m.name for m in metrics]
        assert "iris_cpu_usage" in names
        assert "iris_phys_mem_percent_used" in names


class TestParseLabels:
    """Metrics with labels — {id="value", dir="path"} syntax."""

    def test_single_label(self):
        text = (
            "# HELP iris_cpu_pct CPU pct\n"
            "# TYPE iris_cpu_pct gauge\n"
            'iris_cpu_pct{id="CSPSRV"} 3.5\n'
        )
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].name == "iris_cpu_pct"
        assert metrics[0].labels == {"id": "CSPSRV"}
        assert metrics[0].value == 3.5

    def test_multiple_labels(self):
        text = (
            "# HELP iris_db_size_mb DB size\n"
            "# TYPE iris_db_size_mb gauge\n"
            'iris_db_size_mb{id="USER",dir="/usr/iris/mgr/user/"} 512\n'
        )
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].labels == {"id": "USER", "dir": "/usr/iris/mgr/user/"}
        assert metrics[0].value == 512.0

    def test_multiple_samples_same_metric_different_labels(self):
        text = (
            "# HELP iris_cpu_pct CPU pct\n"
            "# TYPE iris_cpu_pct gauge\n"
            'iris_cpu_pct{id="CSPSRV"} 3.5\n'
            'iris_cpu_pct{id="GARCOL"} 1.2\n'
        )
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 2
        assert metrics[0].labels == {"id": "CSPSRV"}
        assert metrics[1].labels == {"id": "GARCOL"}

    def test_label_with_escaped_quote(self):
        text = (
            "# HELP iris_process Process\n"
            "# TYPE iris_process gauge\n"
            'iris_process{id="pid\\"1"} 1\n'
        )
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].labels == {"id": 'pid"1'}


class TestParseSpecialValues:
    """Edge-case values: NaN, +Inf, -Inf, scientific notation, negatives."""

    def test_nan_value(self):
        text = "iris_cache_efficiency NaN\n"
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert math.isnan(metrics[0].value)

    def test_positive_inf(self):
        text = "iris_some_metric +Inf\n"
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert math.isinf(metrics[0].value)
        assert metrics[0].value > 0

    def test_negative_value(self):
        text = "iris_some_metric -5.3\n"
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].value == -5.3

    def test_scientific_notation(self):
        text = "iris_some_metric 1.23e+4\n"
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].value == 12300.0


class TestParseEdgeCases:
    """Empty text, comments, whitespace, blank lines."""

    def test_empty_string(self):
        metrics = parse_prometheus_text("")
        assert metrics == []

    def test_only_comments(self):
        text = "# HELP iris_cpu_usage CPU usage\n# TYPE iris_cpu_usage gauge\n"
        metrics = parse_prometheus_text(text)
        assert metrics == []

    def test_blank_lines_between_metrics(self):
        text = (
            "# HELP iris_cpu_usage CPU\n"
            "# TYPE iris_cpu_usage gauge\n"
            "\n"
            "iris_cpu_usage 10.0\n"
            "\n"
            "# HELP iris_mem Memory\n"
            "# TYPE iris_mem gauge\n"
            "\n"
            "iris_mem 50.0\n"
        )
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 2

    def test_trailing_whitespace(self):
        text = "iris_cpu_usage 10.0   \n"
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].value == 10.0

    def test_no_trailing_newline(self):
        text = "# HELP iris_cpu_usage CPU\n# TYPE iris_cpu_usage gauge\niris_cpu_usage 10.0"
        metrics = parse_prometheus_text(text)
        assert len(metrics) == 1
        assert metrics[0].value == 10.0


class TestMetricSampleDataclass:
    """Verify MetricSample dataclass fields."""

    def test_metric_sample_creation(self):
        sample = MetricSample(name="iris_cpu_usage", value=12.5, labels={})
        assert sample.name == "iris_cpu_usage"
        assert sample.value == 12.5
        assert sample.labels == {}

    def test_metric_sample_with_labels(self):
        sample = MetricSample(name="iris_db_size_mb", value=100, labels={"id": "USER"})
        assert sample.labels["id"] == "USER"
