# Prism — Test Gap Analysis

_Generated: 2026-08-02 12:20 by Hermes Agent_

## 1. Test Suite Run Results

| Metric | Value |
|---|---|
| Command | `PYTHONPATH='' uv run pytest tests/unit/ -v --tb=short` |
| Passed | 955 |
| Skipped | 11 |
| Failed | 0 |
| Duration | ~24–29s |
| Unit test functions | 884 |
| Integration test functions | 82 (require live IRIS) |
| GUI test functions | 29 (require display) |
| MCP protocol test functions | 0 (`tests/mcp/test_mcp_protocol.py` exists but contains no test functions) |
| Total test functions | 995 |
| `pytest.raises` assertions | 73 |

**Verdict:** The unit suite is green and stable. The 11 skips are intentional (integration-only / environment-gated). No flaky failures observed.

## 2. Coverage Measurement (pytest-cov, unit tests only)

> `pytest-cov` / `coverage` are **not** declared dev dependencies. Coverage was measured by running `uv run --with coverage --with pytest-cov python -m pytest tests/unit/ --cov=prism --cov-report=json`. The repo's documented baseline (955 passed) is reproduced.

| Metric | Value |
|---|---|
| Total statements | 5614 |
| Missing (uncovered) lines | 1690 |
| **Overall line coverage** | **70%** |
| Source `.py` files (excl. `__init__`) | 65 |
| Files WITH ≥1 test file mapped | 63 |
| Files WITHOUT any test file | 2 |
| Files at 0% coverage | 2 |
| Files 1–49% coverage | 11 |
| Files 50–79% coverage | 17 |
| Files ≥ 80% coverage | 35 |

### Coverage by tier

| Tier | Files | % of non-init files |
|---|---|---|
| High (≥80%) | 35 | 54% |
| Medium (50–79%) | 17 | 26% |
| Low (1–49%) | 11 | 17% |
| Zero (0%) | 2 | 3% |

### Per-file coverage (sorted ascending)

