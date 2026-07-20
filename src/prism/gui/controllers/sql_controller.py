"""SQL controller — bridges async IRIS queries with the tkinter main loop.

tkinter is single-threaded.  ``root.after()`` is **not** thread-safe —
calling it from a background thread silently fails (the callback is
never scheduled).  Instead, we use a ``queue.Queue`` for thread-safe
communication and the main window polls it via ``root.after()``.

Flow:
  1. ``execute()`` pushes work onto a background daemon thread.
  2. Background thread runs ``asyncio.run(execute_query(...))``, puts
     the ``QueryResult`` into ``self._queue``.
  3. The Tk main loop calls ``poll()`` every 100 ms via ``root.after()``.
  4. ``poll()`` drains the queue and invokes the stored callback.
"""

from __future__ import annotations

import asyncio
import html
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import tkinter as tk


@dataclass
class QueryResult:
    """Structured result of an SQL query execution."""

    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    elapsed: float = 0.0
    error: str | None = None
    raw: dict | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


class SQLController:
    """Controller that executes SQL queries off the UI thread.

    Usage from a widget::

        controller = SQLController(root)
        controller.start_polling()          # begin checking for results
        controller.execute("SELECT 1", on_done=self._show_results)
    """

    POLL_MS = 100  # how often to check the queue (milliseconds)

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._queue: queue.Queue[QueryResult] = queue.Queue()
        self._running = False
        self._thread: threading.Thread | None = None
        self._pending_callback: Callable[[QueryResult], None] | None = None
        self._polling = False
        # Cancellation support
        self._cancel_requested = False

    @property
    def is_running(self) -> bool:
        """Whether a query is currently executing."""
        return self._running

    def start_polling(self) -> None:
        """Start polling the result queue on the Tk main loop.

        Call once after GUI creation.
        """
        if self._polling:
            return
        self._polling = True
        self._poll()

    def stop_polling(self) -> None:
        """Stop polling — call on window destroy to prevent after() leaks."""
        self._polling = False

    def _poll(self) -> None:
        """Check the queue for completed results (runs on Tk main thread)."""
        try:
            result = self._queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self._running = False
            cb = self._pending_callback
            self._pending_callback = None
            if cb is not None:
                cb(result)

        if self._polling:
            self._root.after(self.POLL_MS, self._poll)

    def execute(
        self,
        query: str,
        namespace: str | None = None,
        on_done: Callable[[QueryResult], None] | None = None,
    ) -> None:
        """Run *query* in a background thread.

        When finished, the ``on_done`` callback is invoked on the Tk
        main thread (via the polling mechanism).
        """
        if self._running:
            return

        self._running = True
        self._cancel_requested = False
        self._pending_callback = on_done
        self._thread = threading.Thread(
            target=self._run_query,
            args=(query, namespace),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> bool:
        """Request cancellation of the running query.

        Returns True if a cancellation was requested, False if no query
        is running. The actual httpx request can't be interrupted, but
        the result will be discarded.
        """
        if not self._running:
            return False
        self._cancel_requested = True
        return True

    def check_connection(
        self,
        on_done: Callable[[bool], None] | None = None,
    ) -> None:
        """Check if IRIS is reachable — runs off the UI thread.

        Args:
            on_done: Called with ``True`` if IRIS is reachable, ``False``
                     otherwise. Executed on the Tk main thread.
        """
        if self._running:
            return  # already busy

        self._running = True
        self._cancel_requested = False
        self._pending_callback = (
            None  # connection check doesn't use QueryResult callback
        )

        def _conn_done(connected: bool) -> None:
            self._running = False
            if on_done is not None:
                self._root.after(0, lambda: on_done(connected))

        t = threading.Thread(
            target=self._run_connection_check,
            args=(_conn_done,),
            daemon=True,
        )
        t.start()

    def execute_update(
        self,
        sql: str,
        on_done: Callable[[QueryResult], None] | None = None,
    ) -> bool:
        """Execute an UPDATE/INSERT/DELETE off the UI thread.

        Returns True if the update was queued, False if the controller
        is busy. The ``on_done`` callback receives a QueryResult with
        ``error`` set on failure.
        """
        if self._running:
            return False

        self._running = True
        self._cancel_requested = False
        self._pending_callback = on_done
        self._thread = threading.Thread(
            target=self._run_update,
            args=(sql,),
            daemon=True,
        )
        self._thread.start()
        return True

    # ── Internal ────────────────────────────────────────────────────

    def _run_connection_check(self, on_done: Callable[[bool], None]) -> None:
        """Run connection probe in a background thread."""
        import httpx

        from prism.iris.sdk.http import base_url

        try:
            url = base_url()
            r = httpx.get(f"{url}/csp/sys/UtilHome.csp", timeout=3.0)
            connected = r.status_code in (200, 302, 401)
        except Exception:
            connected = False

        on_done(connected)

    def _run_update(self, sql: str) -> None:
        """Execute an UPDATE statement in a background thread."""
        import httpx

        from prism.iris.sdk.http import api_url, parse_json
        from prism.settings import settings

        result = QueryResult()

        try:
            url = f"{api_url(None)}/action/query"
            r = httpx.post(
                url,
                json={"query": sql},
                auth=httpx.BasicAuth(settings.iris_username, settings.iris_password),
                timeout=15.0,
            )
            r.raise_for_status()
            raw = parse_json(r)

            status = raw.get("status", {})
            errors = status.get("errors", [])
            if errors:
                result.error = errors[0].get("error", "Unknown IRIS error")
                result.error = html.unescape(result.error)
        except Exception as exc:
            result.error = str(exc)

        # Check if cancelled while running — discard result if so
        if self._cancel_requested:
            self._running = False
            self._pending_callback = None
            return

        self._queue.put(result)

    def _run_query(self, query: str, namespace: str | None) -> None:
        """Execute query in a fresh asyncio event loop within this thread.

        We create a *new* event loop and a *new* httpx client per call
        rather than using ``asyncio.run()``.  ``asyncio.run()`` closes
        the loop at exit, which corrupts the shared ``httpx.AsyncClient``
        cached in ``prism.iris.sdk.http`` — making every subsequent query
        fail with "Event loop is closed".
        """
        import httpx
        from prism.settings import settings
        from prism.iris.sdk.http import api_url, parse_json

        result = QueryResult()
        start = time.monotonic()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:

            async def _do():
                async with httpx.AsyncClient(
                    auth=httpx.BasicAuth(
                        settings.iris_username, settings.iris_password
                    ),
                    timeout=30.0,
                ) as c:
                    url = f"{api_url(namespace)}/action/query"
                    r = await c.post(url, json={"query": query})
                    r.raise_for_status()
                    return parse_json(r)

            raw = loop.run_until_complete(_do())
            result = self._parse_response(raw, start)
        except Exception as exc:
            result.error = str(exc)
            result.elapsed = time.monotonic() - start
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

        # Put result in the queue — poll() will pick it up on the main thread
        if self._cancel_requested:
            self._running = False
            self._pending_callback = None
            return

        self._queue.put(result)

    @staticmethod
    def _parse_response(raw: dict, start: float) -> QueryResult:
        """Parse IRIS /action/query response into a ``QueryResult``."""
        result = QueryResult()
        result.raw = raw
        result.elapsed = time.monotonic() - start

        # Check for IRIS-level errors
        status = raw.get("status", {})
        errors = status.get("errors", [])
        if errors:
            msg = errors[0].get("error", "Unknown IRIS error")
            result.error = html.unescape(msg)
            return result

        # Extract rows from result.content
        content = raw.get("result", {}).get("content", [])
        if not content:
            return result

        # Columns = keys of first row (preserves IRIS order in Python 3.7+)
        result.columns = list(content[0].keys())

        for row in content:
            result.rows.append([row.get(col) for col in result.columns])

        result.row_count = len(result.rows)
        return result
