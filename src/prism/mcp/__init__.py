"""MCP tool auto-discovery.

Any async function decorated with ``@logged_tool`` (which sets
``_is_mcp_tool = True``) in a public module under this package is
automatically collected by :func:`discover_tools`.
"""

import importlib
import pkgutil
from pathlib import Path

from prism.settings import settings

_SKIP_MODULES: set[str] = set()
if not settings.iris_workspace:
    _SKIP_MODULES.add("workspace")
if not settings.iris_debug_enabled:
    _SKIP_MODULES.add("debugger")


def discover_tools() -> list:
    """Import all public modules in this package and return MCP tool functions."""
    package_dir = Path(__file__).parent
    tools = []
    for info in pkgutil.iter_modules([str(package_dir)]):
        if info.name.startswith("_"):
            continue
        if info.name in _SKIP_MODULES:
            continue
        module = importlib.import_module(f".{info.name}", __package__)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and getattr(attr, "_is_mcp_tool", False):
                tools.append(attr)
    return tools
