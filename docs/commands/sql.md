# prism sql

Run an InterSystems SQL query and print the raw Atelier response as JSON.
Supports `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`, DDL, and
`CALL` for stored procedures (`[SqlProc]` class methods).

## Usage

```
prism sql "<QUERY>" [OPTIONS]
```

## Arguments

| Name | Type | Description |
|------|------|-------------|
| `QUERY` | string | The SQL statement to execute. Quote it so your shell doesn't interpret it. |

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |

## Output

The raw Atelier REST response, wrapping the result rows inside
`result.content`:

```json
{
  "status": {"errors": [], "summary": ""},
  "console": [],
  "result": {
    "content": [
      {"ID": 1, "Name": "Alice", "Age": 30},
      {"ID": 2, "Name": "Bob", "Age": 25}
    ]
  }
}
```

For `INSERT`, `UPDATE`, `DELETE`, and DDL statements, `result.content`
is typically an empty list. Errors from IRIS are returned inline as part
of `status.errors`:

```json
{
  "status": {
    "errors": [
      {
        "error": "ERROR #5540: SQLCODE: -30 Table 'SQLUSER.NOPE' not found",
        "code": 5540
      }
    ]
  },
  "result": {"content": []}
}
```

## Examples

**Basic `SELECT` with `%ID`.** Every persistent class has an
auto-generated row ID — use `%ID` to retrieve it:

```powershell
prism sql "SELECT TOP 5 %ID, Name, Age FROM MyApp.Person WHERE Age > 30"
```

**Namespace override.** Query a different namespace without changing
your saved settings:

```powershell
prism sql "SELECT TOP 1 Name FROM %Dictionary.ClassDefinition" --namespace %SYS
```

**`INSERT`.** Dot/single quoting matters — use single quotes around
the string literal inside the SQL, and double quotes around the whole
argument:

```powershell
prism sql "INSERT INTO MyApp.Person (Name, Age) VALUES ('Alice', 30)"
```

**`CALL` a stored procedure.** ObjectScript class methods marked
`[SqlProc]` are exposed as SQL functions using the
`Package.Class_Method` naming convention:

```powershell
prism sql "CALL MyApp.Utils_Greet('Prism')"
```

**DDL.**

```powershell
prism sql "CREATE TABLE MyApp.Employee (Name VARCHAR(100), Salary INTEGER)"
```

**Pipe into `jq`** (Linux) to extract just the rows:

```bash
prism sql "SELECT TOP 5 Name FROM %Dictionary.ClassDefinition" \
  | jq '.result.content'
```

**PowerShell equivalent:**

```powershell
(prism sql "SELECT TOP 5 Name FROM %Dictionary.ClassDefinition" `
  | ConvertFrom-Json).result.content
```

## Tips

### Table ↔ class naming

SQL tables map directly to ObjectScript class names. The class
`MyApp.Person` is the SQL table `MyApp.Person` — dots are preserved as
schema separators.

### Compiled classes only

A class must be compiled before its table is queryable. If you just
uploaded a new class via [`prism put-doc`](documents.md#put-doc), follow
up with [`prism compile`](compile.md) before running SQL against it.

### `[SqlProc]` naming

The dot between package and class is kept as a schema separator; the
class and method names are joined with an underscore:

```
package.class.method   →   SQL    package.class_method()
```

So `MyApp.Utils.Calculate` becomes `MyApp.Utils_Calculate()` in SQL.

### Empty strings and `$CHAR(0)`

In IRIS SQL, the empty string literal `''` is stored as `$CHAR(0)`
internally. `[SqlProc]` methods that take string parameters should
check for `$Char(0)` and convert to a real empty string when needed.

## Related

- [`prism compile`](compile.md) — compile classes before querying them.
- [`prism terminal`](terminal.md) — when SQL isn't enough.
- MCP tool: `execute_sql` (returns a simpler `{"rows", "count"}` shape —
  see [MCP tools](../mcp/tools.md)).