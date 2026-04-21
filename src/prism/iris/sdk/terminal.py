"""IRIS terminal via irisnative — run ObjectScript commands over SuperServer.

Each call creates a separate IRIS process via irisnative, enabling true
parallel execution. Requires the MCP.Terminal helper class on the server,
which is auto-deployed on first use.
"""

from __future__ import annotations

import asyncio
import functools
import time

from prism.config import (
    IRIS_BASE_URL,
    IRIS_USERNAME,
    IRIS_PASSWORD,
    IRIS_NAMESPACE,
    IRIS_SUPERSERVER_PORT,
)

HELPER_CLASS = "MCP.Terminal"
HELPER_DOC = "MCP.Terminal.cls"
HELPER_SOURCE = [
    "Class MCP.Terminal Extends %RegisteredObject",
    "{",
    "",
    "ClassMethod Execute(code As %String) As %String [ ProcedureBlock = 0 ]",
    "{",
    '  set str=""',
    "  set tOldIO=$io",
    "  set tOldRedirect=##class(%Device).ReDirectIO()",
    "  set tOldMnemonic=##class(%Device).GetMnemonicRoutine()",
    "  try {",
    '    use $io::("^"_$ZNAME)',
    "    do ##class(%Device).ReDirectIO(1)",
    "    XECUTE (code)",
    "  } catch ex {",
    '    set str="ERROR: "_ex.DisplayString()',
    "  }",
    '  if (tOldMnemonic\'="") { use tOldIO::("^"_tOldMnemonic) }',
    "  else { use tOldIO }",
    "  do ##class(%Device).ReDirectIO(tOldRedirect)",
    "  quit str",
    "rchr(c)",
    "  quit",
    "rstr(sz,to)",
    "  quit",
    "wchr(s)",
    "  do output($char(s))",
    "  quit",
    "wff()",
    "  do output($char(12))",
    "  quit",
    "wnl()",
    "  do output($char(13,10))",
    "  quit",
    "wstr(s)",
    "  do output(s)",
    "  quit",
    "wtab(s)",
    '  do output($justify("",s))',
    "  quit",
    "output(s)",
    "  set str=str_s",
    "  quit",
    "}",
    "",
    "}",
]

_deploy_lock = asyncio.Lock()
_helper_deployed = False


def _parse_host(base_url: str) -> str:
    """Extract hostname from IRIS_BASE_URL (e.g. 'http://192.168.1.100:52773' -> '192.168.1.100')."""
    url = base_url.split("://", 1)[-1]
    return url.split(":")[0].split("/")[0]


def _connect(namespace: str | None = None):
    """Create an irisnative connection to the SuperServer."""
    # Import 'iris' before 'irisnative' to ensure the external InterSystems
    # module is cached in sys.modules. This prevents a naming collision with
    # prism.iris in PyInstaller builds where irisnative's internal
    # 'import iris' could otherwise resolve to the wrong module.
    import iris  # noqa: F401 - required for sys.modules side-effect
    import irisnative

    host = _parse_host(IRIS_BASE_URL)
    ns = namespace or IRIS_NAMESPACE
    return irisnative.createConnection(
        host, IRIS_SUPERSERVER_PORT, ns, IRIS_USERNAME, IRIS_PASSWORD
    )


async def ensure_helper_deployed() -> None:
    """Deploy the MCP.Terminal helper class if not already deployed.

    Uses an asyncio lock to prevent concurrent deploys on first parallel use.
    Deployment happens via the Atelier REST API (httpx), not irisnative.
    """
    global _helper_deployed
    if _helper_deployed:
        return

    async with _deploy_lock:
        if _helper_deployed:
            return

        from prism.iris.api.documents import get_document, put_document
        from prism.iris.api.compile import compile_documents

        try:
            await get_document(HELPER_DOC)
            _helper_deployed = True
            return
        except Exception:
            pass

        await put_document(HELPER_DOC, HELPER_SOURCE)
        await compile_documents([HELPER_DOC])
        _helper_deployed = True


def _run_command_sync(command: str, namespace: str | None = None) -> str:
    """Execute an ObjectScript command via irisnative (blocking)."""
    # Import 'iris' before 'irisnative' — see _connect() for rationale
    import iris  # noqa: F401 - required for sys.modules side-effect
    import irisnative

    conn = _connect(namespace)
    try:
        iris_obj = irisnative.createIris(conn)
        return iris_obj.classMethodString(HELPER_CLASS, "Execute", command)
    finally:
        conn.close()


async def execute_command(
    command: str,
    namespace: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """Execute an ObjectScript command via irisnative.

    Auto-deploys the helper class on first use. Runs the blocking irisnative
    call in a thread executor so it doesn't block the event loop.

    Returns ``{"namespace": ..., "command": ..., "output": ..., "prompt": ""}``.
    """
    start = time.monotonic()
    # Include helper auto-deploy in the same timeout budget so callers don't
    # wait unboundedly on first use.
    await asyncio.wait_for(ensure_helper_deployed(), timeout=timeout)

    elapsed = time.monotonic() - start
    remaining = timeout - elapsed
    if remaining <= 0:
        raise TimeoutError(
            f"Terminal command timed out after {timeout}s before execution started"
        )

    ns = namespace or IRIS_NAMESPACE
    loop = asyncio.get_running_loop()
    run_sync = functools.partial(_run_command_sync, command, namespace)
    output = await asyncio.wait_for(
        loop.run_in_executor(None, run_sync), timeout=remaining
    )

    return {
        "namespace": ns,
        "command": command,
        "output": output,
        "prompt": "",
    }
