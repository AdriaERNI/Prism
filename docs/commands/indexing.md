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
(`%Library`, `%SYS`, `%Api`) plus bare `SYS.` / `Api.` prefixes — and no longer
silently drops user classes whose names merely contain `Library.`, `SYS.` or
`Api.`.

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