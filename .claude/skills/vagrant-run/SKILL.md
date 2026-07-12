---
name: vagrant-run
description: Run commands, PowerShell scripts, and file transfers inside the running Vagrant Windows VM via WinRM. Use when the user asks to execute, run, check, or inspect something inside the Windows VM, run the integration tests, or copy a file to/from the guest. Handles WinRM-specific quoting, exit-code, and sentinel gotchas that silently bite if ignored.
---

# vagrant-run — run commands inside the Vagrant Windows VM

The project VM is **Windows Server 2022**, reached over **WinRM** (not SSH). All
execution and file transfer go through `vagrant winrm` and `vagrant upload`/
`vagrant download`. Read this before issuing any in-VM command — WinRM has three
behaviors that silently bite if you assume it behaves like SSH.

## Prerequisite

The VM must be up. If unsure:

```bash
cd vagrant && vagrant status   # expect: running (libvirt)
```

If not running, see [[vagrant-up]] to start it, then come back here.

**All `vagrant` commands run from `vagrant/`** (the directory with the `Vagrantfile`).

## Running a one-off command

```bash
cd vagrant
vagrant winrm --shell powershell --command "<PowerShell>"
vagrant winrm --shell cmd        --command "<cmd>"
```

- `--shell powershell` is the default mental model — use it for anything nontrivial.
- Add `-e` / `--elevated` to run as Administrator (needed for service/firewall/
  install actions). Plain `vagrant winrm` runs as the `vagrant` user.

### Examples

```bash
cd vagrant

# Who am I / where am I
vagrant winrm --shell powershell --command "whoami; \$PWD"

# Is the IRIS web server listening?
vagrant winrm --shell powershell --command \
  "(Test-NetConnection -ComputerName 127.0.0.1 -Port 52773).TcpTestSucceeded"

# List IRIS services (needs the real service names, not 'iris')
vagrant winrm --shell powershell -e --command \
  "Get-Service ISCAgent,IRIS_c-_intersystems_iris,IRIShttpd | Format-Table Name,Status -AutoSize"

# Run the installed prism.exe
vagrant winrm --shell powershell --command "& 'C:\Program Files\prism\prism.exe' --help"
```

## Gotcha #1 — exit codes lie

**`vagrant winrm` exits 0 even when the inner command fails.** Do not trust the
shell exit code for pass/fail. Either:

1. **Print a sentinel** and grep for it on the host (this is what
   `vagrant/run-integration-tests.sh` does — it looks for `RUNALL_RESULT=PASS`),
   **or**
2. Have the inner script explicitly write the exit code and read it back:

```bash
vagrant winrm --shell powershell --command "do-something; Write-Host \"RC=\$LASTEXITCODE\""
```

## Gotcha #2 — quoting is two layers deep

The host shell (bash/zsh) sees the `--command` string first; PowerShell sees it
second. Rules that hold up in practice:

- Wrap the whole command in double quotes on the host side.
- Use **`\$`** for PowerShell variables so the host shell doesn't expand them
  (`$env:Path`, `$LASTEXITCODE`, `$_` → `\$env:Path`, `\$LASTEXITCODE`, `\$_`).
- Use **single quotes inside** PowerShell for string literals
  (`'C:\Program Files\prism'`).
- Never use host-side single quotes for the whole `--command` value when the
  command contains `$` — bash will still try to expand them.

```bash
# Good: host double-quotes, PS vars escaped, PS string in single quotes
vagrant winrm --shell powershell --command \
  "\$p='C:\Program Files\prism\prism.exe'; & \$p --version"
```

For multi-line scripts, prefer **uploading a `.ps1` and executing it** (below)
rather than fighting one giant quoted string.

## Gotcha #3 — `&` and `&&` mean different things

- PowerShell uses `;` for sequencing and `if`/`$LASTEXITCODE` for conditional flow,
  **not** `&&` (Windows PowerShell 5.1, the version in this box, does not support
  `&&`).
