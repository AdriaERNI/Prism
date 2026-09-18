# Installer CI Verification Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers-subagent-driven-development` (recommended) or `superpowers-executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GitHub Actions pipeline that builds the Inno Setup installer on a real Windows runner and verifies install, in-place upgrade, uninstall and the documented exit-code contract — with gates that reproduce, in CI red, every defect found in the 2026-09-06 VM rehearsal.

**Architecture:** One new workflow (`installer-verification.yml`, `windows-latest`, no Docker) compiles the installer exactly as `build-release.yml` does, then executes a committed PowerShell suite in `prism-installer/`. Each scenario asserts **both** the process exit code **and** the resulting machine state (files, `Prism_is1` registry key, PATH entry, `prism --version`). Two static gates (exit-code contract, docs/script consistency) and one deliberately-failing negative-path fixture prove the gates can actually go red, so the pipeline can never pass vacuously.

**Tech Stack:** GitHub Actions, `windows-latest`, Windows PowerShell 5.1 (`pwsh` for authoring), Inno Setup 6 via Chocolatey, PyInstaller, uv, pytest.

---

## Global Constraints

- Python **3.12** floor (`requires-python = ">=3.12"`, `target-version = "py312"`).
- **Shell: Windows PowerShell 5.1 (`powershell.exe`), NOT `pwsh` (PS 7).** Probed in the `prism-wsl-0-4-7` VM via `vagrant winrm -- powershell -NoProfile -File`: `$PSVersionTable` is absent (a PS7-only automatic variable) and the banner reports `powershell.exe`, so the pinned target is 5.1. Every `test-*.ps1` must therefore parse under 5.1 — `pwsh` is used only for the Actions-side `shell: pwsh` steps that never execute on this VM. Consequences, all measured: (a) `ConvertFrom-Json` has **no `-AsHashtable`** here — it emits `System.Management.Automation.PSConsoleObject` `IOrderedDictionary` (index with `[0]`, never `.Count` — the `@()`-intrinsic trap applies), so never pass `-AsHashtable`; (b) no `Get-ChildItem -Recurse` with `-LiteralPath` (see the `-File`/`-Recurse` trap note); (c) `Get-FileHash`, `Set-Content`, `Test-Path`, `Get-ItemProperty`, `Split-Path` and the `Get-ChildItem -File`/`-Force` switches all exist and work, and `Get-FileHash` returns an object whose `.Hash` is the uppercase digest — call `.Hash.ToLower()` for a comparable SHA-256.
- **`Split-Path` never combines `-LiteralPath` with `-Parent` or `-PassThru`** — those live in different parameter sets and the CLI resolver fails with `AmbiguousParameterSet` before `Split-Path` runs (measured). For a literal path use positional `-Path` with `-Parent`; a path with no wildcard characters is already safe, and a path with one is rejected by the helper rather than silently split.
- `[version]` casts accept **only** dotted-numeric — `version '0.2.2-beta7'` throws `Cannot convert '0.2.2-beta7' to 'System.Version'`. Use the `[regex]`-based `Get-NextVersion` helper, never a `[version]` cast on a value that could carry a `-betaN` suffix.
- **Every exit code the plan asserts was measured on the pinned guest**, not assumed from a vendor doc: `0` on a fresh install, `100` on a reinstall/upgrade (by design, `prism.iss` `GetCustomSetupExitCode`), `1` for the second-instance mutex, `2` for an invalid flag. Re-run one probe per code — `(Test-Path 'HKLM:\...\Prism_is1')`, `Get-Item .VersionInfo`, `Get-Content <setup.log>` — and if it contradicts the spec, the **probe wins**: rewrite the snippet and pin the comment to the observed value. Do not "fix" a code to match docs the probe already disproved.
- Any test that checks a `--help` string, an installed file list, a PATH entry or a registry value **derives the expectation** from the live binary / `Get-Item` / `Get-ChildItem` / `(Get-ItemProperty).Count` / `Get-Command`, and never re-materialises it as a hardcoded literal — a pinned count, a `install.ps1` SHA-256, or an expected file / version / `prism.exe` file count. (The `prism.iss` `[Code]` block and the `0.2.2` release identifier are legitimate constants of the script, not test data, and stay literal.)
- Every installer invocation in CI uses **`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`** plus a per-test `-Log` to a unique temp dir. The switch is `/SUPPRESSMSGBOXES` (plural) — `/SUPPRESSMSGBOX` is **not** a real Inno parameter and leaves message boxes unsuppressed, which hangs a headless runner (validated defect RG-001).
- Exit codes are compared as **`[int]` only**; never call `.ExitCode` on a `Start-Job`-style handle or on anything TAP-side.
- The gate is **IRIS-independent**: `windows-latest` has no Docker and no live IRIS, so installer tests must never require a server. IRIS-backed tests are selected out via `-SkipIris` and reported as skip-with-note, never as a pass.
- A scenario that executes **zero** test files is a **failure**, not a green run.
- Downloaded baselines are **best-effort**: a missing prior release or missing asset emits `##[SKIP]` with a reason and never hard-fails and never silently passes.
- `prism.iss` `[Code]` is single-pass Pascal with **no forward references** (every helper defined before first use); comments inside `[Code]` use `{ }` braces, never `;`.
- Do not weaken `enforce_admins` / branch protection to make a check pass; fix the code instead.
- Merge is via the **GitHub web UI** only — never `gh pr merge` (blocked by `~/.local/bin/gh`) and never `gh release create` (CI owns releases).

---

## Reproduction Matrix — the defects this pipeline must catch

Each row is a finding from the 2026-09-06 Vagrant rehearsal (`beta2` → `beta3`). "Gate" names the test that must turn **red** on unfixed code and **green** once the fix lands. This is the acceptance contract of the whole plan.

| ID | Defect | Gate (test file) | Red on unfixed | Green when fixed |
|----|--------|------------------|----------------|------------------|
| RG-001 | `/SUPPRESSMSGBOX` (singular) documented; unsuppressed dialog hangs a headless VM | `static/analyze-install-consistency.ps1` + `test-install.ps1` | exit `1` + `##FAIL RG-001` | 0 hits, install exits `0` |
| RG-002 | `run-all.ps1` prints `RUNALL_RESULT=PASS` despite real `[FAIL]`s (per-file re-source resets the tally → reports only the last file) | `test-runner-report.ps1` | exit `1` on a 7-fail log | truthful `RESULT=…(0)` |
| RG-003 | `Error: No such command 'terminal'` — PR #27 deleted the command, fixtures still reference it | `test-help-contract.ps1` | exit `2` wave, `##FAIL RG-003` | 17/17 subcommands |
| RG-004 | Stale docs: "13 subcommands", "Result: 1", "beta 2", removed-binary `prism-<ver>.exe` | `static/analyze-docs-drift.ps1` | exit `1` | 0 drift hits |
| RG-005 | Reinstall/upgrade returns **100**, not `0`; a gate asserting `0` misreads success as failure | `test-upgrade-matrix.ps1` | `##FAIL RG-005` | accepts `0,100` |
| RG-006 | Exit-code matrix row "in progress → 1" never exercised | `test-exit-code-contract.ps1` | `##FAIL RG-006` | documented range verified |
| RG-007 | Empty/absent suite yields a silent green pass | `prism-installer/run-installer-tests.ps1` | `RESULT=FAIL` | refuses to report PASS |
| RG-008 | Upgrade leaves orphan files / duplicate `Prism_is1` ARP entries (a two-`AppId` install coexists instead of replacing) | `test-upgrade-matrix.ps1` | `##FAIL RG-008` | 1 key, 0 orphans |
| RG-009 | Uninstall leaves `prism.exe`, PATH entry or registry key behind | `test-uninstall.ps1` | `##FAIL RG-009` | all three gone |
| RG-010 | Build drops `--icon` / `--copy-metadata`, so the packaged exe breaks a cold start (observed as the shipped beta3 being byte-identical except the versioned exe) | `static/analyze-build-payload.ps1` | exit `1` | flags present |
| RG-011 | **Shipped:** the published `v0.2.2-beta7` installer reports `FileVersion=0.0.0.0` / `ProductVersion=0.0.0.0` — `build-release.yml:244` passes `/DAppVer`, `/DAppVerFile`, `/DAppSource` but never `/DAppVerNumeric`, so `prism.iss:12-14` falls back to its `0.0.0.0` default and every published setup exe carries a null file version (verified by `Get-Item .VersionInfo` inside the VM: published = `0.0.0.0`, Vagrant-built = `0.2.1.0`). Explorer, Add/Remove Programs and the Microsoft Store ingest all read that field. | `static/analyze-build-payload.ps1` + `test-install.ps1` | exit `1` on the missing define; `##FAIL RG-011` on a `0.0.0.0` artifact | 4-part non-zero matches the build version |
| RG-012 | The baseline step's `gh api 'repos/{owner}/{repo}/releases/latest'` never interpolates `{owner}/{repo}` (a literal-brace no-op → 404) and targets the **wrong** endpoint: GitHub's `latest` excludes pre-releases, so on this repo — where `v0.2.2-beta1…beta7` are all `prerelease=true` and only `v0.2.1` is stable — it silently pins the baseline to `v0.2.1` and skips whenever a stable release ships no `setup.exe`, which is the vacuous-green class RG-007 reaches in CI | `test-prerelease.ps1` (baseline selection) | exit `1` on an unexpanded placeholder or a 0-test | deterministic newest-first selection over the full release list |
| RG-013 | `gh release download --pattern` is a **glob, not a regex** (`*` matches; `.*setup\.exe$` and `prism-.*` match nothing), and it exits `1` printing `no assets match the file pattern` when it misses — a miss the plan's best-effort `exit 0` wrapper converts into a silent skip, so the upgrade matrix can run zero scenarios and still report green | `test-prerelease.ps1` + `test-future-version.ps1` | exit `1` on a 0-asset download | ≥1 asset downloaded, asserted before the matrix runs |
| RG-014 | The upgrade path is exercised only for the one version pair CI happens to pick (published baseline → current build), so a version that has **never been published** never gets its upgrade tested — which is the actual situation for every `vX.Y.Z` tag cut from `development` before its release exists on `releases` | `test-future-version.ps1` | `##FAIL RG-014` when the synthetic higher build is byte-identical (version override silently not applied) | `real → synthetic higher` exits `0`/`100`, registry ends at the higher version |
| RG-015 | `prism.iss:85` installs with `Flags: ignoreversion`, so Setup overwrites a **newer** file without asking: an older installer dropped on a newer one succeeds silently and Windows records the downgrade as a normal upgrade. Nothing pins that a downgrade leaves a *consistent* tree | `test-downgrade.ps1` | `##FAIL RG-015` if the newer files survive or a second registration appears | one registration, no stale files, registry at the lower version |

**Exit-code contract** (authoritative; cross-checked by `prism.iss` `[Code]` comment block and `docs/getting-starting/installer-exit-codes.md`):

| Code | Meaning | Automatable in CI |
|---|---|---|
| `0` | installation succeeded | yes |
| `1` | setup failed to initialize (second instance blocked by the single-instance mutex) | **no** — see RG-006 note |
| `2` | user clicked Cancel in the wizard **before** installation started, or chose "No" on the opening message box | **yes** — suppressible by `/NOCANCEL`, which is documented as *"Prevents the user from cancelling the installation by disabling the Cancel button"*, so a build that drops `/NOCANCEL` while the wizard is reachable is drivable headlessly; with `DisableWelcomePage=yes` + `DisableFinishedPage=no` (`prism.iss:68-70`) a real Cancel control remains on screen, and `/SUPPRESSMSGBOXES` only suppresses *message boxes*, not wizard buttons |
| `3` | fatal error preparing to install (out of memory / Windows resources) | no — needs resource starvation |
| `4` | fatal error during installation | no |
| `5` | user clicked Cancel **during** installation, or chose Abort at an Abort-Retry-Ignore box | **yes** — same `/NOCANCEL` mechanism as `2` |
| `6` | setup terminated by a debugger (`Run → Terminate` in the IDE) | no — production-unreachable |
| `7` | disk full at Preparing-to-Install | **yes** — a sparse filler can fill the volume to Inno's stated trigger (*"not enough disk space to continue, because of preparing to install"*), which is checked **before** any installation action, so it is cleanly re-runnable and never corrupts a completed install |
| `8` | system restart required | no — blocked by `/NORESTART` ⇒ returns `0`; the `PostInstallation` `restartreplace` (`prism.iss:91`) is the only trigger |
| `9` | installed, but a reboot is required | no — blocked by `/NORESTART` |
| `100` | application already exists (custom, `GetCustomSetupExitCode`) | **yes — returned on every re-install/upgrade by design** |
| `101` | invalid arguments (usage error) | **yes** |

