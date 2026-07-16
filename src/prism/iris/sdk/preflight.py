"""Startup connectivity check for IRIS."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import typer

from prism.iris.sdk.http import base_url, auth
from prism.iris.sdk.log import logger
from prism.settings import settings


def preflight_check() -> None:
    """Verify IRIS connectivity and log server info. Exits on failure."""
    url = f"{base_url()}/api/atelier/"
    logger.info(f"Connecting to IRIS at {base_url()} ...")
    try:
        r = httpx.get(url, auth=auth(), timeout=10.0)
        r.raise_for_status()
    except httpx.ConnectError:
        typer.echo(
            f"Error: Cannot connect to IRIS at {base_url()}. "
            f"Is the server running? Use --skip-preflight to bypass.",
            err=True,
        )
        sys.exit(1)
    except httpx.ConnectTimeout:
        typer.echo(
            f"Error: Connection to IRIS at {base_url()} timed out. "
            f"Use --skip-preflight to bypass.",
            err=True,
        )
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        typer.echo(
            f"Error: IRIS responded with HTTP {exc.response.status_code}. "
            f"Check your credentials and URL. Use --skip-preflight to bypass.",
            err=True,
        )
        sys.exit(1)
    except httpx.RequestError as exc:
        typer.echo(
            f"Error: Failed to connect to IRIS: {exc}. Use --skip-preflight to bypass.",
            err=True,
        )
        sys.exit(1)

    data = r.json()
    result = data.get("result", {}).get("content", data)
    version = result.get("version", "unknown")
    raw_ns = result.get("namespaces", [])
    namespaces = [ns.get("name", ns) if isinstance(ns, dict) else ns for ns in raw_ns]

    ns_list = ", ".join(namespaces) if namespaces else "n/a"
    logger.info(f"{version} | ns: {ns_list} | target: {settings.iris_namespace}")

    if namespaces and settings.iris_namespace not in namespaces:
        typer.echo(
            f"Error: Namespace '{settings.iris_namespace}' not found on server. "
            f"Available: {ns_list}",
            err=True,
        )
        sys.exit(1)

    if settings.iris_workspace:
        ws_path = Path(settings.iris_workspace).resolve()
        ws_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace: {ws_path}")
    else:
        logger.info("Workspace: not configured (get/put/put_and_compile disabled)")
