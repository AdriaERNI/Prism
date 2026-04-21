"""Debug session lifecycle management.

Tracks active DBGP debug sessions across MCP tool calls. Each session holds
a live WebSocket connection to IRIS and is identified by a UUID.
"""

from __future__ import annotations

import asyncio
import time
import uuid

from prism.config import IRIS_DEBUG_IDLE_TIMEOUT
from prism.iris.sdk.dbgp import DbgpConnection


class DebugSession:
    """A single active debug session."""

    def __init__(self, conn: DbgpConnection, target: str, namespace: str | None):
        self.id: str = uuid.uuid4().hex[:12]
        self.conn: DbgpConnection = conn
        self.target: str = target
        self.namespace: str | None = namespace
        self.created_at: float = time.monotonic()
        self.last_active: float = self.created_at
        self.state: str = "starting"  # starting | running | break | ended

    def touch(self) -> None:
        """Reset the idle timer."""
        self.last_active = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_active

    @property
    def is_expired(self) -> bool:
        return self.idle_seconds > IRIS_DEBUG_IDLE_TIMEOUT


class SessionManager:
    """Singleton registry of active debug sessions."""

    def __init__(self, max_sessions: int = 1):
        self._sessions: dict[str, DebugSession] = {}
        self._max_sessions = max_sessions
        self._cleanup_task: asyncio.Task | None = None

    def _ensure_cleanup(self) -> None:
        """Start the background cleanup loop if not already running."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Periodically close expired sessions."""
        while self._sessions:
            await asyncio.sleep(30)
            expired = [sid for sid, s in self._sessions.items() if s.is_expired]
            for sid in expired:
                await self.close(sid)
        self._cleanup_task = None

    async def create(
        self,
        conn: DbgpConnection,
        target: str,
        namespace: str | None = None,
    ) -> DebugSession:
        """Register a new debug session.

        Raises RuntimeError if the maximum number of concurrent sessions is reached.
        """
        # Clean up any expired sessions first
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            await self.close(sid)

        if len(self._sessions) >= self._max_sessions:
            raise RuntimeError(
                f"Maximum concurrent debug sessions ({self._max_sessions}) reached. "
                "Stop an existing session before starting a new one."
            )

        session = DebugSession(conn, target, namespace)
        self._sessions[session.id] = session
        self._ensure_cleanup()
        return session

    def get(self, session_id: str) -> DebugSession:
        """Retrieve a session by ID, resetting its idle timer.

        Raises KeyError if the session does not exist or has expired.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"No active debug session with ID '{session_id}'")
        if session.is_expired:
            # Schedule cleanup but report as missing
            asyncio.create_task(self.close(session_id))
            raise KeyError(
                f"Debug session '{session_id}' has expired due to inactivity"
            )
        session.touch()
        return session

    async def close(self, session_id: str) -> bool:
        """Close and remove a session. Returns True if it existed."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.state = "ended"
        try:
            await session.conn.close()
        except Exception:
            pass
        return True

    async def close_all(self) -> int:
        """Close all active sessions. Returns the count closed."""
        ids = list(self._sessions.keys())
        for sid in ids:
            await self.close(sid)
        return len(ids)

    @property
    def active_sessions(self) -> list[dict]:
        """Summary of all active sessions."""
        return [
            {
                "session_id": s.id,
                "target": s.target,
                "state": s.state,
                "idle_seconds": round(s.idle_seconds, 1),
                "namespace": s.namespace,
            }
            for s in self._sessions.values()
            if not s.is_expired
        ]


# Module-level singleton
_manager = SessionManager()


def get_session_manager() -> SessionManager:
    return _manager
