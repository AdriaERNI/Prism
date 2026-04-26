"""Integration test fixtures.

Requires a running IRIS instance configured in .env.
Run with: uv run pytest tests/integration/ -v
"""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp import Client

import prism.iris.sdk.http as http_mod
import prism.mcp as tools_pkg
from prism.mcp.server import create_mcp
from prism.settings import settings

# ── Workspace emulation ─────────────────────────────────────────────

WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"

ALL_TEST_DOCS = [
    "Test.MCPPerson.cls",
    "Test.MCPUtils.cls",
    "Test.MCPAddress.cls",
    "Test.MCPEmployee.cls",
    "Test.MCPRoutine.mac",
    "Test.MCPHeader.inc",
    "Test.MCPSampleTest.cls",
    "Test.MCPFailingTest.cls",
    "Test.MCPBgHelper.cls",
]

# Helper classes auto-deployed by MCP tools — cleaned up separately
MCP_HELPER_DOCS = [
    "MCP.TestRunner.cls",
]


def stage_file(workspace: Path, name: str) -> None:
    """Copy a file from ``tests/workspace/`` into the temporary workspace."""
    src = WORKSPACE_DIR / name
    dest = workspace / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def write_to_workspace(workspace: Path, name: str, lines: list[str]) -> None:
    """Write *lines* to ``workspace / name`` (for dynamic content in tests)."""
    dest = workspace / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines))


# ── Fixtures ─────────────────────────────────────────────────────────


def _workspace_patch(workspace: Path):
    """Patch ``settings.iris_workspace`` for the duration of a test."""
    return patch.object(settings, "iris_workspace", str(workspace))


@pytest.fixture(autouse=True)
def _reset_http_client():
    """Reset the shared httpx client so each test gets a fresh one on its event loop."""
    http_mod._client = None
    yield
    if http_mod._client is not None and not http_mod._client.is_closed:
        # Can't await close in a sync fixture; just discard the reference.
        # The GC will clean it up.
        http_mod._client = None


@pytest.fixture(params=["native", "ws"])
def terminal_method(request):
    """Parametrize tests to run with both terminal backends."""
    method = request.param
    with patch.object(settings, "iris_terminal_method", method):
        yield method


@pytest.fixture
def workspace(tmp_path) -> Path:
    """Return a temporary workspace directory."""
    return tmp_path


@pytest.fixture
def client(workspace):
    """MCP client with IRIS_WORKSPACE patched and debug tools enabled."""
    orig_skip = tools_pkg._SKIP_MODULES.copy()
    tools_pkg._SKIP_MODULES.discard("workspace")
    tools_pkg._SKIP_MODULES.discard("debugger")
    with _workspace_patch(workspace):
        mcp = create_mcp()
        yield Client(mcp)
    tools_pkg._SKIP_MODULES = orig_skip


@pytest.fixture
async def live(client):
    """Yield a connected client; skip if IRIS is unreachable."""
    try:
        async with client:
            yield client
    except Exception as e:
        pytest.skip(f"IRIS not reachable: {e}")


@pytest.fixture(autouse=True)
async def cleanup(workspace):
    """Close debug sessions first, then delete all test documents."""
    yield

    # 1. Close any leftover debug sessions before deleting documents
    from prism.iris.sdk.debug_session import get_session_manager

    mgr = get_session_manager()
    await mgr.close_all()

    # 2. Delete test documents
    orig_skip = tools_pkg._SKIP_MODULES.copy()
    tools_pkg._SKIP_MODULES.discard("workspace")
    try:
        with _workspace_patch(workspace):
            mcp = create_mcp()
            c = Client(mcp)
            try:
                async with c:
                    for doc in ALL_TEST_DOCS:
                        try:
                            await c.call_tool("delete_document", {"name": doc})
                        except Exception:
                            pass
            except Exception:
                pass
    finally:
        tools_pkg._SKIP_MODULES = orig_skip