| Source file | Cov% | Stmts | Missing | Test file(s) |
|---|---|---|---|---|
| `src/prism/__main__.py` | 0% | 3 | 3 | **— (none) —** |
| `src/prism/iris/sdk/preflight.py` | 0% | 41 | 41 | **— (none) —** |
| `src/prism/mcp/testing.py` | 15% | 75 | 64 | tests/unit/test_iris_api/test_testing.py |
| `src/prism/cli/commands/gui.py` | 21% | 14 | 11 | tests/gui/test_e2e_user_scenarios.py, tests/unit/test_gui_sql.py, tests/unit/test_gui_tabs.py, tests/unit/test_gui_widgets.py |
| `src/prism/cli/commands/serve.py` | 33% | 15 | 10 | tests/mcp/test_mcp_protocol.py, tests/unit/test_cli_setup.py, tests/unit/test_completion.py, tests/unit/test_pyinstaller_compat.py |
| `src/prism/cli/interactive.py` | 34% | 275 | 181 | tests/unit/test_cli_config.py, tests/unit/test_cli_interactive_ws.py |
| `src/prism/cli/commands/documents.py` | 38% | 55 | 34 | tests/integration/test_terminal_native.py, tests/unit/test_iris_api/test_documents.py, tests/unit/test_iris_api/test_terminal_native.py, tests/unit/test_iris_api/test_testing.py, tests/unit/test_tool_errors.py |
| `src/prism/mcp/sql.py` | 43% | 14 | 8 | tests/unit/test_cast_integration.py, tests/unit/test_cli_edge_cases.py, tests/unit/test_completion.py, tests/unit/test_iris_api/test_sql.py |
| `src/prism/cli/commands/chatbot.py` | 43% | 144 | 82 | tests/unit/test_chatbot_agent.py, tests/unit/test_chatbot_skills.py, tests/unit/test_cli_chatbot.py |
| `src/prism/cli/commands/index.py` | 44% | 16 | 9 | tests/unit/test_index.py |
| `src/prism/iris/sdk/dbgp.py` | 46% | 84 | 45 | tests/unit/test_debugger.py |
| `src/prism/gui/widgets/database_tree.py` | 47% | 265 | 141 | tests/unit/test_gui_tabs.py, tests/unit/test_gui_widgets.py |
| `src/prism/gui/theme.py` | 48% | 117 | 61 | tests/unit/test_gui_widgets.py |
| `src/prism/iris/api/debugger.py` | 50% | 327 | 162 | tests/unit/test_debugger.py |
| `src/prism/iris/sdk/terminal.py` | 52% | 98 | 47 | tests/integration/test_terminal_native.py, tests/unit/test_cli_interactive_ws.py, tests/unit/test_iris_api/test_interactive_ws.py, tests/unit/test_iris_api/test_terminal.py, tests/unit/test_iris_api/test_terminal_facade.py, tests/unit/test_iris_api/test_terminal_native.py |
| `src/prism/gui/controllers/sql_controller.py` | 53% | 189 | 88 | tests/unit/test_gui_sql.py, tests/unit/test_gui_tabs.py, tests/unit/test_gui_widgets.py |
| `src/prism/cli/commands/testing.py` | 55% | 22 | 10 | tests/unit/test_iris_api/test_testing.py |
| `src/prism/gui/widgets/results_table.py` | 55% | 359 | 163 | tests/unit/test_gui_widgets.py |
| `src/prism/mcp/server_info.py` | 57% | 7 | 3 | tests/unit/test_iris_api/test_server_info.py |
| `src/prism/mcp/debugger.py` | 61% | 36 | 14 | tests/unit/test_debugger.py |
| `src/prism/mcp/compile.py` | 62% | 16 | 6 | tests/unit/test_iris_api/test_compile.py, tests/unit/test_iris_api/test_terminal_native.py, tests/unit/test_tool_errors.py |
| `src/prism/cli/commands/compile.py` | 65% | 20 | 7 | tests/unit/test_iris_api/test_compile.py, tests/unit/test_iris_api/test_terminal_native.py, tests/unit/test_tool_errors.py |
| `src/prism/gui/widgets/toolbar.py` | 66% | 103 | 35 | tests/unit/test_gui_widgets.py |
| `src/prism/mcp/workspace.py` | 67% | 24 | 8 | tests/unit/test_tool_errors.py, tests/unit/test_workspace.py |
| `src/prism/cli/commands/cast.py` | 68% | 76 | 24 | tests/unit/test_cast_integration.py, tests/unit/test_cli_cast.py, tests/unit/test_cli_edge_cases.py, tests/unit/test_completion.py |
| `src/prism/gui/widgets/sql_editor.py` | 74% | 340 | 90 | tests/unit/test_gui_sql.py, tests/unit/test_gui_tabs.py, tests/unit/test_gui_widgets.py |
| `src/prism/gui/app.py` | 76% | 304 | 74 | tests/gui/test_e2e_user_scenarios.py, tests/gui/test_gui_interactions.py, tests/unit/test_cast_integration.py, tests/unit/test_cli_cast.py, tests/unit/test_cli_chatbot.py, tests/unit/test_cli_config.py, tests/unit/test_cli_edge_cases.py, tests/unit/test_cli_interactive_ws.py, tests/unit/test_cli_monitor.py, tests/unit/test_cli_setup.py, tests/unit/test_gui_sql.py, tests/unit/test_gui_tabs.py, tests/unit/test_gui_widgets.py, tests/unit/test_monitor_event_loop.py |
| `src/prism/chatbot/agent.py` | 77% | 312 | 71 | tests/unit/test_chatbot_agent.py |
| `src/prism/cli/commands/monitor.py` | 78% | 80 | 18 | tests/unit/test_cli_monitor.py, tests/unit/test_iris_api/test_monitor.py, tests/unit/test_mcp_monitor.py, tests/unit/test_monitor_averages.py, tests/unit/test_monitor_collector.py, tests/unit/test_monitor_dashboard.py, tests/unit/test_monitor_event_loop.py, tests/unit/test_monitor_parser.py, tests/unit/test_monitor_scorer.py |
| `src/prism/cli/commands/terminal.py` | 78% | 32 | 7 | tests/integration/test_terminal_native.py, tests/unit/test_cli_interactive_ws.py, tests/unit/test_iris_api/test_interactive_ws.py, tests/unit/test_iris_api/test_terminal.py, tests/unit/test_iris_api/test_terminal_facade.py, tests/unit/test_iris_api/test_terminal_native.py |
| `src/prism/cli/errors.py` | 82% | 17 | 3 | tests/unit/test_cli_edge_cases.py, tests/unit/test_cli_monitor.py |
| `src/prism/iris/api/testing.py` | 82% | 51 | 9 | tests/unit/test_iris_api/test_testing.py |
| `src/prism/cli/commands/install.py` | 84% | 209 | 34 | tests/unit/test_cli_setup.py, tests/unit/test_completion.py |
| `src/prism/mcp/terminal.py` | 86% | 7 | 1 | tests/integration/test_terminal_native.py, tests/unit/test_cli_interactive_ws.py, tests/unit/test_iris_api/test_interactive_ws.py, tests/unit/test_iris_api/test_terminal.py, tests/unit/test_iris_api/test_terminal_facade.py, tests/unit/test_iris_api/test_terminal_native.py |
| `src/prism/mcp/files.py` | 86% | 78 | 11 | tests/unit/test_mcp_files.py |
| `src/prism/cast/manager.py` | 86% | 211 | 29 | tests/unit/test_cast_integration.py, tests/unit/test_cli_cast.py, tests/unit/test_cli_edge_cases.py |
| `src/prism/mcp/shell.py` | 87% | 53 | 7 | tests/unit/test_mcp_shell.py |
| `src/prism/iris/sdk/log.py` | 88% | 43 | 5 | tests/unit/test_log.py |
| `src/prism/cli/commands/config.py` | 89% | 122 | 14 | tests/unit/test_cli_chatbot.py, tests/unit/test_cli_config.py, tests/unit/test_completion.py |
| `src/prism/mcp/index.py` | 89% | 9 | 1 | tests/unit/test_index.py |
| `src/prism/mcp/documents.py` | 90% | 58 | 6 | tests/integration/test_terminal_native.py, tests/unit/test_iris_api/test_documents.py, tests/unit/test_iris_api/test_terminal_native.py, tests/unit/test_iris_api/test_testing.py, tests/unit/test_tool_errors.py |
| `src/prism/mcp/monitor.py` | 91% | 11 | 1 | tests/unit/test_cli_monitor.py, tests/unit/test_iris_api/test_monitor.py, tests/unit/test_mcp_monitor.py, tests/unit/test_monitor_averages.py, tests/unit/test_monitor_collector.py, tests/unit/test_monitor_dashboard.py, tests/unit/test_monitor_event_loop.py, tests/unit/test_monitor_parser.py, tests/unit/test_monitor_scorer.py |
| `src/prism/iris/sdk/debug_session.py` | 91% | 78 | 7 | tests/unit/test_debugger.py |
| `src/prism/cli/commands/server_info.py` | 92% | 12 | 1 | tests/unit/test_iris_api/test_server_info.py |
| `src/prism/iris/api/terminal.py` | 92% | 87 | 7 | tests/integration/test_terminal_native.py, tests/unit/test_cli_interactive_ws.py, tests/unit/test_iris_api/test_interactive_ws.py, tests/unit/test_iris_api/test_terminal.py, tests/unit/test_iris_api/test_terminal_facade.py, tests/unit/test_iris_api/test_terminal_native.py |
| `src/prism/settings.py` | 93% | 95 | 7 | tests/gui/test_e2e_user_scenarios.py, tests/integration/test_background.py, tests/integration/test_debugger.py, tests/integration/test_terminal_native.py, tests/unit/test_cast_integration.py, tests/unit/test_chatbot_agent.py, tests/unit/test_cli_chatbot.py, tests/unit/test_cli_config.py, tests/unit/test_cli_interactive_ws.py, tests/unit/test_debugger.py, tests/unit/test_gui_tabs.py, tests/unit/test_iris_api/test_compile.py, tests/unit/test_iris_api/test_interactive_ws.py, tests/unit/test_iris_api/test_terminal.py, tests/unit/test_iris_api/test_terminal_facade.py, tests/unit/test_iris_api/test_terminal_native.py, tests/unit/test_iris_api/test_testing.py, tests/unit/test_mcp_files.py, tests/unit/test_mcp_shell.py, tests/unit/test_output.py, tests/unit/test_settings.py, tests/unit/test_tool_errors.py, tests/unit/test_tools.py, tests/unit/test_workspace.py |
| `src/prism/iris/api/interactive_ws.py` | 93% | 123 | 9 | tests/unit/test_iris_api/test_interactive_ws.py |
| `src/prism/cli/commands/sql.py` | 94% | 16 | 1 | tests/unit/test_cast_integration.py, tests/unit/test_cli_edge_cases.py, tests/unit/test_completion.py, tests/unit/test_iris_api/test_sql.py |
| `src/prism/mcp/_decorator.py` | 94% | 32 | 2 | tests/unit/test_output.py, tests/unit/test_tools.py |
| `src/prism/chatbot/skills.py` | 95% | 40 | 2 | tests/unit/test_chatbot_skills.py |
| `src/prism/mcp/server.py` | 96% | 23 | 1 | tests/unit/test_debugger.py, tests/unit/test_index.py, tests/unit/test_pyinstaller_compat.py, tests/unit/test_tools.py |
| `src/prism/output.py` | 96% | 23 | 1 | tests/unit/test_cast_integration.py, tests/unit/test_cli_edge_cases.py, tests/unit/test_cli_monitor.py, tests/unit/test_cli_setup.py, tests/unit/test_output.py |
| `src/prism/cli/app.py` | 96% | 54 | 2 | tests/gui/test_e2e_user_scenarios.py, tests/unit/test_cast_integration.py, tests/unit/test_cli_cast.py, tests/unit/test_cli_chatbot.py, tests/unit/test_cli_config.py, tests/unit/test_cli_edge_cases.py, tests/unit/test_cli_interactive_ws.py, tests/unit/test_cli_monitor.py, tests/unit/test_cli_setup.py, tests/unit/test_gui_tabs.py, tests/unit/test_gui_widgets.py, tests/unit/test_monitor_event_loop.py |
| `src/prism/iris/api/index.py` | 97% | 111 | 3 | tests/unit/test_index.py |
| `src/prism/iris/monitor/parser.py` | 98% | 42 | 1 | tests/unit/test_cli_monitor.py, tests/unit/test_monitor_parser.py, tests/unit/test_monitor_scorer.py |
| `src/prism/iris/monitor/scorer.py` | 98% | 90 | 2 | tests/unit/test_cli_monitor.py, tests/unit/test_mcp_monitor.py, tests/unit/test_monitor_averages.py, tests/unit/test_monitor_dashboard.py, tests/unit/test_monitor_event_loop.py, tests/unit/test_monitor_scorer.py |
| `src/prism/gui/widgets/status_bar.py` | 98% | 47 | 1 | tests/unit/test_gui_widgets.py |
| `src/prism/iris/monitor/dashboard.py` | 99% | 183 | 2 | tests/unit/test_cli_monitor.py, tests/unit/test_monitor_averages.py, tests/unit/test_monitor_dashboard.py |
| `src/prism/iris/api/compile.py` | 100% | 8 | 0 | tests/unit/test_iris_api/test_compile.py, tests/unit/test_iris_api/test_terminal_native.py, tests/unit/test_tool_errors.py |
| `src/prism/iris/api/documents.py` | 100% | 39 | 0 | tests/integration/test_terminal_native.py, tests/unit/test_iris_api/test_documents.py, tests/unit/test_iris_api/test_terminal_native.py, tests/unit/test_iris_api/test_testing.py, tests/unit/test_tool_errors.py |
| `src/prism/iris/api/monitor.py` | 100% | 12 | 0 | tests/unit/test_cli_monitor.py, tests/unit/test_iris_api/test_monitor.py, tests/unit/test_mcp_monitor.py, tests/unit/test_monitor_averages.py, tests/unit/test_monitor_collector.py, tests/unit/test_monitor_dashboard.py, tests/unit/test_monitor_event_loop.py, tests/unit/test_monitor_parser.py, tests/unit/test_monitor_scorer.py |
| `src/prism/iris/api/server_info.py` | 100% | 7 | 0 | tests/unit/test_iris_api/test_server_info.py |
| `src/prism/iris/api/sql.py` | 100% | 7 | 0 | tests/unit/test_cast_integration.py, tests/unit/test_cli_edge_cases.py, tests/unit/test_completion.py, tests/unit/test_iris_api/test_sql.py |
| `src/prism/iris/sdk/http.py` | 100% | 21 | 0 | tests/gui/test_e2e_user_scenarios.py, tests/integration/test_debugger.py, tests/unit/test_iris_api/test_sql.py, tests/unit/test_iris_api/test_terminal.py |
| `src/prism/iris/sdk/workspace.py` | 100% | 26 | 0 | tests/unit/test_tool_errors.py, tests/unit/test_workspace.py |

