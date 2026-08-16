"""Code indexing API — builds a compact, token-efficient index of IRIS
source code using %Dictionary SQL metadata.

The index includes class hierarchies, methods, properties, SQL projections,
imports, and dependencies — without fetching full source files. This lets AI agents
understand a large IRIS codebase using a fraction of the tokens needed to
read every document.

The index also exposes a lightweight directed graph (``edges`` / ``r_edges`` /
``degree``) so consumers can answer subclass, impact and reachability queries
without paying for a full source scan.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from dataclasses import dataclass, field

from prism.iris.api.documents import get_document
from prism.iris.indexing.callgraph import build_call_graph
from prism.iris.sdk.http import api_url, client, parse_json

# ── Constants ───────────────────────────────────────────────────────────────
#
# Overall cap for the Tier-2 body-fetch pass. Bounded concurrency + this
# timeout guarantee the call-graph build can never hang forever when a single
# document request stalls on a large namespace.
_FETCH_BODIES_TIMEOUT = 600.0

# ── Input validation ─────────────────────────────────────────────────────────
#
# The Atelier /action/query endpoint accepts a single SQL string and does NOT
# support bind parameters, so user-supplied values interpolated into queries
# must be validated against a strict allowlist of safe identifier characters.

# IRIS class-name prefix: alphanumerics, dots, underscores.  A leading % is
# allowed for system packages (e.g. %SYS).  Wildcards (%, _) in LIKE context
# are rejected by requiring the first char to be a letter or %.
_FILTER_PREFIX_RE = re.compile(r"^[A-Za-z%][A-Za-z0-9._]*$")


def _validate_filter_prefix(prefix: str) -> str:
    """Validate that *prefix* is a safe IRIS class-name prefix for prefix filters.

    Raises ``ValueError`` if *prefix* contains characters outside the
    allowlist (e.g. quotes, semicolons, SQL wildcards used as first char).
    """
    if not isinstance(prefix, str) or not prefix or not _FILTER_PREFIX_RE.match(prefix):
        raise ValueError(f"invalid filter prefix: {prefix!r}")
    return prefix


# ── System-class exclusion ────────────────────────────────────────────────
#
# The class filters used to be written with unanchored LIKE patterns
# ('\%', '%SYS.%', '%Library.%', '%Api.%'), which had two bugs:
#
#   * '\%' alone matched nothing (no ESCAPE clause), so ~4,700 %-prefixed
#     system classes were KEPT despite the intent to drop them; and
#   * the leading '%' in '%SYS.%' / '%Library.%' / '%Api.%' is a wildcard,
#     so the pattern meant "contains anywhere" and silently DROPPED user
#     classes such as AppLibrary.BaseObject.
#
# Anchoring with %STARTSWITH fixes both directions: it matches the class-name
# prefix exactly and needs no escape clause. The predicate is defined once and
# reused by every query so the copies cannot drift apart.


# ObjectScript packages reserved by InterSystems for system classes. These are
# shipped with every IRIS instance and are NOT user code, but unlike the
# `%`-prefixed system classes they do not carry a `%` marker. The Ensemble
# packages (Ens/EnsLib/EnsPortal/Ensemble), the CSP dashboard (CSPX), and the
# SQL schemas (INFORMATION_SCHEMA as INFORMATION) all appear in an ordinary
# USER namespace's %Dictionary.ClassDefinition, and without excluding them
# they pollute the index (statistics.classes, edges, call graph). Measured on
# a 2025.3 Community instance: ~1,570 such classes leaked into what should be
# a user-only index.
#
# `Ens` covers `Ens.*`; `EnsLib.*`, `EnsPortal.*`, `Ensemble.*` are separate
# first-level packages and need their own prefixes (for example Ensemble
# production framework vs its library and portal UI).
_SYSTEM_EXCLUDE = (
    "NOT ({col} %STARTSWITH '%') "
    "AND NOT ({col} %STARTSWITH 'SYS.') "
    "AND NOT ({col} %STARTSWITH 'Api.') "
    "AND NOT ({col} %STARTSWITH 'Ens.') "
    "AND NOT ({col} %STARTSWITH 'EnsLib.') "
    "AND NOT ({col} %STARTSWITH 'EnsPortal.') "
    "AND NOT ({col} %STARTSWITH 'Ensemble.') "
    "AND NOT ({col} %STARTSWITH 'CSPX.') "
    "AND NOT ({col} %STARTSWITH 'INFORMATION.')"
)


def _system_exclude(col: str) -> str:
    """SQL predicate excluding system classes from *col* (a class-name column).

    Excludes everything under ``%`` (which covers ``%Library``, ``%SYS``,
    ``%Api``), bare ``SYS.`` / ``Api.`` names, and InterSystems' reserved
    non-``%`` system packages (``Ens*``, ``EnsLib.*``, ``EnsPortal.*``,
    ``Ensemble.*``, ``CSPX.*``, ``INFORMATION.*``).
    """
    return _SYSTEM_EXCLUDE.format(col=col)


def _class_filter(include_system: bool, filter_prefix: str | None) -> str:
    """Build the SQL WHERE clause (or ``''``) for build_index queries.

    Excludes system classes unless *include_system*, and optionally restricts
    to *filter_prefix*. The clause filters on the column alias ``Name`` (the
    inner class-select's column), so it can be embedded directly in the
    ``Parent->Name IN (SELECT Name FROM ...)`` subqueries too.
    """
    clauses: list[str] = []
    if not include_system:
        clauses.append(_system_exclude("Name"))
    if filter_prefix:
        _validate_filter_prefix(filter_prefix)
        clauses.append(f"Name %STARTSWITH '{filter_prefix}'")
    if not clauses:
        return ""
    return "WHERE " + " AND ".join(clauses)


# ── Data structures ──────────────────────────────────────────────────────


@dataclass
class ClassInfo:
    name: str
    super: str = ""
    class_type: str = ""
    sql_table: str = ""
    description: str = ""
    properties: list[dict] = field(default_factory=list)
    methods: list[dict] = field(default_factory=list)
    parameters: list[dict] = field(default_factory=list)
    sql_procedures: list[dict] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def to_compact(self) -> dict:
        """Return a compact dict representation for the index."""
        result: dict = {"name": self.name}
        if self.super:
            result["super"] = self.super
        if self.description:
            # Truncate description to first sentence
            desc = self.description.split(".")[0].strip()
            if desc:
                result["desc"] = desc[:200]
        if self.sql_table:
            result["sql_table"] = self.sql_table
        if self.properties:
            result["properties"] = {p["name"]: p["type"] for p in self.properties}
        if self.methods:
            result["methods"] = {m["name"]: m.get("return_type", "") or "" for m in self.methods}
        if self.parameters:
            result["parameters"] = {p["name"]: p.get("default", "") for p in self.parameters}
        if self.sql_procedures:
            result["sql_procs"] = [p["name"] for p in self.sql_procedures]
        if self.imports:
            result["imports"] = self.imports
        return result


# ── Graph / parsing helpers ───────────────────────────────────────────────


def _split_supers(super_str: str) -> list[str]:
    """Split a ``Super`` string (a comma-separated list) into individual names."""
    return [s.strip() for s in (super_str or "").split(",") if s.strip()]


def _extract_signature_types(formal_spec: str) -> list[str]:
    """Return non-system type names referenced in a method ``FormalSpec``.

    FormalSpec is a comma-separated parameter list, e.g.
    ``"pArg1 As %String, pArg2 As MyApp.Model = 1"``.  We pull every
    ``As <Type>`` token and keep types that are not ``%``-prefixed (they are
    the ones that can be application-class references and thus real edges).
    """
    types: list[str] = []
    for m in re.finditer(r"\bAs\s+([%A-Za-z][\w.]*)", formal_spec or ""):
        t = m.group(1).rstrip(".")
        if not t.startswith("%"):
            types.append(t)
    return types


def _edge_maps(
    class_map: dict[str, ClassInfo],
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, int]]:
    """Build forward/reverse edge maps and a degree map from the class set.

    Edges are directed *usage* edges ``from -> to`` meaning "class *from*
    references class *to*". Sources:

      * superclass list (``Class extends Base``)
      * property types (``Property Foo As MyApp.Model``)
      * method signature types (``Method Bar(p As MyApp.Model)``)

    Edges only ever point at classes that are actually in the index, so
    ``-> %Persistent`` style edges to excluded system classes are omitted.
    """
    edges: dict[str, list[str]] = {}
    r_edges: dict[str, list[str]] = {}

    def _add(frm: str, to: str) -> None:
        if frm in class_map and to in class_map and frm != to and to not in edges.get(frm, []):
            edges.setdefault(frm, []).append(to)
            r_edges.setdefault(to, []).append(frm)

    for ci in class_map.values():
        for sup in _split_supers(ci.super):
            _add(ci.name, sup)
        for p in ci.properties:
            t = p["type"].strip()
            if t and not t.startswith("%"):
                _add(ci.name, t)
        for m in ci.methods:
            for sig_t in m.get("signature_types", []):
                _add(ci.name, sig_t)

    degree = {
        cls: len(edges.get(cls, [])) + len(r_edges.get(cls, []))
        for cls in set(edges) | set(r_edges)
    }
    return edges, r_edges, degree


def reachable(edges: dict[str, list[str]], start: str, max_hops: int = 3) -> dict[str, int]:
    """BFS over the forward edge map from *start*, up to *max_hops*.

    Returns ``{reachable_class: shortest_distance}`` (including *start* at
    distance 0 when it has edges). Use for reachability / n-hop impact and
    shortest-path questions against an ``edges`` map.
    """
    if start not in edges or max_hops <= 0:
        return {start: 0} if start in edges else {}
    dist = {start: 0}
    q: deque[str] = deque([start])
    while q:
        node = q.popleft()
        if dist[node] >= max_hops:
            continue
        for nb in edges.get(node, []):
            if nb not in dist:
                dist[nb] = dist[node] + 1
                q.append(nb)
    return dist


# ── Index build ──────────────────────────────────────────────────────────


async def _run_query(
    query: str,
    namespace: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> list[dict]:
    """Execute a SQL query via the Atelier API and return rows."""
    c = client(target_host=target_host, target_port=target_port)
    r = await c.post(
        f"{api_url(namespace, target_host, target_port)}/action/query",
        json={"query": query},
    )
    r.raise_for_status()
    data = parse_json(r)
    content = data.get("result", {}).get("content", [])
    return content if isinstance(content, list) else []


async def _fetch_bodies(
    class_names: list[str],
    namespace: str | None,
    target_host: str | None,
    target_port: int | None,
) -> dict[str, str]:
    """Fetch the full source of each class in *class_names* in parallel.

    Returns ``{class_name: source_text}``. Classes whose document fetch fails
    (e.g. a generated class with no stored source, a 404) are skipped — their
    call-site contributions are simply absent, which is a bounded, visible
    gap rather than a hard failure.

    Concurrency is bounded by a semaphore and the whole pass is wrapped in a
    timeout so a single stuck document request (a slow IRIS, a stalled
    connection) can NEVER block the call-graph build forever. Without this,
    an unbounded ``asyncio.gather`` over thousands of bodies would saturate
    the shared httpx connection pool and hang indefinitely when one request
    stalls — the "prism never finishes the call graph" failure on large
    namespaces.
    """

    # Bounded concurrency: keep requests well under the shared httpx pool's
    # connection limit so none queue behind it for minutes.
    sem = asyncio.Semaphore(16)

    async def _one(name: str) -> tuple[str, str | None]:
        async with sem:
            try:
                data = await get_document(f"{name}.cls", namespace, target_host, target_port)
                content = data.get("result", {}).get("content", [])
                if isinstance(content, list):
                    return name, "\n".join(content)
                return name, None
            except Exception:
                return name, None

    # Overall cap on the whole body pass. On timeout we return whatever
    # completed so far — the call graph is built over a partial body set
    # rather than hanging indefinitely.
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(_one(n) for n in class_names), return_exceptions=True),
            timeout=_FETCH_BODIES_TIMEOUT,
        )
    except TimeoutError:
        return {}

    bodies: dict[str, str] = {}
    for r in results:
        # Individual _one errors are already swallowed (name, None); this
        # also guards any exception object that slips through.
        if isinstance(r, tuple) and len(r) == 2 and isinstance(r[1], str):
            bodies[r[0]] = r[1]
    return bodies


def _to_call_graph_dict(cg) -> dict:
    """Convert a :class:`CallGraph` into a compact, JSON-serialisable dict."""
    methods_with_calls = sum(1 for k in cg.r_call_edges if "." in k)
    return {
        "call_edges": dict(sorted(cg.call_edges.items())),
        "r_call_edges": {k: sorted(v) for k, v in sorted(cg.r_call_edges.items())},
        "code_refs": {k: sorted(v) for k, v in sorted(cg.code_refs.items())},
        "r_code_refs": {k: sorted(v) for k, v in sorted(cg.r_code_refs.items())},
        "unresolved": dict(sorted(cg.unresolved.items())),
        "stats": {
            "call_edges": cg.edge_count,
            "code_refs": cg.ref_count,
            "unresolved_calls": cg.unresolved_count,
            "methods_with_calls": methods_with_calls,
        },
    }


async def build_index(
    namespace: str | None = None,
    include_system: bool = False,
    filter_prefix: str | None = None,
    include_call_graph: bool = False,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """Build a compact index of all classes in the namespace.

    Args:
        namespace: IRIS namespace (defaults to configured).
        include_system: Include system classes (%Library, %SYS, etc.).
        filter_prefix: Only include classes starting with this prefix.
        include_call_graph: Also read method bodies and build a method-level
            call graph (Tier 2). This is opt-in and significantly slower — it
            fetches every in-index class's source. When False (default), only
            the fast %Dictionary path runs.

    Returns:
        Index dict with class summaries, statistics, a dependency map, and
        graph maps (``edges``, ``r_edges``, ``degree``). When
        *include_call_graph* is set, the dict also carries ``call_edges``,
        ``r_call_edges``, ``call_stats``, ``code_refs`` and ``unresolved``.
    """
    # Build the class filter once and reuse it across all six queries so the
    # system-exclusion predicate cannot drift apart between them.
    where = _class_filter(include_system, filter_prefix)

    classes_q = f"SELECT Name, Super, ClassType, SqlTableName, Description FROM %Dictionary.ClassDefinition {where} ORDER BY Name"
    methods_q = (
        "SELECT Parent->Name AS parent, Name, ReturnType, FormalSpec "
        f"FROM %Dictionary.MethodDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {where}) "
        "ORDER BY Parent->Name, Name"
    )
    props_q = f"SELECT Parent->Name AS parent, Name, Type FROM %Dictionary.PropertyDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {where}) ORDER BY Parent->Name, Name"
    params_q = f"SELECT Parent->Name AS parent, Name, Default FROM %Dictionary.ParameterDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {where}) ORDER BY Parent->Name, Name"
    sqlprocs_q = f"SELECT Parent->Name AS parent, Name FROM %Dictionary.MethodDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {where}) AND SqlProc = 1 ORDER BY Parent->Name, Name"
    imports_q = f"SELECT Parent->Name AS parent, Name FROM %Dictionary.ImportDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {where}) ORDER BY Parent->Name, Name"

    # Run all queries in parallel
    (
        classes_raw,
        methods_raw,
        props_raw,
        params_raw,
        sqlprocs_raw,
        imports_raw,
    ) = await asyncio.gather(
        _run_query(classes_q, namespace, target_host, target_port),
        _run_query(methods_q, namespace, target_host, target_port),
        _run_query(props_q, namespace, target_host, target_port),
        _run_query(params_q, namespace, target_host, target_port),
        _run_query(sqlprocs_q, namespace, target_host, target_port),
        _run_query(imports_q, namespace, target_host, target_port),
    )

    # Build class info objects
    class_map: dict[str, ClassInfo] = {}
    for row in classes_raw:
        name = row.get("Name", "")
        if not name:
            continue
        class_map[name] = ClassInfo(
            name=name,
            super=row.get("Super", "") or "",
            class_type=row.get("ClassType", "") or "",
            sql_table=row.get("SqlTableName", "") or "",
            description=row.get("Description", "") or "",
        )

    # Attach methods (incl. FormalSpec for signature-type edges)
    for row in methods_raw:
        parent = row.get("parent", "")
        if parent in class_map:
            class_map[parent].methods.append(
                {
                    "name": row.get("Name", ""),
                    "return_type": row.get("ReturnType", "") or "",
                    "signature_types": _extract_signature_types(row.get("FormalSpec", "") or ""),
                }
            )

    # Attach properties
    for row in props_raw:
        parent = row.get("parent", "")
        if parent in class_map:
            class_map[parent].properties.append(
                {"name": row.get("Name", ""), "type": row.get("Type", "") or ""}
            )

    # Attach parameters
    for row in params_raw:
        parent = row.get("parent", "")
        if parent in class_map:
            class_map[parent].parameters.append(
                {"name": row.get("Name", ""), "default": row.get("Default", "") or ""}
            )

    # Attach SQL procedures
    for row in sqlprocs_raw:
        parent = row.get("parent", "")
        if parent in class_map:
            class_map[parent].sql_procedures.append({"name": row.get("Name", "")})

    # Attach imports
    for row in imports_raw:
        parent = row.get("parent", "")
        if parent in class_map:
            class_map[parent].imports.append(row.get("Name", ""))

    # Build compact index
    classes = [ci.to_compact() for ci in sorted(class_map.values(), key=lambda x: x.name)]

    # Build statistics
    total_classes = len(classes)
    persistent_classes = sum(1 for ci in class_map.values() if "%Persistent" in ci.super)
    total_methods = sum(len(ci.methods) for ci in class_map.values())
    total_properties = sum(len(ci.properties) for ci in class_map.values())
    total_sql_procs = sum(len(ci.sql_procedures) for ci in class_map.values())
    total_imports = sum(len(ci.imports) for ci in class_map.values())

    # Build dependency map (class -> superclass) for backward compatibility
    dependency_map = {ci.name: ci.super for ci in class_map.values() if ci.super}

    # Build graph maps
    edges, r_edges, degree = _edge_maps(class_map)

    result: dict = {
        "namespace": namespace or "USER",
        "statistics": {
            "classes": total_classes,
            "persistent": persistent_classes,
            "methods": total_methods,
            "properties": total_properties,
            "sql_procedures": total_sql_procs,
            "imports": total_imports,
        },
        "classes": classes,
        "dependencies": dependency_map,
        "edges": edges,
        "r_edges": r_edges,
        "degree": degree,
    }

    # Tier 2 — optional method-level call graph. Read each in-index class's
    # body and resolve the seven ObjectScript call forms. This is the slow,
    # opt-in path (the ~+20s pass) and is only performed when requested.
    if include_call_graph:
        sources = await _fetch_bodies(list(class_map), namespace, target_host, target_port)
        cg = build_call_graph(class_map, sources)
        result["call_graph"] = _to_call_graph_dict(cg)

    return result


async def index_summary(
    namespace: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """Return a brief summary of the namespace — just counts, no class details.

    Useful for agents to quickly understand the scope of a codebase.
    """
    # Reuse the shared system-exclusion predicate (on the parent class column).
    excl = _system_exclude("Parent->Name")
    class_count = await _run_query(
        f"SELECT COUNT(*) AS cnt FROM %Dictionary.ClassDefinition WHERE {_system_exclude('Name')}",
        namespace,
        target_host,
        target_port,
    )
    method_count = await _run_query(
        f"SELECT COUNT(*) AS cnt FROM %Dictionary.MethodDefinition WHERE {excl}",
        namespace,
        target_host,
        target_port,
    )
    prop_count = await _run_query(
        f"SELECT COUNT(*) AS cnt FROM %Dictionary.PropertyDefinition WHERE {excl}",
        namespace,
        target_host,
        target_port,
    )
    sqlproc_count = await _run_query(
        f"SELECT COUNT(*) AS cnt FROM %Dictionary.MethodDefinition WHERE {excl} AND SqlProc = 1",
        namespace,
        target_host,
        target_port,
    )

    def _get_count(rows):
        if rows and isinstance(rows, list) and rows[0]:
            return list(rows[0].values())[0]
        return 0

    return {
        "namespace": namespace or "USER",
        "classes": _get_count(class_count),
        "methods": _get_count(method_count),
        "properties": _get_count(prop_count),
        "sql_procedures": _get_count(sqlproc_count),
    }


# ── Fingerprint (TimeChanged) ─────────────────────────────────────────────


def _fingerprint(rows: list[dict]) -> str:
    """Return a stable change-detector hash over ordered ``TimeChanged`` values.

    ``%Dictionary.ClassDefinition.TimeChanged`` is a ``$horolog`` string that
    changes whenever a class definition is edited or recompiled, so a hash of
    the ordered values is an exact "has anything in the indexed scope changed"
    check. Rows without a usable value are hashed as empty strings so a
    missing value can never mask a change.
    """
    import hashlib

    digest = hashlib.sha256()
    for row in rows:
        digest.update(str(row.get("TimeChanged", "")).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _index_target(
    include_system: bool = False,
    filter_prefix: str | None = None,
    include_call_graph: bool = False,
) -> str:
    """Return the cache-target key for a build_index argument set.

    The target identifies *which* index a cache row belongs to — the same
    arguments always map to the same target, and different arguments map to
    different targets, so ``(namespace, target)`` is a unique cache key.

    ``include_call_graph`` is part of the key: a Tier-2 (call-graph) index is a
    strictly larger payload than the fast metadata-only index, and without it
    in the key a fast build would wrongly serve (or be served to) an
    ``include_call_graph`` query — silently missing call edges.
    """
    parts = ["all"] if not filter_prefix else [f"prefix:{filter_prefix}"]
    if include_system:
        parts.append("system")
    if include_call_graph:
        parts.append("callgraph")
    return ":".join(parts)


# ── Cache-aware index access ──────────────────────────────────────────────


async def get_index(
    namespace: str | None = None,
    include_system: bool = False,
    filter_prefix: str | None = None,
    include_call_graph: bool = False,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """Return a build_index result, serving a fresh local cache hit when possible.

    Existence is decided by a ``%Dictionary.ClassDefinition TimeChanged``
    fingerprint (one fast SQL query). When a cached index for the same
    ``(namespace, target, fingerprint)`` exists it is returned instantly
    (no method-body round-trips); otherwise the index is built and persisted
    so repeated queries are near-instant.

    The fingerprint covers the class *scope* only. When *include_call_graph*
    is True, the fingerprint must also detect a change in any *body* (a method
    edit updates ``TimeChanged`` too), so the same check remains exact.
    """
    fp_q = (
        "SELECT Name, TimeChanged FROM %Dictionary.ClassDefinition "
        f"{_class_filter(include_system, filter_prefix)} ORDER BY Name"
    )

    rows = await _run_query(fp_q, namespace, target_host, target_port)
    fingerprint = _fingerprint(rows)
    target = _index_target(include_system, filter_prefix, include_call_graph)

    from prism.iris.indexing.cache import cache_load

    cached = cache_load(namespace or "USER", target, fingerprint)
    if cached is not None:
        cached["cached"] = True
        return cached

    index = await build_index(
        namespace=namespace,
        include_system=include_system,
        filter_prefix=filter_prefix,
        include_call_graph=include_call_graph,
        target_host=target_host,
        target_port=target_port,
    )
    from prism.iris.indexing.cache import cache_put

    cache_put(namespace or "USER", target, fingerprint, index)
    index["cached"] = False
    return index


# ── Symbol search (server-side %Dictionary SQL) ───────────────────────────


def _is_safe_search_text(text: str) -> bool:
    """Allow only identifier characters (letters, digits, underscore, dot, %)."""
    return not text or bool(re.fullmatch(r"[A-Za-z0-9_%.]+", text) and not text.endswith("."))


def _search_query_unsafe(term: str) -> str | None:
    """Return None (safe) or a message when *term* could inject SQL.

    Values are interpolated into SQL text (the Atelier /action/query endpoint
    does not support bind parameters), so anything outside the identifier
    allowlist is rejected up-front.
    """
    if not _is_safe_search_text(term):
        return "search term must contain only letters, digits, underscore, dot or %"
    return None


async def search_symbols(
    query: str,
    kind: str | None = None,
    limit: int = 50,
    exact: bool = False,
    namespace: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """Server-side SQL symbol search across class / method / property names.

    The IRIS ``%Dictionary`` tables are queried directly (the fast metadata
    path — tens of ms) for class names, method names, property names and
    ``SqlTableName``. Supports exact matches (fastest), ``%STARTSWITH`` prefix
    matches, and a whole-word fallback when a term contains a dot or is too
    short for a useful prefix scan.

    Args:
        query: Term to search. Exact-name hits rank first, then prefix hits,
            then whole-word contains (when applicable).
        kind: Restrict to ``class``, ``method``, ``property`` or ``table``.
        limit: Maximum results returned (1..200).
        exact: Only return exact-name matches (the fastest path).
        namespace: IRIS namespace (defaults to configured).

    Returns:
        ``{query, kind, exact, count, results: [{kind, symbol, owner, detail}]}``
    """
    err = _search_query_unsafe(query)
    if err:
        return {
            "query": query,
            "kind": kind,
            "exact": exact,
            "count": 0,
            "results": [],
            "error": err,
        }

    limit = max(1, min(limit, 200))

    if kind not in {None, "class", "method", "property", "table"}:
        return {
            "query": query,
            "kind": kind,
            "exact": exact,
            "count": 0,
            "results": [],
            "error": "kind must be one of: class, method, property, table",
        }

    # -- Build the per-kind SELECT blocks with the term as a literal -------
    # The Atelier /action/query endpoint has no bind support, so the (already
    # validated, identifier-char only) term is interpolated directly.
    lit = f"'{query}'"

    def _class_block(cond: str) -> str:
        return (
            f"SELECT 'class' AS kind, Name AS symbol, '' AS owner, "
            f"COALESCE(SqlTableName,'') AS detail, 0 AS rnk "
            f"FROM %Dictionary.ClassDefinition WHERE {cond}"
        )

    def _method_block(cond: str) -> str:
        return (
            f"SELECT 'method' AS kind, Name AS symbol, Parent->Name AS owner, "
            f"COALESCE(ReturnType,'') AS detail, 1 AS rnk "
            f"FROM %Dictionary.MethodDefinition WHERE {cond}"
        )

    def _property_block(cond: str) -> str:
        return (
            f"SELECT 'property' AS kind, Name AS symbol, Parent->Name AS owner, "
            f"COALESCE(Type,'') AS detail, 2 AS rnk "
            f"FROM %Dictionary.PropertyDefinition WHERE {cond}"
        )

    def _table_block(cond: str) -> str:
        return (
            f"SELECT 'table' AS kind, SqlTableName AS symbol, Name AS owner, "
            f"'' AS detail, 3 AS rnk "
            f"FROM %Dictionary.ClassDefinition WHERE {cond}"
        )

    # Each kind runs its own query with a server-side TOP cap (no ORDER BY /
    # LIMIT — IRIS returns 0 rows for ``ORDER BY <computed alias> LIMIT``).
    # The filter lives inside each block's WHERE; the outer select only caps
    # per-kind rows. Ranking and slicing happen in Python below.
    cond_exprs: dict[str, str] = {
        "class": ("Name = " + lit if exact else "Name %STARTSWITH " + lit),
        "method": ("Name = " + lit if exact else "Name %STARTSWITH " + lit),
        "property": ("Name = " + lit if exact else "Name %STARTSWITH " + lit),
        "table": ("SqlTableName = " + lit if exact else "SqlTableName %STARTSWITH " + lit),
    }
    builders = {
        "class": _class_block,
        "method": _method_block,
        "property": _property_block,
        "table": _table_block,
    }
    if not query.isalnum() and "." not in query:
        # Whole-word contains fallback for short terms where a prefix scan
        # would be too restrictive.
        for k in cond_exprs:
            cond_exprs[k] = cond_exprs[k].replace(
                "Name %STARTSWITH " + lit, "Name LIKE " + f"'%{query}%'"
            )
        cond_exprs["table"] = "SqlTableName LIKE " + f"'%{query}%'"

    kinds = [None, "class", "method", "property", "table"]
    picked = (
        (["class", "method", "property", "table"] if kind is None else [kind])
        if kind in kinds
        else []
    )

    if not picked:
        return {
            "query": query,
            "kind": kind,
            "exact": exact,
            "count": 0,
            "results": [],
            "error": "kind must be one of: class, method, property, table",
        }

    queries = [f"SELECT TOP {limit} * FROM ({builders[k](cond_exprs[k])}) AS t" for k in picked]

    rowsets = await asyncio.gather(
        *(_run_query(q, namespace, target_host, target_port) for q in queries)
    )

    # Merge, rank (kind order: class=0, method=1, property=2, table=3), then
    # stable-sort by (rank, symbol) and slice to the requested limit.
    merged: list[dict] = []
    rank = {"class": 0, "method": 1, "property": 2, "table": 3}
    for rows in rowsets:
        for r in rows:
            merged.append(
                {
                    "kind": r.get("kind", ""),
                    "symbol": r.get("symbol", ""),
                    "owner": r.get("owner", "") or "",
                    "detail": r.get("detail", "") or "",
                    "rnk": rank.get(r.get("kind", ""), 99),
                }
            )
    merged.sort(key=lambda r: (r["rnk"], r["symbol"]))
    # Dedupe exact (kind, symbol, owner) rows — a method with the same name
    # on the same parent can appear once per matching kind query.
    seen: set[tuple] = set()
    unique: list[dict] = []
    for r in merged:
        key = (r["kind"], r["symbol"], r["owner"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    results = [
        {
            "kind": r["kind"],
            "symbol": r["symbol"],
            "owner": r["owner"].replace("\x00", ""),
            "detail": r["detail"].replace("\x00", ""),
        }
        for r in unique[:limit]
    ]

    return {
        "query": query,
        "kind": kind,
        "exact": exact,
        "count": len(results),
        "results": results,
    }


# ── Index node (full picture of one class) ────────────────────────────────


def _split(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _method_signature(m) -> dict:
    """Expand a compact method entry into a signature dict for index_node.

    The compact index stores methods as ``{name: return_type}`` (string
    values); the full ClassInfo keeps ``{name, return_type, signature_types}``
    lists. Both shapes are accepted.
    """
    if isinstance(m, str):
        return {"name": "", "return_type": m, "signature_types": []}
    return {
        "name": m.get("name", ""),
        "return_type": m.get("return_type", ""),
        "signature_types": m.get("signature_types", []),
    }


def class_node(index: dict, class_name: str) -> dict:
    """Assemble the focused 'full picture' of one class from an index dict.

    Pure assembly over the existing maps: base info from ``classes``, child
    classes from ``r_edges``, callers from ``r_call_edges``, callees from
    ``call_edges``, body references from ``code_refs``, and connectivity from
    ``degree``. Returns a flat dict, or a ``{"error": ...}`` dict when the
    class is not part of the index.
    """
    matched = [c for c in index.get("classes", []) if c.get("name") == class_name]
    if not matched:
        return {"error": f"class {class_name!r} not in index"}
    info = matched[0]

    # Children: reverse structural edges (what references/extends this class).
    children: list[str] = sorted(index.get("r_edges", {}).get(class_name, []))

    # The call-graph maps live under the ``call_graph`` key (Tier 2). Fall
    # back to top-level keys for indexes that carry them flat.
    cg = index.get("call_graph", {}) or {}
    r_call_edges = cg.get("r_call_edges", {}) or index.get("r_call_edges", {}) or {}
    call_edges = cg.get("call_edges", {}) or index.get("call_edges", {}) or {}

    # Callers of this class's methods. Group *all* reverse call-graph edges
    # whose key is ``Class.<method>`` — including methods inherited from
    # out-of-index system supers (e.g. ``%New``) that are not declared on the
    # class itself, so the picture is complete.
    prefix = f"{class_name}."
    callers: dict[str, list[str]] = {}
    for key, srcs in r_call_edges.items():
        if key.startswith(prefix):
            method = key[len(prefix) :]
            callers.setdefault(method, [])
            callers[method].extend(srcs)
    callers = {m: sorted(set(s)) for m, s in callers.items() if s}

    # Callees of this class's methods, likewise from the full forward map.
    callees: dict[str, list[str]] = {}
    for key, edges in call_edges.items():
        if key.startswith(prefix):
            method = key[len(prefix) :]
            tgt = [e.get("to") if isinstance(e, dict) else str(e) for e in edges]
            callees.setdefault(method, [])
            callees[method].extend(t for t in tgt if t)
    callees = {m: sorted(set(s)) for m, s in callees.items() if s}

    refs = sorted(index.get("code_refs", {}).get(class_name, []))
    degree = index.get("degree", {}).get(class_name, 0)
    out_degree = len(index.get("edges", {}).get(class_name, []))

    raw_methods = info.get("methods", {})
    if isinstance(raw_methods, dict):
        methods = {name: _method_signature(sig) for name, sig in raw_methods.items()}
    else:
        methods = {m.get("name", ""): _method_signature(m) for m in raw_methods}

    node: dict = {
        "name": class_name,
        "super": info.get("super", ""),
        "class_type": info.get("class_type", ""),
        "sql_table": info.get("sql_table", ""),
        "description": info.get("desc", ""),
        "methods": methods,
        "properties": info.get("properties", {}),
        "parameters": info.get("parameters", {}),
        "supers": _split(info.get("super", "")),
        "children": children,
        "callers": callers,
        "callees": callees,
        "code_refs": refs,
        "degree": degree,
        "out_degree": out_degree,
    }
    return node


def _class_in_index(index: dict, class_name: str) -> bool:
    """Return True when *class_name* is one of the indexed class summaries."""
    return any(c.get("name") == class_name for c in index.get("classes", []))


def class_refs(index: dict, class_name: str) -> dict:
    """Who references *class_name* in method bodies (r_code_refs, already computed).

    Returns the referencing classes, a count, and a ``found`` flag. The
    ``r_code_refs`` map lives under the ``call_graph`` key (Tier 2) with a
    top-level fallback.
    """
    cg = index.get("call_graph", {}) or {}
    r_code_refs = cg.get("r_code_refs", {}) or index.get("r_code_refs", {}) or {}
    refs = sorted(r_code_refs.get(class_name, []))
    return {
        "target": class_name,
        "found": _class_in_index(index, class_name) or bool(refs),
        "count": len(refs),
        "referenced_by": refs,
    }


def method_impact(index: dict, method: str, max_hops: int | None = None) -> dict:
    """Transitive blast radius of a method over the built call graph.

    Uses :func:`prism.iris.indexing.callgraph.impact_analysis` over the
    materialised ``r_call_edges`` and structural ``r_edges``. *method* may be
    ``'Class.method'`` (method-level) or a bare ``'Class'``.
    """
    from prism.iris.indexing.callgraph import impact_analysis

    cg = index.get("call_graph", {})
    r_call_edges = cg.get("r_call_edges", {}) or {}
    result = impact_analysis(r_call_edges, index.get("r_edges", {}), method, max_hops)
    # Only report method-level dependents that carry a method part.
    method_nodes = sorted(
        (n for n in result["hops"] if "." in n and n != method),
        key=lambda n: (result["hops"][n], n),
    )
    result["methods"] = method_nodes
    return result


def method_path(index: dict, source: str, target: str) -> dict:
    """Shortest method-to-method path via BFS predecessor tracking.

    Uses :func:`prism.iris.indexing.callgraph.shortest_path` over the merged
    call graph. Endpoints may be ``'Class.method'`` or bare ``'Class'``.
    """
    from prism.iris.indexing.callgraph import shortest_path

    cg = index.get("call_graph", {})
    return shortest_path(
        cg.get("call_edges", {}) or {},
        cg.get("r_call_edges", {}) or {},
        index.get("r_edges", {}) or {},
        source,
        target,
    )


async def index_status(
    namespace: str | None = None,
    include_system: bool = False,
    filter_prefix: str | None = None,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """Report cache freshness / counts / age for the index scope.

    Computes the current ``TimeChanged`` fingerprint (one fast SQL query),
    compares it with the persisted cache entry, and reports the class count,
    cache age, whether the entry is fresh, and a refresh flag. Passing
    ``refresh=True`` on the tool rebuilds and re-persists the index.
    """
    from prism.iris.indexing.cache import (
        cache_is_fresh,
        cache_status,
    )

    target = _index_target(include_system, filter_prefix)
    ns = namespace or "USER"

    rows = await _run_query(
        f"SELECT Name, TimeChanged FROM %Dictionary.ClassDefinition "
        f"{_class_filter(include_system, filter_prefix)} ORDER BY Name",
        namespace,
        target_host,
        target_port,
    )
    fingerprint = _fingerprint(rows)

    entries = cache_status(ns, target)
    cached = entries[0] if entries else None
    fresh = bool(cached is not None and cache_is_fresh(ns, target, fingerprint))

    result: dict = {
        "namespace": ns,
        "target": target,
        "classes": len(rows),
        "fresh": fresh,
        "cached": cached is not None,
    }
    if cached is not None:
        result["age_seconds"] = cached["age_seconds"]
        result["built_at"] = cached["built_at"]
    return result


async def refresh_index(
    namespace: str | None = None,
    include_system: bool = False,
    filter_prefix: str | None = None,
    include_call_graph: bool = False,
    target_host: str | None = None,
    target_port: int | None = None,
) -> dict:
    """Force a cache refresh: rebuild + re-persist the index for the scope."""
    from prism.iris.indexing.cache import cache_put, cache_remove

    ns = namespace or "USER"
    target = _index_target(include_system, filter_prefix, include_call_graph)

    rows = await _run_query(
        f"SELECT Name, TimeChanged FROM %Dictionary.ClassDefinition "
        f"{_class_filter(include_system, filter_prefix)} ORDER BY Name",
        namespace,
        target_host,
        target_port,
    )
    fingerprint = _fingerprint(rows)

    cache_remove(ns, target)
    index = await build_index(
        namespace=namespace,
        include_system=include_system,
        filter_prefix=filter_prefix,
        include_call_graph=include_call_graph,
        target_host=target_host,
        target_port=target_port,
    )
    cache_put(ns, target, fingerprint, index)
    index["cached"] = False
    return index
