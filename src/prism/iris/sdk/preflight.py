"""Startup connectivity check for IRIS."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from prism.config import IRIS_NAMESPACE, IRIS_WORKSPACE
from prism.iris.sdk.http import base_url, auth
from prism.iris.sdk.log import logger


def preflight_check() -> None:
    """Verify IRIS connectivity and log server info. Exits on failure."""
    url = f"{base_url()}/api/atelier/"
    logger.info(f"Connecting to IRIS at {base_url()} ...")
    try:
        r = httpx.get(url, auth=auth(), timeout=10.0)
        r.raise_for_status()
    except httpx.ConnectError:
        logger.error(f"Cannot connect to {base_url()}")
        sys.exit(1)
    except httpx.ConnectTimeout:
        logger.error(f"Connection to {base_url()} timed out")
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        logger.error(f"IRIS responded with {exc.response.status_code}")
        sys.exit(1)
    except httpx.RequestError as exc:
        logger.error(f"{exc}")
        sys.exit(1)

    data = r.json()
    result = data.get("result", {}).get("content", data)
    version = result.get("version", "unknown")
    raw_ns = result.get("namespaces", [])
    namespaces = [ns.get("name", ns) if isinstance(ns, dict) else ns for ns in raw_ns]

    ns_list = ", ".join(namespaces) if namespaces else "n/a"
    logger.info(f"{version} | ns: {ns_list} | target: {IRIS_NAMESPACE}")

    if namespaces and IRIS_NAMESPACE not in namespaces:
        logger.error(
            f"Namespace '{IRIS_NAMESPACE}' not found on server. Available: {ns_list}"
        )
        sys.exit(1)

    if IRIS_WORKSPACE:
        ws_path = Path(IRIS_WORKSPACE).resolve()
        ws_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace: {ws_path}")
    else:
        logger.info("Workspace: not configured (get/put/put_and_compile disabled)")