## 3. Source-to-Test Mapping & Depth Assessment

Mapping built by (a) scanning each test file for `prism.<module>` imports and (b) applying known name conventions (e.g. `test_monitor_parser.py` → `iris/monitor/parser.py`). Depth is assessed across four signals: **happy path**, **error/exception path** (`pytest.raises`, error/fail/404 keywords), **edge cases** (empty/none/zero/boundary/limit keywords), and **boundary conditions** (clamp/overflow/exceed/range).

### 3.1 Well-tested (≥80%, broad depth) — 32 files

Dedicated test files; happy path + error path + edge cases all present. Representative exemplars:

| Source file | Cov% | Test file | Depth |
|---|---|---|---|
| `src/prism/settings.py` | 93% | `tests/unit/test_settings.py` (28 tests) | All 28 fields enumerated (regression guard), env override, defaults, validators — error + edge + boundary |
| `src/prism/iris/sdk/workspace.py` | 100% | `tests/unit/test_workspace.py` (12 tests) | Roundtrip, nested paths, parent-dir creation, traversal blocked, 12 doc-name boundary patterns |
| `src/prism/iris/api/documents.py` | 100% | `tests/unit/test_iris_api/test_documents.py` (16 tests) | get/list/put/delete/compile + 404 + non-list content + empty content |
| `src/prism/iris/monitor/parser.py` | 98% | `tests/unit/test_monitor_parser.py` (23 tests) | Gauges, histograms, help/type lines, missing labels |
| `src/prism/iris/monitor/scorer.py` | 98% | `tests/unit/test_monitor_scorer.py` (22 tests) | 0-100 score, missing metrics, min/max/avg/variance, weighted bounds |
| `src/prism/iris/monitor/dashboard.py` | 99% | `tests/unit/test_monitor_dashboard.py` | Rich rendering: sparklines, bars, history |
| `src/prism/iris/sdk/debug_session.py` | 91% | `tests/unit/test_debugger.py` (59 tests) | XDebug lifecycle: init/step/vars/stack + connection/timeout/closed errors |
| `src/prism/iris/api/interactive_ws.py` | 93% | `tests/unit/test_iris_api/test_interactive_ws.py` (37 tests) | WebSocket terminal: connect/send/recv failures, timeouts, reconnection, encoding |
| `src/prism/chatbot/agent.py` | 77% | `tests/unit/test_chatbot_agent.py` (73 tests) | Non-streaming tool-use loop: happy + error + edge (but **streaming path untested**) |
| `src/prism/mcp/shell.py` | 87% | `tests/unit/test_mcp_shell.py` (13 tests) | Shell exec: timeout, failure, empty output, cwd |
| `src/prism/mcp/files.py` | 86% | `tests/unit/test_mcp_files.py` (23 tests) | File listing/reading: traversal, missing, glob, binary, large |
| `src/prism/cast/manager.py` | 86% | `tests/unit/test_cast_integration.py` + `test_cli_cast.py` | list/add/remove/run/update repos |
| `src/prism/mcp/server.py` | 96% | `tests/unit/test_tools.py` + `test_debugger.py` | Auto-discovery + conditional registration (with/without workspace + debug gating) |

