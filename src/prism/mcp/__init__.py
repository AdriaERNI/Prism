"""MCP tool auto-discovery.

Any async function decorated with ``@logged_tool`` (which sets
``_is_mcp_tool = True``) in a public module under this package is
automatically collected by :func:`discover_tools`.

In PyInstaller frozen builds, ``pkgutil.iter_modules`` cannot scan
inside the PYZ archive, so we fall back to an explicit module list.
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

# Explicit list for PyInstaller frozen builds where pkgutil.iter_modules
# cannot enumerate modules inside the PYZ archive.
_ALL_TOOL_MODULES = [
    "compile",
    "debugger",
    "documents",
    "index",
    "server_info",
    "sql",
    "terminal",
    "testing",
    "workspace",
]


def discover_tools() -> list:
    """Import all public modules in this package and return MCP tool functions."""
    package_dir = Path(__file__).parent
    tools = []

    # Try pkgutil first (works in dev mode with a real filesystem)
    module_names: list[str] = []
    for info in pkgutil.iter_modules([str(package_dir)]):
        if not info.name.startswith("_") and info.name != "__init__":
            module_names.append(info.name)

    # Fallback for frozen builds (PyInstaller PYZ archive)
    if not module_names:
        module_names = [m for m in _ALL_TOOL_MODULES if m not in _SKIP_MODULES]
    else:
        module_names = [m for m in module_names if m not in _SKIP_MODULES]

    for name in module_names:
        module = importlib.import_module(f".{name}", __package__)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and getattr(attr, "_is_mcp_tool", False):
                tools.append(attr)
    return tools
