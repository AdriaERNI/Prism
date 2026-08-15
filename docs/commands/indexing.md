# prism index

Build a compact, token-efficient index of all classes in an IRIS namespace.

Uses the IRIS `%Dictionary` SQL metadata tables to extract class structure
without fetching source files. This lets AI agents understand a large IRIS
codebase using a fraction of the tokens needed to read every document.

## Usage

```bash
prism index [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--namespace`, `-n` | IRIS namespace to index. Defaults to `IRIS_NAMESPACE`. |
| `--system` | Include system classes (`%Library`, `%SYS`, `%Api`, etc.). |
| `--prefix` | Only index classes starting with this prefix (e.g. `MyApp`). |
| `--summary` | Only show counts (classes, methods, properties). No class details. |
| `--call-graph` | Also build a method-level call graph by reading every in-index class's body. Slow (adds ~20s). Adds `call_edges`, `r_call_edges`, `code_refs` and unresolved-call counts. |

## Examples

### Quick overview

```bash
prism index --summary
```

```json
{
  "namespace": "USER",
  "classes": 6480,
  "methods": 50036,
  "properties": 24456
}
```

### Index all custom classes

```bash
prism index
```

Returns a JSON object with:

- `statistics`: counts of classes, persistent classes, methods, properties, SQL procedures
- `classes`: array of compact class summaries (name, super, properties, methods, parameters, SQL procedures)
- `dependencies`: class → superclass mapping

### Filter by prefix

```bash
prism index --prefix MyApp
```

Only includes classes whose name starts with `MyApp`.

### Include system classes

```bash
prism index --system
```

Includes `%Library.*`, `%SYS.*`, `%Api.*` and other system classes.

## Output shape

```json
{
  "namespace": "USER",
  "statistics": {
    "classes": 179,
    "persistent": 12,
    "methods": 1061,
    "properties": 394,
    "sql_procedures": 9
  },
  "classes": [
    {
      "name": "MyApp.Model",
      "super": "%Persistent",
      "properties": {"Name": "%String", "Age": "%Integer"},
      "methods": {"Save": "%Status", "Load": "MyApp.Model"}
    }
  ],
  "dependencies": {
    "MyApp.Model": "%Persistent"
  },
  "edges": {
    "MyApp.Child": ["MyApp.Base"]
  },
  "r_edges": {
    "MyApp.Base": ["MyApp.Child"]
  },
  "degree": {
    "MyApp.Base": 1
  }
}
```

### Graph maps

Besides `dependencies` (class → superclass string), the index now exposes a
real directed *use* graph:

- **`edges`** — forward map `from → [to...]`: class *from* references class *to*
  via a superclass link, a property type, or a method-signature type.
- **`r_edges`** — reverse map `to → [from...]`: which classes reference *to*.
  This is the impact-analysis direction.
- **`degree`** — `in + out` edge count per class ("most connected classes").

Edges only point at classes that are actually in the index, so references to
excluded system classes (`%Persistent`, `%Library.*`, etc.) are omitted.

### Exclusion correctness

System classes are excluded with anchored `%STARTSWITH` predicates (not the
old unanchored `LIKE` patterns). This excludes every `%`-prefixed class
(`%Library`, `%SYS`, `%Api`), bare `SYS.` / `Api.` prefixes, and InterSystems'
reserved non-`%` system packages — the Ensemble framework (`Ens.`, `EnsLib.`,
`EnsPortal.`, `Ensemble.`), the CSP dashboard (`CSPX.`), and the SQL schema
views (`INFORMATION.`). These ship in every IRIS instance's `USER` namespace and
would otherwise inflate the index with ~1,500 non-user classes. The anchored
predicates no longer silently drop user classes whose names merely contain
`Library.`, `SYS.` or `Api.`.

## Method-level call graph (`--call-graph`)

The metadata index models class *relationships* from declarations (superclass,
property types, signature types). It cannot see what happens *inside method
bodies* — so it cannot answer "who calls this method?". Enable the opt-in `--call-graph`
pass to read every in-index class's body and build a **method-level** call
graph:

```bash
prism index --call-graph
```

This is the slow path (it streams all method bodies; ~+20s on a large
namespace). It is deliberately **not** the default, so `prism index` stays fast
for class lookup, hierarchy and impact queries.

### Output (added to the index)

| Key | Meaning |
|-----|---------|
| `call_edges` | `"Class.method" -> [{"to": "Other.method", "pattern": N}]` — what each method calls |
| `r_call_edges` | reverse map — **who calls this method**. The high-value direction, materialised. |
| `code_refs` / `r_code_refs` | class-level "who references this class" edges from body text (nearly free, falls out of the same scan) |
| `unresolved` | `{method: count}` — call sites seen but not resolvable against the index |
| `stats` | totals: `call_edges`, `code_refs`, `unresolved_calls`, `methods_with_calls` |

Each call edge carries a `pattern` (1-7) identifying the ObjectScript call form
that produced it, so you can apply a confidence distinction (patterns 1–4 are
syntactically certain; 5–7 are heuristics):

| # | Form | Confidence |
|---|------|-----------|
| 1 | `##class(Cls).Method(` | certain |
| 2 | `..Method(` (self / inheritance chain) | certain |
| 3 | `##class(Cls).%New(...).Method(` | certain |
| 4 | `..property.Method(` (property type) | certain |
| 5 | `localVar.Method(` (#Dim / FormalSpec type) | heuristic |
| 6 | `$ClassMethod("Cls","Method")` | heuristic |
| 7 | `$method()` / `..Invoke()` framework dispatch | heuristic |

`unresolved` counts the call sites that could not be resolved (e.g. a call to a
`%`-system method, a call to an unindexed class, or an untyped local variable).
It is the only way to judge how complete the graph is.

### Precision / recall

- **Precision** — every reported caller genuinely contains the call (calls in
  comments and string literals are ignored).
- **Recall** — resolution to a specific method requires the target class to be
  in the index (so `--prefix` narrowing can reduce recall for out-of-prefix
  targets) and the receiver type to be determinable. Recheck `unresolved`
  counts when judging completeness.

## Find who calls a method (`index-callers`)

The `--call-graph` index answers "who calls `Class.Method`?" in bulk (the
`r_call_edges` map). `prism index-callers` is the lightweight, focused way to
ask that one question — it builds the same call graph but returns only the
edges for a single method:

```bash
# Who calls MyApp.Person.Save? (impact analysis before renaming/deleting)
prism index-callers MyApp.Person.Save

# What does Main.Run call?
prism index-callers MyApp.Main.Run --direction forward
```

| Option | Description |
|--------|-------------|
| `method` | The method as `Class.method` (positional, required). |
| `-d, --direction` | `reverse` = who calls this (default); `forward` = what it calls. |
| `-m, --max` | Maximum callers/callees to return (default 50). |
| `--prefix` | Only index classes with this prefix. |
| `--system` | Include system classes in the index. |
| `-n, --namespace` | IRIS namespace to index. |

Each forward result carries the `pattern` (1-7) that produced it, giving a
confidence distinction (patterns 1-4 syntactically certain; 5-7 heuristic).
Callers are only visible when the calling class is inside the index — so a
`--prefix` that narrows the class set also narrows which callers are found.

This is the method-granularity sibling of `index_reachability` (which works on
classes). Both are exposed as MCP tools (`index_callers`, `index_reachability`).

## Token efficiency

The index uses `%Dictionary` SQL metadata — the IRIS compiler's own metadata
tables — so no source files are fetched. Benchmark against IPM (InterSystems
Package Manager, 179 classes):

| Metric | Reading all source | `prism index` | Savings |
|--------|-------------------|---------------|---------|
| Size | ~345K tokens | ~24K tokens | **93%** |
| API calls | ~170 | 5 | **97%** |
| Time | ~30s | 0.64s | **47×** |

## Related

- [MCP tool reference](../mcp/tools.md) — the `index_code` MCP tool
- [`prism sql`](sql.md) — run raw SQL queries against `%Dictionary` tables