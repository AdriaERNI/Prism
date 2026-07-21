# Agent Instructions for Prism

Prism is an MCP server and CLI for InterSystems IRIS development. It exposes
tools for SQL, documents, compilation, debugging, testing, and ObjectScript
execution via the Atelier REST API.

## License

Copyright © 2026 Adria Sanchez. Licensed under the GNU Affero General Public
License v3.0 (AGPL-3.0). See [LICENSE](LICENSE) for full terms.

## Quick Reference

| Task | Command |
|------|---------|
| Install deps | `uv sync` |
| Run server | `uv run prism serve` |
| Unit tests | `uv run pytest tests/unit/ -v` |
| Integration tests | `IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/ -v` |
| GUI tests | `uv run pytest tests/gui/ -v` (needs a display) |
| Document slicing tests | `uv run pytest tests/integration/test_document_slicing.py -v` |
| Debugger extra tests | `uv run pytest tests/integration/test_debugger_extra.py -v` (skips if XDebug unavailable) |
| Windows tests | `bash vagrant/run-integration-tests.sh` (see [docs/testing.md](docs/testing.md)) |
| Lint | `uv run ruff check . && uv run ruff format --check .` |
| Fix lint | `uv run ruff check --fix . && uv run ruff format .` |
| Build docs | `uv run mkdocs build --strict` |
| CLI help | `uv run prism --help` |

Full testing guide: [docs/testing.md](docs/testing.md) — covers unit, integration,
GUI, and Windows Vagrant tests with log reading and troubleshooting.

## CI

GitHub Actions workflows (all target `development` branch, promoted to `main`
via PR):

| Workflow | File | What it runs |
|----------|------|--------------|
| Test Linux | `.github/workflows/test-linux.yml` | Lint, Unit tests, Integration tests (Docker IRIS) |
| Test Windows | `.github/workflows/test-windows.yml` | Unit tests, PyInstaller build verification |
| Build and Release | `.github/workflows/build-release.yml` | Full pipeline + GitHub Release (triggered by `v*` tags) |
| GitHub Pages | `.github/workflows/pages.yml` | MkDocs build + deploy (on push to `main`) |

Branch protection is enabled on `main` and `development`. Required status checks:
Lint, Unit Tests. PRs must pass CI before merge. Linear history enforced
(squash merges only). See [docs/releases.md](docs/releases.md) for the full
release workflow.

### Branch model (Git Flow)

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready. Only accepts PRs from `release/*` or `hotfix/*`. |
| `development` | Active development. Target for all `feature/*` branches and Dependabot. |
| `feature/*` | Cut from `development`, PR'd back to `development`. |
| `release/vX.Y.Z` | Cut from `development`, PR'd to `main`, then merged back to `development`. |
| `hotfix/vX.Y.Z` | Cut from `main`, PR'd to `main`, then synced back to `development`. |

Branch naming: `v` prefix on release/hotfix branches and tags (e.g.
`release/v0.2.0`, `v0.2.0`). Feature branches use descriptive names.

Dependabot is configured to target `development` (not `main`) in
`.github/dependabot.yml`.

## Architecture

```
src/prism/
├── settings.py         # pydantic-settings: env, .env, and config.json loader (21 fields)
├── iris/
│   ├── sdk/            # Shared utilities: http, logging, workspace, debug protocols
│   └── api/            # Thin HTTP wrappers for IRIS REST API
├── mcp/                # MCP tools with @logged_tool decorator
│   ├── _decorator.py   # logged_tool implementation
│   ├── server.py       # FastMCP server with auto-discovery
│   └── *.py            # One module per tool domain
├── gui/                # tkinter SQL editor GUI
│   ├── app.py          # Main window, menu, layout, shortcuts
│   ├── theme.py        # Dark colour palette
│   ├── controllers/    # SQL execution controller (async)
│   └── widgets/        # DatabaseTree, SQLEditor, ResultsTable, StatusBar, Toolbar
└── cli/                # Typer commands (sync wrappers around async API)
```

### MCP Tool Registration

Tools are registered conditionally based on settings:

| Category | Count | Condition |
|----------|-------|-----------|
| Always-on | 11 | Always registered (including `index_code`) |
| Workspace-gated | 2 | `IRIS_WORKSPACE` is set (`put_document`, `put_and_compile`) |
| Debug-gated | 9 | `IRIS_DEBUG_ENABLED=true` (`debug_*` tools) |
| **Maximum** | **22** | Both workspace + debug enabled |

### Settings (21 fields)

Import the singleton `from prism.settings import settings` and read fields like
`settings.iris_base_url`. Sources are merged with precedence:
env > `.env` > `<user-data>/prism/config.json` > field defaults.

All 21 fields are documented in
[docs/getting-started/configuration.md](docs/getting-started/configuration.md)
and guarded by a regression test in `tests/unit/test_settings.py`.

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

**URL encoding**: `api_url()` pre-encodes `%` → `%25` for namespaces like `%SYS`.
Pass raw namespace names (e.g., `api_url('%SYS')`), not pre-encoded ones.

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

**Integration tests** (`tests/integration/`): Use `live` fixture, tests skip if IRIS
unreachable.

```python
async def test_with_iris(live, cleanup):
    result = await live.call_tool("execute_sql", {"query": "SELECT 1"})
    cleanup("Test.MyDoc.cls")  # auto-delete after test
```

**Key fixtures**: `client` (MCP client), `live` (connected client), `workspace`
(tmp_path), `cleanup` (auto-delete docs), `debug_session` (skip if XDebug unavailable).

**Test counts**: 586 unit tests, 87 integration tests, 29 GUI tests (7 integration
tests skip on CI due to IRIS Community license limits).

## Conventions

- **Async everywhere**: All API calls and MCP tools are async; CLI uses `asyncio.run()`
- **Document validation**: Use `validate_doc_name()` and `resolve_safe()` from `prism.iris.sdk.workspace`
- **Commits**: Follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`)
- **Python 3.12+** required
- **Never remove branch protection** on `main` or `development` without user's explicit approval
- **Dependabot PRs** target `development`, not `main`

## Documentation

- [docs/](docs/) — MkDocs Material site with command reference and MCP tool docs
- [mkdocs.yml](mkdocs.yml) — Theme config (indigo palette, JetBrains Mono, sticky tabs)
- [docs/mcp/tools.md](docs/mcp/tools.md) — Full MCP tool reference with return shapes
- [docs/commands/gui.md](docs/commands/gui.md) — GUI SQL editor documentation
- [docs/getting-started/configuration.md](docs/getting-started/configuration.md) — All 21 environment variables
- [docs/testing.md](docs/testing.md) — CI section, test layers, troubleshooting

## Known Issues

1. `debug_attach` (attach by PID) does not work on Windows IRIS due to a server-side
   limitation. Use `debug_start` with breakpoints instead.
2. Parallel native terminal tests skip on CI — IRIS Community license limits
   concurrent SuperServer connections (3+ parallel calls fail with "Unable to
   allocate a license").
3. Native terminal `_run_command_sync` retries 3× on transient errors (CLASS DOES
   NOT EXIST, license limit, COMMUNICATION LINK ERROR) with 2s delay.