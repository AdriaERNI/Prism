# Prism Documentation Review & Testing Plan

> **Goal:** Verify every documented feature matches actual code behavior, identify
> documentation gaps, and establish a complete cross-platform (Linux + Windows) testing
> strategy. This plan is the output of a full audit of `docs/`, `src/prism/`, `tests/`,
> and `mkdocs.yml`.

---

## 1. Audit Summary

### What was reviewed

| Area | Files read | Key findings |
|------|-----------|--------------|
| Documentation (18 files) | All `.md` in `docs/` | See gap analysis below |
| Source code (43 files) | All `.py` in `src/prism/` | 21 settings, 13 CLI commands, 21–30 MCP tools |
| Tests (33 files) | All `.py` in `tests/` | 244 unit tests (passing), 10 integration test modules, 15 Vagrant PS1 tests |
| mkdocs.yml | Nav structure | 7 nav sections, matches docs/ layout |
| CI workflows (4 files) | All `.yml` in `.github/workflows/` | Linux lint+unit+integration, Windows unit+build, Pages deploy |
| Vagrant scripts (22 files) | All `.ps1` in `vagrant/scripts/` | 15 test suites + install/uninstall/setup/teardown/run-all |

### Tool inventory (from source code)

**CLI commands (13):** `config`, `sql`, `terminal`, `ws`, `compile`, `get-doc`, `list-docs`,
`put-doc`, `delete-doc`, `info`, `test`, `list-tests`, `serve`

**MCP tools (21 default, 30 with debug):**

| Always registered (12) | Workspace-gated (2) | Debug-gated (9) |
|----------------------|--------------------|--------------------|
| `execute_sql` | `put_document` | `debug_list_processes` |
| `execute_terminal` | `put_and_compile` | `debug_attach` |
| `get_server_info` | | `debug_start` |
| `list_documents` | | `debug_step` |
| `get_document` | | `debug_inspect` |
| `delete_document` | | `debug_variables` |
| `compile_documents` | | `debug_stack` |
| `list_tests` | | `debug_breakpoints` |
| `run_tests` | | `debug_stop` |
| `get_test_results` | | |
| `get_server_info` | | |

**Settings (21 fields in `Settings` class):**

| # | Field | Default | Documented in config.md? |
|---|-------|---------|--------------------------|
| 1 | `iris_base_url` | `http://localhost:52773` | ✅ |
| 2 | `iris_username` | `_SYSTEM` | ✅ |
| 3 | `iris_password` | `SYS` | ✅ |
| 4 | `iris_namespace` | `USER` | ✅ |
| 5 | `iris_workspace` | `""` | ✅ |
| 6 | `iris_api_prefix` | `api/atelier/v8` | ✅ |
| 7 | `iris_compile_flags` | `cuk` | ✅ |
| 8 | `iris_superserver_port` | `1972` | ✅ |
| 9 | `iris_terminal_method` | `native` | ✅ |
| 10 | `iris_terminal_max_output_chars` | `100000` | ❌ **Missing from config.md env var table** |
| 11 | `iris_test_runner_class` | `MCP.TestRunner` | ✅ |
| 12 | `iris_test_runner_method` | `RunTests` | ✅ |
| 13 | `iris_test_manager_class` | `%UnitTest.Manager` | ✅ |
| 14 | `iris_test_auto_deploy` | `True` | ✅ |
| 15 | `prism_output_format` | `json` | ❌ **Missing from config.md env var table** |
| 16 | `iris_debug_enabled` | `False` | ✅ |
| 17 | `iris_debug_step_granularity` | `line` | ✅ |
| 18 | `iris_debug_max_data` | `8192` | ✅ |
| 19 | `iris_debug_max_children` | `32` | ✅ |
| 20 | `iris_debug_max_depth` | `2` | ✅ |
| 21 | `iris_debug_idle_timeout` | `300` | ✅ |

---

## 2. Gap Analysis: Documentation vs. Code

### 2.1. Documented features not matching code behavior

