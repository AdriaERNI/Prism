# vagrant/scripts — installed-build integration tests

PowerShell-based smoke tests that run **inside the Vagrant Windows VM**
against the Inno Setup-installed `prism.exe` (i.e. `C:\Program Files\prism\prism.exe`).
The goal is to catch regressions that only surface in the packaged build —
PATH issues, PyInstaller bundling gaps, missing IRIS native libs, etc.

## Layout

```
vagrant/scripts/
├── _common.ps1            # Test framework + Invoke-Prism wrapper
├── install.ps1            # Run setup.exe /VERYSILENT, verify install
├── uninstall.ps1          # Run unins000.exe /VERYSILENT
├── setup-test-env.ps1     # `prism config` for the VM-local IRIS
├── teardown-test-env.ps1  # Drop test docs + reset config
├── run-all.ps1            # Discover + run tests/*.ps1
└── tests/
    ├── 01-help.ps1
    ├── 02-config.ps1
    ├── 03-info.ps1
    ├── 04-sql.ps1
    ├── 05-terminal.ps1       # native irisnative
    ├── 06-ws.ps1             # WebSocket terminal
    ├── 07-list-docs.ps1
    ├── 08-put-doc.ps1
    ├── 09-get-doc.ps1
    ├── 10-compile.ps1
    ├── 11-delete-doc.ps1
    ├── 12-list-tests.ps1
    ├── 13-test.ps1
    ├── 14-serve.ps1          # MCP HTTP server
    └── 15-output-format.ps1  # global --format flag
```

## How to run

From the repo root, on the host:

```bash
./vagrant/build-windows.sh           # produce dist/prism-<ver>-setup.exe
./vagrant/run-integration-tests.sh   # run the full suite in the VM
```

Subset:

```bash
./vagrant/run-integration-tests.sh --filter "*sql*"
```

Skip the uninstall step (e.g. to poke at the installed binary afterwards):

```bash
./vagrant/run-integration-tests.sh --keep-installed
```

## Inside the VM

The bash runner uploads the bundle to `C:\prism-tests\` and the VM ends
up with:

```
C:\prism-tests\
├── setup.exe          # the Inno installer
├── bundle.tar.gz      # the staged scripts + fixtures
├── scripts\           # everything from vagrant/scripts/
└── fixtures\          # everything from tests/workspace/
```

You can also run pieces by hand from a vagrant winrm session:

```powershell
powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\install.ps1
powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\run-all.ps1 -Filter "*sql*"
powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\uninstall.ps1
```

## Writing a new test file

Drop a `tests/NN-<name>.ps1` file in alphabetic order:

```powershell
. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "my-feature"

Test-Case "thing works" {
    $r = Invoke-Prism my-command --some-flag
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "expected output"
}
```

Helpers in `_common.ps1`:

- `Invoke-Prism <args...>` — runs the installed `prism.exe`, returns
  `{Stdout, Stderr, ExitCode}`.
- `Invoke-PrismJson <args...>` — same, but throws on non-zero and parses
  JSON for you.
- Assertions: `Assert-True`, `Assert-Equal`, `Assert-Contains`,
  `Assert-NotContains`, `Assert-Match`, `Assert-ExitCode`,
  `Assert-HasProperty`.
- `Get-FixturesDir` — returns the path to the staged `tests/workspace/`.

## How this differs from `tests/integration/`

| Aspect | `tests/integration/` (pytest) | `vagrant/scripts/` |
|---|---|---|
| Runs | on the host with `uv run pytest` | inside the Vagrant VM |
| Calls | the Python source under `src/prism` | the Inno-installed `prism.exe` |
| Verifies | logic | the **packaged** build (PyInstaller + Inno) |
| Surface | MCP tool calls (FastMCP `Client`) | CLI commands + flags |

Both suites talk to the same IRIS instance.