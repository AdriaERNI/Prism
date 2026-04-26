"""@logged_tool decorator — auto-logs request/response for MCP tools."""

import functools
import inspect

from fastmcp import Context
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from prism.iris.sdk.log import log_request, log_response
from prism.output import format_output
from prism.settings import settings


def logged_tool(fn=None, *, task=None):
    """Wrap an async MCP tool function with automatic request/response logging.

    Sets ``_is_mcp_tool = True`` on the wrapper so that auto-discovery can
    collect it.  Pass ``task=True`` to mark the tool as background-capable
    (forwarded to ``FastMCP.tool()`` during registration).

    When ``settings.prism_output_format`` is ``"toon"`` and the tool returns a dict,
    the result is returned as a ``ToolResult`` with TOON-formatted
    ``TextContent``, bypassing FastMCP's default dict → structuredContent
    serialization.
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            params = {
                k: v for k, v in bound.arguments.items() if not isinstance(v, Context)
            }

            log_request(fn.__name__, params)
            result = await fn(*args, **kwargs)

            if settings.prism_output_format == "toon" and isinstance(
                result, (dict, list)
            ):
                toon_text = format_output(result, "toon")
                log_response(fn.__name__, toon_text)
                return ToolResult(
                    content=[TextContent(type="text", text=toon_text)],
                )

            log_response(fn.__name__, result)
            return result

        wrapper._is_mcp_tool = True
        wrapper._mcp_tool_kwargs = {}
        if task is not None:
            wrapper._mcp_tool_kwargs["task"] = task
        return wrapper

    if fn is not None:
        # Called as @logged_tool without parentheses
        return decorator(fn)
    # Called as @logged_tool(task=True) with parentheses
    return decorator
