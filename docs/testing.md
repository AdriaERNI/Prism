# Testing

Prism has four test layers that build on each other: unit tests (no IRIS),
integration tests against a live IRIS instance, GUI tests for the tkinter
SQL editor, and Windows packaging tests via Vagrant.

## Test layers at a glance

| Layer | Where | Runs on | Needs IRIS? | What it catches |
|-------|-------|---------|-------------|-----------------|
| **Unit** | `tests/unit/` | Linux (host) | No | Logic errors, API wire-format, settings, CLI arg parsing |
| **Integration** | `tests/integration/` | Linux (host) | Yes | End-to-end MCP tool calls against a real IRIS server |
| **GUI** | `tests/gui/` | Linux (host) | No* | GUI widget behavior, visual regression, E2E user scenarios |
| **Windows Vagrant** | `vagrant/scripts/` | Windows VM | Yes (in-VM) | PyInstaller bundling gaps, PATH issues, installer behavior, native lib loading |

*GUI tests that need a display skip in headless environments.

## Quick start

```bash
# Lint (must pass before any commit)
uv run ruff check . && uv run ruff format --check .

# Unit tests (no IRIS needed — 586 tests, < 1s)
uv run pytest tests/unit/ -v

# Integration tests (need a running IRIS instance — 87 tests)
IRIS_BASE_URL=http://<iris-host>:52773 uv run pytest tests/integration/ -v

# GUI tests (29 tests, needs a display)
uv run pytest tests/gui/ -v

# Windows packaging tests (need Vagrant VM with IRIS)
cd vagrant && vagrant up --provider=libvirt      # first time only
bash vagrant/build-windows.sh                      # build the installer
bash vagrant/run-integration-tests.sh               # run the tests
```

---

## 1. Unit tests (Linux, no IRIS required)

Unit tests verify the Python logic without connecting to IRIS. They mock HTTP
responses with `httpx.MockTransport` and run in under a second.

### Run

```bash
uv run pytest tests/unit/ -v
```

### What they cover

- `test_cli_config.py` — CLI config command (display, set, remove, reset, redaction)
- `test_cli_cast.py` — Cast plugin CLI commands (add, list, delete, update, run)
- `test_cli_edge_cases.py` — CLI edge cases and error handling
- `test_cli_interactive_ws.py` — Interactive WebSocket terminal CLI
- `test_cli_setup.py` — `prism setup` command (MCP registration in external tools)
- `test_cast_integration.py` — Cast plugin integration (importlib, registry, cache)
- `test_completion.py` — Shell completion generation
- `test_debugger.py` — Debug session lifecycle, stepping, breakpoints, variable inspection
- `test_gui_sql.py` — GUI SQL controller and query execution logic
- `test_gui_widgets.py` — GUI widget unit tests (tree, editor, results table, toolbar)
- `test_index.py` — Code indexing tool and CLI
- `test_settings.py` — Settings loading precedence (env > .env > config.json > defaults)
- `test_output.py` — Output format support (JSON, TOON)
- `test_pyinstaller_compat.py` — PyInstaller frozen build compatibility checks
- `test_tool_errors.py` — Tool error handling, invalid document names, path traversal protection
- `test_tools.py` — MCP tool registration and workspace conditional loading
- `test_workspace.py` — Workspace path resolution, validation, save/load roundtrip
- `test_log.py` — Logging configuration
- `test_iris_api/` — IRIS REST API wire-format tests (mocked HTTP)

### Writing a unit test

```python
import httpx
from unittest.mock import patch
from prism.iris.api import my_api

def mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))

async def test_my_api():
    def handler(request):
        return httpx.Response(200, json={"result": "ok"})

    with patch.object(my_api, "client", lambda: mock_client(handler)):
        result = await my_api.my_operation("test")
        assert result["result"] == "ok"
```

---

## 2. Integration tests (Linux, requires live IRIS)

Integration tests call the MCP tools through a FastMCP `Client` against a real
IRIS instance. They auto-skip if IRIS is unreachable.

### Prerequisites

You need a running IRIS server. Options:

=== "Docker (fastest)"

    ```bash
    docker run --name my-iris -d --publish 1972:1972 --publish 52773:52773 \
      intersystemsdc/iris-community:latest
    ```

    IRIS will be at `http://localhost:52773` with credentials `_SYSTEM / SYS`.

=== "Vagrant VM"

    If you already have the Vagrant VM running (see section 3 below), connect
    directly to the VM's IP instead of the forwarded port:

    ```bash
    # Get the VM IP
    cd vagrant && vagrant ssh-config 2>/dev/null | awk '/HostName/ {print $2}'
    # Use that IP, e.g. http://192.168.121.170:52773
    ```

    !!! note
        The Vagrantfile's `forwarded_port` directive does not work reliably
        with the libvirt provider. Connect directly to the VM's IP on port
        52773 instead of `localhost:52774`.