| # | Doc file | Issue | Severity |
|---|---------|-------|----------|
| G1 | `docs/index.md` L37 | Says "21 tools" but actually 21 tools default + 9 debug = 30 total when debug enabled. The number "21" refers to default tools. ✅ Actually correct but could be clearer. | Low |
| G2 | `docs/commands/index.md` L1 | Says "13 CLI commands" — correct per `app.py` (13 registered commands). ✅ | None |
| G3 | `docs/commands/config.md` L42 | Lists `--output-format` with values `json \| toon` — matches `output.py`. But the global `--format` flag on the CLI root (`app.py` L33) is **not documented** in `commands/index.md` Common options table. | Medium |
| G4 | `docs/getting-started/configuration.md` | Missing `IRIS_TERMINAL_MAX_OUTPUT_CHARS` from env var table. The setting exists in `settings.py` (line 76) and is configurable via `--terminal-max-output` in `prism config` (documented in `commands/config.md` L51), but the env var reference page omits it. | Medium |
| G5 | `docs/getting-started/configuration.md` | Missing `PRISM_OUTPUT_FORMAT` from env var table. The setting exists in `settings.py` (line 85) and is configurable via `prism config -f`, but the configuration reference page doesn't list it as an environment variable. | Medium |
| G6 | `docs/commands/serve.md` L67 | Says "21 tools by default, or 30 when `IRIS_DEBUG_ENABLED=true`" — this is correct (12 base + 2 workspace + 9 debug = 23 with workspace, but the 21 count assumes no workspace). Actually: 12 always + 2 workspace-gated = 14 without workspace, 21 with workspace+debug... **Need to verify exact count.** | Medium |
| G7 | `docs/mcp/tools.md` L38 | Says "21 tools by default, 30 when `IRIS_DEBUG_ENABLED=true`" — same as above. The actual count depends on workspace mode: without workspace = 12 tools, with workspace = 14, with workspace+debug = 23. The doc says 21 which doesn't match any combination. **This is a factual error.** | High |
| G8 | `docs/commands/terminal.md` L69 | Says native terminal uses `MCP.Terminal` helper class — matches `src/prism/iris/sdk/terminal.py` (`HELPER_CLASS = "MCP.Terminal"`). ✅ | None |
| G9 | `docs/commands/terminal.md` L81 | WebSocket URL shows `/api/atelier/v8/%25SYS/terminal` — matches `terminal.py` `_ws_url()` which uses `settings.iris_api_prefix`. ✅ | None |
| G10 | `docs/commands/compile.md` L60 | Says "exit is still `0`" on compiler failure — need to verify. The CLI `compile.py` doesn't check `status.errors`, it just prints the response. So exit code is indeed `0` on compiler errors. ✅ | None |
| G11 | `docs/commands/testing.md` L8 | Says `get_test_results` is MCP-only with no CLI equivalent — correct, no CLI command exists for it. ✅ | None |
| G12 | `docs/mcp/tools.md` L30 | Says `debug_attach` is "Not supported on Windows IRIS" — matches `AGENTS.md` known issue and `test_debugger.py` skip logic. ✅ | None |
| G13 | `docs/commands/config.md` L170 | Help text for `--terminal-method` says "native or websocket" but the actual setting value for WebSocket is `ws` (not `websocket`), per `settings.py` default `native` and `terminal.py` dispatch on `"native"`. The config flag help text in code says "native or websocket" but the value used in `IRIS_TERMINAL_METHOD` must be `ws`. | Medium |
| G14 | `docs/testing.md` L92 | Docker command uses `intersystems/iris-community:latest-cd` but CI uses `intersystemsdc/iris-community:latest`. Inconsistent image names. | Medium |
| G15 | `docs/testing.md` L372 | References `.github/workflows/ci.yml` but the actual workflow files are `test-linux.yml` and `test-windows.yml` (no `ci.yml` exists). | High |
| G16 | `docs/testing.md` | Does not mention the GitHub Actions **integration test** job that runs against a Docker IRIS container (in `test-linux.yml`). Only mentions lint and unit tests in CI. | Medium |
| G17 | `docs/index.md` L43-46 | Install section only covers Windows installer. No mention of `uv` / pip install for Linux development. The `installation.md` also only covers Windows. | Medium |
| G18 | `docs/commands/index.md` L65 | Common options table lists `--namespace` for `put-doc` and `delete-doc` but doesn't list `--format` (the global flag from `app.py`). | Low |
| G19 | `docs/mcp/tools.md` | The quick reference table lists `get_server_info` only once, but the tool count includes it. ✅ No issue actually. | None |
| G20 | `docs/mcp/debugging.md` | `debug_step` action `stop` is listed as a step action, but in the code (`debugger.py` API), `stop` terminates the session — equivalent to `debug_stop`. The doc lists it as a step action which is technically correct per DBGP protocol. ✅ | None |
| G21 | `docs/getting-started/configuration.md` L99 | `IRIS_TEST_AUTO_DEPLOY` documented as `true` (string) but the actual Python default is `True` (boolean). The env var parsing handles this via pydantic-settings. ✅ Minor. | Low |

### 2.2. Code features not documented