_…plus 20 more files at ≥80% (see per-file table above) — all with happy + error + edge coverage via mocked HTTP/API responses._

### 3.2 Medium-tested (50–79%, partial depth) — 13 files

Test files exist but with meaningful gaps — typically happy path covered but **error paths, interactive/REPL branches, or specific sub-features untested**:

| Source file | Cov% | Test file | Gap |
|---|---|---|---|
| `src/prism/cli/commands/monitor.py` | 78% | `tests/unit/test_cli_monitor.py` | JSON watch loop (`_watch_json_loop`, L145-172) untested |
| `src/prism/cli/commands/terminal.py` | 78% | `tests/unit/test_iris_api/test_terminal.py` + ws tests | Native terminal init path (L38-44, L90) untested |
| `src/prism/cli/commands/cast.py` | 68% | `tests/unit/test_cli_cast.py` | `cast_callback` dispatch + lazy repo/command registration (L97-184) untested |
| `src/prism/gui/widgets/toolbar.py` | 66% | `tests/unit/test_gui_widgets.py` | Most button handlers (L163-221) untested |
| `src/prism/mcp/workspace.py` | 67% | `tests/unit/test_workspace.py` + `test_tool_errors.py` | Error/fallback branches (L51-52, L94-99) untested |
| `src/prism/mcp/compile.py` | 62% | `tests/unit/test_iris_api/test_compile.py` | `_parse_compile` + `compile_documents` error branches (L14-17, L60-61) untested |
| `src/prism/mcp/debugger.py` | 61% | `tests/unit/test_debugger.py` | Per-tool error propagation branches untested |
| `src/prism/mcp/server_info.py` | 57% | `tests/unit/test_iris_api/test_server_info.py` | Error branch (L17-19) untested |
| `src/prism/gui/widgets/results_table.py` | 55% | `tests/unit/test_gui_widgets.py` | Cell edit, save, export, filter, sort (L216-720) untested |
| `src/prism/cli/commands/testing.py` | 55% | `tests/unit/test_iris_api/test_testing.py` | CLI command bodies (L36-70) untested — only API layer tested |
| `src/prism/gui/controllers/sql_controller.py` | 53% | `tests/unit/test_gui_sql.py` + `test_gui_tabs.py` | `_run_query`/`_run_updates`/`_run_connection_check` async bodies (L217-342) untested |
| `src/prism/iris/sdk/terminal.py` | 52% | `tests/unit/test_iris_api/test_terminal_native.py` + facade | Native `_run_command_sync` (L184-221) + IRIS-Python loading (L94-119) untested |
| `src/prism/iris/api/debugger.py` | 50% | `tests/unit/test_debugger.py` | `start_session`, `_do_attach`, `step`, `manage_breakpoints`, `_set_breakpoint` (L46-667) untested |

