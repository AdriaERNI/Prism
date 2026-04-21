"""Integration tests for the native (irisnative) terminal SDK.

Exercises ``prism.iris.sdk.terminal`` directly against a live IRIS:
- helper class auto-deploy
- basic ObjectScript execution
- error capture (try/catch in the helper)
- true parallel execution via separate SuperServer sessions
"""

from __future__ import annotations

import asyncio
import time

import pytest

from prism.config import IRIS_NAMESPACE
from prism.iris.api.documents import DocumentNotFound, delete_document, get_document
from prism.iris.sdk import terminal as native_terminal


@pytest.fixture(autouse=True)
def _reset_deploy_flag():
    """Force ``ensure_helper_deployed`` to re-check IRIS on each test."""
    native_terminal._helper_deployed = False
    yield
    native_terminal._helper_deployed = False


@pytest.fixture
async def _probe_iris():
    """Skip the module if IRIS (or the SuperServer port) isn't reachable."""
    try:
        await native_terminal.execute_command('Write "ping"', timeout=5.0)
    except Exception as exc:
        pytest.skip(f"IRIS native terminal not reachable: {exc}")


class TestBasicExecution:
    async def test_write_literal(self, _probe_iris):
        result = await native_terminal.execute_command('Write "hello"')
        assert result["output"] == "hello"
        assert result["command"] == 'Write "hello"'
        assert result["namespace"] == IRIS_NAMESPACE

    async def test_arithmetic(self, _probe_iris):
        result = await native_terminal.execute_command("Write 2 + 3")
        assert result["output"].strip() == "5"

    async def test_multi_statement(self, _probe_iris):
        result = await native_terminal.execute_command('Set x=42 Write "x=",x')
        assert "x=42" in result["output"]

    async def test_namespace_override(self, _probe_iris):
        result = await native_terminal.execute_command(
            "Write $namespace", namespace="USER"
        )
        assert result["namespace"] == "USER"
        assert "USER" in result["output"]


class TestErrorHandling:
    async def test_bad_command_caught_by_helper(self, _probe_iris):
        """The helper class wraps XECUTE in try/catch, so IRIS errors come
        back as ``ERROR: ...`` strings instead of killing the connection."""
        result = await native_terminal.execute_command("ZZZNotACommand")
        assert result["output"].startswith("ERROR:")


class TestHelperAutoDeploy:
    async def test_auto_deploys_helper_when_missing(self, _probe_iris):
        """Deleting the helper should force the next call to redeploy it."""
        try:
            await delete_document(native_terminal.HELPER_DOC)
        except DocumentNotFound:
            pass

        native_terminal._helper_deployed = False

        await native_terminal.execute_command('Write "redeployed"')

        # Helper must exist after execute_command() completes.
        doc = await get_document(native_terminal.HELPER_DOC)
        assert doc is not None

    async def test_deploy_lock_prevents_duplicate_deploys(self, _probe_iris):
        """Concurrent first-time calls must serialize through the asyncio.Lock."""
        try:
            await delete_document(native_terminal.HELPER_DOC)
        except DocumentNotFound:
            pass

        native_terminal._helper_deployed = False

        results = await asyncio.gather(
            native_terminal.execute_command('Write "a"'),
            native_terminal.execute_command('Write "b"'),
            native_terminal.execute_command('Write "c"'),
        )

        outputs = sorted(r["output"] for r in results)
        assert outputs == ["a", "b", "c"]


class TestParallelExecution:
    async def test_parallel_hangs_run_concurrently(self, _probe_iris):
        """Three 2-second sleeps via separate irisnative connections should
        finish in ~2s (max), not ~6s (sum)."""
        # Ensure the helper is already deployed so we're not measuring that.
        await native_terminal.execute_command('Write "warmup"')

        start = time.monotonic()
        results = await asyncio.gather(
            native_terminal.execute_command('Hang 2 Write "one"', timeout=10.0),
            native_terminal.execute_command('Hang 2 Write "two"', timeout=10.0),
            native_terminal.execute_command('Hang 2 Write "three"', timeout=10.0),
        )
        elapsed = time.monotonic() - start

        outputs = sorted(r["output"] for r in results)
        assert outputs == ["one", "three", "two"]
        assert elapsed < 5.0, (
            f"Three 2s hangs took {elapsed:.1f}s — should be <5s if parallel"
        )
