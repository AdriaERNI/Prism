# Testing

Two CLI commands for the `%UnitTest.TestCase` framework: discover test
classes and run them.

A third operation — fetching historical test results — is only
available through the MCP server as `get_test_results`; there's no CLI
equivalent yet. See [MCP tools](../mcp/tools.md).

---

## list-tests

Discover `%UnitTest.TestCase` classes and their `Test*` methods by
querying the IRIS `%Dictionary`.

### Usage

```
prism list-tests [OPTIONS]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--filter`, `-f` | — | Class name prefix (e.g. `MyApp.Tests`). |
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |

### Example

```powershell
prism list-tests --filter MyApp.Tests
```

Output:

```json
{
  "status": {"errors": [], "summary": ""},
  "result": {
    "content": [
      {"class_name": "MyApp.Tests.Calc", "method_name": "TestAddition"},
      {"class_name": "MyApp.Tests.Calc", "method_name": "TestSubtraction"},
      {"class_name": "MyApp.Tests.Person", "method_name": "TestAgeValidation"}
    ]
  }
}
```

Each entry is one test method. To list just the classes:

=== "PowerShell"

    ```powershell
    (prism list-tests | ConvertFrom-Json).result.content.class_name `
      | Sort-Object -Unique
    ```

=== "Linux (jq)"

    ```bash
    prism list-tests | jq -r '.result.content[].class_name' | sort -u
    ```

---

## test

Run a unit test class (optionally a single method) via the deployed
runner.

### Usage

```
prism test TEST_CLASS [OPTIONS]
```

### Arguments

| Name | Type | Description |
|------|------|-------------|
| `TEST_CLASS` | string | Fully-qualified test class name (e.g. `MyApp.Tests.Calc`). |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--method`, `-m` | all methods | Run a single `Test*` method instead of the whole class. |
| `--manager` | `IRIS_TEST_MANAGER_CLASS` (default `%UnitTest.Manager`) | Override the test manager class. |
| `--namespace`, `-n` | `IRIS_NAMESPACE` setting | Target namespace. |

### Example

```powershell
prism test MyApp.Tests.Calc
```

Output:

```json
{
  "status": {"errors": [], "summary": ""},
  "console": [
    "",
    "Use the following URL to view the result:",
    "http://127.0.0.1:57772/csp/sys/%25UnitTest.Portal.Indices.cls?Index=49&$NAMESPACE=USER",
    "All PASSED"
  ],
  "result": {
    "content": [{"Result": "1"}]
  }
}
```

`Result: 1` means every assertion passed. On failure, the console log
describes which method / assertion failed, and `Result: -1` is
returned.

### Single method

```powershell
prism test MyApp.Tests.Calc --method TestAddition
```

### How it works

First time you run `prism test`, Prism deploys a small helper class
(`MCP.TestRunner` by default — configurable via `IRIS_TEST_RUNNER_CLASS`)
that wraps `%UnitTest.Manager.DebugRunTestCase`. It writes results to
the `^UnitTestRoot` global using a temporary directory under
`$System.Util.ManagerDirectory()/Temp/UnitTest/`.

Auto-deploy can be disabled with `IRIS_TEST_AUTO_DEPLOY=false` — useful
when the runner class is already present on the server and you'd rather
not have Prism touch it.

---

## Writing test classes

A `%UnitTest.TestCase` subclass with `Test*` methods:

```objectscript
Class MyApp.Tests.Calc Extends %UnitTest.TestCase
{
Method TestAddition()
{
    Do $$$AssertEquals(2 + 2, 4, "2+2 should be 4")
}

Method TestSubtraction()
{
    Do $$$AssertEquals(10 - 4, 6)
}
}
```

Upload and compile it like any other class:

```powershell
prism put-doc MyApp.Tests.Calc.cls .\MyApp.Tests.Calc.cls
prism compile MyApp.Tests.Calc.cls
prism test MyApp.Tests.Calc
```

Common assertions:

| Macro | Description |
|-------|-------------|
| `$$$AssertEquals(a, b)` | `a` equals `b`. |
| `$$$AssertNotEquals(a, b)` | `a` does not equal `b`. |
| `$$$AssertStatusOK(sc)` | `%Status` is `$$$OK`. |
| `$$$AssertStatusEquals(sc, expected)` | Status code match. |
| `$$$LogMessage("…")` | Free-form log entry in results. |

## Related

- [`prism compile`](compile.md) — required after uploading test
  classes.
- MCP tools: `run_tests`, `list_tests`, `get_test_results`. See
  [MCP tools](../mcp/tools.md).
