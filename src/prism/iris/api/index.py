"""Code indexing API — builds a compact, token-efficient index of IRIS
source code using %Dictionary SQL metadata.

The index includes class hierarchies, methods, properties, SQL projections,
imports, and dependencies — without fetching full source files. This lets AI agents
understand a large IRIS codebase using a fraction of the tokens needed to
read every document.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from prism.iris.sdk.http import api_url, client, parse_json


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
            result["methods"] = {
                m["name"]: m.get("return_type", "") or "" for m in self.methods
            }
        if self.parameters:
            result["parameters"] = {
                p["name"]: p.get("default", "") for p in self.parameters
            }
        if self.sql_procedures:
            result["sql_procs"] = [p["name"] for p in self.sql_procedures]
        if self.imports:
            result["imports"] = self.imports
        return result


# ── Index queries ──────────────────────────────────────────────────────


_CLASSES_QUERY = """SELECT
  Name, Super, ClassType, SqlTableName, Description
FROM %Dictionary.ClassDefinition
WHERE Name NOT LIKE '\\%' AND Name NOT LIKE '%SYS.%'
  AND Name NOT LIKE '%Library.%' AND Name NOT LIKE '%Api.%'
ORDER BY Name"""

_METHODS_QUERY = """SELECT
  Parent->Name AS parent, Name, ReturnType, Description
FROM %Dictionary.MethodDefinition
WHERE Parent->Name NOT LIKE '\\%' AND Parent->Name NOT LIKE '%SYS.%'
  AND Parent->Name NOT LIKE '%Library.%' AND Parent->Name NOT LIKE '%Api.%'
ORDER BY Parent->Name, Name"""

_PROPERTIES_QUERY = """SELECT
  Parent->Name AS parent, Name, Type
FROM %Dictionary.PropertyDefinition
WHERE Parent->Name NOT LIKE '\\%' AND Parent->Name NOT LIKE '%SYS.%'
  AND Parent->Name NOT LIKE '%Library.%' AND Parent->Name NOT LIKE '%Api.%'
ORDER BY Parent->Name, Name"""

_PARAMETERS_QUERY = """SELECT
  Parent->Name AS parent, Name, Default
FROM %Dictionary.ParameterDefinition
WHERE Parent->Name NOT LIKE '\\%' AND Parent->Name NOT LIKE '%SYS.%'
  AND Parent->Name NOT LIKE '%Library.%' AND Parent->Name NOT LIKE '%Api.%'
ORDER BY Parent->Name, Name"""

_SQLPROCS_QUERY = """SELECT
  Parent->Name AS parent, Name
FROM %Dictionary.MethodDefinition
WHERE Parent->Name NOT LIKE '\\%' AND Parent->Name NOT LIKE '%SYS.%'
  AND Parent->Name NOT LIKE '%Library.%' AND Parent->Name NOT LIKE '%Api.%'
  AND SqlProc = 1
ORDER BY Parent->Name, Name"""

_IMPORTS_QUERY = """SELECT
  Parent->Name AS parent, Name
FROM %Dictionary.ImportDefinition
WHERE Parent->Name NOT LIKE '\\%' AND Parent->Name NOT LIKE '%SYS.%'
  AND Parent->Name NOT LIKE '%Library.%' AND Parent->Name NOT LIKE '%Api.%'