### 3.3 Low-tested (1–49%) & Zero-coverage — 18 + 2 files

Mostly CLI command bodies, interactive REPLs, GUI widgets, and MCP tool orchestration that are registered/exercised via registration tests but whose **bodies are never executed** under unit tests:

| Source file | Cov% | Test file | Untested features/functions |
|---|---|---|---|
| `src/prism/iris/sdk/preflight.py` | 0% | **— none —** | `preflight_check()`: all 4 exception branches (ConnectError, ConnectTimeout, HTTPStatusError, RequestError) + namespace validation. **Runs on every CLI command.** |
| `src/prism/__main__.py` | 0% | **— none —** | `python -m prism` entrypoint. Trivial wrapper. |
| `src/prism/mcp/testing.py` | 15% | `tests/unit/test_iris_api/test_testing.py` (API only) | `run_tests`/`list_tests`/`get_test_results` MCP tool bodies (64 lines): SQL-error parsing, result aggregation, status mapping, assertion fetch, history grouping |
| `src/prism/cli/commands/gui.py` | 21% | GUI tests (app-level) | `gui()` launch body (L17-33) — blocking `mainloop()` |
| `src/prism/cli/commands/serve.py` | 33% | `tests/unit/test_cli_setup.py` | `serve()` stdio transport startup (L28-44) — blocking server |
| `src/prism/cli/interactive.py` | 34% | `tests/unit/test_cli_interactive_ws.py` | `run_interactive`, `_async_interactive`, `_simple_repl`, `_print_help`, `_print_startup_banner`, `_print_history`, `_format_prompt` (181 lines — largest single gap) |
| `src/prism/cli/commands/documents.py` | 38% | `tests/unit/test_iris_api/test_documents.py` (API only) | `get_doc`/`list_docs`/`put_doc`/`delete_doc` CLI bodies (L33-132) |
| `src/prism/mcp/sql.py` | 43% | `tests/unit/test_iris_api/test_sql.py` (API only) | `execute_sql` error/empty-result branch (L41-48) |
| `src/prism/cli/commands/chatbot.py` | 43% | `tests/unit/test_cli_chatbot.py` | `_async_repl` interactive loop (L282-357), banner, help, config-from-flags |
| `src/prism/cli/commands/index.py` | 44% | `tests/unit/test_index.py` (API only) | `index()` CLI body (L34-51) |
| `src/prism/iris/sdk/dbgp.py` | 46% | `tests/unit/test_debugger.py` (session-level) | `DbgpConnection`: `connect`, `send_command`, `close` (L47-137) — raw XDebug TCP protocol |
| `src/prism/gui/widgets/database_tree.py` | 47% | `tests/unit/test_gui_widgets.py` | Async schema/table/column loading, polling, expand, double-click (141 lines) |
| `src/prism/gui/theme.py` | 48% | `tests/unit/test_gui_widgets.py` | `apply_theme` (L109-300) + font helpers |
| `src/prism/iris/api/debugger.py` | 50% | `tests/unit/test_debugger.py` | see medium section |

