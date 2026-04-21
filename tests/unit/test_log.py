"""Unit tests for logging truncation helpers."""

from prism.iris.sdk.log import _truncate_result


def test_truncate_result_keeps_small_output():
    result = {"output": "hello", "command": 'Write "hello"'}
    assert _truncate_result(result) == result


def test_truncate_result_summarizes_large_output():
    large = "A" * 5000
    result = {"output": large, "command": "Write big"}

    truncated = _truncate_result(result)

    assert isinstance(truncated, dict)
    assert truncated["command"] == "Write big"
    assert truncated["output"] != large
    assert "chars omitted" in truncated["output"]
    assert len(truncated["output"]) < len(large)
