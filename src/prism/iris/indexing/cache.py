"""Persisted index cache — store build_index results on disk.

Building the full index (and especially the Tier 2 call graph) is expensive:
~20s+ on a large namespace. The cache stores one JSON payload per
(namespace, target) keyed on a ``%Dictionary.ClassDefinition`` fingerprint
(class count + latest ``TimeChanged``), so an unchanged namespace is served
instantly from SQLite instead of re-querying IRIS.

The cache lives in the platform user cache directory (``platformdirs
user_cache_path("prism")``) so it survives restarts without polluting the
workspace or repo. Writes are atomic and torn files are discarded on read.

Schema: ``(namespace, target, fingerprint, built_at, data)`` where ``data`` is
the JSON-serialised ``build_index`` payload.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from platformdirs import user_cache_path

_DDL = """
CREATE TABLE IF NOT EXISTS index_cache (
    namespace   TEXT NOT NULL,
    target      TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    built_at    REAL NOT NULL,
    data        TEXT NOT NULL,
    PRIMARY KEY (namespace, target)
)
"""


def _db_path() -> Path:
    """Return the SQLite database path (creating parent dirs)."""
    path = user_cache_path("prism", appauthor=False) / "index_cache.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10.0)
    conn.executescript(_DDL)
    conn.commit()
    return conn


def _load_payload(data: str) -> dict | None:
    """Return the parsed payload dict, or ``None`` if the stored JSON is corrupt."""
    try:
        loaded = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _status_dict(
    namespace: str, target: str, fingerprint: str, built_at: float, payload: dict
) -> dict:
    return {
        "namespace": namespace,
        "target": target,
        "fingerprint": fingerprint,
        "classes": len(payload.get("classes", []))
        if isinstance(payload.get("classes"), list)
        else 0,
        "built_at": built_at,
        "age_seconds": max(0.0, time.time() - built_at),
    }


# ── Public API ──────────────────────────────────────────────────────────────


def cache_put(namespace: str, target: str, fingerprint: str, payload: dict) -> None:
    """Atomically store (or replace) *payload* for (namespace, target)."""
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO index_cache "
                "(namespace, target, fingerprint, built_at, data) VALUES (?, ?, ?, ?, ?)",
                (
                    namespace,
                    target,
                    fingerprint,
                    time.time(),
                    json.dumps(payload, separators=(",", ":")),
                ),
            )
            conn.commit()
    except (OSError, sqlite3.Error):
        # Cache failures are non-fatal — callers fall back to live queries.
        pass


def cache_get(namespace: str, target: str) -> dict | None:
    """Return the cached payload dict for (namespace, target), or ``None`` if absent."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT data FROM index_cache WHERE namespace = ? AND target = ?",
                (namespace, target),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None
    if row is None:
        return None
    return _load_payload(row[0])


def cache_load(namespace: str, target: str, fingerprint: str) -> dict | None:
    """Return the cached payload if it matches *fingerprint*; ``None`` when stale/absent."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT fingerprint, data FROM index_cache WHERE namespace = ? AND target = ?",
                (namespace, target),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None
    if row is None or row[0] != fingerprint:
        return None
    return _load_payload(row[1])


def cache_is_fresh(namespace: str, target: str, fingerprint: str) -> bool:
    """True if a cached entry exists for (namespace, target) with a matching fingerprint."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT fingerprint FROM index_cache WHERE namespace = ? AND target = ?",
                (namespace, target),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return False
    return row is not None and row[0] == fingerprint


def cache_status(namespace: str | None = None, target: str | None = None) -> list[dict]:
    """List cache entries as status dicts, optionally filtered.

    ``cache_status()`` → all; ``cache_status(ns)`` → that namespace;
    ``cache_status(ns, target)`` → the single matching row.
    """
    clauses: list[str] = []
    params: list[str] = []
    if namespace is not None:
        clauses.append("namespace = ?")
        params.append(namespace)
    if target is not None:
        clauses.append("target = ?")
        params.append(target)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        with _connect() as conn:
            rows = conn.execute(
                f"SELECT namespace, target, fingerprint, built_at, data FROM index_cache {where} "
                "ORDER BY namespace, target",
                params,
            ).fetchall()
    except (OSError, sqlite3.Error):
        return []
    out = []
    for ns, tgt, fp, built_at, data in rows:
        payload = _load_payload(data)
        if payload is None:
            payload = {}
        out.append(_status_dict(ns, tgt, fp, built_at, payload))
    return out


def cache_remove(namespace: str, target: str) -> int:
    """Remove the cache entry for (namespace, target). Return removed count (0 or 1)."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                "DELETE FROM index_cache WHERE namespace = ? AND target = ?",
                (namespace, target),
            )
            conn.commit()
            return cur.rowcount
    except (OSError, sqlite3.Error):
        return 0


def cache_delete(namespace: str | None = None, target: str | None = None) -> int:
    """Delete cache rows (all when no args; filtered by namespace/target otherwise)."""
    clauses: list[str] = []
    params: list[str] = []
    if namespace is not None:
        clauses.append("namespace = ?")
        params.append(namespace)
    if target is not None:
        clauses.append("target = ?")
        params.append(target)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        with _connect() as conn:
            cur = conn.execute(f"DELETE FROM index_cache {where}", params)
            conn.commit()
            return cur.rowcount
    except (OSError, sqlite3.Error):
        return 0
