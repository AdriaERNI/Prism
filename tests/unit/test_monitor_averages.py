"""Tests for EWMA (exponentially weighted moving average) and SMA (simple
moving average) computation in the monitoring dashboard.

The EWMA follows the Linux load average model: three windows (1m, 5m, 15m)
with exponential decay, so recent samples weigh more than old ones.

The SMA is a plain arithmetic mean of all stored overall scores.

Trend arrows compare the 1m EWMA against the 5m EWMA:
  ↑  1m > 5m  → load rising
  →  1m ≈ 5m  → load stable
  ↓  1m < 5m  → load falling
"""

from prism.iris.monitor.dashboard import HistoryBuffer, _trend_arrow, _ewma, _sma
from prism.iris.monitor import MonitorSnapshot
from prism.iris.monitor.scorer import LoadScore


def _snap(overall: float = 50.0, cpu: float = 50.0) -> MonitorSnapshot:
    return MonitorSnapshot(
        timestamp=1234567890.0,
        score=LoadScore(
            overall=overall,
            cpu=cpu,
            memory=50.0,
            disk=50.0,
            process=50.0,
            details={},
        ),
        grade="healthy",
        metrics={},
        metric_count=0,
        alerts_count=0,
    )


class TestSma:
    """Simple moving average of overall scores."""

    def test_empty_history_returns_zero(self):
        buf = HistoryBuffer()
        assert _sma(buf.score_history()) == 0.0

    def test_single_value(self):
        buf = HistoryBuffer()
        buf.add(_snap(overall=42.0))
        assert _sma(buf.score_history()) == 42.0

    def test_multiple_values(self):
        buf = HistoryBuffer()
        for v in [10.0, 20.0, 30.0, 40.0]:
            buf.add(_snap(overall=v))
        assert _sma(buf.score_history()) == 25.0

    def test_with_many_values(self):
        buf = HistoryBuffer()
        for v in [50.0] * 60:
            buf.add(_snap(overall=v))
        assert _sma(buf.score_history()) == 50.0


class TestEwma:
    """Exponentially weighted moving average."""

    def test_empty_data_returns_zero(self):
        assert _ewma([], window_s=60.0, interval_s=1.0) == 0.0

    def test_single_value(self):
        result = _ewma([50.0], window_s=60.0, interval_s=1.0)
        assert result == 50.0

    def test_constant_values_converge(self):
        data = [50.0] * 100
        result = _ewma(data, window_s=60.0, interval_s=1.0)
        assert abs(result - 50.0) < 0.1

    def test_recent_values_weight_more(self):
        # 10 low values then 10 high values — EWMA should be closer to high
        data = [0.0] * 10 + [100.0] * 10
        result = _ewma(data, window_s=10.0, interval_s=1.0)
        assert result > 50.0  # weighted toward recent highs

    def test_old_values_decay(self):
        # 10 high values then 10 low values — EWMA should be closer to low
        data = [100.0] * 10 + [0.0] * 10
        result = _ewma(data, window_s=10.0, interval_s=1.0)
        assert result < 50.0  # weighted toward recent lows

    def test_longer_window_smooths_more(self):
        # With a spike, longer window should smooth it more
        data = [50.0] * 20 + [100.0] + [50.0] * 20
        short = _ewma(data, window_s=10.0, interval_s=1.0)
        long_w = _ewma(data, window_s=60.0, interval_s=1.0)
        # The long window should be closer to the baseline (50)
        assert abs(long_w - 50.0) < abs(short - 50.0)


class TestTrendArrow:
    """Trend arrow comparing short vs long EWMA."""

    def test_rising(self):
        # 1m > 5m → rising (↑)
        assert _trend_arrow(current=60.0, baseline=40.0) == "↑"

    def test_falling(self):
        # 1m < 5m → falling (↓)
        assert _trend_arrow(current=30.0, baseline=50.0) == "↓"

    def test_stable(self):
        # 1m ≈ 5m → stable (→)
        assert _trend_arrow(current=45.0, baseline=45.0) == "→"

    def test_stable_within_threshold(self):
        # Within 2 points → stable
        assert _trend_arrow(current=46.0, baseline=45.0) == "→"
        assert _trend_arrow(current=44.0, baseline=45.0) == "→"

    def test_rising_above_threshold(self):
        # More than 2 points difference → rising
        assert _trend_arrow(current=50.0, baseline=45.0) == "↑"

    def test_falling_below_threshold(self):
        # More than 2 points difference → falling
        assert _trend_arrow(current=40.0, baseline=45.0) == "↓"


class TestHistoryBufferAverages:
    """HistoryBuffer convenience methods for averages."""

    def test_sma_method(self):
        buf = HistoryBuffer()
        for v in [10.0, 20.0, 30.0]:
            buf.add(_snap(overall=v))
        assert buf.sma() == 20.0

    def test_ewma_1min_method(self):
        buf = HistoryBuffer()
        for v in [50.0] * 10:
            buf.add(_snap(overall=v))
        # With constant data, EWMA should equal the value
        result = buf.ewma_1m(interval_s=1.0)
        assert abs(result - 50.0) < 1.0

    def test_ewma_5min_method(self):
        buf = HistoryBuffer()
        for v in [50.0] * 10:
            buf.add(_snap(overall=v))
        result = buf.ewma_5m(interval_s=1.0)
        assert abs(result - 50.0) < 1.0

    def test_ewma_15min_method(self):
        buf = HistoryBuffer()
        for v in [50.0] * 10:
            buf.add(_snap(overall=v))
        result = buf.ewma_15m(interval_s=1.0)
        assert abs(result - 50.0) < 1.0

    def test_trend_method(self):
        buf = HistoryBuffer()
        # Rising trend: low then high values
        for v in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]:
            buf.add(_snap(overall=v))
        arrow = buf.trend(interval_s=1.0)
        assert arrow == "↑"

    def test_trend_falling(self):
        buf = HistoryBuffer()
        for v in [80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0]:
            buf.add(_snap(overall=v))
        arrow = buf.trend(interval_s=1.0)
        assert arrow == "↓"
