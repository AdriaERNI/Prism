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
| `index_code` | [`prism index`](../commands/indexing.md) | Builds a compact index of all classes using `%Dictionary` SQL metadata. Returns `{namespace, statistics, classes, dependencies, edges, r_edges, degree}`. Also accepts `include_call_graph=True` to add a method-level call graph (`call_edges`, `r_call_edges`, `code_refs`, `unresolved`) — the slow opt-in Tier 2 pass. Token-efficient alternative to reading every source file (93% reduction). |
| `index_reachability` | — | **(MCP only.)** Walks the class dependency graph from a class. Returns `{start, max_hops, direction, reachable: [[class, distance]...]}`. Default `direction="reverse"` (what depends on this class — impact analysis); pass `direction="forward"` for what this class depends on. Edges come from superclass, property-type and method-signature-type links. |
| `index_search` | [`prism index-search`](../commands/indexing.md) | Searches IRIS symbol names (classes, methods, properties, SQL tables) server-side via fast `%Dictionary` SQL. Exact + `%STARTSWITH` prefix, `kind`/`limit` params, ranking class > method > property > table. Returns `{query, count, results: [{kind, symbol, owner, detail}]}`. |
| `index_node` | [`prism index-node`](../commands/indexing.md) | Focused full picture of one class: methods+signatures, properties, supers, children, callers (from the reverse call graph), callees, body code references and degree. Pure assembly of the already-built index. Returns `{name, methods, properties, callers, callees, ...}`. |
| `index_refs` | [`prism index-refs`](../commands/indexing.md) | Which classes reference a class in their method bodies (the `r_code_refs` map). Returns `{target, found, count, referenced_by}`. |
| `index_impact` | [`prism index-impact`](../commands/indexing.md) | Transitive blast radius of a method or class (who transitively calls it) over `r_call_edges` + structural `r_edges`. Returns `{start, hops, count, truncated, methods}`. |
| `index_path` | [`prism index-path`](../commands/indexing.md) | Shortest method-to-method path in the call graph (BFS with predecessor tracking). Returns `{found, path, length, hops}`. |
| `index_queries` | [`prism index-queries`](../commands/indexing.md) | Runs one of five named queries over the call graph: `callers_of_method`, `callers_high_fanin`, `method_calls_outbound`, `class_references`, `find_path`. Takes a `query` name plus the query's params. Returns a per-query result shape. |
| `index_status` | [`prism index-status`](../commands/indexing.md) | Reports index-cache freshness/count/age for a scope (via the `TimeChanged` fingerprint), with `refresh=True` to force a rebuild. Returns `{namespace, target, classes, fresh, cached, age_seconds}`. |
| `monitor_system` | [`prism monitor`](../commands/monitor.md) | Fetches live metrics from IRIS `/api/monitor`, computes a 0–100 load score with per-category sub-scores (CPU, memory, disk, process), and returns a snapshot with grade, key metrics, and alert count. Use two snapshots to compare instances — lower score wins. |
| `list_files` | — | **(MCP only.)** Lists files in the `IRIS_WORKSPACE` directory. Returns `{files: [{name, size, modified}], count}`. |
| `read_file` | — | **(MCP only.)** Reads a file from the `IRIS_WORKSPACE` directory. Returns `{name, content, found}`. |
| `run_shell` | — | **(MCP only.)** Runs a shell command in the `IRIS_WORKSPACE` directory. Returns `{stdout, stderr, exit_code}`. |
| `debug_list_processes` | — | **(MCP only.)** See [Interactive debugger](debugging.md). |
| `debug_start` | — | **(MCP only.)** |
| `debug_attach` | — | **(MCP only.)** Not supported on Windows IRIS. |
| `debug_step` | — | **(MCP only.)** |
| `debug_inspect` | — | **(MCP only.)** |
| `debug_variables` | — | **(MCP only.)** |
| `debug_stack` | — | **(MCP only.)** |
| `debug_breakpoints` | — | **(MCP only.)** |
| `debug_stop` | — | **(MCP only.)** |

21 tools are always registered (including `index_code`, `index_reachability`,
`index_queries` and `monitor_system`).
5 workspace-gated tools (`put_document`, `put_and_compile`, `list_files`,
`read_file`, `run_shell`) are added when `IRIS_WORKSPACE` is set — 25 total.
9 debug-gated tools are added when `IRIS_DEBUG_ENABLED=true` — up to 34 total
with both workspace and debug enabled.

## Workspace-gated tools

When `IRIS_WORKSPACE` is empty (the default), Prism skips the
`workspace`, `files`, and `shell` modules entirely and **does not
register** `put_document`, `put_and_compile`, `list_files`, `read_file`,
or `run_shell`. Set `IRIS_WORKSPACE` to a local directory path to
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

## Multi-server targeting

Every IRIS-targeting tool accepts two optional parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `target_host` | `str \| None` | IRIS server hostname or IP (e.g. `192.168.1.100`) |
| `target_port` | `int \| None` | IRIS REST API port (e.g. `52773`) |

When both are omitted, the tool uses the configured `IRIS_BASE_URL` from
settings. When provided, a separate HTTP client is created and cached per
`host:port` pair, allowing concurrent calls to multiple IRIS instances
without changing global configuration.

```python
# Query the default server
await execute_sql("SELECT 1")

# Query a different IRIS instance
await execute_sql("SELECT 1", target_host="10.0.0.50", target_port=52774)
```

This applies to all tools that connect to IRIS: `execute_sql`,
`execute_terminal`, `get_server_info`, `list_documents`, `get_document`,
`put_document`, `put_and_compile`, `delete_document`, `compile_documents`,
`run_tests`, `list_tests`, `get_test_results`, `index_code`, and
`monitor_system`. The index query tools (`index_search`, `index_node`,
`index_refs`, `index_impact`, `index_path`, `index_queries`, `index_status`)
also accept them.

Tools that operate locally (`list_files`, `read_file`, `run_shell`) do not
accept these parameters.

## Tool annotations

Tools carry MCP annotations per the specification:

| Annotation | Meaning |
|------------|---------|
| `readOnlyHint` | Tool does not modify state |
| `destructiveHint` | Tool may destroy data |
| `idempotentHint` | Repeated calls produce the same result |
| `openWorldHint` | Tool interacts with external systems |

## Response size limits

Read-heavy tools (`execute_sql`, `get_document`, `list_documents`) apply a
`CHARACTER_LIMIT = 25000` truncation when the serialized response exceeds
the limit. Truncated responses include `truncated: true` and a
`truncation_message` with guidance on reducing the result size.

`list_documents` also supports pagination via `limit` (default 50, max 200)
and `offset` (default 0) parameters. The response includes `total`,
`has_more`, and `next_offset` for navigation.

## Related

- [`prism serve`](../commands/serve.md) — start the server.
- [MCP client setup](client-setup.md) — configure IDEs / AI clients.
- [Interactive debugger](debugging.md) — the `debug_*` tools.
