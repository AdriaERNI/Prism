---
name: vagrant-integration-tests
description: Run the Prism Windows integration test suite via Vagrant (libvirt/KVM + WinRM). Covers building the installer, installing it in the Windows VM, running PowerShell smoke tests against the packaged prism.exe, and reading test logs. Use when the user asks to run, verify, or debug Windows integration tests.
---

# Vagrant Windows Integration Tests

Prism's Vagrant integration tests verify the **packaged Windows build** (PyInstaller + Inno Setup) by installing prism.exe in a Windows Server 2022 VM with IRIS Community and running 15 PowerShell smoke test suites against it.

## Prerequisites

```bash
# All vagrant commands MUST run from vagrant/ directory
cd ~/Projects/ERNI/Prism/vagrant

# Check VM is running
vagrant status    # expect: running (libvirt)

# Check IRIS is up (inside VM)
vagrant winrm --shell powershell --command \\
  "(Test-NetConnection -ComputerName 127.0.0.1 -Port 52773).TcpTestSucceeded"

# Check IRIS REST API (from host, forwarded port)
curl -s -o /dev/null -w "%{http_code}" \\
  -H "Authorization: Basic $(echo -n '_SYSTEM:SYS' | base64)" \\
  http://localhost:52774/api/atelier/v8/USER
# Expect: 200
```

If the VM is not running, see the `vagrant-up` skill first.

## Full pipeline (3 steps)

### Step 1: vagrant up (first time only, ~20-30 min)

```bash
cd ~/Projects/ERNI/Prism/vagrant
vagrant up --provider=libvirt
```

Idempotent — if already running, just reattaches. Provisions IRIS + build tools on first run.

### Step 2: Build the Windows installer

```bash
cd ~/Projects/ERNI/Prism
bash vagrant/build-windows.sh
```

Produces `dist/prism-<version>-setup.exe`. Uploads source to VM, runs uv sync + PyInstaller + Inno Setup inside Windows, downloads artifacts back.

Success indicator: `BUILD_SUCCESS` in output, and `dist/prism-*.exe` files exist.

### Step 3: Run integration tests

```bash
cd ~/Projects/ERNI/Prism

# Full suite (WARNING: test 14-serve hangs WinRM, see Known Issues)
bash vagrant/run-integration-tests.sh

# Subset by filter (glob pattern on test filename)
bash vagrant/run-integration-tests.sh --filter "*sql*"
bash vagrant/run-integration-tests.sh --filter "0[1-6]*"    # tests 01-06
bash vagrant/run-integration-tests.sh --filter "0[89]*"     # tests 08-09 (put-doc, get-doc)
bash vagrant/run-integration-tests.sh --filter "1[0-3]*"    # tests 10-13 (compile, delete, list-tests, test)

# Keep prism installed after tests (for manual inspection)
bash vagrant/run-integration-tests.sh --keep-installed
```

Success indicator: `RUNALL_RESULT=PASS` and `==> Integration tests PASSED` in output.

## Recommended run pattern (avoids hangs)

The full `*` filter includes test 14 (serve) which hangs WinRM indefinitely because `prism serve` starts a background HTTP server that blocks the WinRM session. Run tests in two batches instead:

```bash
# Batch 1: tests 01-06, 08-09 (help, config, info, sql, terminal, ws, put-doc, get-doc)
bash vagrant/run-integration-tests.sh --filter "0[1-689]*"

# Batch 2: tests 10-13 (compile, delete-doc, list-tests, test)
# NOTE: These depend on put-doc (08) having run first!
# Run them as a second invocation right after batch 1 without uninstalling:
bash vagrant/run-integration-tests.sh --filter "1[0-3]*" --keep-installed
```

Alternatively, run everything except 07 and 14-15:
```bash
bash vagrant/run-integration-tests.sh --filter "0[1-689]*"
# then
bash vagrant/run-integration-tests.sh --filter "1[0-3]*"
```

## Test inventory

