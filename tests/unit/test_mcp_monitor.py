"""Unit tests for the MCP monitoring tool — monitor_system."""

from unittest.mock import AsyncMock, patch


from prism.mcp.monitor import monitor_system


class TestMonitorSystemTool:
    async def test_returns_snapshot_dict(self):
        """monitor_system returns a dict with score, grade, metrics."""
        with patch(
            "prism.mcp.monitor.collect_snapshot", new_callable=AsyncMock
        ) as mock:
            from prism.iris.monitor import MonitorSnapshot
            from prism.iris.monitor.scorer import LoadScore

            mock.return_value = MonitorSnapshot(
                timestamp=1234567890.0,
                score=LoadScore(
                    overall=25.0,
                    cpu=20.0,
                    memory=30.0,
                    disk=25.0,
                    process=25.0,
                    details={},
                ),
                grade="healthy",
                metrics={"iris_cpu_usage": 12.5},
                metric_count=42,
                alerts_count=0,
            )
            result = await monitor_system()

        assert isinstance(result, dict)
        assert "score" in result
        assert result["score"]["overall"] == 25.0
        assert result["grade"] == "healthy"
        assert "metrics" in result
        assert result["metric_count"] == 42

    async def test_tool_is_registered(self):
        """The monitor_system function should have _is_mcp_tool = True."""
        assert getattr(monitor_system, "_is_mcp_tool", False) is True
