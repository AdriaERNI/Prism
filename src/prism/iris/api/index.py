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
    """

    async def _one(name: str) -> tuple[str, str | None]:
        try:
            data = await get_document(f"{name}.cls", namespace, target_host, target_port)
            content = data.get("result", {}).get("content", [])
            if isinstance(content, list):
                return name, "\n".join(content)
            return name, None
        except Exception:
            return name, None

    results = await asyncio.gather(*(_one(n) for n in class_names))
    return {name: src for name, src in results if src is not None}


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
