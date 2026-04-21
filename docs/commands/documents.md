# Documents

Four commands to manage IRIS source code documents: list, fetch, upload,
delete. All of them print the raw Atelier REST JSON.

Document name conventions:

- `.cls` — ObjectScript class (`MyApp.Person.cls`)
- `.mac` / `.int` — routines
- `.inc` — include files
- `.bpl` / `.dtl` — business process / data transformation (Ensemble)
- `.hl7` — HL7 schemas

## list-docs

List source documents on the server.

### Usage

```
prism list-docs [OPTIONS]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |
| `--type`, `-t` | all types | Filter by document type: `cls`, `mac`, `int`, `inc`, … |
| `--generated` | off | Include generated documents (usually hidden). |
| `--filter`, `-f` | — | Filter by name prefix (e.g. `MyApp`). |

### Examples

```powershell
prism list-docs --type cls --filter MyApp
prism list-docs --namespace SAMPLES --type mac
```

Response shape:

```json
{
  "status": {"errors": [], "summary": ""},
  "result": {
    "content": [
      {
        "name": "MyApp.Hello.cls",
        "cat": "CLS",
        "ts": "2026-04-18 18:07:18.850",
        "upd": true,
        "db": "USER",
        "gen": false
      }
    ]
  }
}
```

---

## get-doc

Fetch a single document's source.

### Usage

```
prism get-doc NAME [OPTIONS]
```

### Arguments

| Name | Type | Description |
|------|------|-------------|
| `NAME` | string | Document name (e.g. `MyApp.Person.cls`). |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |

### Example

```powershell
prism get-doc MyApp.Hello.cls
```

Response shape:

```json
{
  "status": {"errors": [], "summary": ""},
  "result": {
    "name": "MyApp.Hello.cls",
    "db": "USER",
    "ts": "2026-04-18 18:07:18.850",
    "cat": "CLS",
    "enc": false,
    "content": [
      "Class MyApp.Hello Extends %RegisteredObject",
      "{",
      "",
      "ClassMethod Greet(name As %String = \"world\") As %String",
      "{",
      "  Quit \"hello, \" _ name",
      "}",
      "",
      "}"
    ]
  }
}
```

Every element in `result.content` is one source line. Extract them
to a plain-text file:

=== "PowerShell"

    ```powershell
    (prism get-doc MyApp.Hello.cls | ConvertFrom-Json).result.content `
      | Set-Content MyApp.Hello.cls
    ```

=== "Linux (jq)"

    ```bash
    prism get-doc MyApp.Hello.cls | jq -r '.result.content[]' > MyApp.Hello.cls
    ```

If the document does not exist, Prism exits with code `1` and prints
`Error: Document not found: MyApp.Hello.cls` to stderr.

---

## put-doc

Upload a local file to IRIS as a named document.

### Usage

```
prism put-doc NAME FILE [OPTIONS]
```

### Arguments

| Name | Type | Description |
|------|------|-------------|
| `NAME` | string | Document name on the server (e.g. `MyApp.Person.cls`). |
| `FILE` | path | Local file whose contents will be uploaded. Must exist and be readable. |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |

### Example

```powershell
prism put-doc MyApp.Hello.cls .\MyApp.Hello.cls
```

Remember that classes must be compiled before they're usable — follow
up with [`prism compile`](compile.md):

```powershell
prism compile MyApp.Hello.cls
```

---

## delete-doc

Delete a document from IRIS.

### Usage

```
prism delete-doc NAME [OPTIONS]
```

### Arguments

| Name | Type | Description |
|------|------|-------------|
| `NAME` | string | Document name (e.g. `MyApp.Person.cls`). |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |

### Example

```powershell
prism delete-doc MyApp.Hello.cls
```

Exits non-zero with `Error: Document not found: ...` if the document
doesn't exist.

## Related

- [`prism compile`](compile.md) — compile after uploading classes.
- [`prism sql`](sql.md) — query compiled classes via SQL.
- MCP tools: `list_documents`, `get_document`, `put_document`
  (workspace-backed), `put_and_compile`, `delete_document`. See
  [MCP tools](../mcp/tools.md).