## 4. Untested Features & Functions (Consolidated)

Ranked by risk/impact:

### Critical gaps (run in production paths)

1. **`iris/sdk/preflight.py` — `preflight_check()`** (0%): Runs before *every* CLI command. 4 exception branches + namespace-mismatch + workspace-creation all untested. A bug here breaks every CLI invocation against IRIS.
2. **`cli/interactive.py` — full REPL** (34%, 181 lines): `run_interactive`, `_async_interactive`, `_simple_repl`, help, history, prompt formatting, output rendering. The interactive ObjectScript terminal — a user-facing feature — has no body tests.
3. **`mcp/testing.py` — all 3 tool bodies** (15%, 64 lines): `run_tests`, `list_tests`, `get_test_results`. The API layer is tested but the MCP orchestration (error→fallback, status mapping `_STATUS_MAP`, assertion detail, history grouping) is not.
4. **`iris/sdk/dbgp.py` — `DbgpConnection`** (46%, 45 lines): raw XDebug protocol (`connect`, `send_command`, `close`). Higher-level `debug_session` is mocked-tested, but the actual dbgp XML exchange is not — debugger bugs at the protocol layer would surface only in integration.
5. **`iris/api/debugger.py` — debugger API glue** (50%, 162 lines): `start_session`, `_do_attach`, `step`, `manage_breakpoints`, `_set_breakpoint`. The session SDK is tested but the API layer translating MCP calls→sessions is not.
6. **`cli/commands/chatbot.py` — interactive REPL** (43%, 82 lines): `_async_repl` loop, banner, help. The `chatbot/agent.py` engine is well-tested (73 tests) but the CLI shell is not.

