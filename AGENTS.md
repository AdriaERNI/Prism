# Agent Instructions for Prism

Prism is an MCP server and CLI for InterSystems IRIS development. It exposes tools for SQL, documents, compilation, debugging, testing, and ObjectScript execution via the Atelier REST API.

## Quick Reference

| Task | Command |
|------|---------|
| Install deps | `uv sync` |
| Run server | `uv run python main.py` or `python -m prism` |
| Unit tests | `uv run pytest tests/unit/ -v` |
| Integration tests | `IRIS_BASE_URL=http://<iris>:52773 uv run pytest tests/integration/ -v` |
| Windows tests | `bash vagrant/run-integration-tests.sh` (see [docs/testing.md](docs/testing.md)) |
| Lint | `uv run ruff check . && uv run ruff format --check .` |
| Fix lint | `uv run ruff check --fix . && uv run ruff format .` |

Full testing guide: [docs/testing.md](docs/testing.md) — covers unit, integration,
and Windows Vagrant tests with log reading and troubleshooting.

## Architecture

```
src/prism/
├── settings.py         # pydantic-settings: env, .env, and config.json loader
├── iris/
│   ├── sdk/            # Shared utilities: http, logging, workspace, debug protocols
│   └── api/            # Thin HTTP wrappers for IRIS REST API
├── mcp/                # MCP tools with @logged_tool decorator
│   ├── _decorator.py   # logged_tool implementation
│   ├── server.py       # FastMCP server with auto-discovery
│   └── *.py            # One module per tool domain
└── cli/                # Typer commands (sync wrappers around async API)
```

**Settings access**: import the singleton `from prism.settings import settings` and read fields like `settings.iris_base_url`. Sources are merged with precedence env > `.env` > `<user-data>/prism/config.json` > field defaults.

## Adding an MCP Tool

1. Create or edit a file in `src/prism/mcp/` (e.g., `my_feature.py`)
2. Use the `@logged_tool` decorator:

```python
from typing import Annotated
from pydantic import Field
from prism.mcp._decorator import logged_tool
from prism.iris.api import my_api  # your API module

@logged_tool
async def my_tool(
    param: Annotated[str, Field(description="What this param does")],
    optional: Annotated[str | None, Field(description="Optional param")] = None,
) -> dict:
    """Tool description shown to MCP clients."""
    return await my_api.do_something(param, optional)
```

- Tools are auto-discovered by `discover_tools()` in `src/prism/mcp/__init__.py`
- Use `@logged_tool(task=True)` for background-capable tools
- All tool parameters must use `Annotated[T, Field(description="...")]` for MCP schema generation

## Adding an API Function

API modules in `src/prism/iris/api/` are thin HTTP wrappers:

```python
from prism.iris.sdk.http import api_url, client, parse_json

async def my_operation(param: str, namespace: str | None = None) -> dict:
    c = client()
    r = await c.post(f"{api_url(namespace)}/action/endpoint", json={"param": param})
    r.raise_for_status()
    return parse_json(r)
```

## Testing Patterns

**Unit tests** (`tests/unit/`): Mock HTTP with `httpx.MockTransport`, no IRIS needed.

```python
import httpx
from unittest.mock import patch
from prism.iris.api import my_api

def mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))

async def test_my_api():
    def handler(request):
        return httpx.Response(200, json={"result": "ok"})
    
    with patch.object(my_api, "client", lambda: mock_client(handler)):
        result = await my_api.my_operation("test")
        assert result["result"] == "ok"
```

**Integration tests** (`tests/integration/`): Use `live` fixture, tests skip if IRIS unreachable.

```python
async def test_with_iris(live, cleanup):
    result = await live.call_tool("execute_sql", {"query": "SELECT 1"})
    cleanup("Test.MyDoc.cls")  # auto-delete after test
```

**Key fixtures**: `client` (MCP client), `live` (connected client), `workspace` (tmp_path), `cleanup` (auto-delete docs).

## Conventions

- **Async everywhere**: All API calls and MCP tools are async; CLI uses `asyncio.run()`
- **Document validation**: Use `validate_doc_name()` and `resolve_safe()` from `prism.iris.sdk.workspace`
- **Commits**: Follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`)
- **Python 3.12+** required

## Documentation

- [docs/](docs/) — MkDocs site with command reference and MCP tool docs
- [docs/mcp/tools.md](docs/mcp/tools.md) — Full MCP tool reference
- [docs/getting-started/configuration.md](docs/getting-started/configuration.md) — Environment variables and settings

## Known Issue

`debug_attach` (attach by PID) does not work on Windows IRIS due to a server-side limitation. Use `debug_start` with breakpoints instead.