=== "Existing IRIS"

    Point the tests at any reachable IRIS instance:

    ```bash
    IRIS_BASE_URL=http://<host>:52773 \
    IRIS_USERNAME=_SYSTEM \
    IRIS_PASSWORD=SYS \
    uv run pytest tests/integration/ -v
    ```

### Run

```bash
IRIS_BASE_URL=http://localhost:52773 uv run pytest tests/integration/ -v
```

### What they cover

- `test_sql.py` — SELECT, expressions, string/date functions, invalid SQL, namespace override
- `test_documents.py` — Put/get/delete for .cls, .mac, .inc; overwrite, non-existent
- `test_document_slicing.py` — Document content slicing (head, tail, from_line, to_line)
- `test_compile.py` — Compile classes, routines, custom flags, non-existent class
- `test_terminal.py` — ObjectScript via native and WebSocket backends (parametrized)
- `test_terminal_native.py` — Native terminal helper auto-deploy
- `test_testing.py` — Run unit tests, list test classes, test history, auto-deploy runner
- `test_debugger.py` — Debug start/stop, stepping, breakpoints, variable inspection, process discovery
- `test_debugger_extra.py` — Extended debugger scenarios (skips if XDebug unavailable)
- `test_e2e.py` — Full create-compile-insert-select roundtrip, SQL procs, embedded objects
- `test_index.py` — Code indexing against a live IRIS namespace
- `test_server_info.py` — Server version, namespaces
- `test_background.py` — Background-capable tools

### Key fixtures

| Fixture | What it does |
|---------|-------------|
| `client` | In-process FastMCP `Client` with workspace and debugger tools enabled |
| `live` | Connected client; **skips the test** if IRIS is unreachable |
| `workspace` | Temporary directory for test fixtures |
| `cleanup` | Auto-deletes test documents after each test |
| `terminal_method` | Parametrizes terminal tests over `native` and `ws` backends |

### Writing an integration test

```python
async def test_with_iris(live, cleanup):
    result = await live.call_tool("execute_sql", {"query": "SELECT 1"})
    cleanup("Test.MyDoc.cls")  # auto-delete after test
```

---

## 3. GUI tests (Linux, requires a display)

GUI tests verify the tkinter SQL editor — widget behavior, visual layout
regression, and end-to-end user scenarios (connect, execute, edit results).

### Run

```bash
uv run pytest tests/gui/ -v
```

Tests that need a display skip automatically in headless environments.

### What they cover

- `test_gui_interactions.py` — Widget interactions (clicks, typing, tab switching)
- `test_visual_regression.py` — Visual layout regression (geometry, colours, element positions)
- `test_e2e_user_scenarios.py` — Full user workflows (connect → query → edit → save)

### Key fixtures

| Fixture | What it does |
|---------|-------------|
| `root` | Creates a temporary `tk.Tk()` root window |
| `gui` | Instantiates `PrismGUI` with mocked controller |
| `mock_controller` | Replaces `SQLController` with a mock for isolated widget tests |

---

## 4. Windows Vagrant tests (requires Vagrant + KVM)

These tests verify the **packaged Windows build** — the PyInstaller-bundled
`prism.exe` installed via Inno Setup. They catch issues invisible to the pytest
suites: missing native libraries, PATH registration, installer behavior, and
Windows-specific runtime errors.

### Architecture

```
Host (Linux)                          Windows VM (libvirt/KVM)
─────────────                         ──────────────────────
build-windows.sh ──upload source──►   uv sync + PyInstaller → prism.exe
                                      Inno Setup → prism-<ver>-setup.exe
                ◄──download artifacts── dist/

run-integration-tests.sh
  ├── upload installer + test bundle
  ├── install.ps1 ──►  Inno silent install → C:\Program Files\prism\
  ├── setup-test-env   prism config → VM-local IRIS (_SYSTEM/SYS)
  ├── run-all.ps1      15 PowerShell test suites against prism.exe
  ├── teardown         cleanup test docs + reset config
  └── uninstall.ps1   Inno silent uninstall
```

### Prerequisites

- **Vagrant** 2.4+ with `vagrant-libvirt` plugin
- **KVM** support (nested virtualization if running inside a VM)
- **libvirt** daemon running with default network active
- **~20 GB disk** for the Windows VM image
- **4 GB RAM** available for the VM

```bash
# Install prerequisites (Ubuntu/Debian)
sudo apt install qemu-system-x86 libvirt-daemon-system libvirt-clients \
     bridge-utils dnsmasq-base vagrant
vagrant plugin install vagrant-libvirt

# Verify KVM is available
ls -la /dev/kvm  # should exist
```