| # | Feature | Where in code | Should be documented in |
|---|---------|---------------|----------------------|
| U1 | Global `--format` CLI flag (`json`/`toon`) | `src/prism/cli/app.py` L33 | `docs/commands/index.md` Common options table |
| U2 | `IRIS_TERMINAL_MAX_OUTPUT_CHARS` env var | `src/prism/settings.py` L76 | `docs/getting-started/configuration.md` Terminal method section |
| U3 | `PRISM_OUTPUT_FORMAT` env var | `src/prism/settings.py` L85 | `docs/getting-started/configuration.md` new "Output" section |
| U4 | Terminal output truncation behavior | `src/prism/iris/api/terminal.py` `_finalize_result()` | `docs/commands/terminal.md` — document `output_truncated` and `output_omitted_chars` fields |
| U5 | Terminal output sanitization (control char stripping) | `src/prism/iris/api/terminal.py` `_clean_text()` | `docs/commands/terminal.md` |
| U6 | Native terminal retry logic (3 attempts for CLASS DOES NOT EXIST, license errors, comm errors) | `src/prism/iris/sdk/terminal.py` L186-221 | `docs/commands/terminal.md` How it works section |
| U7 | `put_document` MCP tool `path` parameter (defaults to doc name) | `src/prism/mcp/workspace.py` L25 | `docs/mcp/tools.md` workspace-gated tools section |
| U8 | `get_document` MCP tool slicing validation errors (ValueError combinations) | `src/prism/mcp/documents.py` L62-67 | `docs/mcp/tools.md` |
| U9 | `get_document` returns `found: false` instead of raising for missing docs | `src/prism/mcp/documents.py` L73 | `docs/mcp/tools.md` — already partially documented but return shape could be clearer |
| U10 | `delete_document` MCP returns `deleted: false, reason: "not found"` for missing docs | `src/prism/mcp/documents.py` L207 | `docs/mcp/tools.md` |
| U11 | `compile_documents` MCP tool returns `{success, errors, console}` (not raw Atelier) | `src/prism/mcp/compile.py` L12-21 | `docs/mcp/tools.md` — already noted but return shape not fully documented |
| U12 | `run_tests` MCP tool returns structured `{class, status, passed, failed, skipped, methods}` with assertion details | `src/prism/mcp/testing.py` L40-143 | `docs/commands/testing.md` and `docs/mcp/tools.md` — MCP return shape is much richer than CLI return shape |
| U13 | `list_tests` MCP tool groups by class: `{classes: [{name, methods}], count}` | `src/prism/mcp/testing.py` L170-190 | `docs/mcp/tools.md` — currently just says "Same shape" but MCP shape is different from CLI |
| U14 | `get_test_results` MCP tool returns `{runs: [{run_id, run_time, duration, test_class, status}], count}` | `src/prism/mcp/testing.py` L232-242 | `docs/mcp/tools.md` — return shape not documented |
| U15 | `get_server_info` MCP returns simplified `{version, api, namespaces}` (not raw Atelier) | `src/prism/mcp/server_info.py` L17-21 | `docs/mcp/tools.md` — says "Same shape" but it's actually flattened |
| U16 | `list_documents` MCP returns simplified `{documents: [{name, type, modified, database}], count}` | `src/prism/mcp/documents.py` L169-178 | `docs/mcp/tools.md` — says "Same shape" but it's actually flattened |
| U17 | MCP server instructions (system prompt) vary based on workspace/debug mode | `src/prism/mcp/server.py` L8-225 | Not documented — could add to `docs/mcp/index.md` |
| U18 | Preflight check creates workspace directory if it doesn't exist | `src/prism/iris/sdk/preflight.py` L51-53 | `docs/commands/serve.md` Preflight section |
| U19 | Native terminal helper class source code (`MCP.Terminal`) | `src/prism/iris/sdk/terminal.py` L19-65 | Could add to `docs/commands/terminal.md` as collapsible reference |
| U20 | Test runner helper class source code (`MCP.TestRunner`) | `src/prism/iris/api/testing.py` L14-39 | Could add to `docs/commands/testing.md` as collapsible reference |
| U21 | TOON output format support (optional `toons` package) | `src/prism/output.py` L33-40 | `docs/commands/index.md` or new section |
| U22 | `execute_terminal` MCP tool supports background execution (task protocol) | `src/prism/mcp/_decorator.py` `task=True` option, `server.py` instructions | `docs/mcp/tools.md` — noted in server instructions but not in tool reference |
| U23 | `execute_terminal` MCP tool `on_output` callback for streaming | `src/prism/iris/api/terminal.py` L126 | Not user-facing — skip |
| U24 | `debug_variables` MCP tool `stack_level=0` means "auto-detect" | `src/prism/mcp/debugger.py` L212 | `docs/mcp/debugging.md` |
| U25 | Document name validation regex | `src/prism/iris/sdk/workspace.py` L10-12 | `docs/commands/documents.md` — document valid name patterns |

### 2.3. Tested features not documented

| # | Test | What it tests | Documentation gap |
|---|------|---------------|------------------|
| T1 | `test_terminal_native.py::TestParallelExecution` | True parallel execution via separate SuperServer sessions | Documented in terminal.md but parallel tests are skipped on CI |
| T2 | `test_terminal_native.py::TestHelperAutoDeploy` | Helper class auto-deploy and redeploy | Documented but redeploy-after-delete behavior could be clearer |
| T3 | `test_background.py::TestTerminalExecution` | Background terminal execution via MCP task protocol | Not documented in MCP tools reference |
| T4 | `test_debugger.py::TestAttachToProcess` | Full attach workflow with variable inspection | Documented in debugging.md but Windows limitation is only in a warning box |
| T5 | `test_e2e.py::test_serial_embedded_object` | Serial embedded objects in SQL | Not mentioned in SQL docs |
| T6 | `test_e2e.py::test_call_sqlproc_via_sql` | Calling `[SqlProc]` methods from SQL | Documented in sql.md ✅ |
| T7 | `test_e2e.py::test_modify_class_recompile` | Modify class and recompile | Documented in compile.md ✅ |
| T8 | Vagrant test `15-output-format.ps1` | Global `--format` flag | Not documented in commands/index.md |

### 2.4. Documented features not tested

