"""@logged_tool decorator — auto-logs request/response for MCP tools."""

import functools
import inspect

from fastmcp import Context

from prism.iris.sdk.log import log_request, log_response


def logged_tool(fn=None, *, task=None):
    """Wrap an async MCP tool function with automatic request/response logging.

    Sets ``_is_mcp_tool = True`` on the wrapper so that auto-discovery can
    collect it.  Pass ``task=True`` to mark the tool as background-capable
    (forwarded to ``FastMCP.tool()`` during registration).
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