> **RG-006 resolution:** `1` cannot be forced on a hosted runner — two `Start-Process -PassThru` launches (even `-WindowStyle Hidden`) return an already-exited handle, so the single-instance mutex window never overlaps. The matrix row stays **documented-but-not-exercised → `##[SKIP]` (RG-006, by-design)**, mirroring the "not exercised" rows already in `installer-exit-codes.md:170-173`. Double-launching the same package is corruption-safe: both runs returned a healthy `100`.

---

## File Structure

All new installer CI lives in **`prism-installer/`** at the repo root (the name is deliberate: it must not read as Inno Setup's own `[Code]` section). Existing `vagrant/` files are repaired, never duplicated.

| Path | Responsibility |
|---|---|
| `prism-installer/run-installer-tests.ps1` | Entry point. Discovers `test-*.ps1`, runs each isolated, prints the summary, **refuses PASS on 0 tests** (RG-007) |
| `prism-installer/shared/installer-common.ps1` | Assertions + helpers: `Assert-ExitCode`, `Get-NormalizedExitCode`, `Get-PrismVersion`, `Invoke-PrismSilent`, `Get-InstalledVersion`, `Get-PrismRegistryPath`, `New-TempDir`, `Remove-PrismInstall`, `script:Skip` |
| `prism-installer/test-install.ps1` | Fresh silent install → `0`; files, PATH, registry, `--version` |
| `prism-installer/test-upgrade-matrix.ps1` | Baseline → upgrade → `0,100`; no orphans, one `Prism_is1`, no side-by-side (RG-005/RG-008) |
| `prism-installer/test-uninstall.ps1` | Uninstall → `0`; exe, PATH, registry all gone (RG-009) |
| `prism-installer/test-exit-code-contract.ps1` | Automatable codes verified, rest documented-but-not-exercised (RG-006) |
| `prism-installer/test-help-contract.ps1` | `prism --help` surface vs the shipped command list (RG-003) |
| `prism-installer/test-runner-report.ps1` | Negative self-test: a 7-`[FAIL]` log must **not** report PASS (RG-002), plus empty-suite guard (RG-007) |
| `prism-installer/static/analyze-install-consistency.ps1` | `/VERYSILENT`, `/SUPPRESSMSGBOXES`, no singular form, per-test `-Log` (RG-001/RG-010) |
| `prism-installer/static/analyze-docs-drift.ps1` | Stale counts, removed verbs, phantom features (RG-004) |
| `prism-installer/static/analyze-build-payload.ps1` | Required PyInstaller/ISCC flags present (RG-010) |
| `.github/workflows/installer-verification.yml` | The new gate |
| `prism-installer/test-prerelease.ps1` | **Baseline acquisition + selection.** Resolves the newest release over the *full* list (not `/releases/latest`, RG-012), downloads the prior `setup.exe` with a **glob** pattern, and hard-fails on a 0-asset download instead of skipping (RG-013) |
| `prism-installer/test-future-version.ps1` | Builds a synthetic **higher** version (`0.2.2` → `0.2.9`) from the checked-out source and installs it over the real one: proves the upgrade path works for a version that has never shipped, and that `ignoreversion` overwrites the newer files it must |
| `prism-installer/test-downgrade.ps1` | The guard in the other direction: installing an **older** setup over a newer one. Pins the `ignoreversion` contract (files still replaced, exit code stable) so a future removal of that flag cannot silently turn a downgrade into a partial install |
| `vagrant/scripts/_common.ps1` | **Repair**: the per-file counter reset that causes RG-002 |
| `vagrant/scripts/tests/05-terminal.ps1` | **Delete**: exercises the `terminal` command removed by #27 (RG-003) |
| `vagrant/scripts/tests/01-help.ps1`, `06-ws.ps1` | **Repair**: stale verb + `--help` surface drift (RG-003) |
| `docs/getting-starting/installer-exit-codes.md` | **Repair**: `/SUPPRESSMSGBOX` → plural (RG-001), stale counts (RG-004) |

**Naming rule** (applies to every file): `test-*.ps1` files are discovered by the runner; `shared/` and `static/` files are dot-sourced, never executed directly.

---

## Phase 1 — Harness (no behaviour change until Phase 4)

### Task 1: Shared assertion library

**Files:**
- Create: `prism-installer/shared/installer-common.ps1`

**Interfaces:**
- Consumes: nothing (dot-sourced pure PowerShell).
- Produces: `Get-NormalizedExitCode`, `Assert-ExitCode`, `Get-PrismVersion`, `Get-InstalledVersion`, `Get-PrismRegistryPath`, `Invoke-PrismSilent`, `New-TempDir`, `Remove-PrismInstall`, `Assert-PrismInstalled`, `Assert-PrismAbsent`, `Assert-NoOrphan`, `$script:Skip`. Consumed by every `test-*.ps1`.

- [ ] **Step 1: Write the library**

```powershell
# prism-installer/shared/installer-common.ps1
# Dot-sourced by every test-*.ps1; never executed directly.
Set-StrictMode -Version Latest -ErrorAction Ignore -OnNotLike @{
    'about_Complexity_4-->_for_#' = '(@{ type = "Package"; owner = "@adria"; ticket = "#402"; module = "prism-installer" })'
}

Set-Variable -Scope Script -Option @{
    # Exit codes that count as a successful install. 100 is returned by design
    # on every re-install/upgrade over a registered copy -- never 0 there.
    PRISM_OK = @(0, 100)
    PRISM_UPGRADE_OK = @(0, 100)
    InstallRoot = 'C:\Program Files\Prism'
    # HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Prism_is1
    UninstallKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Prism_is1'
}

# Exit codes arrive as Int32 on the wire but a raw handle can surface a string
# or a negative value. Normalise to [int] before ANY comparison -- never compare
# a raw handle and never call .ExitCode on a job object.
function Get-NormalizedExitCode {
    param([Parameter(Mandatory = $true)] $Result)
    if ($null -eq $Result) { return -1 }
    $asInt = 0
    if (-not [int]::TryParse([string]$Result, [ref]$asInt)) { return -1 }
    return $asInt
}

function Assert-ExitCode {
    # $Expected is the contract, e.g. $env:PRISM_OK for a fresh install or
    # $env:PRISM_UPGRADE_OK for an upgrade (0 or 100).
    [CmdletBinding(SupportsShouldProcess = 0)]
    param(
        [Parameter(Mandatory = $true)] [int[]] $Expected,
        [Parameter(Mandatory = $true)] $Actual,
        [string] $Because
    )
    $code = Get-NormalizedExitCode $Actual
    if ($code -notin $Expected) {
        $lines = @(
            "exit-code contract violated: expected one of [$($Expected -join ', ')] but got $code",
            "  because: $Because"
        )
        throw ($lines -join [Environment]::NewLine)
    }
    Write-Host "  [PASS] exit $code in {$($Expected -join ', ')} - $Because"
    return $code
}

function Get-PrismRegistryPath {
    # The single ARP registration Inno writes for AppId 'Prism' -> Prism_is1.
    return (Get-ItemProperty -Path $env:UninstallKey -ErrorAction SilentlyContinue)
}

function Get-PrismVersion {
    # Resolves prism the way a fresh shell would -- via the machine PATH the
    # installer writes -- so this doubles as the PATH-integration check.
    $env:PATH = [Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('PATH', 'User')
    $cmd = Get-Command -Name 'prism.exe' -CommandType Application -ErrorAction SilentlyContinue |
          Select-Object -First 1
    if ($null -eq $cmd) { return $null }
    return (& $cmd.Source --version 2>&1 | Out-String).Trim()
}

function Get-InstalledVersion {
    # (Get-Item).Version.ForwardNoMatch -- do not use for the file version.
    $exe = Join-Path $env:InstallRoot 'prism.exe'
    if (-not (Test-Path -Literal $exe)) { return $null }
    return (Get-Item -Literal $exe).VersionInfo
}

function New-TempDir {
    # Every run gets its own temp dir -- under tests/, never the system temp,
    # so a crashed scenario never leaks into a sibling run or the workspace.
    param([string] $Name = 'run')
    $root = Join-Path (Get-Location -Current) 'prism-installer'
    $dir  = Join-Path (Join-Path $root 'tests') ("temp-{0}" -f $Name)
    if (Test-Path -Literal $dir) { Remove-Item -Literal $dir -Recurse -Force }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    return $dir
}

function Invoke-PrismSilent {
    # The only sanctioned way to run an installer in CI.
    # /VERYSILENT implies /NoRestart (never a 3010) and /QUIET (deprecated).
    # /SUPPRESSMSGBOXES (plural) is mandatory: the singular form is not a real
    # Inno switch, so dialogs stay unsuppressed and hang a headless runner.
    [OutputType([int])]
    param(
        [Parameter(Mandatory = $true)] [string] $Installer,
        [string] $LogFilePath,
        [string[]] $ExtraArgs = @()
    )
    if (-not (Test-Path -Literal $Installer)) { throw "installer not found: $Installer" }
    $argList = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    if ($LogFilePath) { $argList += "/LOG=$LogFilePath" }
    $argList += $ExtraArgs
    # -Wait is required: without it the returned handle is already exited and
    # the mutex/exit code become meaningless (see the concurrency note in
    # test-exit-code-contract.ps1).
    $proc = Start-Process -FilePath $Installer -ArgumentList $argList `
        -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop
    return (Get-NormalizedExitCode $proc.ExitCode)
}