| # | Documented feature | Test coverage | Gap |
|---|-------------------|---------------|-----|
| D1 | `prism config -i` interactive mode | Unit tested in `test_cli_config.py::TestInteractive` (4 tests) ✅ | None |
| D2 | `prism config --reset-all` | Unit tested ✅ | None |
| D3 | `prism serve --skip-preflight` | Not tested in integration tests | **Add integration test** |
| D4 | `prism serve --port 4000` | Not tested | **Add integration test** |
| D5 | Terminal `--timeout` option | Not directly tested (only default 30s used) | **Add integration test** |
| D6 | `prism compile --flags cub` (branch compile) | Not tested — only `cuk` and `ck` tested | **Add integration test** |
| D7 | `get_document` MCP `head`/`tail`/`from_line`/`to_line` slicing | Not tested in integration tests | **Add integration test** |
| D8 | `get_document` MCP slicing validation errors | Not tested | **Add integration test** |
| D9 | `list_documents` MCP `generated` parameter | Not tested | **Add integration test** |
| D10 | `run_tests` MCP `manager_class` parameter | Not tested | **Add integration test** |
| D11 | `get_test_results` MCP `limit` parameter | Tested with `limit=5` ✅ | None |
| D12 | `debug_breakpoints` enable/disable actions | Not tested — only `set` and `list` tested | **Add integration test** |
| D13 | `debug_breakpoints` conditional breakpoints | Not tested in integration | **Add integration test** |
| D14 | `debug_variables` `context="public"` and `context="class"` | Not tested — only `private` tested | **Add integration test** |
| D15 | `debug_inspect` `stack_level` parameter | Not tested — only `stack_level=0` tested | **Add integration test** |
| D16 | `debug_step` `step_out` action | Not tested — only `step_over` and `run` tested | **Add integration test** |
| D17 | `debug_step` `step_into` action | Not tested | **Add integration test** |
| D18 | Terminal output truncation (`output_truncated` field) | Not tested | **Add integration test** |
| D19 | TOON output format | Unit tested in `test_output.py` ✅, Vagrant test 15 ✅ | None |
| D20 | `prism config --terminal-method ws` | Not tested via CLI | **Add unit test** |
| D21 | Document name validation (invalid names) | Unit tested in `test_tool_errors.py` ✅ | None |
| D22 | Workspace path traversal protection | Unit tested in `test_workspace.py` ✅ | None |

---

## 3. Documentation Updates Needed

### 3.1. Critical fixes (factual errors)

| Priority | File | Fix |
|----------|------|-----|
| P0 | `docs/mcp/tools.md` L38 | Fix tool count: "14 tools by default (12 base + 2 workspace-gated when `IRIS_WORKSPACE` is set), 23 with workspace + debug, 21 without workspace but with debug... **Recount and state clearly.**" |
| P0 | `docs/commands/serve.md` L67 | Same tool count fix |
| P0 | `docs/testing.md` L372 | Replace `.github/workflows/ci.yml` with `.github/workflows/test-linux.yml` and `test-windows.yml` |
| P0 | `docs/testing.md` L92 | Standardize Docker image name: use `intersystemsdc/iris-community:latest` (matching CI) or document both |
| P1 | `docs/commands/config.md` L170 | Clarify `--terminal-method` values: `native` or `ws` (not `websocket`) |
| P1 | `docs/getting-started/configuration.md` | Add `IRIS_TERMINAL_MAX_OUTPUT_CHARS` to Terminal method section |
| P1 | `docs/getting-started/configuration.md` | Add `PRISM_OUTPUT_FORMAT` to a new "Output" section |

### 3.2. Content additions (missing documentation)

| Priority | File | Addition |
|----------|------|----------|
| P1 | `docs/commands/index.md` | Add `--format` to Common options table (global flag, `json`/`toon`) |
| P1 | `docs/commands/terminal.md` | Document `output_truncated` and `output_omitted_chars` response fields |
| P1 | `docs/commands/terminal.md` | Document control character sanitization in output |
| P1 | `docs/commands/terminal.md` | Document retry logic (3 attempts for transient errors) |
| P2 | `docs/mcp/tools.md` | Document actual MCP return shapes for each tool (not just "Same shape") |
| P2 | `docs/mcp/tools.md` | Document `put_document` `path` parameter defaulting to document name |
| P2 | `docs/mcp/tools.md` | Document `get_document` slicing validation rules |
| P2 | `docs/mcp/tools.md` | Document `delete_document` return: `{deleted: false, reason: "not found"}` |
| P2 | `docs/mcp/tools.md` | Document `compile_documents` return: `{success, errors, console}` |
| P2 | `docs/mcp/tools.md` | Document `run_tests` return: `{class, status, passed, failed, skipped, methods}` |
| P2 | `docs/mcp/tools.md` | Document `list_tests` return: `{classes: [{name, methods}], count}` |
| P2 | `docs/mcp/tools.md` | Document `get_test_results` return: `{runs: [{run_id, run_time, duration, test_class, status}], count}` |
| P2 | `docs/mcp/tools.md` | Document `get_server_info` return: `{version, api, namespaces}` (flattened, not raw Atelier) |
| P2 | `docs/mcp/tools.md` | Document `list_documents` return: `{documents: [{name, type, modified, database}], count}` (flattened) |
| P2 | `docs/mcp/tools.md` | Document `execute_terminal` background execution support |
| P2 | `docs/mcp/debugging.md` | Document `debug_variables` `stack_level=0` means auto-detect |
| P2 | `docs/commands/serve.md` | Document preflight workspace directory creation |
| P2 | `docs/commands/documents.md` | Document valid document name pattern: `Package.Name.ext` |
| P3 | `docs/getting-started/installation.md` | Add Linux/development installation via `uv` / pip |
| P3 | `docs/mcp/index.md` | Mention server instructions vary based on workspace/debug mode |
| P3 | `docs/commands/terminal.md` | Add collapsible MCP.Terminal helper class source |
| P3 | `docs/commands/testing.md` | Add collapsible MCP.TestRunner helper class source |

### 3.3. Structural improvements

| Priority | Change |
|----------|--------|
| P2 | Add "MCP Return Shapes" section to `docs/mcp/tools.md` with a table showing each tool's return dict structure |
| P3 | Add "Linux Installation" section to `installation.md` (uv sync, pip install, dev setup) |
| P3 | Add "CI" subsection to `testing.md` documenting the GitHub Actions workflows (test-linux, test-windows, pages, build-release) |