### Step 1: Start the VM (first time, ~20-30 min)

```bash
cd vagrant
vagrant up --provider=libvirt
```

This boots a Windows Server 2022 VM and provisions it:

1. **DNS** — configure 8.8.8.8 on network adapters
2. **Build tools** — Chocolatey, Python 3.12, Inno Setup, uv
3. **IRIS** — silent install InterSystems IRIS Community 2025.3
4. **httpd fix** — add missing `Listen 52773` directive
5. **Verify** — configure firewall, start IRIS services, verify REST API responds

!!! tip
    This is idempotent. If the VM is already running, `vagrant up` just
    reattaches and exits. Re-provision with `vagrant up --provision` or
    `vagrant up --provision-with=verify` to re-run specific provisioners.

### Step 2: Build the Windows installer

```bash
bash vagrant/build-windows.sh
```

This uploads the project source to the VM, runs `uv sync` + PyInstaller +
Inno Setup inside Windows, and downloads the artifacts to `dist/`:

- `dist/prism-<version>.exe` — standalone PyInstaller binary
- `dist/prism-<version>-setup.exe` — Inno Setup installer (adds to PATH)

Success indicator: `BUILD_SUCCESS` in output.

### Step 3: Run the integration tests

```bash
# Full suite
bash vagrant/run-integration-tests.sh

# Subset (glob pattern on test filename)
bash vagrant/run-integration-tests.sh --filter "*sql*"
bash vagrant/run-integration-tests.sh --filter "0[1-6]*"   # tests 01-06
bash vagrant/run-integration-tests.sh --filter "0[89]*"    # put-doc, get-doc
bash vagrant/run-integration-tests.sh --filter "1[0-3]*"   # compile, delete, tests

# Keep prism installed after tests (for manual inspection)
bash vagrant/run-integration-tests.sh --keep-installed
```

Success indicator: `RUNALL_RESULT=PASS` and `==> Integration tests PASSED`.

### Recommended run pattern

The `serve` test (14) starts a background HTTP server that blocks WinRM
indefinitely. Run in two batches to avoid the hang:

```bash
# Batch 1: tests 01-06, 08-09 (no dependency issues, no serve)
bash vagrant/run-integration-tests.sh --filter "0[1-689]*"

# Batch 2: tests 10-13 (depend on put-doc having run, so run right after)
bash vagrant/run-integration-tests.sh --filter "1[0-3]*"
```

### Test inventory

| # | File | Suite | Tests | What it verifies |
|---|------|-------|-------|------------------|
| 01 | `01-help.ps1` | help | 17 | All subcommands appear in `--help` |
| 02 | `02-config.ps1` | config | 9 | Config display, redaction, set/remove/reset |
| 03 | `03-info.ps1` | info | 3 | Server info JSON, version, TOON format |
| 04 | `04-sql.ps1` | sql | 7 | SELECT, arithmetic, system classes, errors, namespace, TOON |
| 05 | `05-terminal.ps1` | terminal (native) | 6 | ObjectScript via irisnative, quoting, timeout |
| 06 | `06-ws.ps1` | ws | 4 | WebSocket terminal, quoting, timeout |
| 07 | `07-list-docs.ps1` | list-docs | 2 | **Slow** — may timeout on large namespaces |
| 08 | `08-put-doc.ps1` | put-doc | 6 | Upload .cls/.mac/.inc, overwrite, missing file |
| 09 | `09-get-doc.ps1` | get-doc | 4 | Retrieve class/routine, namespace, non-existent |
| 10 | `10-compile.ps1` | compile | 6 | Compile class/routine, flags, namespace, non-existent |
| 11 | `11-delete-doc.ps1` | delete-doc | 3 | Delete class, non-existent, namespace |
| 12 | `12-list-tests.ps1` | list-tests | 4 | List test classes, filter, namespace |
| 13 | `13-test.ps1` | test | 4 | Run unit tests, single method, namespace, non-existent |
| 14 | `14-serve.ps1` | serve | 3 | **Hangs WinRM** — starts background HTTP server |
| 15 | `15-output-format.ps1` | output-format | ~3 | Global `--format` flag |
| — | `test_mcp_tools.py` | mcp-protocol | — | Deep MCP protocol tests (run from Windows CI) |

### Test dependencies

Tests 10 (compile) and 11 (delete-doc) depend on test 08 (put-doc) having
uploaded documents first. When running with a filter that excludes 08,
these tests will fail with "Class does not exist" or "Document not found".
This is expected — always include 08 when running 10-11.

### Known issues

**Test 14 (serve) hangs WinRM**
:   `prism serve` starts a background HTTP server. WinRM waits for all child
    processes to exit, blocking indefinitely. Workaround: exclude test 14
    from runs using `--filter`.