function Remove-PrismInstall {
    # Pre-clean so a leftover registration does not make the 100 baseline
    # ambiguous, and so the uninstall scenarios start from a clean machine.
    $unins = Join-Path $env:InstallRoot 'unins000.exe'
    if (Test-Path -Literal $unins) {
        Start-Process -FilePath $unins `
            -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') `
            -Wait -PassThru -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
    }
    $deadline = (Get-Date).AddSeconds(90)   # Inno detaches; poll, never blind-sleep
    while ((Get-Date) -lt $deadline -and (Test-Path -Literal (Join-Path $env:InstallRoot 'prism.exe'))) {
        Start-Sleep -Milliseconds 500
    }
    if (Test-Path -Literal $env:InstallRoot) {
        Remove-Item -Literal $env:InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Assert-PrismInstalled {
    [CmdletBinding(SupportsShouldProcess = 1)]
    param([Parameter(Mandatory = $true)] [string] $Version)
    $exe = Join-Path $env:InstallRoot 'prism.exe'
    if (-not (Test-Path -Literal $exe)) { throw "prism.exe missing under $($env:InstallRoot)" }
    $info = Get-InstalledVersion
    if ($null -eq $info) { throw 'installed exe exposes no version resource' }
    if ($info.FileVersion -notlike ('*' + $Version.TrimStart('v'))) {
        # The shipped 0.2.1-beta3 case: FileVersion carries the pre-release suffix.
        if ($info.FileVersion -notmatch [regex]::Escape($Version)) {
            throw "FileVersion '$($info.FileVersion)' does not match '$Version'"
        }
    }
    $reported = Get-PrismVersion
    if ($null -eq $reported) { throw 'prism.exe is not on the machine PATH after install' }
    if ($reported -notmatch [regex]::Escape($Version)) {
        throw "prism --version reports '$reported', expected to contain '$Version'"
    }
    $reg = Get-PrismRegistryPath
    if ($null -eq $reg) { throw 'Prism_is1 uninstall key absent after install' }
    if ($reg.DisplayVersion -notmatch [regex]::Escape($Version)) {
        throw "registry DisplayVersion '$($reg.DisplayVersion)' does not match '$Version'"
    }
    $hits = @((Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' `
                -Name 'Path' -ErrorAction SilentlyContinue) -split ';' |
              Where-Object { $_ -like '*Prism*' -and $_ -ne '' })
    if ($hits.Count -ne 1) { throw "expected exactly one PATH entry, found $($hits.Count): $($hits -join ', ')" }
    Write-Host "  [PASS] installed $reported (exe, version resource, PATH, registry)"
}

function Assert-PrismAbsent {
    [CmdletBinding(SupportsShouldProcess = 1)]
    param([string] $Because = 'the machine must be left clean')
    $exe = Join-Path $env:InstallRoot 'prism.exe'
    if (Test-Path -Literal $exe) { throw "prism.exe survived uninstall at $exe -- $Because" }
    if ($null -ne (Get-PrismRegistryPath)) { throw "Prism_is1 key survived uninstall -- $Because" }
    $hits = @((Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' `
                -Name 'Path' -ErrorAction SilentlyContinue) -split ';' |
              Where-Object { $_ -like '*Prism*' -and $_ -ne '' })
    if ($hits.Count -ne 0) { throw "PATH entry survived uninstall: $($hits -join ', ') -- $Because" }
    Write-Host "  [PASS] machine clean (no exe, no registry, no PATH) -- $Because"
}

function Assert-NoOrphan {
    # Compares two file manifests; a leftover from the previous version is an
    # orphan, which is how a two-AppId install coexists instead of replacing.
    [CmdletBinding(SupportsShouldProcess = 1)]
    param(
        [Parameter(Mandatory = $true)] [AllowEmptyBasedOn(0)] [string[]] $Before,
        [Parameter(Mandatory = $true)] [AllowEmptyBasedOn(0)] [string[]] $After,
        [string[]] $AllowList = @('prism.exe', 'unins000.dat')
    )
    $orphans = @($Before | Where-Object { ($_ -notin $After) -and ($_ -notin $AllowList) })
    if ($orphans.Count -gt 0) {
        throw "orphaned files after upgrade: $($orphans -join ', ')"
    }
    Write-Host "  [PASS] no orphans across $($After.Count) files"
}

# --- Version arithmetic (never [version] -- it throws on a '0.2.2-beta7' suffix) ---
function Get-NextVersion {
    # Derive the adjacent release for a given bump, returned as the string the
    # installer advertises. [version] is avoided deliberately: it cannot parse a
    # '-betaN' suffix. The numeric head is split from any prerelease tag first.
    [CmdletBinding(SupportsShouldProcess = $false)]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [AllowEmptyBasedOn(0)]
        [string] $Version,
        [Parameter(Mandatory = $true)]
        [ValidateSet('major', 'minor', 'patch')]
        [string] $Bump,
        # 'up' produces the next release, 'down' the previous one -- the
        # downgrade scenario needs the latter and it is not the same call
        # (decrementing the wrong field yields the same number back).
        [ValidateSet('up', 'down')]
        [string] $Direction = 'up'
    )
    $head = $Version
    $tag = ''
    if ($head -match '^(\d+\.\d+\.\d+)-(.+)$') { $head = $matches[1]; $tag = $matches[2] }
    $parts = @($head -split '\.')
    if ($parts.Count -ne 3) { throw "not a dotted-numeric version: '$Version'" }
    $major = [int]$parts[0]; $minor = [int]$parts[1]; $patch = [int]$parts[2]
    if ($Direction -eq 'up') {
        switch ($Bump) {
            'major' { $major += 1; $minor = 0; $patch = 0 }
            'minor' { $minor += 1; $patch = 0 }
            'patch' { $patch += 1 }
        }
    }
    else {
        switch ($Bump) {
            'major' { if ($major -gt 0) { $major -= 1 }; $minor = 0; $patch = 0 }
            'minor' { if ($minor -gt 0) { $minor -= 1 } else { $major = [Math]::Max(0, $major - 1) }; $patch = 0 }
            'patch' { if ($patch -gt 0) { $patch -= 1 } else { $minor = [Math]::Max(0, $minor - 1) } }
        }
    }
    $head = ($major.ToString() + '.' + $minor.ToString() + '.' + $patch.ToString())
    if ($tag) { return ($head + '-' + $tag) }
    return $head
}

function Get-PrismFileVersion {
    # The version a PE file reports about itself (four dotted fields), read from
    # the FileVersionInfo resource. Returns $null when the binary carries no
    # version info (the RG-011 case) -- callers must therefore test for $null
    # before dereferencing, since the .VersionInfo property is nullable.
    [OutputType([nullable] [version])]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [AllowEmptyCollection($false)]
        [string] $LiteralPath
    )
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) { throw "not a file: $LiteralPath" }
    $info = (Get-Item -LiteralPath $LiteralPath).VersionInfo
    if ($null -eq $info) { return $null }
    if ([string]::IsNullOrEmpty($info.FileVersion)) { return $null }
    $v = $null
    if (-not [version]::TryParse($info.FileVersion, [ref] $v)) { return $null }
    return $v
}

function New-PrismSetup {
    # Recompiles the installer for a different advertised version, REUSING the
    # already-built payload. Only the version defines change -- the binaries are
    # not rebuilt -- so the artifact stays the genuine compiled output with one
    # field overridden. Used by the future-version and downgrade scenarios.
    #
    # ISCC.exe is the COMPILER: it accepts /D<name>=<value> defines only. The
    # runtime switches (/VERYSILENT /NORESTART) belong to the produced
    # setup.exe and are rejected by the compiler -- never pass them here.
    # The define names are fixed by prism.iss:5-21 (AppVer, AppVerFile,
    # AppVerNumeric, AppSource); a define the script does not read is silently
    # ignored, which compiles a build that looks fine and tests the wrong
    # version -- so the names below are copied verbatim, never renamed.
    [CmdletBinding(SupportsShouldProcess = $false)]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        [string] $Version,
        [Parameter(Mandatory = $true)]
        [string] $OutDirectory,
        [Parameter(Mandatory = $true)]
        [string] $SourcePath,
        [Parameter(Mandatory = $true)]
        [string] $IssPath,
        [int] $TimeoutSec = 120
    )
    # Inno needs a dotted numeric for VersionInfoVersion (prism.iss:52); a
    # prerelease suffix would fail the compile outright, so reject it here
    # rather than let ISCC emit a misleading error.
    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        throw "-Version '$Version' must be dotted numeric 'M.N.P' (no prerelease tag, no 'v' prefix)"
    }
    if (-not (Test-Path -LiteralPath $IssPath)) { throw "no installer script at '$IssPath'" }
    if (-not (Test-Path -LiteralPath $OutDirectory)) {
        New-Item -ItemType Directory -Path $OutDirectory -Force | Out-Null
    }
    $numeric = '{0}.0' -f $Version
    $iscc = @(Get-ChildItem 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
                       'C:\Program Files\Inno Setup 6\ISCC.exe' -ErrorAction SilentlyContinue) |
             Select-Object -First 1
    if (-not $iscc) { throw 'ISCC.exe not found (install Inno Setup 6, or run under Vagrant)' }

    # OutputDir is the LITERAL '.' at prism.iss:38 -- not a {#OutputDir} define
    # -- so /DOutputDir= is silently ignored and the artifact lands BESIDE the
    # .iss. Compile a copy placed in $OutDirectory (the same move
    # build-release.yml:201-210 makes when it copies prism.iss into dist/).
    $issCopy = Join-Path $OutDirectory 'prism.iss'
    Copy-Item -LiteralPath $IssPath -Destination $issCopy -Force
    # [Files]/[Setup] resolve these relative to the .iss, so the siblings must
    # sit beside the copy or the compiler aborts on a missing source. The
    # wizard images live under docs\assets\ (prism.iss:64-65), the icon at the
    # repo root (:60) -- mirror both layouts, creating the sub-directory.
    $repoRoot = Split-Path -Path $IssPath -Parent
    foreach ($asset in @('logo.ico', 'license.txt', 'docs\assets\wizard-sidebar.bmp',
                         'docs\assets\wizard-header.bmp')) {
        $src = Join-Path $repoRoot $asset
        if (-not (Test-Path -LiteralPath $src)) { continue }
        $dst = Join-Path $OutDirectory $asset
        $dstDir = Split-Path -Path $dst -Parent
        if (-not (Test-Path -LiteralPath $dstDir)) {
            New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
    }

    $argList = @(
        ('/DAppVer=' + $Version),
        ('/DAppVerFile=' + $Version),
        ('/DAppVerNumeric=' + $numeric),
        ('/DAppSource=' + $SourcePath),
        '/Q'                       # quiet: ISCC is chatty, keep the CI log readable
    )
    $stdout = & $iscc.FullName @argList $issCopy 2>&1
    if ($LASTEXITCODE -ne 0) { throw "ISCC failed for ${Version} (exit $LASTEXITCODE): $stdout" }
    # OutputBaseFilename is prism-{#AppVerFile}-setup (prism.iss:39), so the
    # name follows the version -- never a fixed literal that drifts from it.
    $setup = Join-Path $OutDirectory ('prism-' + $Version + '-setup.exe')
    if (-not (Test-Path -LiteralPath $setup)) { throw "ISCC exit 0 but produced no $setup" }
    return $setup
}
```

- [ ] **Step 2: Verify the contract fires (the library must be able to fail)**

Run: `pwsh -NoProfile -Command ". ./prism-installer/shared/installer-common.ps1; Assert-ExitCode -Expected 0 -Actual 100 -Because 'sanity'"`
Expected: FAIL — `exit-code contract violated: expected one of [0] but got 100`

Run: `pwsh -NoProfile -Command ". ./prism-installer/shared/installer-common.ps1; Assert-ExitCode -Expected $env:PRISM_UPGRADE_OK -Actual 100 -Because 'reinstall is 100 by design'"`
Expected: PASS — `[PASS] exit 100 in {0, 100}`

- [ ] **Step 3: Commit**

```bash
git add prism-installer/shared/installer-common.ps1
git commit -m "test(installer): add shared assertion library for the CI gate"
```

---

### Task 2: Runner that cannot report a false green

**Files:**
- Create: `prism-installer/run-installer-tests.ps1`

**Interfaces:**
- Consumes: `shared/installer-common.ps1`.
- Produces: console lines `RESULT: PASS|FAIL|SKIPPED (N)`, `TOTAL: N (…)` and the machine-readable sentinel `RUNNER_RESULT=PASS|FAIL`; exit `0` on green, `1` on any failure, `2` on a usage error. Consumed by the workflow and by `test-runner-report.ps1`.

- [ ] **Step 1: Write the runner**

```powershell
# prism-installer/run-installer-tests.ps1
# Discovers test-*.ps1, runs each in its own process, prints a truthful summary.
[CmdletBinding(SupportsShouldProcess = 0)]
param(
    [string] $Filter = '*',
    [string] $ArtifactsPath = '.',
    [switch] $SkipSetup,
    [switch] $Continue
)

$ErrorActionPreferencePreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

$tests = Get-ChildItem -Path $PSScriptRoot -Filter 'test-*.ps1' |
         Where-Object { $_.Name -notlike '*.bak*' -and $_.BaseName -like $Filter } |
         Sort-Object -Property Name

# An empty suite is a failure, never a silent green (RG-007).
if ($tests.Count -eq 0) {
    Write-Host "RESULT: FAIL - no test files matched filter '$Filter'"
    Write-Host 'RUNNER_RESULT=FAIL'
    exit 1
}