ORDER BY Parent->Name, Name"""


async def _run_query(query: str, namespace: str | None = None) -> list[dict]:
    """Execute a SQL query via the Atelier API and return rows."""
    c = client()
    r = await c.post(
        f"{api_url(namespace)}/action/query",
        json={"query": query},
    )
    r.raise_for_status()
    data = parse_json(r)
    content = data.get("result", {}).get("content", [])
    return content if isinstance(content, list) else []


async def build_index(
    namespace: str | None = None,
    include_system: bool = False,
    filter_prefix: str | None = None,
) -> dict:
    """Build a compact index of all classes in the namespace.

    Args:
        namespace: IRIS namespace (defaults to configured).
        include_system: Include system classes (%Library, %SYS, etc.).
        filter_prefix: Only include classes starting with this prefix.

    Returns:
        Index dict with class summaries, statistics, and dependency map.
    """
    # Adjust queries based on options
    class_filter = ""
    if not include_system:
        # Exclude system classes (names starting with %)
        class_filter = (
            "WHERE Name NOT LIKE '\\%%' AND Name NOT LIKE '%SYS.%' "
            "AND Name NOT LIKE '%Library.%' AND Name NOT LIKE '%Api.%'"
        )
    if filter_prefix:
        prefix_filter = f"Name LIKE '{filter_prefix}%'"
        if class_filter:
            class_filter += f" AND {prefix_filter}"
        else:
            class_filter = f"WHERE {prefix_filter}"

    classes_q = f"SELECT Name, Super, ClassType, SqlTableName, Description FROM %Dictionary.ClassDefinition {class_filter} ORDER BY Name"
    methods_q = f"SELECT Parent->Name AS parent, Name, ReturnType FROM %Dictionary.MethodDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {class_filter}) ORDER BY Parent->Name, Name"
    props_q = f"SELECT Parent->Name AS parent, Name, Type FROM %Dictionary.PropertyDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {class_filter}) ORDER BY Parent->Name, Name"
    params_q = f"SELECT Parent->Name AS parent, Name, Default FROM %Dictionary.ParameterDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {class_filter}) ORDER BY Parent->Name, Name"
    sqlprocs_q = f"SELECT Parent->Name AS parent, Name FROM %Dictionary.MethodDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {class_filter}) AND SqlProc = 1 ORDER BY Parent->Name, Name"
    imports_q = f"SELECT Parent->Name AS parent, Name FROM %Dictionary.ImportDefinition WHERE Parent->Name IN (SELECT Name FROM %Dictionary.ClassDefinition {class_filter}) ORDER BY Parent->Name, Name"

    # Run all queries in parallel
    (
        classes_raw,
        methods_raw,
        props_raw,
        params_raw,
        sqlprocs_raw,
        imports_raw,
    ) = await asyncio.gather(
        _run_query(classes_q, namespace),
        _run_query(methods_q, namespace),
        _run_query(props_q, namespace),
        _run_query(params_q, namespace),
        _run_query(sqlprocs_q, namespace),
        _run_query(imports_q, namespace),
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

    # Attach methods
    for row in methods_raw:
        parent = row.get("parent", "")
        if parent in class_map:
            class_map[parent].methods.append(
                {
                    "name": row.get("Name", ""),
                    "return_type": row.get("ReturnType", "") or "",
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
    classes = [
        ci.to_compact() for ci in sorted(class_map.values(), key=lambda x: x.name)
    ]

    # Build statistics
    total_classes = len(classes)
    persistent_classes = sum(
        1 for ci in class_map.values() if "%Persistent" in ci.super
    )
    total_methods = sum(len(ci.methods) for ci in class_map.values())
    total_properties = sum(len(ci.properties) for ci in class_map.values())
    total_sql_procs = sum(len(ci.sql_procedures) for ci in class_map.values())
    total_imports = sum(len(ci.imports) for ci in class_map.values())

    # Build dependency map (class -> superclass)
    dependency_map = {ci.name: ci.super for ci in class_map.values() if ci.super}

    return {
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
    }


async def index_summary(namespace: str | None = None) -> dict:
    """Return a brief summary of the namespace — just counts, no class details.

    Useful for agents to quickly understand the scope of a codebase.
    """
    class_count = await _run_query(
        "SELECT COUNT(*) AS cnt FROM %Dictionary.ClassDefinition WHERE Name NOT LIKE '\\%' AND Name NOT LIKE '%SYS.%' AND Name NOT LIKE '%Library.%' AND Name NOT LIKE '%Api.%'",
        namespace,
    )
    method_count = await _run_query(
        "SELECT COUNT(*) AS cnt FROM %Dictionary.MethodDefinition WHERE Parent->Name NOT LIKE '\\%' AND Parent->Name NOT LIKE '%SYS.%' AND Parent->Name NOT LIKE '%Library.%' AND Parent->Name NOT LIKE '%Api.%'",
        namespace,
    )
    prop_count = await _run_query(
        "SELECT COUNT(*) AS cnt FROM %Dictionary.PropertyDefinition WHERE Parent->Name NOT LIKE '\\\\%' AND Parent->Name NOT LIKE '%SYS.%' AND Parent->Name NOT LIKE '%Library.%' AND Parent->Name NOT LIKE '%Api.%'",
        namespace,
    )
    sqlproc_count = await _run_query(
        "SELECT COUNT(*) AS cnt FROM %Dictionary.MethodDefinition WHERE Parent->Name NOT LIKE '\\\\%' AND Parent->Name NOT LIKE '%SYS.%' AND Parent->Name NOT LIKE '%Library.%' AND Parent->Name NOT LIKE '%Api.%' AND SqlProc = 1",
        namespace,
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
