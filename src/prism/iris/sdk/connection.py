"""Per-call IRIS connection target override.

Allows MCP tools to target a different IRIS instance (host + port) than
the one configured in pydantic settings, without changing global state.

Usage in MCP tools::

    from prism.iris.sdk.connection import resolve_host, resolve_port

    host = resolve_host(target_host)
    port = resolve_port(target_port)

When a parameter is ``None``, the settings default is used.
"""

from __future__ import annotations

from prism.settings import settings


def resolve_host(target_host: str | None) -> str:
    """Return the IRIS hostname, preferring *target_host* over settings.

    Falls back to parsing ``settings.iris_base_url`` when *target_host* is
    ``None`` or empty.
    """
    if target_host and target_host.strip():
        return target_host.strip()
    return _parse_host(settings.iris_base_url)


def resolve_port(target_port: int | None) -> int:
    """Return the IRIS REST API port, preferring *target_port* over settings.

    Falls back to the port embedded in ``settings.iris_base_url`` when
    *target_port* is ``None``.
    """
    if target_port is not None and target_port > 0:
        return target_port
    return _parse_port(settings.iris_base_url)


def resolve_base_url(target_host: str | None, target_port: int | None) -> str:
    """Build a base URL from override or settings.

    Constructs ``http://{host}:{port}`` (or ``https://`` if the settings
    base URL uses HTTPS) using the override values, falling back to the
    settings defaults for any ``None``/empty values.

    Examples::

        resolve_base_url(None, None)          → "http://localhost:52773"
        resolve_base_url("10.0.0.5", 8080)     → "http://10.0.0.5:8080"
        resolve_base_url("10.0.0.5", None)     → "http://10.0.0.5:52773"
    """
    scheme = "https" if settings.iris_base_url.startswith("https://") else "http"
    host = resolve_host(target_host)
    port = resolve_port(target_port)
    return f"{scheme}://{host}:{port}"


def _parse_host(base_url: str) -> str:
    """Extract hostname from a base URL string.

    ``"http://192.168.1.100:52773"`` → ``"192.168.1.100"``
    ``"https://iris.example.com/api"`` → ``"iris.example.com"``
    """
    url = base_url.split("://", 1)[-1]
    return url.split(":")[0].split("/")[0]


def _parse_port(base_url: str) -> int:
    """Extract port from a base URL string.

    ``"http://192.168.1.100:52773"`` → ``52773``
    ``"http://localhost"`` → ``80`` (http default) or ``443`` (https default)
    """
    scheme = "https" if base_url.startswith("https://") else "http"
    url = base_url.split("://", 1)[-1]
    # Remove path if present
    url = url.split("/")[0]
    if ":" in url:
        port_str = url.split(":", 1)[1]
        try:
            return int(port_str)
        except ValueError:
            pass
    return 443 if scheme == "https" else 80