---

## 4. Tests to Add

### 4.1. Integration tests (Linux, Docker IRIS)

| # | Test file | Test name | What it verifies |
|---|----------|-----------|------------------|
| I1 | `test_sql.py` | `test_call_stored_procedure` | `CALL` with `[SqlProc]` method (currently only in e2e) |
| I2 | `test_sql.py` | `test_ddl_create_table` | `CREATE TABLE` and `DROP TABLE` |
| I3 | `test_documents.py` | `test_get_document_head` | `get_document` with `head=5` |
| I4 | `test_documents.py` | `test_get_document_tail` | `get_document` with `tail=3` |
| I5 | `test_documents.py` | `test_get_document_range` | `get_document` with `from_line=2, to_line=5` |
| I6 | `test_documents.py` | `test_get_document_invalid_slicing` | `head` + `from_line` raises ValueError |
| I7 | `test_documents.py` | `test_list_documents_generated` | `list_documents` with `generated=true` |
| I8 | `test_compile.py` | `test_compile_with_branch_flags` | `compile` with `--flags cub` (branch compile) |
| I9 | `test_terminal.py` | `test_terminal_timeout` | `terminal --timeout 5` with a long command |
| I10 | `test_terminal.py` | `test_terminal_output_truncation` | Verify `output_truncated` field with small `IRIS_TERMINAL_MAX_OUTPUT_CHARS` |
| I11 | `test_testing.py` | `test_run_tests_with_custom_manager` | `run_tests` with `manager_class` parameter |
| I12 | `test_debugger.py` | `test_debug_step_into` | `debug_step` with `action=step_into` |
| I13 | `test_debugger.py` | `test_debug_step_out` | `debug_step` with `action=step_out` |
| I14 | `test_debugger.py` | `test_debug_conditional_breakpoint` | `debug_breakpoints` with `condition` parameter |
| I15 | `test_debugger.py` | `test_debug_breakpoint_enable_disable` | `debug_breakpoints` enable/disable actions |
| I16 | `test_debugger.py` | `test_debug_variables_public` | `debug_variables` with `context=public` |
| I17 | `test_debugger.py` | `test_debug_variables_class` | `debug_variables` with `context=class` |
| I18 | `test_debugger.py` | `test_debug_inspect_stack_level` | `debug_inspect` with `stack_level=1` |
| I19 | `test_serve.py` (new) | `test_serve_default_port` | `prism serve` starts on port 3000 |
| I20 | `test_serve.py` (new) | `test_serve_custom_port` | `prism serve --port 4000` |
| I21 | `test_serve.py` (new) | `test_serve_skip_preflight` | `prism serve --skip-preflight` doesn't check IRIS |
| I22 | `test_serve.py` (new) | `test_serve_preflight_creates_workspace` | Preflight creates workspace dir if missing |

### 4.2. Unit tests

| # | Test file | Test name | What it verifies |
|---|----------|-----------|------------------|
| U1 | `test_cli_config.py` | `test_terminal_method_ws` | `prism config --terminal-method ws` saves `iris_terminal_method: "ws"` |
| U2 | `test_cli_config.py` | `test_terminal_max_output` | `prism config --terminal-max-output 50000` saves correctly |
| U3 | `test_output.py` | `test_format_toon_missing_package` | TOON format raises RuntimeError with install hint when `toons` not installed |
| U4 | `test_settings.py` | `test_21_settings_count` | Verify Settings class has exactly 21 fields (regression guard) |

---

## 5. Linux Testing Strategy (Docker IRIS)

### 5.1. Prerequisites

```bash
# Docker installed and running
docker info

# uv installed
which uv

# Project cloned
cd /home/hermes/Projects/ERNI/Prism/.worktrees/feature-vagrant-integration-tests
```

### 5.2. Start IRIS Community container

```bash
# Pull and start IRIS Community
docker run --name prism-iris -d \
  --publish 1972:1972 --publish 52773:52773 \
  intersystemsdc/iris-community:latest

# Wait for IRIS to be ready (health check)
until curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Basic $(echo -n '_SYSTEM:SYS' | base64)" \
  http://localhost:52773/api/atelier/ | grep -q 200; do
  echo "Waiting for IRIS..."
  sleep 5
done
echo "IRIS is ready"
```

### 5.3. Run tests

```bash
# Install dependencies
uv sync

# 1. Lint (must pass)
uv run ruff check . && uv run ruff format --check .

# 2. Unit tests (no IRIS needed)
uv run pytest tests/unit/ -v --tb=short

# 3. Integration tests (need IRIS)
IRIS_BASE_URL=http://localhost:52773 \
IRIS_USERNAME=_SYSTEM \
IRIS_PASSWORD=SYS \
uv run pytest tests/integration/ -v --tb=short --continue-on-collection-errors

# 4. Specific integration test modules
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_sql.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_documents.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_compile.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_terminal.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_terminal_native.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_testing.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_debugger.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_e2e.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_server_info.py -v
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/test_background.py -v
```

### 5.4. CLI verification (manual, Linux)