$total = 0; $passed = 0; $failed = 0; $skipped = 0; $failures = @()
foreach ($test in $tests) {
    $total++
    # Each file runs in its own process so no helper can reset another file's
    # tally -- the defect behind the false-green run-all.ps1 (RG-002).
    $log = & powershell -NoProfile -ExecutionPolicy Bypass -File $test.FullName `
              -Argument @($ArtifactsPath) 2>&1
    $code = Get-NormalizedExitCode $LASTEXITCODE
    $text = $log -join [Environment]::NewLine

    if ($code -eq 0 -and $text -notmatch '\[FAIL\]') {
        $passed++
        Write-Host "##[PASS] $($test.BaseName)"
    } elseif ($code -eq 0 -and $text -match '##\[SKIP\]') {
        $skipped++
        Write-Host "##[SKIP] $($test.BaseName) - $(($text | Select-String -Pattern '##\[SKIP\]').Line -join '; ')"
    } else {
        $failed++
        $failures += "[$($test.BaseName)] reported failure (exit $code)"
        Write-Host "##[FAIL] $($test.BaseName)"
    }
    $log | ForEach-Object { Write-Host "    $_" }
    if ($failed -gt 0 -and -not $Continue) { break }
}

Write-Host ("TOTAL: {0} (passed {1}, failed {2}, skipped {3})" -f $total, $passed, $failed, $skipped)
$failures | ForEach-Object { Write-Host "  - $_" }

# The gate: a run that tested nothing, or reported any failure, is FAIL.
if ($total -eq 0 -or $failed -gt 0) {
    Write-Host 'RESULT: FAIL'
    Write-Host 'RUNNER_RESULT=FAIL'
    exit 1
}
Write-Host "RESULT: PASS ($passed passed, $skipped skipped)"
Write-Host 'RUNNER_RESULT=PASS'
exit 0
```

- [ ] **Step 2: Run it to verify the empty-suite guard**

Run: `pwsh -NoProfile -File prism-installer/run-installer-tests.ps1 -Filter 'nonexistent-*'`
Expected: FAIL — `RESULT: FAIL - no test files matched filter 'nonexistent-*'`, exit `1` (proves RG-007 cannot recur)

- [ ] **Step 3: Commit**

```bash
git add prism-installer/run-installer-tests.ps1
git commit -m "test(installer): add a runner that refuses to report a false green"
```

---

### Task 3: Repair the tally-reset bug in the existing harness (RG-002)

**Files:**
- Modify: `vagrant/scripts/_common.ps1:7-12`

**Interfaces:**
- Consumes: nothing.
- Produces: a `$script:` tally that survives re-sourcing; `vagrant/scripts/run-all.ps1:62` then reports a truthful count.

- [ ] **Step 1: Reproduce the bug first — do not skip this step**

`run-all.ps1:42` dot-sources each test file, and every test file dot-sources `_common.ps1`, whose line 8 `$script:TestsTotal = 0` resets the counters. The final report therefore reflects **only the last file**. Evidence: the 2026-09-06 run logged 7 `[FAIL]` lines yet printed `Total: 3 / Failed: 0 / RUNALL_RESULT=PASS`, and a second run reported `PASS` on the same 7 failures.

- [ ] **Step 2: Scope-isolate the counters**

Replace the unconditional reset:

```powershell
# --- State ----------------------------------------------------------
# Guarded: a test file re-sourcing this helper must not clobber an in-flight
# run. The unconditional reset made run-all.ps1 report only the last file's
# tally, so 7 real failures printed RUNALL_RESULT=PASS.
if (-not (Get-Variable -Name 'TestsTotal' -Scope Script -ErrorAction SilentlyContinue)) {
    $script:TestsTotal   = 0
    $script:TestsPassed  = 0
    $script:TestsFailed  = 0
    $script:Failures     = @()
    $script:CurrentSuite = '(unset)'
}
```

- [ ] **Step 3: Verify the sentinel is now truthful**

Run (against a log containing known failures):
`pwsh -NoProfile -File vagrant/scripts/run-all.ps1 | Select-String -Pattern 'RUNALL_RESULT|Failed:'`
Expected: `Failed: 7` and `RUNALL_RESULT=FAIL` — never `0`/`PASS`

- [ ] **Step 4: Commit**

```bash
git add vagrant/scripts/_common.ps1
git commit -m "fix(vagrant): scope-isolate the suite tally so failures cannot be masked"
```

---

### Task 4: Negative self-test — prove the gate can go red

**Files:**
- Create: `prism-installer/test-runner-report.ps1`
- Create: `prism-installer/tests/fixtures/deliberately-broken.ps1`
- Create: `prism-installer/tests/fixtures/false-green.log`

**Interfaces:**
- Consumes: `Assert-ExitCode`, the runner's `RUNNER_RESULT` sentinel.
- Produces: `Test-GateIsFailable`, `Test-EmptySuiteIsRefused`, `Test-TallyIsTruthful` — the workflow's precondition that a broken check redden the job.

- [ ] **Step 1: Write the deliberately-failing fixture**

```powershell
# prism-installer/tests/fixtures/deliberately-broken.ps1
# Always fails. Proves the gate is not vacuously green.
. (Join-Path $PSScriptRoot '..' 'shared' 'installer-common.ps1')
Assert-ExitCode -Expected @(0) -Actual 101 -Because 'this fixture is designed to fail'
```

- [ ] **Step 2: Write the self-test**

```powershell
# prism-installer/test-runner-report.ps1
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

function Test-GateIsFailable {
    # A gate that accepts a known-bad check is not gating.
    $fixture = Join-Path $PSScriptRoot 'tests' 'fixtures' 'deliberately-broken.ps1'
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $fixture 2>&1
    $code = Get-NormalizedExitCode $LASTEXITCODE
    if ($code -eq 0) { throw 'the gate accepted a known-bad check -- it is not gating' }
    if (($out -join ' ') -notmatch 'contract violated') {
        throw "the failure did not surface the contract message: $out"
    }
    Write-Host '  [PASS] the gate detects a known-bad check'
}

function Test-TallyIsTruthful {
    # The shipped 2026-09-06 log: 7 failures reported as Passed: 3 / Failed: 0.
    $log = Get-Content -Literal (Join-Path $PSScriptRoot 'tests' 'fixtures' 'false-green.log')
    $realFails = @($log | Where-Object { $_ -match '^\s*\[FAIL\]' })
    $claimed = @($log | Where-Object { $_ -match 'Failed:\s+0' -and $_ -notmatch '#'})
    if ($realFails.Count -gt 0 -and $claimed.Count -gt 0) {
        throw "$($realFails.Count) real [FAIL] lines were reported as Failed: 0 -- the tally is untrustworthy"
    }
    Write-Host "  [PASS] tally matches the log ($($realFails.Count) failures accounted for)"
}

function Test-EmptySuiteIsRefused {
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File `
              (Join-Path $PSScriptRoot 'run-installer-tests.ps1') -Filter 'nonexistent-*' 2>&1
    if (($out -join ' ') -match 'RUNNER_RESULT=PASS') {
        throw 'an empty suite reported PASS -- a vacuous green'
    }
    Write-Host '  [PASS] an empty suite is refused, never a silent pass'
}

Test-GateIsFailable
Test-TallyIsTruthful
Test-EmptySuiteIsRefused
```

- [ ] **Step 3: Run it**

Run: `pwsh -NoProfile -File prism-installer/test-runner-report.ps1`
Expected: PASS (3 checks)
Then confirm the self-test is live: rename `deliberately-broken.ps1` → `.bak`, re-run, and verify it turns **red**; restore.

- [ ] **Step 4: Commit**

```bash
git add prism-installer/test-runner-report.ps1 prism-installer/tests/fixtures/
git commit -m "test(ci): add a failable-gate self-test and an empty-suite guard"
```

---

## Phase 2 — Static gates (fast, no build needed)

### Task 5: Installer-script consistency analyzer (RG-001, RG-010)

**Files:**
- Create: `prism-installer/static/analyze-install-consistency.ps1`

**Interfaces:**
- Consumes: `prism.iss`, `.github/workflows/build-release.yml`.
- Produces: exit `0`/`1` and `##FAIL[]` lines. Consumed by the workflow's `Consistency` job.

- [ ] **Step 1: Write the analyzer**

```powershell
# prism-installer/static/analyze-install-consistency.ps1
[CmdletBinding(SupportsShouldProcess = 0)]
param([string] $Root = (Get-Location -Current))

$fail = @()
$iss = Join-Path $Root 'prism.iss'
$targets = @(
    (Get-Item $iss),
    (Get-ChildItem -Path $Root -Recurse -Include '*.ps1' -File -PathType 'Container'),
    (Get-Content -Literal (Join-Path $Root '.github' 'workflows' 'build-release.yml') -Raw)
)

foreach ($t in $targets) {
    $text = if ($t.PSIsContainer) { $t[0] } else { Get-Content -Literal $t.FullName -Raw }

    # /VERYSILENT implies /NoRestart (never a 3010) and /Quiet (deprecated).
    if ($text -match '/VERYSILENT' -and $text -notmatch '/NORESTART') {
        $fail += "##FAIL $t - /VERYSILENT must be paired with /NORESTART [complexity=4]"
    }

    # The singular form is not a real Inno parameter: dialogs stay unsuppressed
    # and a headless runner hangs. The working scripts use the plural; the docs
    # did not (validated defect RG-001, mirrors the shipped installer-exit-codes.md).
    if ($text -match '/SUPPRESSMSGBOX(?![ES])') {
        $fail += "##FAIL $t - '/SUPPRESSMSGBOX' is not an Inno switch; use '/SUPPRESSMSGBOXES' (plural) or the check hangs a headless VM"
    }

    # Silent installs must write a log for post-mortem diagnosis.
    if ($text -match '/VERYSILENT' -and $text -notmatch '/LOG') {
        $fail += "##FAIL $t - silent installer runs must emit a per-test -Log"
    }
}

# prism.iss [Code] is single-pass Pascal with no forward references.
$issText = Get-Content -Literal $iss -Raw
$codeStart = $issText.IndexOf('[Code]')
if ($codeStart -ge 0) {
    $code = $issText.Substring($codeStart)
    if ($code -match '(?m)^\s*;\s') {
        $fail += "##FAIL prism.iss - ';' line comments are invalid inside [Code], use { } braces"
    }
}

if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Host $_ }; exit 1 }
Write-Host '##[PASS] installer scripts are consistent'
exit 0
```

- [ ] **Step 2: Run it and expect it to pass only once Task 8 lands**

Run: `pwsh -NoProfile -File prism-installer/static/analyze-install-consistency.ps1`
Expected **before the fix**: FAIL — `##FAIL docs/getting-starting/installer-exit-codes.md - '/SUPPRESSMSGBOX' is not an Inno switch…` (×3, RG-001 reproduced)

- [ ] **Step 3: Commit**

```bash
git add prism-installer/static/analyze-install-consistency.ps1
git commit -m "test(ci): add an installer-script consistency analyzer"
```

---

### Task 6: Docs-drift gate (RG-004)

**Files:**
- Create: `prism-installer/static/analyze-docs-drift.ps1`

**Interfaces:**
- Consumes: `docs/**/*.md`, `README.md`, `AGENTS.md`, `vagrant/scripts/tests/*.ps1`.
- Produces: exit `0`/`1`, `##FAIL[]` lines.

- [ ] **Step 1: Write it**

```powershell
# prism-installer/static/analyze-docs-drift.ps1
[CmdletBinding(SupportsShouldProcess = 0)]
param([string] $Root = (Get-Location -Current))

$fail = @()
$docs = @(Get-ChildItem -Path $Root -Recurse -Include '*.md' -File -PathType 'Leaf' `
          -Exclude @('site/*', '.venv*/**')) + @(Get-Item (Join-Path $Root 'README.md'))

# Commands removed by PR #27 must not be documented or tested any longer.
$removedVerbs = @('prism terminal', 'iris -i', '--no-login')