| # | File | Suite | Tests | What it verifies |
|---|------|-------|-------|------------------|
| 01 | 01-help.ps1 | help | 14 | All subcommands appear in --help |
| 02 | 02-config.ps1 | config | 9 | Config display, redaction, set/remove/reset |
| 03 | 03-info.ps1 | info | 3 | Server info JSON, version, TOON format |
| 04 | 04-sql.ps1 | sql | 7 | SELECT, arithmetic, system classes, errors, namespace, TOON |
| 05 | 05-terminal.ps1 | terminal (native) | 6 | ObjectScript via irisnative, quoting, timeout |
| 06 | 06-ws.ps1 | ws | 4 | WebSocket terminal, quoting, timeout |
| 07 | 07-list-docs.ps1 | list-docs | 2 | **SLOW** — IRIS returns thousands of ENSLIB classes, may timeout at 120s |
| 08 | 08-put-doc.ps1 | put-doc | 6 | Upload .cls/.mac/.inc, overwrite, missing file |
| 09 | 09-get-doc.ps1 | get-doc | 4 | Retrieve class/routine, namespace, non-existent |
| 10 | 10-compile.ps1 | compile | 6 | Compile class/routine, flags, namespace, non-existent |
| 11 | 11-delete-doc.ps1 | delete-doc | 3 | Delete class, non-existent, namespace |
| 12 | 12-list-tests.ps1 | list-tests | 4 | List test classes, filter, namespace |
| 13 | 13-test.ps1 | test | 4 | Run unit tests, single method, namespace, non-existent |
| 14 | 14-serve.ps1 | serve | 3 | **HANGS WinRM** — starts background HTTP server |
| 15 | 15-output-format.ps1 | output-format | ~3 | Global --format flag |

## Test dependencies

Tests 10 (compile) and 11 (delete-doc) depend on test 08 (put-doc) having uploaded documents first. When running with a filter that excludes 08, these tests will fail with "Class does not exist" / "Document not found". This is expected — run 08 before 10-11.

## Known issues

1. **Test 14 (serve) hangs WinRM**: `prism serve` starts a background HTTP server. WinRM waits for all child processes to exit, so the `vagrant winrm` command blocks indefinitely. Workaround: run with `--filter` excluding serve, or run serve tests manually inside the VM.

2. **Test 07 (list-docs) may timeout**: `prism list-docs -n USER -t cls` returns the entire USER namespace document list, which includes thousands of ENSLIB/IRISLIB classes. The PyInstaller-packaged prism.exe may take >120s to process this. The test framework kills hung processes after 120s.

3. **Test 13 (test -m method)**: The assertion `Assert-Contains $r.Stdout "TestAddition"` may fail because the test method name appears in a different JSON field than expected. The test actually passes (output shows "All PASSED") but the assertion doesn't find the string in the right place.

## Reading test logs

### Where logs are

- **Install log**: `C:\prism-tests\install.log` (inside VM)
- **Serve logs**: `C:\prism-tests\serve.out.log`, `C:\prism-tests\serve.err.log` (inside VM)
- **Host-side logs**: The bash runner streams output to stdout. Capture with `tee`:
  ```bash
  bash vagrant/run-integration-tests.sh --filter "*sql*" 2>&1 | tee /tmp/test.log
  ```

### Reading pass/fail from logs

```bash
# Quick summary
grep -E '\[PASS\]|\[FAIL\]|RUNALL_RESULT|Total:|Passed:|Failed:' /tmp/test.log

# Just failures with details
grep -B1 -A3 'FAIL' /tmp/test.log
```

### Reading logs inside the VM

```bash
cd ~/Projects/ERNI/Prism/vagrant

# IRIS httpd error logs (when IRIS won't start)
vagrant winrm --shell powershell --command \\
  "Get-ChildItem 'C:\InterSystems\IRIS\httpd\logs' | ForEach-Object { Write-Host '---'; Get-Content \$_.FullName -Tail 20 }"

# Prism install log
vagrant winrm --shell powershell --command "Get-Content C:\prism-tests\install.log -Tail 50"

# Serve output (if test 14 ran before hanging)
vagrant winrm --shell powershell --command "Get-Content C:\prism-tests\serve.out.log"
```

### Diagnosing failures

1. Check if IRIS is up: `curl -s -o /dev/null -w "%{http_code}" http://localhost:52774/api/atelier/v8/USER`
2. Check if prism is installed: `vagrant winrm --shell powershell --command "& 'C:\Program Files\prism\prism.exe' --help"`
3. Check prism config: `vagrant winrm --shell powershell --command "& 'C:\Program Files\prism\prism.exe' config"`
4. Run a single test manually:
   ```bash
   vagrant winrm --shell powershell --command \\
     "powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\run-all.ps1 -Filter '*sql*' -SkipSetup"
   ```
5. Check WinRM exit code gotcha: `vagrant winrm` exits 0 even on inner failure. Look for `RUNALL_RESULT=PASS/FAIL` sentinel.

## Manual test execution inside the VM

```bash
cd ~/Projects/ERNI/Prism/vagrant

# Install prism manually
vagrant winrm --shell powershell --command \\
  "powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\install.ps1"

# Configure
vagrant winrm --shell powershell --command \\
  "powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\setup-test-env.ps1"

# Run specific tests
vagrant winrm --shell powershell --command \\
  "powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\run-all.ps1 -Filter '*sql*'"

# Uninstall
vagrant winrm --shell powershell --command \\
  "powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\uninstall.ps1"
```