```bash
# Configure
uv run python -m prism config -u _SYSTEM -p SYS -U http://localhost:52773 -n USER

# Verify config display
uv run python -m prism config

# Server info
uv run python -m prism info

# SQL
uv run python -m prism sql "SELECT 1 AS val"
uv run python -m prism sql "SELECT TOP 3 Name FROM %Dictionary.ClassDefinition"

# Terminal (native)
uv run python -m prism terminal 'Write "hello"'
uv run python -m prism terminal 'Write $ZVersion'
uv run python -m prism terminal 'Set x=42 Write "x=",x'

# Terminal (WebSocket)
uv run python -m prism ws 'Write "hello"'

# Documents
echo 'Class MyApp.Hello Extends %RegisteredObject
{
ClassMethod Greet(name As %String = "world") As %String
{
  Quit "hello, " _ name
}
}' > /tmp/MyApp.Hello.cls

uv run python -m prism put-doc MyApp.Hello.cls /tmp/MyApp.Hello.cls
uv run python -m prism list-docs --type cls --filter MyApp
uv run python -m prism get-doc MyApp.Hello.cls
uv run python -m prism compile MyApp.Hello.cls
uv run python -m prism terminal 'Write ##class(MyApp.Hello).Greet("Prism")'
uv run python -m prism delete-doc MyApp.Hello.cls

# Testing
uv run python -m prism list-tests
uv run python -m prism test %UnitTest.TestCase

# MCP server (start, verify, stop)
uv run python -m prism serve --port 3000 &
sleep 2
curl -s http://localhost:3000/mcp | head -5
kill %1

# Output format
uv run python -m prism info --format toon  # if toons installed
uv run python -m prism info --format json
```

### 5.5. MCP server verification (Linux)

```bash
# Start with workspace and debug
IRIS_WORKSPACE=/tmp/prism-workspace IRIS_DEBUG_ENABLED=true \
  uv run python -m prism serve --port 3000 &

# Verify tool list via MCP protocol
# (Use a simple MCP client or curl against the streamable-http endpoint)
sleep 2

# Check server is running
curl -s http://localhost:3000/mcp

# Stop
kill %1
```

---

## 6. Windows Testing Strategy (Vagrant VM)

### 6.1. Prerequisites

- Vagrant 2.4+ with `vagrant-libvirt` plugin
- KVM/libvirt running
- ~20 GB disk, 4 GB RAM for VM

### 6.2. Start VM and build

```bash
cd /home/hermes/Projects/ERNI/Prism/.worktrees/feature-vagrant-integration-tests

# Start Windows VM (first time ~20-30 min)
cd vagrant
vagrant up --provider=libvirt

# Build Windows installer
cd ..
bash vagrant/build-windows.sh
# Look for BUILD_SUCCESS and dist/prism-<version>-setup.exe
```

### 6.3. Run Vagrant integration tests

```bash
# Full suite (tests 01-15)
bash vagrant/run-integration-tests.sh

# Subset — avoid serve test (14) which hangs WinRM
bash vagrant/run-integration-tests.sh --filter "0[1-689]*"  # tests 01-06, 08-09
bash vagrant/run-integration-tests.sh --filter "1[0-3]*"    # tests 10-13

# Keep prism installed for manual inspection
bash vagrant/run-integration-tests.sh --keep-installed

# Success indicator: RUNALL_RESULT=PASS
```

### 6.4. Manual Windows verification

```powershell
# After install (via --keep-installed or manual install)

# 1. Help
prism --help

# 2. Config
prism config -u _SYSTEM -p SYS -U http://localhost:52773 -n USER
prism config

# 3. Info
prism info

# 4. SQL
prism sql "SELECT 1 AS val"
prism sql "SELECT TOP 3 Name FROM %Dictionary.ClassDefinition"

# 5. Terminal (native — SuperServer)
prism terminal 'Write "hello"'
prism terminal 'Write $ZVersion'

# 6. Terminal (WebSocket)
prism ws 'Write "hello"'

# 7. Document lifecycle
# (Create MyApp.Hello.cls file first)
prism put-doc MyApp.Hello.cls .\MyApp.Hello.cls
prism list-docs --type cls --filter MyApp
prism get-doc MyApp.Hello.cls
prism compile MyApp.Hello.cls
prism terminal 'Write ##class(MyApp.Hello).Greet("Prism")'
prism delete-doc MyApp.Hello.cls

# 8. Testing
prism list-tests
prism test MyApp.Tests.Calc

# 9. Serve (starts background server)
prism serve
# Ctrl+C to stop

# 10. Output format
prism info --format toon
prism info --format json
```

### 6.5. Windows-specific verification items

| # | What to verify | How | Expected |
|---|----------------|-----|----------|
| W1 | `prism.exe` on PATH | `Get-Command prism` | Shows `C:\Program Files\prism\prism.exe` |
| W2 | Config file location | `prism config` | Shows `%LOCALAPPDATA%\prism\config.json` |
| W3 | Native terminal (SuperServer 1972) | `prism terminal 'Write 42'` | Returns `{"output": "42", ...}` |
| W4 | WebSocket terminal | `prism ws 'Write 42'` | Returns `{"output": "42", ...}` |
| W5 | `debug_attach` fails gracefully | Start MCP with debug, try `debug_attach` | Should fail with connection closed error |
| W6 | All other debug tools work | Start MCP with debug, `debug_start` then step/inspect/stop | Should work normally |
| W7 | Installer adds to PATH | After install, open new terminal | `prism --help` works |
| W8 | Uninstaller removes from PATH | After uninstall, open new terminal | `prism` not found |
| W9 | TOON format | `prism info --format toon` | Works if `toons` package bundled |
| W10 | PyInstaller native lib loading | `prism terminal 'Write 42'` | irisnative loads correctly in frozen binary |