- On the **host** side, an unquoted `&` backgrounds the process — quote it or use
  it only inside the `--command` string.

## Running a PowerShell script file

The reliable pattern for anything beyond a one-liner: upload the script, run it
with execution policy bypassed, detect success via a sentinel it prints.

```bash
cd vagrant

# Upload a local script into the guest
vagrant upload ./my-script.ps1 'C:\prism-tests\my-script.ps1'

# Run it and capture output to a host log
vagrant winrm --shell powershell --command \
  "powershell -ExecutionPolicy Bypass -File C:\prism-tests\my-script.ps1" \
  | tee /tmp/prism-script.log

# Decide pass/fail from a sentinel the script prints, NOT from winrm's exit code
grep -q "MY_RESULT=PASS" /tmp/prism-script.log
```

## File transfer

```bash
cd vagrant

# Host → guest
vagrant upload ./local-file.txt 'C:\prism-tests\local-file.txt'

# guest → host
vagrant download 'C:\prism-tests\some-output.txt' ./some-output.txt

# Whole tree → guest: tar it on the host, extract inside (the canonical wrappers
# do exactly this; see vagrant/build-windows.sh and run-integration-tests.sh)
tar czf /tmp/bundle.tar.gz -C "$STAGE" .
vagrant upload /tmp/bundle.tar.gz 'C:\prism-tests\bundle.tar.gz'
vagrant winrm --shell powershell --command \
  "tar xzf C:\prism-tests\bundle.tar.gz -C C:\prism-tests"
```

`/vagrant` is **disabled** as a synced folder in this Vagrantfile — there is no
automatic shared directory. Everything must go through `upload`/`download`.

## Running the integration tests (canonical workflow)

Prefer the host-side wrapper rather than hand-rolling WinRM calls:

```bash
./vagrant/run-integration-tests.sh                  # full suite
./vagrant/run-integration-tests.sh --filter "*sql*" # subset
./vagrant/run-integration-tests.sh --keep-installed # don't uninstall after
```

It boots the VM if needed, uploads the installer + test bundle, runs
`scripts/run-all.ps1`, and detects pass/fail via the `RUNALL_RESULT=PASS`
sentinel — exactly the pattern to copy for any "did it actually succeed?"
check (see Gotcha #1).

To run pieces manually inside the VM (mirrors `vagrant/scripts/README.md`):

```bash
cd vagrant
vagrant winrm --shell powershell --command \
  "powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\install.ps1"
vagrant winrm --shell powershell --command \
  "powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\run-all.ps1 -Filter '*sql*'"
vagrant winrm --shell powershell --command \
  "powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\uninstall.ps1"
```

## Building the Windows exe/installer (canonical workflow)

```bash
./vagrant/build-windows.sh
```

It uploads the source tarball, runs `vagrant/build-in-vm.ps1` inside the guest,
serves the artifacts back over a temporary HTTP listener on port 8888, and
downloads them into `dist/`. Don't reimplement this — call the wrapper.

## Useful paths inside the guest

| Path                                           | What's there                                    |
|------------------------------------------------|-------------------------------------------------|
| `C:\Program Files\prism\prism.exe`             | Inno-installed prism (target of integration tests) |
| `C:\build\prism\`                              | Source tree extracted for a build               |
| `C:\prism-tests\`                              | Integration-test staging (installer + bundle)   |
| `C:\InterSystems\IRIS\`                        | IRIS install; `httpd\`, `mgr\`, `bin\`          |
| `C:\InterSystems\IRIS\httpd\logs\`             | httpd error logs (debug IRIS startup failures)   |

## Related skills and scripts

- [[vagrant-up]] — start the VM before running anything here.
- `vagrant/build-windows.sh`, `vagrant/build-in-vm.ps1` — build pipeline.
- `vagrant/run-integration-tests.sh`, `vagrant/scripts/*.ps1` — test pipeline.