**Test 07 (list-docs) may timeout**
:   `prism list-docs -n USER -t cls` returns thousands of ENSLIB/IRISLIB
    classes. The PyInstaller-packaged binary may exceed the 120s timeout.
    To fix: increase `$script:PrismTimeoutSec` in `_common.ps1`.

**Test 13 (`-m` method assertion)**
:   The assertion checks for the method name in stdout, but the JSON response
    puts it in a nested field. The test actually passes (output shows "All
    PASSED") but the assertion doesn't find the string. Fix pending.

---

## Reading test logs

### Host-side logs

The bash runners stream output to stdout. Capture with `tee`:

```bash
# Integration test log
bash vagrant/run-integration-tests.sh --filter "*sql*" 2>&1 | tee /tmp/test.log

# Build log
bash vagrant/build-windows.sh 2>&1 | tee /tmp/build.log
```

Quick summary from a saved log:

```bash
# Pass/fail summary
grep -E '\[PASS\]|\[FAIL\]|RUNALL_RESULT|Total:|Passed:|Failed:' /tmp/test.log

# Just failures with context
grep -B1 -A3 'FAIL' /tmp/test.log
```

### Inside the VM

| Path | What |
|------|------|
| `C:\prism-tests\install.log` | Inno Setup install log |
| `C:\prism-tests\serve.out.log` | `prism serve` stdout (test 14) |
| `C:\prism-tests\serve.err.log` | `prism serve` stderr (test 14) |
| `C:\InterSystems\IRIS\httpd\logs\` | IRIS Apache httpd error logs |
| `C:\InterSystems\IRIS\mgr\messages.log` | IRIS system messages log |

Read logs inside the VM:

```bash
cd vagrant

# IRIS httpd error logs
vagrant winrm --shell powershell --command \
  "Get-ChildItem 'C:\InterSystems\IRIS\httpd\logs' | ForEach-Object { Write-Host '---'; Get-Content \$_.FullName -Tail 20 }"

# Prism install log
vagrant winrm --shell powershell --command "Get-Content C:\prism-tests\install.log -Tail 50"

# IRIS services status
vagrant winrm --shell powershell -e --command \
  "Get-Service ISCAgent,IRIS_c-_intersystems_iris,IRIShttpd | Format-Table Name,Status -AutoSize"
```

---

## CI

GitHub Actions runs on every push and pull request to `main` and
`development` branches. The CI pipelines are:

| Workflow | File | What it runs |
|----------|------|--------------|
| **Test Linux** | `.github/workflows/test-linux.yml` | Lint (`ruff check` + `ruff format --check`), Unit tests, Integration tests (Docker IRIS) |
| **Test Windows** | `.github/workflows/test-windows.yml` | Unit tests, PyInstaller build verification |
| **Build and Release** | `.github/workflows/build-release.yml` | Full pipeline: Lint → Test Linux/Windows → Build wheel + exe → GitHub Release (triggered by `v*` tags) |
| **GitHub Pages** | `.github/workflows/pages.yml` | MkDocs build + deploy to GitHub Pages (on push to `main`) |

The Linux integration tests run against an `intersystemsdc/iris-community:latest`
Docker container with both port 52773 (Atelier REST API) and port 1972
(SuperServer for native terminal) exposed.

---

## Troubleshooting

### Integration tests fail with "ConnectError: All connection attempts failed"

IRIS is not reachable. Check:

```bash
# Is IRIS listening?
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Basic $(echo -n '_SYSTEM:SYS' | base64)" \
  http://<iris-host>:52773/api/atelier/v8/USER
# Expect: 200
```

### Vagrant: "Permission denied" on libvirt socket

```bash
sudo usermod -aG libvirt,libvirt-qemu $USER
sudo chmod 666 /var/run/libvirt/libvirt-sock  # or reboot to pick up group
```

### Vagrant: WinRM connection refused after boot

Windows is still booting. Wait 30s and retry:

```bash
cd vagrant && vagrant up --provider=libvirt  # idempotent
```

### Vagrant: IRIS web server not starting

Re-run the verify provisioner:

```bash
cd vagrant && vagrant up --provider=libvirt --provision-with=verify
```

Check httpd error logs:

```bash
vagrant winrm --shell powershell --command \
  "Get-ChildItem 'C:\InterSystems\IRIS\httpd\logs' | ForEach-Object { Write-Host '---'; Get-Content \$_.FullName -Tail 20 }"
```

### Vagrant: `vagrant up` from repo root fails

All `vagrant` commands must run from the `vagrant/` directory:

```bash
cd vagrant  # then run vagrant up / status / winrm / etc. here
```