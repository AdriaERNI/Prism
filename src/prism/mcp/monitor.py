"""MCP tool for monitoring IRIS system resources.

Exposes ``monitor_system`` which fetches live metrics from the IRIS
``/api/monitor/metrics`` endpoint, computes a weighted load score, and
returns a structured snapshot suitable for benchmarking and comparison.
"""

from typing import Annotated

from pydantic import Field

from prism.iris.monitor import collect_snapshot
from prism.mcp._decorator import logged_tool


@logged_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def monitor_system(
    include_raw_metrics: Annotated[
        bool,
        Field(
            description="If true, include all raw metric samples in the response "
            "(default: false — only key metrics and score are returned)."
        ),
    ] = False,
    target_host: Annotated[
        str | None,
        Field(
            description="IRIS server host or IP. "
            "Uses the configured default if omitted."
        ),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port. Uses the configured default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Fetch live IRIS metrics and return a load snapshot.

    **Runs on: IRIS server** (remote, `/api/monitor`). Returns a snapshot
    with `score` (composite 0-100 load, higher = more loaded) and per-category
    sub-scores (`cpu`, `memory`, `disk`, `process`), `grade`
    (idle..critical), curated `metrics`, `metric_count`, and `alerts_count`.
    Use two snapshots to compare instances — the lower score wins.
    """
    snapshot = await collect_snapshot(
        target_host=target_host,
        target_port=target_port,
    )
    result = snapshot.to_dict()

    if include_raw_metrics:
        result["raw_metrics"] = [
            {"name": s.name, "value": s.value, "labels": s.labels} for s in snapshot.raw_samples
        ]

    return result