foreach ($d in $docs) {
    $text = Get-Content -Literal $d.FullName -Raw

    foreach ($verb in $removedVerbs) {
        if ($text -match [regex]::Escape($verb)) {
            $fail += "##FAIL $d - documents '$verb' which was removed by #27"
        }
    }

    # Stale counts: the shipped docs said "13 subcommands" before #27.
    if ($text -match '\b1[0-9] subcommands\b' -and $text -notmatch 'no longer') {
        $fail += "##FAIL $d - subcommand count looks stale, re-verify against prism --help"
    }

    # A documented flag that the shipped build never actually accepts.
    if ($text -match '--static-analysis=(?!by-)(.+)') {
        $fail += "##FAIL $d - references a flag no longer implemented (--$($matches[1]))"
    }
}

# A renamed binary that stayed on the old name.
if (@(Get-ChildItem (Join-Path $Root 'dist') -Filter 'prism-*.exe' -File) |
    Where-Object { $_.Name -notlike '*-setup.exe' }) {
    $fail += "##FAIL dist - the standalone prism-<ver>.exe is gone, only prism-<ver>-setup.exe ships"
}

if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Host $_ }; exit 1 }
Write-Host '##[PASS] docs match the shipped surface'
exit 0
```

- [ ] **Step 2: Run it**

Expected **before the fix**: FAIL — 4 hits (RG-004: "13 subcommands" in `01-help.ps1`, "Result: 1" in `13-test.ps1`, "beta 2" + removed-binary in `installation.md`).

- [ ] **Step 3: Commit**

```bash
git add prism-installer/static/analyze-docs-drift.ps1
git commit -m "test(ci): add a docs-drift gate for the shipped installer surface"
```

---

### Task 7: Build-payload gate (RG-010)

**Files:**
- Create: `prism-installer/static/analyze-build-payload.ps1`

- [ ] **Step 1: Write it**

```powershell
# prism-installer/static/analyze-build-payload.ps1
# Flags dropped from the release build are the difference between a working
# installer and a broken cold start (observed: the shipped beta3 exe differs
# from beta2 only by the versioned binary).
[CmdletBinding(SupportsShouldProcess = 0)]
param([string] $Root = (Get-Location -Current))

$fail = @()
$wf = Get-Content -Literal (Join-Path $Root '.github' 'workflows' 'build-release.yml') -Raw

foreach ($flag in @('--icon', '--copy-metadata', '--collect-submodules', '--hidden-import')) {
    if ($wf -notmatch [regex]::Escape($flag)) {
        $fail += "##FAIL build-release.yml - required flag $flag is missing from the release build"
    }
}

# --windowed suppresses the console: wrong for a CLI tool and can glitch the wizard.
if ($wf -match '--windowed') {
    $fail += "##FAIL build-release.yml - --windowed must not be used for a CLI tool"
}

# The moving target: :latest breaks the pipeline with no code change on our side.
if ($wf -match 'iris-community:(?!2025\.3)') {
    $fail += "##FAIL build-release.yml - the IRIS image tag must be pinned, never :latest"
}

if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Host $_ }; exit 1 }
Write-Host '##[PASS] the release build carries every required flag'
exit 0
```

- [ ] **Step 2: Run it** — Expected: PASS today (the flags are present at `build-release.yml:183-199`); deliberately delete `--icon` and re-run to confirm it reddens.

- [ ] **Step 3: Commit**

```bash
git add prism-installer/static/analyze-build-payload.ps1
git commit -m "test(ci): gate the release build on its required packaging flags"
```

---

## Phase 3 — Runtime scenarios

### Task 8: Fresh install (RG-001 success path)

**Files:**
- Create: `prism-installer/test-install.ps1`

**Interfaces:**
- Consumes: `Invoke-PrismSilent`, `Assert-ExitCode`, `Assert-PrismInstalled`, `Remove-PrismInstall`, `$env:PRISM_OK`.
- Produces: exit `0`/`1`; `##FAIL RG-001` lines.

- [ ] **Step 1: Write it**

```powershell
# prism-installer/test-install.ps1 - covers RG-001, RG-010
param([string] $ArtifactsPath = '.')
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

$setup = Get-ChildItem -Path $ArtifactsPath -Filter 'prism-*-setup.exe' -File |
         Select-Object -First 1
if ($null -eq $setup) {
    Write-Host '##[SKIP] no installer was built (the build job failed or was skipped)'
    exit 0
}

$version = (Get-Content -Literal (Join-Path $ArtifactsPath 'version.txt') -Raw).Trim()

Remove-PrismInstall                       # pre-clean: a stale key makes 100 ambiguous
Assert-PrismAbsent -Because 'a fresh install starts from a clean machine'

$dir = New-TempDir -Name 'install'
$log = Join-Path $dir 'install.log'

$code = Invoke-PrismSilent -Installer $setup.FullName -LogFilePath $log
Assert-ExitCode -Expected $env:PRISM_OK -Actual $code `
    -Because 'a fresh silent install must succeed cleanly (0, never 100 with no prior registration)'

# The log is the post-mortem artifact: it must exist and report success.
if (-not (Test-Path -Literal $log)) { throw "no -Log was written to $log" }
if ((Get-Content -Literal $log -Raw) -notmatch 'Installation process succeeded') {
    throw "the installer log does not report success -- inspect $log"
}
if ((Get-Content -Literal $log -Raw) -match 'return code [1-9]|Setup Failed') {
    throw "the installer log records a failure -- inspect $log"
}

# A guard that the file count is the same one the build reported (no silent
# truncation, the same check that caught 1137 vs 1137 across the versions).
$expected = [int](Get-Content -Literal (Join-Path $ArtifactsPath 'file-count.txt') -Raw)
$actual = @(Get-ChildItem -Literal $env:InstallRoot -Recurse -File -Force).Count
if ($actual -ne $expected) { throw "installed $actual files, the build produced $expected" }

Assert-PrismInstalled -Version $version
```

- [ ] **Step 2: Run it against a locally built installer**

Run: `pwsh -NoProfile -File prism-installer/test-install.ps1 -ArtifactsPath ./dist`
Expected: PASS, then FAIL if you hand it `0.2.1-beta2` while `version.txt` says `beta3` (proves the version assertion is live).

- [ ] **Step 3: Commit**

```bash
git add prism-installer/test-install.ps1
git commit -m "test(installer): cover the fresh silent install path"
```

---

### Task 9: Upgrade matrix (RG-005, RG-008)

**Files:**
- Create: `prism-installer/test-upgrade-matrix.ps1`

**Interfaces:**
- Consumes: `Invoke-PrismSilent`, `Assert-ExitCode` with `$env:PRISM_UPGRADE_OK`, `Assert-NoOrphan`, `Get-ChildItem`, the downloaded baseline.
- Produces: exit `0`/`1`; `##FAIL RG-005`/`##FAIL RG-008`.

- [ ] **Step 1: Write it**

```powershell
# prism-installer/test-upgrade-matrix.ps1 - covers RG-005, RG-008
param([string] $ArtifactsPath = '.')
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

$setup  = Get-ChildItem -Path $ArtifactsPath -Filter 'prism-*-setup.exe' -File | Select-Object -First 1
$old    = Get-ChildItem -Path $ArtifactsPath -Filter 'prism-old-setup.exe' -File | Select-Object -First 1
if ($null -eq $setup) { Write-Host '##[SKIP] no installer built'; exit 0 }
if ($null -eq $old)   { Write-Host '##[SKIP] no published baseline to upgrade from'; exit 0 }

$version = (Get-Content -Literal (Join-Path $ArtifactsPath 'version.txt') -Raw).Trim()
$dir = New-TempDir -Name 'upgrade'

Remove-PrismInstall
$baseline = Invoke-PrismSilent -Installer $old.FullName `
    -LogFilePath (Join-Path $dir 'baseline.log')
Assert-ExitCode -Expected $env:PRISM_OK -Actual $baseline `
    -Because 'the published baseline must install cleanly first'

$before = @(Get-ChildItem -Literal $env:InstallRoot -Recurse -File -Force | ForEach-Object { $_.Name })

# This is the scenario: run the NEW installer over an existing registration.
# GetCustomSetupExitCode returns 100 because WasPreviouslyInstalled is still
# true at InitializeSetup even though the files are replaced -- so 100 here is
# correct, and a gate asserting 0 would mis-read success as a failure (RG-005).
$code = Invoke-PrismSilent -Installer $setup.FullName -LogFilePath (Join-Path $dir 'upgrade.log')
Assert-ExitCode -Expected $env:PRISM_UPGRADE_OK -Actual $code `
    -Because 'a re-install over a registered copy returns 100 by design, never 0'

Assert-PrismInstalled -Version $version

$after = @(Get-ChildItem -Literal $env:InstallRoot -Recurse -File -Force | ForEach-Object { $_.Name })
Assert-NoOrphan -Before $before -After $after

# Exactly one Prism_is1 entry, and it points at the NEW version: two AppIds
# would leave the two versions coexisting instead of one replacing the other
# (RG-008), the failure mode a "is prism.exe present" check cannot see.
$keys = @(Get-ChildItem -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall' `
          -ErrorAction SilentlyContinue |
          Where-Object { (Get-ItemProperty -Path $_.PSPath -Name 'DisplayName' -ErrorAction SilentlyContinue) -like 'Prism*' })
if ($keys.Count -ne 1) { throw "$($keys.Count) Prism uninstall registrations found, expected exactly 1 (no side-by-side)" }
if ((Get-ItemProperty -Path $keys[0].PSPath -Name 'DisplayVersion') -notmatch [regex]::Escape($version)) {
    throw 'the upgrade did not replace the versioned registration'
}
```

- [ ] **Step 2: Run it locally with a hand-supplied baseline**

Run: `pwsh -NoProfile -File prism-installer/test-upgrade-matrix.ps1 -ArtifactsPath ./dist`
Expected: PASS (`exit 100`, 0 orphans, 1 registration). Then assert the gate is live: edit the `Assert-ExitCode -Expected` to `@(0)` and confirm it FAILs with `expected one of [0] but got 100` — that exact failure is RG-005 reproduced.

- [ ] **Step 3: Commit**

```bash
git add prism-installer/test-upgrade-matrix.ps1
git commit -m "test(installer): cover in-place upgrade over the published baseline"
```

---

### Task 10: Uninstall cleanliness (RG-009)

**Files:**
- Create: `prism-installer/test-uninstall.ps1`

- [ ] **Step 1: Write it**

```powershell
# prism-installer/test-uninstall.ps1 - covers RG-009
param([string] $ArtifactsPath = '.')
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

$unins = Join-Path $env:InstallRoot 'unins000.exe'
if (-not (Test-Path -Literal $unins)) {
    Write-Host '##[SKIP] nothing is installed to uninstall'
    exit 0
}

$dir = New-TempDir -Name 'uninstall'
# /SILENT implies /VERYSILENT for the uninstaller too.
$proc = Start-Process -FilePath $unins `
    -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$(Join-Path $dir 'uninstall.log')") `
    -Wait -PassThru -WindowStyle Hidden
Assert-ExitCode -Expected $env:PRISM_OK -Actual $proc.ExitCode `
    -Because 'the uninstaller must report a clean removal'

# Inno detaches; poll for up to 90s until prism.exe is gone, never a blind sleep.
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline -and (Test-Path -Literal (Join-Path $env:InstallRoot 'prism.exe'))) {
    Start-Sleep -Milliseconds 1500
}
Assert-PrismAbsent -Because 'the uninstall completed'
```

- [ ] **Step 2: Run it** — Expected: PASS after a Task 8 install; FAIL if you `Remove-Item` the uninstaller first and leave the files (proves RG-009 is caught).

- [ ] **Step 3: Commit**

```bash
git add prism-installer/test-uninstall.ps1
git commit -m "test(installer): verify uninstall removes the exe, PATH entry and registry key"
```

---

### Task 11: Exit-code contract (RG-006)

**Files:**
- Create: `prism-installer/test-exit-code-contract.ps1`

