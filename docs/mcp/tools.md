# MCP tool reference

Every MCP tool Prism exposes, along with the CLI command it corresponds
to. Tools are auto-discovered: every `@logged_tool` function under
`src/prism/mcp/` is registered when `prism serve` starts.

Most tools have a matching CLI command with similar arguments. A few are
MCP-only — marked **(MCP only)** — either because they rely on the
`IRIS_WORKSPACE` workspace, return cached state, or drive an interactive
session the CLI can't hold open.

## Quick reference

| MCP tool | Corresponding CLI | Notes |
|----------|-------------------|-------|
| `execute_sql` | [`prism sql`](../commands/sql.md) | MCP shape is `{"rows": [...], "count": N}` (flattened), CLI shows the raw Atelier envelope. |
| `execute_terminal` | [`prism terminal`](../commands/terminal.md) (native) or [`prism ws`](../commands/terminal.md) | MCP picks backend via `IRIS_TERMINAL_METHOD`. CLI lets you pick per-invocation. |
| `get_server_info` | [`prism info`](../commands/info.md) | MCP returns simplified `{version, api, namespaces}` (flattened, not raw Atelier envelope). |
| `list_documents` | [`prism list-docs`](../commands/documents.md#list-docs) | MCP returns `{documents: [{name, type, modified, database}], count}` (flattened). |
| `get_document` | [`prism get-doc`](../commands/documents.md#get-doc) | MCP version supports slicing via `head`, `tail`, `from_line`, `to_line`. Returns `{name, content, found, ...}` — `found: false` for missing docs (no exception). |
| `put_document` | [`prism put-doc`](../commands/documents.md#put-doc) | **(MCP only flow)** Reads the file from `IRIS_WORKSPACE`, not a user-provided path. Requires `IRIS_WORKSPACE` to be set. `path` param defaults to document name. |
| `put_and_compile` | combine [`prism put-doc`](../commands/documents.md#put-doc) + [`prism compile`](../commands/compile.md) | **(MCP only.)** Workspace-based, one-shot upload + compile. |
| `delete_document` | [`prism delete-doc`](../commands/documents.md#delete-doc) | MCP returns `{name, deleted, reason}` — `deleted: false, reason: "not found"` for missing docs. |
| `compile_documents` | [`prism compile`](../commands/compile.md) | MCP returns `{success: bool, errors: [...], console: [...]}` (not raw Atelier). |
| `list_tests` | [`prism list-tests`](../commands/testing.md#list-tests) | MCP returns `{classes: [{name, methods: [...]}], count}` (grouped by class). |
| `run_tests` | [`prism test`](../commands/testing.md#test) | MCP returns `{class, status, passed, failed, skipped, methods: [{name, status, assertions}]}` (structured, richer than CLI). |
| `get_test_results` | — | **(MCP only.)** Returns `{runs: [{run_id, run_time, duration, test_class, status}], count}`. |
| `debug_list_processes` | — | **(MCP only.)** See [Interactive debugger](debugging.md). |
| `debug_start` | — | **(MCP only.)** |
| `debug_attach` | — | **(MCP only.)** Not supported on Windows IRIS. |
| `debug_step` | — | **(MCP only.)** |
| `debug_inspect` | — | **(MCP only.)** |
| `debug_variables` | — | **(MCP only.)** |
| `debug_stack` | — | **(MCP only.)** |
| `debug_breakpoints` | — | **(MCP only.)** |
| `debug_stop` | — | **(MCP only.)** |

10 tools are always registered. 2 workspace-gated tools (`put_document`,
`put_and_compile`) are added when `IRIS_WORKSPACE` is set — 12 total.
9 debug-gated tools are added when `IRIS_DEBUG_ENABLED=true` — up to 21
total with both workspace and debug enabled.

## Workspace-gated tools

When `IRIS_WORKSPACE` is empty (the default), Prism skips the
`workspace` module entirely and **does not register** `put_document` or
`put_and_compile`. Set `IRIS_WORKSPACE` to a local directory path to
enable them.

The CLI `prism put-doc <name> <file>` ignores `IRIS_WORKSPACE` and
always reads the file you pass directly. If you're scripting from a
shell, prefer the CLI; if you're driving from an AI client that lives
inside the workspace, use the MCP tools.

## Debug-gated tools

The nine `debug_*` tools are only registered when
`IRIS_DEBUG_ENABLED=true`. They have no CLI equivalent — interactive
stepping holds state across calls that only fits into a persistent
session. See [Interactive debugger](debugging.md).

## Return shape

All MCP tools return `dict`s. Error handling varies per tool:

- **SQL errors** come back as `{"error": "...", "rows": [], "count": 0}`
  rather than raising an exception. This keeps the tool call deterministic
  and lets the client show the error to the user.
- **Document-not-found** from `get_document` / `delete_document` raises
  `DocumentNotFound`, which the MCP layer surfaces as an error response.
- **Compilation** errors are reported in the Atelier response's `status.errors`
  and `console` fields — the tool call itself succeeds.

## Related

- [`prism serve`](../commands/serve.md) — start the server.
- [MCP client setup](client-setup.md) — configure IDEs / AI clients.
- [Interactive debugger](debugging.md) — the `debug_*` tools.
