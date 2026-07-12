---
name: vagrant-logs
description: Read and diagnose Vagrant Windows VM logs for Prism integration tests — IRIS httpd logs, prism install logs, serve output, WinRM communication issues, and test failure analysis. Use when tests fail, IRIS won't start, prism won't install, or WinRM hangs.
---

# Reading Vagrant VM Logs and Diagnosing Issues

## Log locations

### Host-side logs

| Location | What |
|----------|------|
| `bash vagrant/run-integration-tests.sh 2>&1 \| tee /tmp/test.log` | Full test run output |
| `bash vagrant/build-windows.sh 2>&1 \| tee /tmp/build.log` | Full build output |
| `/tmp/prism-install.log` | Install result (created by run-integration-tests.sh) |
| `dist/prism-<ver>-setup.exe` | Built installer artifact |

### Inside the VM

| Path | What |
|------|------|
| `C:\prism-tests\install.log` | Inno Setup install log |
| `C:\prism-tests\serve.out.log` | prism serve stdout (test 14) |
| `C:\prism-tests\serve.err.log` | prism serve stderr (test 14) |
| `C:\InterSystems\IRIS\httpd\logs\` | IRIS Apache httpd error logs |
| `C:\InterSystems\IRIS\mgr\messages.log` | IRIS system messages log |
| `C:\ProgramData\chocolatey\logs\chocolatey.log` | Chocolatey package install log |

## Quick diagnostics

### Is the VM running?

```bash
cd ~/Projects/ERNI/Prism/vagrant
vagrant status    # running (libvirt) = OK
```

### Is WinRM responsive?

```bash
vagrant winrm --shell powershell --command "whoami; \$PWD"
# Expect: prism-win\vagrant and a path
```

If WinRM hangs: Windows is still booting. Wait 30s and retry `vagrant up` (idempotent).

### Is IRIS listening?

```bash
# Inside VM
vagrant winrm --shell powershell --command \\
  "(Test-NetConnection -ComputerName 127.0.0.1 -Port 52773).TcpTestSucceeded"
# Expect: True

# From host (forwarded port)
curl -s -o /dev/null -w "%{http_code}" \\
  -H "Authorization: Basic $(echo -n '_SYSTEM:SYS' | base64)" \\
  http://localhost:52774/api/atelier/v8/USER
# Expect: 200
```

### Is prism installed?

```bash
vagrant winrm --shell powershell --command \\
  "& 'C:\Program Files\prism\prism.exe' --version"
```

### Is prism config correct?

```bash
vagrant winrm --shell powershell --command \\
  "& 'C:\Program Files\prism\prism.exe' config"
# Should show: iris_base_url=http://localhost:52773, username=_SYSTEM, namespace=USER
```

## Common failures and fixes

### IRIS web server not starting

```bash
# Check IRIS services
vagrant winrm --shell powershell -e --command \\
  "Get-Service ISCAgent,IRIS_c-_intersystems_iris,IRIShttpd | Format-Table Name,Status -AutoSize"

# Check httpd error logs
vagrant winrm --shell powershell --command \\
  "Get-ChildItem 'C:\InterSystems\IRIS\httpd\logs' | ForEach-Object { Write-Host '---'; Get-Content \$_.FullName -Tail 20 }"

# Fix: re-run the verify provisioner
vagrant up --provider=libvirt --provision-with=verify
```

### prism.exe not found after install

```bash
# Check if installer ran
vagrant winrm --shell powershell --command "Test-Path 'C:\Program Files\prism\prism.exe'"

# Check install log
vagrant winrm --shell powershell --command "Get-Content C:\prism-tests\install.log -Tail 50"

# Reinstall manually
vagrant winrm --shell powershell -e --command \\
  "Start-Process 'C:\prism-tests\setup.exe' -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait"
```

### WinRM hangs during test 14 (serve)

**Root cause**: `prism serve` starts a background HTTP server. WinRM waits for all child processes to exit, blocking indefinitely.

**Fix**: Exclude test 14 from runs:
```bash
bash vagrant/run-integration-tests.sh --filter "0[1-689]*"
bash vagrant/run-integration-tests.sh --filter "1[0-3]*"
```

**To kill a hung WinRM session**: kill the vagrant process on the host:
```bash
pkill -f "vagrant winrm"
```

### Test 07 (list-docs) times out

**Root cause**: `prism list-docs -n USER -t cls` returns thousands of ENSLIB/IRISLIB classes. The PyInstaller-packaged prism.exe is slow to serialize this large JSON response within the 120s timeout.

**Diagnosis**: The test framework kills the process after 120s and reports:
```
stderr: Invoke-Prism timed out after 120s on: C:\Program Files\prism\prism.exe list-docs -n USER -t cls
```

**Fix**: Skip test 07 or increase the timeout in `_common.ps1`:
```powershell
$script:PrismTimeoutSec = 300  # instead of 120
```

### Compile tests fail with "Class does not exist"

**Root cause**: Tests 10 (compile) depend on test 08 (put-doc) having uploaded documents first. If you run with a filter that skips 08, the documents won't exist.

**Fix**: Always include 08-put-doc when running 10-compile:
```bash
bash vagrant/run-integration-tests.sh --filter "0[89]*"   # uploads docs
bash vagrant/run-integration-tests.sh --filter "1[0]*" --keep-installed  # compiles them
```

### Test 13 -m assertion fails

**Root cause**: The test checks for "TestAddition" in stdout but the JSON response puts the method name in a nested field. The test actually passes (output shows "All PASSED", Result: 1).

**Fix**: Update the assertion in `tests/13-test.ps1` to check for the correct JSON field.

## Reading IRIS internal logs

```bash
cd ~/Projects/ERNI/Prism/vagrant

# IRIS console/messages log
vagrant winrm --shell powershell -e --command \\
  "Get-Content 'C:\InterSystems\IRIS\mgr\messages.log' -Tail 50"

# IRIS httpd access log
vagrant winrm --shell powershell -e --command \\
  "Get-ChildItem 'C:\InterSystems\IRIS\httpd\logs' | Sort-Object LastWriteTime -Descending | Select-Object -First 3 | ForEach-Object { Write-Host '=== '$_.Name' ==='; Get-Content $_.FullName -Tail 30 }"

# Check if IRIS is in error state
vagrant winrm --shell powershell -e --command \\
  "& 'C:\InterSystems\IRIS\bin\iris.exe' list"
```

## VM lifecycle commands

```bash
cd ~/Projects/ERNI/Prism/vagrant

vagrant status              # Check state
vagrant halt                # Graceful shutdown
vagrant reload              # Reboot
vagrant up --provider=libvirt  # Start (idempotent)
vagrant up --provision         # Re-run all provisioners
vagrant up --provision-with=verify  # Re-run just verify
vagrant destroy             # Delete VM completely (WARNING: re-provisions next up)
vagrant suspend / resume    # Save/restore state
```