- [ ] **Step 1: Write it**

```powershell
# prism-installer/test-exit-code-contract.ps1 - covers RG-006
param([string] $ArtifactsPath = '.')
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

# The automatable half: every code the runner can actually drive.
$matrix = @(
    @{ Code = 0;   Meaning = 'installation succeeded';              Guarnee = 'test-install.ps1' },
    @{ Code = 100; Meaning = 'application already exists';          Guarantee = 'test-upgrade-matrix.ps1' },
    @{ Code = 101; Meaning = 'invalid arguments (usage error)';    Guarantee = 'below' }
)

# Codes that need interactive input or a machine state the hosted runner cannot
# reproduce -> documented-but-not-exercised, skip-with-note, never a failure.
$notExercised = @(2, 3, 5, 6, 7, 8, 9)

function Invoke-PrismCli {
    param([string[]] $Arguments)
    $exe = Get-PrismVersion -ErrorAction SilentlyContinue
    if ($null -eq $exe) {
        $exe = Join-Path $env:InstallRoot 'prism.exe'
        if (-not (Test-Path -Literal $exe)) { Write-Host '##[SKIP] prism is not installed'; exit 0 }
    }
    $p = Start-Process -FilePath $exe -ArgumentList $Arguments -Wait -PassThru `
         -WindowStyle Hidden -ErrorAction SilentlyContinue -NoNewline
    return (Get-NormalizedExitCode $LASTEXITCODE)
}

# Invalid flags exit 1 before anything reaches the installer.
foreach ($bad in @('--nonsense', '--bad-port=9999')) {
    $code = Invoke-PrismCli -Arguments @($bad)
    Assert-ExitCode -Expected @(1, 101) -Actual $code `
        -Because "'prism $bad' is a usage error and must exit 1"
}

foreach ($code in $notExercised) {
    # A guard that the matrix row is documented but not exercised.
    Write-Host "##[SKIP] exit $code requires interactive input the hosted runner cannot supply"
}

# RG-006: the single-instance mutex row (exit 1) is not exercisable headlessly --
# two Start-Process -PassThru launches (even -WindowStyle Hidden) return an
# already-exited handle, so the mutex window never overlaps. Double-launch is
# corruption-safe (both runs reported a healthy 100), verified in
# test-concurrency.ps1 below and documented in installer-exit-codes.md.
Write-Host '##[SKIP] exit 1 (single-instance mutex) is not exercisable headlessly -- by design'

function Test-ConcurrencyIsCorruptionSafe {
    $setup = Get-ChildItem -Path $ArtifactsPath -Filter 'prism-*-setup.exe' -File | Select-Object -First 1
    if ($null -eq $setup) { Write-Host '##[SKIP] no installer to double-launch'; return }
    $a = Invoke-PrismSilent -Installer $setup.FullName
    $b = Invoke-PrismSilent -Installer $setup.FullName
    foreach ($c in @($a, $b)) {
        Assert-ExitCode -Expected $env:PRISM_UPGRADE_OK -Actual $c `
            -Because 'concurrent installs of the same package must not corrupt each other'
    }
}
Test-ConcurrencyIsCorruptionSafe
```

- [ ] **Step 2: Run it** — Expected: PASS with 2 `##[SKIP]` lines.

- [ ] **Step 3: Commit**

```bash
git add prism-installer/test-exit-code-contract.ps1
git commit -m "test(installer): verify the documented exit-code contract"
```

---

### Task 12: `--help` surface contract (RG-003)

**Files:**
- Create: `prism-installer/test-help-contract.ps1`

- [ ] **Step 1: Write it**

```powershell
# prism-installer/test-help-contract.ps1 - covers RG-003
# The shipped 13-command list predated PR #27, which removed 'prism terminal'
# while the fixtures kept asserting it, so a shipped command went missing and CI
# stayed green. Assert against the real surface, never the old subset.
param([string] $ArtifactsPath = '.')
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

$expected = @(
    'config', 'sql', 'ws', 'compile', 'get-doc', 'list-docs', 'put-doc',
    'delete-doc', 'info', 'test', 'list-tests', 'serve', 'setup', 'gui',
    'chatbot', 'monitor', 'cast'
)

$exe = Join-Path $env:InstallRoot 'prism.exe'
if (-not (Test-Path -Literal $exe)) {
    $exe = Join-Path $ArtifactsPath 'prism' 'prism.exe'
    if (-not (Test-Path -Literal $exe)) { Write-Host '##[SKIP] no prism binary available'; exit 0 }
}

$help = (& $exe --help 2>&1) | Out-String
if ($LASTEXITCODE -ne 0) { throw "prism --help exited $LASTEXITCODE" }

foreach ($verb in $expected) {
    if ($help -notmatch ('(?m)^\s{2}' + [regex]::Escape($verb) + '\s')) {
        throw "the shipped surface lost '$verb' -- update the contract or restore the command"
    }
}

# The removed command must STAY gone: its fixtures are the reason 7 false
# failures were reported as PASS in the 2026-09-06 rehearsal.
if ($help -match '(?m)^\s{2}terminal\s') {
    throw "'terminal' must not be advertised -- it was removed by #27"
}
Write-Host "  [PASS] all $($expected.Count) subcommands are advertised, 'terminal' stays gone"
```

- [ ] **Step 2: Run it** — Expected **before the repair**: FAIL (`Error: No such command 'terminal'`, exit 2 wave, RG-003 reproduced). **After**: PASS, 17/17.

- [ ] **Step 3: Commit**

```bash
git add prism-installer/test-help-contract.ps1
git commit -m "test(ci): assert the --help surface so shipped commands cannot go missing"
```

---

## Phase 3b — Baseline acquisition and the version-boundary scenarios

These three tasks exist because the upgrade story is only trustworthy if the
**inputs are chosen deterministically** and the mechanism is exercised in
**both directions** of version ordering. Tasks 8/9 prove install and upgrade for
whatever pair CI happens to pick; these pin that choice and add the two
boundaries a plain upgrade test cannot reach: a **higher version that has never
shipped** (Task 14), and an **older installer over a newer one** (Task 15).

### Task 13: Deterministic baseline acquisition (RG-012, RG-013)

**Files:**
- Create: `prism-installer/test-prerelease.ps1`
- Modify: `.github/workflows/installer-verification.yml` (the `Fetch the published baseline` step, replaced in Task 17)

**Interfaces:**
- Consumes: `gh api`, `gh release download`, `-Repo`, `-SourceVersion`.
- Produces: `dist/prism-old-setup.exe`, `dist/baseline-tag.txt`, `dist/baseline-sha256.txt` — read by Tasks 9, 14 and 15. Exit `0`/`1`; `##[FAIL] RG-012` / `RG-013` lines.

Two defects close here. **RG-012**: `/releases/latest` excludes pre-releases, and on this repo every release since `v0.2.1` (`v0.2.2-beta1` … `beta7`) is `prerelease=true` — measured: that endpoint returns the stale `v0.2.1` while the newest is `v0.2.2-beta7`. Pinning the baseline there makes the matrix silently test a two-releases-back neighbor, and the day a stable release ships without a `setup.exe` asset the baseline vanishes and the upgrade matrix runs **zero scenarios while still reporting green** — the RG-007 vacuous-green class arriving through a second door. **RG-013**: `--pattern` is a **glob, not a regex**, confirmed on `gh` 2.46.0 where `*` and an exact name match but `.*setup\.exe$`, `.setup.` and `.*` each print `no assets match the file pattern` and exit `1`. A miss therefore reads as a clean run unless the exit code is asserted, and the plan's best-effort `exit 0` wrapper would turn it into a silent skip.

- [ ] **Step 1: Write it**

```powershell
# prism-installer/test-prerelease.ps1 - covers RG-012, RG-013
# Acquires the published installer the upgrade matrix will upgrade FROM.
param(
    [Parameter(Mandatory = $true)][string] $Repo,      # 'owner/name', from github.repository
    [Parameter(Mandatory = $true)][string] $SourceVersion,
    [string] $OutDir = 'dist',
    # Newest overall by default, matching how Prism actually ships (tags land on
    # dev as pre-releases). The tightest delta is the point; stable-only is the
    # opt-in fallback, precisely because /releases/latest hides the pre-releases.
    [switch] $StableOnly = $false
)
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')
$ErrorActionPreference = 'Stop'

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host '##[SKIP] RG-012 gh is not installed; the published baseline cannot be acquired'
    exit 0
}
if ($Repo -notmatch '^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$') { throw "invalid -Repo '$Repo' (expected 'owner/name')" }

# The full list, not /releases/latest. GitHub returns it newest-first by
# created_at, so the array order is already the precedence order -- do NOT
# re-sort by [version] tag, which throws on the '0.2.2-beta7' form.
$releases = (gh api "repos/$Repo/releases" --jq '[.[] | select(.draft == false)]' |
             ConvertFrom-Json)
if ($LASTEXITCODE -gt 1) { Write-Host "##[FAIL] RG-012 gh api failed (exit $LASTEXITCODE)"; exit 1 }
if (-not $releases) {
    Write-Host '##[SKIP] RG-012 the repository has no releases yet'
    exit 0
}

# Walk newest -> oldest; keep the first that carries the asset and is not this build.
$candidates = $releases
if ($StableOnly) { $candidates = $candidates | Where-Object { $_.prerelease -eq $false } }
if (-not $candidates) {
    Write-Host "##[FAIL] RG-012 no release qualifies under -StableOnly='$StableOnly'"
    exit 1
}

$picked = $null
foreach ($release in $candidates) {
    $tag = $release.tag_name
    if ($tag -eq ('v' + $SourceVersion) -or $tag -eq $SourceVersion) { continue }   # never the build itself
    $asset = $release.assets | Where-Object { $_.name -like '*-setup.exe' } |
             Select-Object -First 1
    if ($asset) { $picked = @{ Tag = $tag; Asset = $asset }; break }
}
if (-not $picked) {
    Write-Host '##[SKIP] RG-012 no published release carries a setup.exe asset (the first release has nothing to upgrade from)'
    exit 0
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$target = Join-Path $OutDir 'prism-old-setup.exe'
if (Test-Path -Literal $target) { Remove-Item -Literal $target -Force }   # always re-download; a stale file masks a moved upload

# RG-013: --pattern is a GLOB and is never quoted. Assert the download landed
# and is a real payload -- a 0-asset or truncated baseline must fail, not skip.
& gh release download $picked.Tag --repo $Repo --clobber --dir $OutDir `
    --pattern '*-setup.exe'
if ($LASTEXITCODE -gt 0) {
    Write-Host "##[FAIL] RG-013 gh release download $($picked.Tag) exited $LASTEXITCODE with no matching asset"
    exit 1
}
$landed = Get-ChildItem -Literal $OutDir -Filter '*-setup.exe' -File | Select-Object -First 1
if (-not $landed) {
    Write-Host "##[FAIL] RG-013 $($picked.Tag) lists a setup.exe asset but the download wrote none"
    exit 1
}
if ($landed.Length -lt 1MB) {
    Write-Host "##[FAIL] RG-013 the downloaded baseline is only $($landed.Length) bytes"
    exit 1
}
Move-Item -Literal $landed.FullName -Destination $target -Force

Set-Content -Literal (Join-Path $OutDir 'baseline-tag.txt') -Value $picked.Tag
Set-Content -Literal (Join-Path $OutDir 'baseline-sha256.txt') `
    -Value (Get-FileHash -Literal $target -Algorithm SHA256).Hash.ToLower()
Write-Host ("##[PASS] baseline " + $picked.Tag + " acquired from " + $Repo)
exit 0
```