### Moderate gaps (CLI command bodies; API layer tested instead)

7. **`cli/commands/documents.py`** (38%): `get_doc`/`list_docs`/`put_doc`/`delete_doc` bodies — the `iris/api/documents` is 100% tested but CLI argparse→output wrapping is not.
8. **`cli/commands/testing.py`** (55%): `test`/`list_tests` bodies — same pattern.
9. **`cli/commands/index.py`** (44%): `index()` body — `iris/api/index` (97%) and `mcp/index` (89%) tested.
10. **`cli/commands/serve.py`** (33%): `serve()` stdio transport — blocking; `tests/mcp/test_mcp_protocol.py` exists but is **empty (0 test functions)**.
11. **`cli/commands/gui.py`** (21%): `gui()` launch — blocking `mainloop()`; covered transitively by app-level GUI tests.

### Moderate gaps (GUI widgets — require display)

12. **`gui/widgets/results_table.py`** (55%, 163 lines): cell edit, save, export, filter, sort.
13. **`gui/controllers/sql_controller.py`** (53%, 88 lines): async query execution, polling, cancel, connection check, updates.
14. **`gui/widgets/database_tree.py`** (47%, 141 lines): async schema/table/column loading, expand, double-click.
15. **`gui/theme.py`** (48%, 61 lines): `apply_theme` + font selection.
16. **`gui/widgets/toolbar.py`** (66%): button handlers.
17. **`gui/app.py`** (76%): `_execute_query`, `_on_query_done`, `_open_file`, `_save_file`, `launch`.

### Minor gaps (error/edge branches in tested files)

18. **`chatbot/agent.py`** (77%): `_call_llm_streaming` (44 lines, the streaming response path) + `_trim_if_needed` + retry-with-backoff — non-streaming path well-tested.
19. **`mcp/sql.py`** (43%): `execute_sql` error branch (L41-48).
20. **`mcp/server_info.py`** (57%): error branch (L17-19).
21. **`mcp/debugger.py`** (61%): per-tool error propagation (1 line each).
22. **`mcp/compile.py`** (62%): `_parse_compile` + error branch.
23. **`mcp/workspace.py`** (67%): `put_and_compile` error/fallback (L94-99).
24. **`cli/commands/cast.py`** (68%): `cast_callback` dispatch + lazy registration.
25. **`cli/commands/install.py`** (84%): `_patch_hermes` (25 lines) — Hermes-specific installer untested.
26. **`cli/commands/monitor.py`** (78%): JSON watch loop.
27. **`iris/sdk/log.py`** (88%): redaction branch (L26-30).
28. **`iris/api/testing.py`** (82%): assertion-detail fetch (L174-200).
29. **`iris/sdk/terminal.py`** (52%): native `_run_command_sync` + IRIS-Python loading (WebSocket path well-tested).

## 5. Coverage Estimate & Summary

**Estimated overall line coverage: ~70%** (5614 statements, 1690 uncovered), measured by pytest-cov over the unit suite only.

### Where coverage is strong

- **IRIS REST API layer** (`iris/api/`): 7/12 files at **100%**, rest ≥82%. Mocked HTTP responses drive happy + error + edge cases.
- **Monitor subsystem** (`iris/monitor/`): parser/scorer/dashboard/collector all **97–100%** with dedicated depth-rich test files (23/22/N tests).
- **Workspace/security** (`iris/sdk/workspace.py`): **100%** with explicit path-traversal and doc-name boundary tests.
- **Settings** (`settings.py`): **93%** with a 28-field regression guard.
- **MCP tool registration** (`mcp/server.py`, `mcp/__init__.py`, `mcp/_decorator.py`): 94–96% — conditional/gated registration well-tested.
- **Chatbot agent (non-streaming)** (`chatbot/agent.py`): 73 tests covering the tool-use loop happy + error + edge.
- **Debugger session SDK** (`iris/sdk/debug_session.py`): 91% with 59 tests.

