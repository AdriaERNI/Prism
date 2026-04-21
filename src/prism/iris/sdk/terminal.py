"""IRIS terminal via native API — run ObjectScript commands over SuperServer.

Each call creates a separate IRIS process, enabling true parallel execution.
Requires the MCP.Terminal helper class on the server, which is auto-deployed
on first use.
"""

from __future__ import annotations

import asyncio
import functools
import logging
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
_deployed_namespaces: set[str] = set()

_log = logging.getLogger(__name__)


def _parse_host(base_url: str) -> str:
    """Extract hostname from IRIS_BASE_URL (e.g. 'http://192.168.1.100:52773' -> '192.168.1.100')."""
    url = base_url.split("://", 1)[-1]
    return url.split(":")[0].split("/")[0]


_iris_sdk = None


def _load_iris():
    """Return the InterSystems ``iris`` module with ``createConnection``.

    In PyInstaller builds, ``iris.__init__`` checks
    ``os.path.exists("_elsdk_.py")`` which fails because the file is compiled
    to ``.pyc``. This causes ``from iris._elsdk_ import *`` to be skipped, so
    ``iris.createConnection`` is never defined.

    This function detects and fixes that by explicitly importing
    ``iris._elsdk_`` and copying its public symbols into the ``iris`` module.
    """
    global _iris_sdk
    if _iris_sdk is not None:
        return _iris_sdk

    _log.debug("Loading InterSystems iris module...")
    import iris  # noqa: F811 — the top-level InterSystems package

    _log.debug(
        "iris module loaded from %s, has createConnection: %s",
        getattr(iris, "__file__", "?"),
        hasattr(iris, "createConnection"),
    )

    if not hasattr(iris, "createConnection"):
        _log.debug("Forcing import of iris._elsdk_ for PyInstaller build...")
        import iris._elsdk_

        for name in dir(iris._elsdk_):
            if not name.startswith("_"):
                setattr(iris, name, getattr(iris._elsdk_, name))
        _log.debug(
            "After _elsdk_ import, has createConnection: %s",
            hasattr(iris, "createConnection"),
        )

    _iris_sdk = iris
    return _iris_sdk


def _connect(namespace: str | None = None):
    """Create a native connection to the IRIS SuperServer."""
    iris_mod = _load_iris()

    host = _parse_host(IRIS_BASE_URL)
    ns = namespace or IRIS_NAMESPACE
    _log.debug("Connecting to %s:%s ns=%s ...", host, IRIS_SUPERSERVER_PORT, ns)
    conn = iris_mod.createConnection(
        host, IRIS_SUPERSERVER_PORT, ns, IRIS_USERNAME, IRIS_PASSWORD
    )
    _log.debug("Connected successfully")
    return conn


async def ensure_helper_deployed(namespace: str | None = None) -> None:
    """Deploy the MCP.Terminal helper class if not already deployed.

    Uses an asyncio lock to prevent concurrent deploys on first parallel use.
    Deployment happens via the Atelier REST API (httpx), not the native API.
    Tracks deployment per namespace so multi-namespace setups work correctly.
    """
    ns = namespace or IRIS_NAMESPACE
    if ns in _deployed_namespaces:
        return

    async with _deploy_lock:
        if ns in _deployed_namespaces:
            return

        from prism.iris.api.documents import get_document, put_document
        from prism.iris.api.compile import compile_documents

        _log.debug("Ensuring %s is deployed in namespace %s", HELPER_DOC, ns)

        try:
            await get_document(HELPER_DOC, namespace=ns)
            _deployed_namespaces.add(ns)
            _log.debug("%s already exists in %s", HELPER_DOC, ns)
            return
        except Exception:
            pass

        _log.debug("Deploying %s to namespace %s", HELPER_DOC, ns)
        await put_document(HELPER_DOC, HELPER_SOURCE, namespace=ns)
        await compile_documents([HELPER_DOC], namespace=ns)
        _deployed_namespaces.add(ns)
        _log.debug("%s deployed and compiled in %s", HELPER_DOC, ns)


def _run_command_sync(command: str, namespace: str | None = None) -> str:
    """Execute an ObjectScript command via the native IRIS API (blocking)."""
    iris_mod = _load_iris()

    conn = _connect(namespace)
    try:
        _log.debug("Creating IRIS object...")
        iris_obj = iris_mod.createIRIS(conn)
        _log.debug("Calling %s.Execute()...", HELPER_CLASS)
        result = iris_obj.classMethodString(HELPER_CLASS, "Execute", command)
        _log.debug("Execute returned %d chars", len(result) if result else 0)
        return result
    finally:
        conn.close()


async def execute_command(
    command: str,
    namespace: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """Execute an ObjectScript command via the native IRIS API.

    Auto-deploys the helper class on first use. Runs the blocking native
    call in a thread executor so it doesn't block the event loop.

    Returns ``{"namespace": ..., "command": ..., "output": ..., "prompt": ""}``.
    """
    start = time.monotonic()
    # Include helper auto-deploy in the same timeout budget so callers don't
    # wait unboundedly on first use.
    await asyncio.wait_for(ensure_helper_deployed(namespace), timeout=timeout)

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