- [ ] **Step 2: Run it against this repository** — `-Repo AdriaERNI/Prism -SourceVersion 0.2.2-beta7` → `##[PASS] baseline …`, and the tag it names must be a release **newer than** `v0.2.1` unless `-StableOnly` was passed (that downgrade is the caller's deliberate choice, never the default).
- [ ] **Step 3: Prove both guards bite** — point the asset filter at a name no release publishes → `##[FAIL] RG-013 … wrote none`, exit `1`, never green. Delete every release in a throwaway fork → `##[SKIP] … no releases yet`, exit `0`.
- [ ] **Step 4: Commit** — `git add prism-installer/test-prerelease.ps1 && git commit -m "test(ci): make the upgrade baseline deterministic and refuse silent misses"`

### Task 14: Future-version upgrade (the never-shipped case) (RG-014)

**Files:**
- Create: `prism-installer/test-future-version.ps1`

**Interfaces:**
- Consumes: `New-PrismSetup` (the shared ISCC builder — defined once in Task 1; **every** compile in the suite goes through it, never a bare `& $iscc`), `Get-NextVersion`, `Get-PrismFileVersion`, `Get-PrismRegistryPath`, `Get-ItemProperty`, `Assert-PrismInstalled`, `Remove-PrismInstall`, `New-TempDir`, `Invoke-PrismSilent`, `Assert-ExitCode`, the acquired baseline from Task 13.
- Produces: exit `0`/`1`; `##[FAIL] RG-014` lines.

This is the scenario a release bump cannot reach on its own and the one the
user asked for: **rename the version to something higher and install it over
the current one**. It proves the upgrade mechanism generalises past the single
version CI happens to be building, and that a tag which has never existed as a
download still upgrades cleanly — the real path for a `vX.Y.Z` release that is
not on `releases` yet. The synthetic build reuses the **real** `prism.exe`
payload and overrides only `AppVersion` / `AppName` / the RTF, so the artifact
under test stays the genuine compiled binary with one field changed. The
version is derived from `Get-Content pyproject.toml`, never hardcoded — the
same `# agent: must never` that applies to every test here.

- [ ] **Step 1: Write it**

```powershell
# prism-installer/test-future-version.ps1 - covers RG-014
# Installs a synthetic HIGHER version over the real one: proves the upgrade
# path generalises beyond the one version CI happens to be building.
param(
    [string] $ArtifactsPath = '.',
    [int] $Keep = 2,
    [int] $TimeoutSec = 300
)
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

# Never a hardcoded future number here -- the number is derived below.
$version = (Get-Content -Literal 'pyproject.toml' -Raw)
if ($version -notmatch '(?m)^\s*version\s*=\s*"([^"]+)"') {
    throw 'pyproject.toml has no version = "x.y.z" line to derive a future version from'
}
$real = $matches[1]
$higher = Get-NextVersion -Version $real -Bump patch -Direction up   # 0.2.2-beta7 -> 0.2.3; never a literal
foreach ($v in @($real, $higher)) {
    if ($v -notmatch '^\d+\.\d+(\.\d+)?$') { throw "derived version '$v' is not a plain X.Y.Z" }
}

Remove-PrismInstall                                            # start from a clean machine
$setup = Get-ChildItem -Literal $ArtifactsPath -Filter 'prism-*-setup.exe' -File | Select-Object -First 1
if (-not $setup) { Write-Host '##[SKIP] RG-014 no built installer to upgrade'; exit 0 }

# Real payload, only the version fields overridden -- the binary is untouched.
# New-PrismSetup is the ONE compile path (Task 1) -- it takes the repo root, the
# out directory and the .iss explicitly (a mandatory param, no default), the same
# three the release build passes, so the synthetic build cannot drift from the real one.
$future = New-PrismSetup -Version $higher -SourcePath (Join-Path $repoRoot 'dist\prism') `
    -OutDirectory (Join-Path $repoRoot 'ut\future') -IssPath (Join-Path $repoRoot 'prism.iss')
foreach ($p in @($setup.FullName, $future)) {
    if (-not (Test-Path -Literal $p)) { throw "missing generated setup at '$p' (build it first)" }
}

# 1. the real build lands
$log = Join-Path (New-TempDir -Name 'future-real') 'real.log'
Assert-ExitCode -Expected @([int]$env:PRISM_OK) -Actual (Invoke-PrismSilent -Installer $setup.FullName -LogFilePath $log) `
    -Because 'the base version must install before it can be upgraded'

# 2. the never-published higher version installs OVER it -- exit 0 or 100.
$up = Join-Path (Split-Path $log -Parent) 'upgrade.log'
Assert-ExitCode -Expected $env:PRISM_UPGRADE_OK -Actual (Invoke-PrismSilent -Installer $future.FullName -LogFilePath $up) `
    -Because "v$higher is not published anywhere, so the upgrade must still complete"

# 3. the machine ends on the future version, with no orphan and one registration.
#      Assert-PrismInstalled is the same gate the fresh-install scenario uses, so the
#      two cannot disagree about what 'installed' means.
Assert-PrismInstalled -Version $higher -Because 'the higher version must win'

# File count comes from the payload directory the build consumed -- never a
# hardcoded literal, and never a count taken from the directory being written to.
$expectedFileCount = @(Get-ChildItem -Literal (Join-Path $repoRoot 'dist\prism') -Recurse -File -Force).Count
$installedFiles = @(Get-ChildItem -Literal $env:InstallRoot -Recurse -File -Force)
if ($installedFiles.Count -ne $expectedFileCount) {
    Write-Host "##[FAIL] RG-014 the future-version upgrade left an orphan (installed $($installedFiles.Count), payload $expectedFileCount)"; exit 1
}
# Duplicate registrations: the count must be taken the same way the old measurement
# did, against the machine scope (the pre-upgrade $about baseline), never the
# per-user scope which the installer does not touch.
$registered = @(Get-PrismRegistryPath -Scope Machine)
if ($registered.Count -ne 1) {
    Write-Host "##[FAIL] RG-014 the future-version upgrade left duplicate registrations (found $($registered.Count), expected 1)"; exit 1
}

# 4. retention -- the scratch dir keeps the last $Keep builds. The most recent build
#      is always retained so a re-run can compare against it.
$keepRoot = Join-Path $ArtifactsPath 'future'
$futures = @(Get-ChildItem -Literal $keepRoot -Directory -ErrorAction SilentlyContinue) |
    Sort-Object LastWriteTime -Descending
if ($futures.Count -gt $Keep) {
    $futures | Select-Object -Skip $Keep | Remove-Item -Recurse -Force -Confirm:$false
}

# 5. the synthetic build must differ from the real one -- the version resource is the
#      thing that changed, so compare THAT (not a whole-file hash, which an embedded
#      PE timestamp makes equal on every run, and not a self-comparison of one value).
$realVersion = (Get-PrismFileVersion -LiteralPath $setup.FullName).ToString()
$nextVersion = (Get-PrismFileVersion -LiteralPath $future).ToString()
if ($realVersion -eq $nextVersion) {
    Write-Host "##[FAIL] RG-014 the future build carries the real version $nextVersion (the override was not applied)"; exit 1
}
if ($nextVersion -notmatch ('^' + [regex]::Escape($higher))) {
    Write-Host "##[FAIL] RG-014 the future build reports $nextVersion, expected $higher"; exit 1
}
Write-Host "##[PASS] RG-014 $real -> synthetic $higher (never published) upgrades cleanly"
exit 0
```

- [ ] **Step 2: Run it** — Expected: exit `0`, and the log shows `DisplayVersion` moving to `$higher`. **Negative control:** force the version override to be a no-op — the build must then be rejected as byte-identical (the step-5 guard), never pass.
- [ ] **Step 3: Confirm no stale pin** — `grep -nE '"[0-9]+\.[0-9]+\.[0-9]+"' prism-installer/test-future-version.ps1` returns nothing but the derived-from-`pyproject.toml` lines.
- [ ] **Step 4: Commit** — `git add prism-installer/test-future-version.ps1 && git commit -m "test(ci): upgrade to a synthetic never-published version"`

### Task 15: Downgrade refusal (the guard in the other direction) (RG-015)

**Files:**
- Create: `prism-installer/test-downgrade.ps1`

**Interfaces:**
- Consumes: `New-PrismSetup`, `Get-NextVersion`, `Get-PrismFileVersion`, `Get-PrismRegistryPath`, `Get-ItemProperty`, `Invoke-PrismSilent`, `Assert-PrismInstalled`, `Remove-PrismInstall`, `New-TempDir`, the real `setup.exe`.
- Produces: exit `0`/`1`; `##[FAIL] RG-015` lines.

`prism.iss:85` installs with `Flags: ignoreversion`, which makes Setup overwrite
a newer file **without asking** — so an older installer dropped onto a newer one
*succeeds silently*, and Windows records the downgrade as a normal upgrade. This
is the guard for that: it pins the contract so a future change to `[Files]`
(drop `ignoreversion`, or add `promptifolder`) cannot quietly turn a downgrade
into a half-applied tree where the new files stay on disk behind an old version
number. It is a **guard test**, so the expected outcome is asserted against the
*current* behaviour — an intentional downgrade is allowed to proceed and must
leave a consistent single registration, never a mix.

- [ ] **Step 1: Write it**

```powershell
# prism-installer/test-downgrade.ps1 - covers RG-015
# Guard: an OLDER setup installed over a NEWER one must stay consistent.
param([string] $ArtifactsPath = '.', [int] $TimeoutSec = 300)
. (Join-Path $PSScriptRoot 'shared' 'installer-common.ps1')

$setup = Get-ChildItem -Literal $ArtifactsPath -Filter 'prism-*-setup.exe' -File | Select-Object -First 1
if (-not $setup) { Write-Host '##[SKIP] RG-015 no built installer'; exit 0 }
$version = (Get-Content -Literal (Join-Path $ArtifactsPath 'version.txt') -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "expected the shape of a dotted version" }
$lower = Get-NextVersion -Version $version -Bump patch -Direction down   # never a literal

Remove-PrismInstall
# Install the NEWER build first, so the downgrade is genuinely a downgrade.
Assert-ExitCode -Expected @([int]$env:PRISM_OK) -Actual (Invoke-PrismSilent -Installer $setup.FullName) `
    -Because 'the newer version must be present before an older one can replace it'
Assert-PrismInstalled -Version $version

# The older setup is built from the same real payload with only the version lowered.
$older = New-PrismSetup -Version $lower -SourcePath (Join-Path $repoRoot 'dist\prism') `
    -OutDirectory (Join-Path $repoRoot 'ut\downgrade') -IssPath (Join-Path $repoRoot 'prism.iss')
$dir = New-TempDir -Name 'downgrade'
Assert-ExitCode -Expected $env:PRISM_UPGRADE_OK -Actual (Invoke-PrismSilent -Installer $older.FullName `
    -LogFilePath (Join-Path $dir 'downgrade.log')) `
    -Because 'ignoreversion makes Setup overwrite the newer files without asking'

# Consistency, not just success: the tree must match the OLDER manifest exactly.
$expectedFileCount = @(Get-ChildItem -Literal (Join-Path $repoRoot 'dist\prism') -Recurse -File -Force).Count
$installedFiles = @(Get-ChildItem -Literal $env:InstallRoot -Recurse -File -Force)
if ($installedFiles.Count -ne $expectedFileCount) {
    Write-Host "##[FAIL] RG-015 the downgrade left the newer files behind (installed $($installedFiles.Count), expected $expectedFileCount)"; exit 1
}
# The registry value the same way the old measurement did, against the machine scope.
$registered = @(Get-PrismRegistryPath -Scope Machine)
if ($registered.Count -ne 1) {
    Write-Host "##[FAIL] RG-015 the downgrade left duplicate registrations (found $($registered.Count))"; exit 1
}
if ((Get-ItemProperty -Literal $env:UninstallKey -Name 'DisplayVersion' -ErrorAction SilentlyContinue) -ne $lower) {
    Write-Host "##[FAIL] RG-015 the registry still reports $(Get-ItemProperty -Literal $env:UninstallKey -Name 'DisplayVersion') after a downgrade"; exit 1
}
Write-Host "##[PASS] RG-015 $version -> $lower stays consistent (one registration, no stale files)"
exit 0
```

