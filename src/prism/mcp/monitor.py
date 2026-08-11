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
            description="IRIS server hostname or IP address (e.g. '192.168.1.100'). "
            "Uses the configured default if omitted."
        ),
    ] = None,
    target_port: Annotated[
        int | None,
        Field(
            description="IRIS REST API port (e.g. 52773). Uses the configured default if omitted.",
            ge=1,
            le=65535,
        ),
    ] = None,
) -> dict:
    """Monitor IRIS instance CPU, RAM, disk I/O, GPU (where available), and process load.

    **Runs on: IRIS server** — fetches live metrics from the IRIS /api/monitor
    REST endpoint (Prometheus/OpenMetrics format).

    Returns a real-time snapshot with:

    * ``score`` — composite 0-100 load score (higher = more loaded) with
      per-category sub-scores: ``cpu``, ``memory``, ``disk``, ``process``
    * ``grade`` — health grade: ``idle``, ``healthy``, ``moderate``,
      ``loaded``, or ``critical``
    * ``metrics`` — curated key metrics (CPU %, memory %, process count,
      physical reads/writes, global references, write-daemon cycle time,
      SQL active queries, license usage, alerts)
    * ``metric_count`` — total number of metric samples collected
    * ``alerts_count`` — number of system alerts since last scrape

    Use two snapshots to compare instances and determine which is less
    loaded — the lower score wins.
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