---

## 7. Verification Steps for Each Tool/Command

### 7.1. CLI Commands

| Command | Linux verification | Windows verification | Tests |
|---------|-------------------|---------------------|-------|
| `prism config` (show) | `prism config` shows 21 settings | Same | `test_cli_config.py::TestShow` (4 tests) |
| `prism config` (set) | `prism config -u admin -p secret` | Same | `test_cli_config.py::TestUpdateFlags` (7 tests) |
| `prism config` (reset) | `prism config -r iris_username` | Same | `test_cli_config.py::TestReset` (4 tests) |
| `prism config -i` | Interactive prompts work | Same | `test_cli_config.py::TestInteractive` (4 tests) |
| `prism config --reset-all` | Deletes config.json | Same | `test_cli_config.py::test_reset_all_deletes_file` |
| `prism info` | `prism info` returns JSON | Same | `test_server_info.py` (2 tests) |
| `prism sql` | `prism sql "SELECT 1"` | Same | `test_sql.py` (6 tests) |
| `prism terminal` | `prism terminal 'Write 42'` | Same | `test_terminal_native.py` (7 tests) |
| `prism ws` | `prism ws 'Write 42'` | Same | `test_terminal.py` (5 tests, parametrized) |
| `prism compile` | Compile after put-doc | Same | `test_compile.py` (6 tests) |
| `prism get-doc` | Fetch document | Same | `test_documents.py` (via MCP) |
| `prism list-docs` | List with filter/type | Same | `test_documents.py` (3 tests) |
| `prism put-doc` | Upload .cls/.mac/.inc | Same | `test_documents.py` (via MCP) |
| `prism delete-doc` | Delete and verify gone | Same | `test_documents.py` (1 test) |
| `prism test` | Run test class | Same | `test_testing.py::TestRunTests` (4 tests) |
| `prism list-tests` | List test classes | Same | `test_testing.py::TestListTests` (2 tests) |
| `prism serve` | Start and verify port | Start and verify | **I19-I22** (new tests needed) |
| `prism --format toon` | `prism info --format toon` | Same | Vagrant test 15 |

### 7.2. MCP Tools

| Tool | Linux verification | Windows verification | Tests |
|------|-------------------|---------------------|-------|
| `execute_sql` | Call via MCP client | Call via MCP client | `test_sql.py` (6 tests) |
| `execute_terminal` | Call with native+ws | Call with native+ws | `test_terminal.py` (5×2=10 tests) |
| `get_server_info` | Returns version+namespaces | Same | `test_server_info.py` (2 tests) |
| `list_documents` | List with filter/type | Same | `test_documents.py` (3 tests) |
| `get_document` | Fetch with slicing | Same | `test_documents.py` (2 tests) + **I3-I6** |
| `put_document` | Upload from workspace | Same | `test_documents.py` (5 tests) |
| `put_and_compile` | Upload + compile in one step | Same | `test_testing.py` (uses it) |
| `delete_document` | Delete and verify | Same | `test_documents.py` (1 test) |
| `compile_documents` | Compile multiple | Same | `test_compile.py` (6 tests) |
| `list_tests` | Discover test classes | Same | `test_testing.py::TestListTests` (2 tests) |
| `run_tests` | Run passing/failing tests | Same | `test_testing.py::TestRunTests` (4 tests) |
| `get_test_results` | Query history | Same | `test_testing.py::TestGetTestResults` (2 tests) |
| `debug_list_processes` | List running processes | Same | `test_debugger.py::TestProcessDiscovery` |
| `debug_start` | Start session | Same | `test_debugger.py::TestDebugStartStop` |
| `debug_attach` | Attach by PID | **Skips on Windows** | `test_debugger.py::TestAttachToProcess` |
| `debug_step` | Step into/over/out/run | Same (except attach) | `test_debugger.py::TestFullSteppingWorkflow` + **I12-I13** |
| `debug_inspect` | Evaluate expression | Same | `test_debugger.py::TestInspectVariables` + **I18** |
| `debug_variables` | Get private/public/class vars | Same | `test_debugger.py` + **I16-I17** |
| `debug_stack` | Get call stack | Same | `test_debugger.py::TestStackInspection` |
| `debug_breakpoints` | Set/list/enable/disable | Same | `test_debugger.py::TestBreakpoints` + **I14-I15** |
| `debug_stop` | Stop session | Same | All debug tests call this |

---

## 8. Estimated Work Items

### 8.1. Documentation fixes (estimate: 4-6 hours)

| # | Item | Effort | Priority |
|---|------|--------|----------|
| 1 | Fix tool count in `tools.md` and `serve.md` | 30 min | P0 |
| 2 | Fix CI workflow reference in `testing.md` | 15 min | P0 |
| 3 | Fix Docker image name in `testing.md` | 10 min | P0 |
| 4 | Add `IRIS_TERMINAL_MAX_OUTPUT_CHARS` to `configuration.md` | 15 min | P1 |
| 5 | Add `PRISM_OUTPUT_FORMAT` to `configuration.md` | 15 min | P1 |
| 6 | Fix `--terminal-method` values in `config.md` | 10 min | P1 |
| 7 | Add `--format` to Common options in `commands/index.md` | 15 min | P1 |
| 8 | Document terminal truncation/sanitization/retry in `terminal.md` | 45 min | P1 |
| 9 | Add MCP return shapes table to `tools.md` | 90 min | P2 |
| 10 | Document `debug_variables` stack_level auto-detect in `debugging.md` | 10 min | P2 |
| 11 | Document preflight workspace creation in `serve.md` | 15 min | P2 |
| 12 | Document valid doc name pattern in `documents.md` | 15 min | P2 |
| 13 | Add Linux installation to `installation.md` | 30 min | P3 |
| 14 | Add CI section to `testing.md` | 20 min | P3 |
| 15 | Add collapsible helper class sources | 30 min | P3 |

