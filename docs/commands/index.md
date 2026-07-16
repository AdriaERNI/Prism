# Commands

Prism ships 14 CLI commands. Each one is a thin wrapper around a single
IRIS operation, so the output is the raw Atelier REST response (as JSON)
unless otherwise noted.

All commands pick up connection settings from (in this order):

1. Environment variables (`IRIS_BASE_URL`, `IRIS_USERNAME`, …).
2. A `.env` file in the current directory.
3. The user's `config.json` (written by [`prism config`](config.md)).

Run any command with `--help` to see its options:

```
prism <command> --help
```

## Command reference

### Setup

| Command | Summary |
|---------|---------|
| [`prism config`](config.md) | Save connection settings to a persistent user-level file. |
| [`prism info`](info.md) | Print IRIS server version, namespaces, and feature flags. |

### SQL and ObjectScript

| Command | Summary |
|---------|---------|
| [`prism sql`](sql.md) | Run an InterSystems SQL query. |
| [`prism terminal`](terminal.md#native) | Run an ObjectScript command via the SuperServer (native driver). |
| [`prism ws`](terminal.md#websocket) | Run an ObjectScript command via the Atelier WebSocket. |

### Documents

| Command | Summary |
|---------|---------|
| [`prism list-docs`](documents.md#list-docs) | List source documents on the server. |
| [`prism get-doc`](documents.md#get-doc) | Fetch a document's source. |
| [`prism put-doc`](documents.md#put-doc) | Upload a local file as a document. |
| [`prism delete-doc`](documents.md#delete-doc) | Delete a document. |
| [`prism compile`](compile.md) | Compile one or more documents on the server. |

### Testing

| Command | Summary |
|---------|---------|
| [`prism list-tests`](testing.md#list-tests) | Discover `%UnitTest.TestCase` classes and their `Test*` methods. |
| [`prism test`](testing.md#test) | Run a unit test class (or a single method). |

### Code indexing

| Command | Summary |
|---------|---------|
| [`prism index`](indexing.md) | Build a compact index of all classes in a namespace. Token-efficient alternative to reading every source file. |

### MCP server

| Command | Summary |
|---------|---------|
| [`prism serve`](serve.md) | Start the Prism MCP server on `http://localhost:3000/mcp`. |

### Plugins

| Command | Summary |
|---------|---------|
| [`prism cast`](cast.md) | Extend Prism with custom commands from Git repositories. Add repos, run commands with typed arguments and shell completion, and manage updates — all without installing packages. |

## Common options

Several options appear on multiple commands. They all behave the same way:

| Option | Long / short | Applies to | Meaning |
|--------|--------------|-----------|---------|
| `--format` | — | **Global** (before the subcommand) | Output format: `json` (default) or `toon`. Example: `prism --format toon sql "SELECT 1"`. |
| `--namespace` | `-n` | `sql`, `terminal`, `ws`, `compile`, `get-doc`, `list-docs`, `put-doc`, `delete-doc`, `test`, `list-tests` | Target IRIS namespace. Defaults to `IRIS_NAMESPACE` from your settings. |
| `--timeout` | `-t` | `terminal`, `ws` | Command timeout in seconds. Default `30.0`. |
| `--port` | `-p` | `serve` | Port for the MCP server. Default `3000`. |
| `--flags` | — | `compile` | IRIS compiler flags (default `cuk`, from `IRIS_COMPILE_FLAGS`). |

## Where outputs go

Every command prints its result to **stdout** as JSON. Errors go to
**stderr** and set a non-zero exit code, so the following works as
expected in scripts:

```powershell
prism sql "SELECT 1" | ConvertFrom-Json
```

or on Linux:

```bash
prism sql "SELECT 1" | jq .result.content
```