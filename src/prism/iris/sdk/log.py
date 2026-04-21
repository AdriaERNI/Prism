"""Stderr logging helpers for MCP tool calls."""

import json
import logging
import sys

logger = logging.getLogger("prism")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False

_WIDTH = 55
_MAX_LOG_OUTPUT_CHARS = 4000


def _pretty(obj: object) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _truncate_content(params: dict) -> dict:
    """Return a copy with long 'content' arrays summarized."""
    if "content" not in params or not isinstance(params["content"], list):
        return params
    lines = params["content"]
    if len(lines) <= 10:
        return params
    truncated = lines[:3] + [f"  ... ({len(lines)} lines total) ..."] + lines[-3:]
    return {**params, "content": truncated}


def _truncate_result(result: object) -> object:
    """Summarize oversized terminal output in logs."""
    if not isinstance(result, dict):
        return result
    output = result.get("output")
    if not isinstance(output, str) or len(output) <= _MAX_LOG_OUTPUT_CHARS:
        return result

    head = output[:2000]
    tail = output[-1000:]
    omitted = len(output) - len(head) - len(tail)
    marker = f"\n... ({omitted} chars omitted) ...\n"
    return {**result, "output": f"{head}{marker}{tail}"}


def log_request(tool: str, params: dict) -> None:
    sep = "\u2500" * (_WIDTH - len(tool) - 14)
    logger.debug(f"\n%s \u2500\u2500 %s \u2500\u2500 REQUEST {sep}", _ts(), tool)
    logger.debug(_pretty(_truncate_content(params)))


def log_response(tool: str, result: object) -> None:
    sep = "\u2500" * (_WIDTH - len(tool) - 15)
    logger.debug(f"\n%s \u2500\u2500 %s \u2500\u2500 RESPONSE {sep}", _ts(), tool)
    logger.debug(_pretty(_truncate_result(result)))


def _ts() -> str:
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S")