### 8.2. New integration tests (estimate: 3-4 hours)

| # | Test | Effort |
|---|------|--------|
| I1-I2 | SQL: stored proc, DDL | 30 min |
| I3-I7 | Documents: slicing, generated | 45 min |
| I8 | Compile: branch flags | 15 min |
| I9-I10 | Terminal: timeout, truncation | 30 min |
| I11 | Testing: custom manager | 20 min |
| I12-I18 | Debugger: step_into/out, conditional BP, enable/disable, public/class vars, stack_level | 90 min |
| I19-I22 | Serve: port, skip-preflight, workspace creation | 45 min |

### 8.3. New unit tests (estimate: 30 min)

| # | Test | Effort |
|---|------|--------|
| U1-U2 | Config: terminal_method, max_output | 10 min |
| U3 | Output: TOON missing package error | 10 min |
| U4 | Settings: 21 fields count guard | 5 min |

### 8.4. Linux test execution (estimate: 30 min)

| Step | Effort |
|------|--------|
| Start Docker IRIS container | 5 min |
| Run unit tests | 1 min |
| Run integration tests | 10 min |
| Manual CLI verification | 15 min |

### 8.5. Windows test execution (estimate: 1-2 hours)

| Step | Effort |
|------|--------|
| `vagrant up` (if not running) | 5-30 min |
| `build-windows.sh` | 10-15 min |
| `run-integration-tests.sh` | 10-15 min |
| Manual verification (if --keep-installed) | 30 min |

### 8.6. Total estimated effort

| Phase | Effort |
|-------|--------|
| Documentation fixes | 4-6 hours |
| New tests | 3-4 hours |
| Linux test execution | 30 min |
| Windows test execution | 1-2 hours |
| **Total** | **9-13 hours** |

---

## 9. Execution Order

1. **Fix P0 documentation errors** (tool count, CI ref, Docker image) — 30 min
2. **Start Docker IRIS on Linux** — 5 min (parallel with step 1)
3. **Run existing unit tests** — verify 244 pass — 1 min
4. **Run existing integration tests on Linux** — identify failures — 10 min
5. **Write new unit tests** (U1-U4) — 30 min
6. **Write new integration tests** (I1-I22) — 3 hours
7. **Run all tests on Linux** — verify pass — 15 min
8. **Fix P1 documentation issues** — 1.5 hours
9. **Fix P2 documentation issues** — 2 hours
10. **Fix P3 documentation issues** — 1 hour
11. **Start Vagrant Windows VM** — 5-30 min (parallel with step 8-10)
12. **Build Windows installer** — 10-15 min
13. **Run Vagrant integration tests** — 10-15 min
14. **Manual Windows verification** — 30 min
15. **Run `mkdocs build --strict`** to verify docs build — 1 min
16. **Commit with conventional commits** (`docs:`, `test:`)

---

## 10. Known Issues & Caveats

1. **`debug_attach` on Windows IRIS** — Server-side limitation, documented in `debugging.md` and `AGENTS.md`. Not a Prism bug.
2. **Vagrant test 14 (serve) hangs WinRM** — `prism serve` starts a blocking HTTP server. Workaround: exclude with `--filter`.
3. **Vagrant test 07 (list-docs) may timeout** — Large namespaces return thousands of docs. Workaround: increase timeout in `_common.ps1`.
4. **Vagrant test 13 (`-m` assertion)** — Assertion checks for method name in stdout but JSON puts it in nested field. Test passes but assertion doesn't find string. Fix pending.
5. **Parallel native terminal tests skip on CI** — IRIS Community license limits concurrent SuperServer connections.
6. **`mkdocs build --strict`** — The pages.yml CI workflow uses `--strict` which fails on any broken links or warnings. All doc changes must pass strict build.
7. **TOON format requires `toons` package** — Not installed by default. `prism info --format toon` will raise RuntimeError if not installed.
8. **Docker image name discrepancy** — `testing.md` says `intersystems/iris-community:latest-cd` but CI uses `intersystemsdc/iris-community:latest`. Need to standardize.

---

## 11. Verification Checklist

After all work is complete, verify:

- [ ] `mkdocs build --strict` passes with no warnings
- [ ] All 244 existing unit tests pass
- [ ] All new unit tests pass
- [ ] All existing integration tests pass on Linux Docker IRIS
- [ ] All new integration tests pass on Linux Docker IRIS
- [ ] All 15 Vagrant Windows tests pass (or known issues documented)
- [ ] Tool count in docs matches actual code count
- [ ] Every MCP tool return shape is documented
- [ ] Every env var in `settings.py` is documented in `configuration.md`
- [ ] Every CLI flag in `app.py` is documented in `commands/index.md`
- [ ] CI workflow references in `testing.md` match actual file names
- [ ] Docker image name is consistent across all docs
- [ ] `--format` global flag documented in Common options
- [ ] Terminal truncation/sanitization/retry documented