### Where coverage is weak

- **CLI command bodies** (documents 38%, index 44%, chatbot 43%, serve 33%, testing 55%, gui 21%): registration tested but bodies untested — the API layer is tested instead, leaving the argparse→output wrapping unverified.
- **Interactive REPLs** (`cli/interactive.py` 34%, `cli/commands/chatbot.py` 43%): the full interactive ObjectScript/chatbot REPL loops are untested.
- **MCP tool orchestration** (`mcp/testing.py` 15%, `mcp/sql.py` 43%, `mcp/server_info.py` 57%): tool registration is tested but the tool bodies that aggregate/transform API responses are not.
- **Debugger low-level + API** (`iris/sdk/dbgp.py` 46%, `iris/api/debugger.py` 50%): raw XDebug protocol + API glue untested; only the session SDK is mocked-tested.
- **GUI widgets** (results_table 55%, sql_controller 53%, database_tree 47%, theme 48%, toolbar 66%): async loading, cell editing, saving, export, theming largely untested (require display).
- **Streaming** (`chatbot/agent.py` `_call_llm_streaming`): the streaming LLM response path is entirely untested (44 lines).
- **Preflight** (`iris/sdk/preflight.py`): **0%** — runs on every CLI command; no tests at all.

### Estimated coverage by subsystem

| Subsystem | Est. coverage | Notes |
|---|---|---|
| `iris/api/` | ~88% | Strong; debugger API is the weak link (50%) |
| `iris/sdk/` | ~70% | workspace/http 100%, but dbgp 46%, terminal 52%, preflight 0% |
| `iris/monitor/` | ~98% | Excellent across parser/scorer/dashboard/collector |
| `mcp/` | ~75% | Registration strong; tool bodies (testing/sql/server_info) weak |
| `cli/` | ~65% | App/edge-cases strong; command bodies + REPLs weak |
| `gui/` | ~62% | status_bar 98%, sql_editor 74%, but table/tree/theme/controller 47–55% |
| `chatbot/` | ~80% | Agent solid (77%) but streaming path + CLI shell weak |
| `cast/` | ~85% | Manager well-tested; CLI lazy-registration gaps |
| `settings.py` / `output.py` | ~95% | Strong |

### Top recommendations (by ROI)

1. **Add unit tests for `preflight_check`** — mock `httpx.get` to hit all 4 exception branches + namespace mismatch. Highest risk, easy to test. (~6 tests → file 0%→~95%.)
2. **Add unit tests for `mcp/testing.py` tool bodies** — mock `testing_api` to exercise error→fallback, status mapping, assertion detail, history grouping. (The API layer is already mocked-tested; the orchestration is not.) (~15 tests → 15%→~90%.)
3. **Add unit tests for CLI command bodies** (`documents`, `testing`, `index`, `monitor` JSON watch) — the API layer is mocked; wrap with a CliRunner and assert output. (~30 tests across 4 files.)
4. **Add unit tests for `chatbot/agent.py` streaming path** (`_call_llm_streaming`) — mock the streaming response. (~8 tests → 77%→~92%.)
5. **Add unit tests for `iris/sdk/dbgp.py`** (`DbgpConnection.connect/send_command`) — mock the socket. (~10 tests → 46%→~85%.)
6. **Populate `tests/mcp/test_mcp_protocol.py`** — currently empty; add MCP protocol-level round-trip tests against a FastMCP `Client` (the integration conftest already sets this up).
7. **GUI** — promote more logic into non-tkinter pure functions (results-table save/export, controller update batching) and unit-test those; keep display-dependent paths in `tests/gui/`.
8. **Add `pytest-cov` to dev dependencies** and a `--cov` CI gate (e.g. fail under 75%) to prevent regression.

---

**Method note:** Coverage was measured with `coverage.py` (not declared in `pyproject.toml`); adding `pytest-cov` to the `dev` dependency group would let CI track this. The source→test mapping was derived by import scanning + name conventions; a few mappings are transitive (e.g. `iris/sdk/http.py` is covered via mocked API tests that import it), which is noted where relevant.