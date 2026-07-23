"""IRIS monitoring API calls — /api/monitor/metrics and /api/monitor/alerts.

The /api/monitor service exposes Prometheus-format metrics (OpenMetrics
standard) and alert data.  These endpoints are enabled by default with
unauthenticated access, but can be secured (see IRIS docs, "Securing REST
Services").

Returns the **raw text** (Prometheus exposition format) so callers can
parse with :func:`prism.iris.monitor.parser.parse_prometheus_text`.
"""

from __future__ import annotations

from prism.iris.sdk.http import base_url, client


async def get_metrics() -> str:
    """GET /api/monitor/metrics — raw Prometheus exposition-format text.

    Returns all instance metrics including CPU, memory, disk, database,
    journal, SQL, process, write-daemon, and WQM sensor groups.

    See: https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GCM_rest
    """
    c = client()
    r = await c.get(f"{base_url()}/api/monitor/metrics")
    r.raise_for_status()
    return r.text


async def get_alerts() -> str:
    """GET /api/monitor/alerts — system alerts since last scrape.

    Returns Prometheus-format alert text.  Alerts are cleared after each
    scrape, so each call returns only newly-posted alerts.
    """
    c = client()
    r = await c.get(f"{base_url()}/api/monitor/alerts")
    r.raise_for_status()
    return r.text
