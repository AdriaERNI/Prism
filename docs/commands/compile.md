# prism compile

Compile one or more source documents on the IRIS server. Compilation
generates the runtime artefacts that make a `.cls` usable as an SQL
table, callable class method, or base for other classes.

## Usage

```
prism compile DOCUMENT [DOCUMENT ...] [OPTIONS]
```

## Arguments

| Name | Type | Description |
|------|------|-------------|
| `DOCUMENT` | string (variadic) | One or more document names (e.g. `MyApp.Person.cls`). |

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |
| `--flags` | `IRIS_COMPILE_FLAGS` (default `cuk`) | IRIS compiler flags. |

### Compiler flags

The default `cuk` covers almost every case:

| Flag | Meaning |
|------|---------|
| `c` | **c**ompile |
| `u` | **u**pdate only (skip classes that are already up-to-date) |
| `k` | **k**eep generated source for inspection |
| `b` | compile the whole **b**ranch (all subclasses) |
| `d` | **d**isplay progress on the console |

Combine flags as a single string, no separators: `--flags cub`.

## Output

IRIS's Atelier response includes a `console` list of log lines from the
compiler. On success:

```json
{
  "status": {"errors": [], "summary": ""},
  "console": [
    "",
    "Compilation started on 04/20/2026 18:07:39 with qualifiers 'cuk'",
    "Compiling class MyApp.Hello",
    "Compiling routine MyApp.Hello.1",
    "Compilation finished successfully in 0.046s."
  ],
  "result": {"content": []}
}
```

On failure, `status.errors` has the details and the exit is still `0`
(Prism doesn't re-raise compiler errors; check the JSON):

```json
{
  "status": {
    "errors": [
      {"error": "ERROR #5002: ClassCompiler: Class 'MyApp.Bad' does not exist"}
    ]
  },
  "console": [
    "Compilation started on 04/20/2026 18:08:02 with qualifiers 'cuk'",
    "ERROR #5373: Class MyApp.Bad does not exist.",
    "Compilation failed."
  ]
}
```

## Examples

**Compile one class:**

```powershell
prism compile MyApp.Hello.cls
```

**Compile several in one pass** (faster than one-by-one because IRIS
batches dependency resolution):

```powershell
prism compile MyApp.Hello.cls MyApp.Utils.cls MyApp.Person.cls
```

**Force recompile** (no `u` flag, so every class is recompiled even if
up-to-date):

```powershell
prism compile MyApp.Hello.cls --flags ck
```

**Compile + keep going** across namespaces:

```powershell
prism compile MyApp.Hello.cls --namespace SAMPLES
```

## Related

- [`prism put-doc`](documents.md#put-doc) — upload before compiling.
- [`prism sql`](sql.md) — query compiled classes.
- MCP tool: `compile_documents`, also `put_and_compile` for
  upload-and-compile in one step. See [MCP tools](../mcp/tools.md).