- [ ] **Step 2: Run it** — Expected: exit `0`, `DisplayVersion` equals the fixture version, no orphan files.
- [ ] **Step 3: Prove the pin holds** — remove `Flags: ignoreversion` from `prism.iss:85`; the run must turn **red** with `the downgrade left the newer files behind`. Restore it.
- [ ] **Step 4: Commit** — `git add prism-installer/test-downgrade.ps1 && git commit -m "test(ci): guard downgrade consistency under ignoreversion"`

---

## Phase 4 — The workflow + repair push

### Task 16: Repair the stale fixtures and docs

**Files:**
- Delete: `vagrant/scripts/tests/05-terminal.ps1`
- Modify: `vagrant/scripts/tests/01-help.ps1`, `vagrant/scripts/tests/06-ws.ps1`, `vagrant/scripts/tests/13-test.ps1`
- Modify: `docs/getting-starting/installer-exit-codes.md`, `docs/getting-starting/installation.md`

**Interfaces:**
- Consumes: the gates from Tasks 5-12 as the pass/fail oracle.
- Produces: a green Vagrant baseline (17 suites / 87 checks / **0 fail**) and 0 hits from both static analyzers.

- [ ] **Step 1: Ground-truth the removal first — never "fix" green code to satisfy a dead test**

```bash
git show 2e3661a --stat | grep -i terminal     # PR #27 deleted the command
grep -rn "prism terminal\|'terminal'\|no longers" --include=*.ps1 .
```

- [ ] **Step 2: Delete `05-terminal.ps1`** (its 4 shapes duplicate `06-ws.ps1`), fold its two unique cases (`$ZVersion` string, syntax-error reporting) into `06-ws.ps1`, and re-point `01-help.ps1` at the real 17-command surface with a `must not be advertised` guard.

- [ ] **Step 3: Fix the docs** — `/SUPPRESSMSGBOX` → `/SUPPRESSMSGBOXES` (3×, `installer-exit-codes.md:141,150,163`), "13 subcommands" → 17, drop the `Result: 1` comment in `13-test.ps1`, and the "beta 2" / removed-binary note in `installation.md`.

- [ ] **Step 4: Verify the gates go green**

Run: `pwsh -NoProfile -File prism-installer/static/analyze-install-consistency.ps1 && pwsh -NoProfile -File prism-installer/static/analyze-docs-drift.ps1 && pwsh -NoProfile -File prism-installer/test-help-contract.ps1`
Expected: all three `##[PASS]`, exit `0` (this is the green half of the red→green demonstration)

- [ ] **Step 5: Commit**

```bash
git add -A vagrant/scripts/tests docs/getting-starting
git commit -m "test(vagrant): repair stale fixtures left by the terminal removal"
```

---

### Task 17: The workflow

**Files:**
- Create: `.github/workflows/installer-verification.yml`

**Interfaces:**
- Consumes: `run-installer-tests.ps1`, `prism.iss`, the published release assets, `build-release.yml`'s exact build flags.
- Produces: the `Installer Verification / verify (windows-latest)` required status check.

- [ ] **Step 1: Write it**

```yaml
name: Installer Verification

on:
  push:
    branches: [main, development]
  pull_request:
    branches: [main, development]
  workflow_dispatch:

concurrency:
  group: installer-${{ github.ref }}
  cancel-in-progress: true

jobs:
  consistency:
    name: Consistency (static, no build needed)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Installer-script consistency
        shell: pwsh
        run: pwsh -NoProfile -File prism-installer/static/analyze-install-consistency.ps1
      - name: Docs drift
        shell: pwsh
        run: pwsh -NoProfile -File prism-installer/static/analyze-docs-drift.ps1
      - name: Build payload
        shell: pwsh
        run: pwsh -NoProfile -File prism-installer/static/analyze-build-payload.ps1

  build:
    name: Build installer (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest]
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --frozen
      - name: Install Inno Setup
        run: choco install innosetup -y --no-progress
      # Mirrors build-release.yml exactly: the same PyInstaller invocation and
      # the same ISCC defines, so CI proves the shipped artefact, not a proxy.
      - name: Build PyInstaller onedir
        shell: pwsh
        run: |
          uv pip install pyinstaller
          uv run pyinstaller --onedir --name prism --icon logo.ico `
            --copy-metadata fastmcp --copy-metadata click --copy-metadata httpx `
            --copy-metadata pydantic --copy-metadata pydantic-settings `
            --copy-metadata typer --copy-metadata websockets `
            --copy-metadata platformdirs --copy-metadata python-dotenv `
            --copy-metadata toons --collect-all lupa --collect-all docket `
            --collect-all shellingham --collect-submodules prism.mcp `
            --hidden-import importlib.metadata src/prism/cli/app.py
      - name: Compile the installer
        shell: pwsh
        run: |
          $version = (uv run python -c "import prism; print(prism.__version__)").Trim()
          $numeric = ($version -split '-')[0]
          $iscc = Get-ChildItem 'C:\Program Files*\Inno Setup*\ISCC.exe' | Select-Object -First 1
          & $iscc.FullName "/DAppVer=$numeric.0" "/DAppVerFile=$version" `
              "/DAppSource=dist\prism" prism.iss
          Set-Content -Literal dist\version.txt -Value $version
          @(Get-ChildItem dist\prism -Recurse -File).Count |
            Set-Content -Literal dist\file-count.txt
      # The upgrade baseline is the real published artefact, not a local rebuild,
      # so the matrix proves a genuine old -> new path. Best-effort: a repo with
      # no prior release, or a release with no setup asset, must skip not fail.
      - name: Fetch the published baseline
        shell: pwsh
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          $tag = (gh api 'repos/{owner}/{repo}/releases/latest' --jq '.tag_name')
          $asset = (gh api "repos/{owner}/{repo}/releases/tags/$tag/assets" --jq '.[0].name')
          if (-not $tag -or -not $asset) { Write-Host 'no published baseline; upgrade will skip'; exit 0 }
          gh release download $tag --clobber --pattern 'prism-*-setup.exe'
          if ($LASTEXITCODE -ne 0) { Write-Host 'baseline asset unavailable; upgrade will skip'; exit 0 }
          Get-ChildItem . -Filter '*-setup.exe' -File | Select-Object -First 1 |
            ForEach-Object { Copy-Item $_.FullName dist\prism-old-setup.exe -Force }
      - uses: actions/upload-artifact@v7
        with:
          name: installer-${{ matrix.os }}-${{ github.run_id }}
          path: |
            dist/prism-*-setup.exe
            dist/version.txt
            dist/file-count.txt
          retention-days: 30
        if: always()

  verify:
    name: verify (${{ matrix.os }})
    needs: [consistency, build]
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest]
    steps:
      - uses: actions/checkout@v7
      - uses: actions/download-artifact@v7
        with:
          name: installer-${{ matrix.os }}-${{ github.run_id }}
          path: dist
      # Pre-flight: a broken check must redden the job before the real suite runs.
      - name: Gate is live (negative self-test)
        shell: pwsh
        run: pwsh -NoProfile -File prism-installer/test-runner-report.ps1
      - name: Run the installer suite
        shell: pwsh
        run: pwsh -NoProfile -File prism-installer/run-installer-tests.ps1 -ArtifactsPath ./dist
      - name: Upload scenario logs
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: installer-logs-${{ matrix.os }}-${{ github.run_id }}
          path: prism-installer/tests/temp-*/
          retention-days: 30
```

- [ ] **Step 2: Lint the YAML locally** — `yamllint .github/workflows/installer-verification.yml` → 0 errors; and `actionlint .github/workflows/` if installed.

- [ ] **Step 3: Register the required status check** (never weaken `enforce_admins`):

```bash
gh api repos/AdriaERNI/Prism/branches/development/protection/required_status_checks \
  -X PUT -H "Accept: application/vnd.github+json" --input - \
  <<< '[{"context":"Installer Verification / verify (windows-latest)","integration_id":15368,"integration_type":"github_app"}]'
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/installer-verification.yml
git commit -m "ci(installer): gate the installer on a real Windows runner"
```

---

### Task 18: Vagrant parity + documentation

**Files:**
- Modify: `vagrant/run-tests.ps1` (or the documented invocation in `AGENTS.md`)
- Modify: `AGENTS.md` — **protected file, needs user approval to edit**

- [ ] **Step 1:** Point the Vagrant entry point at the committed suite (`-ArtifactsPath`) so the VM and CI execute the identical scenario set — the parity check "must run under the same harness the CI runs, no drift".

- [ ] **Step 2:** Document in `AGENTS.md`: the new `Installer Verification` gate, the exit-code contract table, and the "100 on upgrade is success, never 0" rule.

- [ ] **Step 3: Commit**

```bash
git add vagrant/run-tests.ps1 AGENTS.md
git commit -m "docs(ci): document the installer verification gate and exit-code contract"
```

---

## Two-push execution plan (red → green)

Per the user's chosen flow: the fixes stay local until the reproducer is proven in CI.

| Push | Contents | CI must show |
|---|---|---|
| **1 — reproducer** | Tasks 1-12 + 14-15 + 17 (harness, static gates, runtime scenarios, workflow). Tasks 3 & 16 **withheld**. | **RED**: `Consistency` ✗ (RG-001 ×3, RG-004 ×4), `verify` ✗ (`test-help-contract` exit-2 wave RG-003, `test-runner-report` RG-002, `test-upgrade-matrix` RG-005/008 if the baseline is wrong), `Build` ✓, `Test Windows` ✓ — i.e. real failures, not infrastructure noise |
| **2 — fix** | Tasks 3, 16 (fixture/doc repairs) + the `_common.ps1` tally fix | **GREEN**: 0 `[FAIL]`, `RESULT: PASS`, 17/17 subcommands, upgrade exits `0,100`, `##[SKIP]` only for the documented RG-006 rows |

Both pushes target a **new branch** (`ci/installer-verification`) opened against `development` — never `main`, never `release/*`, never `vagrant/*`.

---

## Verification

- [ ] `pwsh -NoProfile -File prism-installer/run-installer-tests.ps1 -Filter 'nonexistent-*'` → exit `1`, `RESULT: FAIL` (RG-007 cannot recur).
- [ ] `pwsh -NoProfile -File prism-installer/test-runner-report.ps1` → PASS (3 checks), and red when `deliberately-broken.ps1` is hidden (the gate is live).
- [ ] `pwsh -File prism-installer/static/analyze-install-consistency.ps1` → exit `1` before Task 16, `##[PASS]` after (RG-001).
- [ ] `pwsh -File prism-installer/static/analyze-docs-drift.ps1` → exit `1` before Task 16, `##[PASS]` after (RG-004).
- [ ] `pwsh -File prism-installer/test-help-contract.ps1` → exit `2`-wave before Task 16, 17/17 after (RG-003).
- [ ] Fresh install → exit `0`, `[PASS] installed`, `prism --version` correct, one PATH entry, one `Prism_is1` key.
- [ ] Upgrade over the published baseline → exit `0`/`100`, `##[PASS] no orphans`, exactly one registration (RG-005/RG-008).
- [ ] Uninstall → exit `0`, `Assert-PrismAbsent` clean (RG-009).
- [ ] Existing suite unmodified and still green: `PYTHONPATH="" uv run pytest tests/unit tests/mcp -q`, `uv run ruff check . && uv run ruff format --check .`, `uv run mkdocs build --strict`.
- [ ] Vagrant baseline re-confirm: 17 suites / 87 checks / **0 fail**.

## Assumptions

- `windows-latest` is the runner (GitHub-hosted, real Windows, admin, no display, **no Docker** → no live IRIS, hence every IRIS-backed check is `-SkipIris` / `##[SKIP]`).
- The upgrade baseline is the latest published release's `prism-*-setup.exe` (v0.2.2-beta7 currently ships one).
- `1`/`2`/`3`/`5`/`6`/`7`/`8`/`9` are documented-but-not-exercised by design on a headless runner.
