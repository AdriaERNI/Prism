# Prism project status — verified review (2026-09-08)

Ground truth gathered this session from git, the live VM, CI API, and the source
files. Every claim below is cross-checked against tool output, not recalled from
history.

## What is DONE and committed (shipped)

Branch `feat/store-exit-codes` is checked out and **pushed** (`remotes/origin/feat/store-exit-codes`
exists). The exit-code work is committed in two commits:

| Commit | Change |
|--------|--------|
| `3ec66db` | `feat(installer): wire Microsoft Store EXE return codes` — `prism.iss` gains the Store EXE-return-code mapping in `[Code]` |
| `a9062ca` | `docs(installer): add Installer Exit Codes page` — `docs/getting-started/installer-exit-codes.md` |

Authoritative wiring (verified against the committed `prism.iss` at `3ec66db`
and the working tree alike):

- `CustomErrorCode: Integer` **declared** (line 129) — comment: `0 -> success; 101/102 reserved for hooks`
- `CustomErrorCode` **read** (line 202) — `Result := CustomErrorCode`
- `CustomErrorCode` has **zero assignment sites** (grep count `0`) in both committed and working versions
- `NeedRestart()` returns hard `False` (line 152/155) despite its own comment claiming it requests a restart
- `GetCustomSetupExitCode()` returns `100` when `WasPreviouslyInstalled` (line 204), else `CustomErrorCode`

Consequence, by construction: the shipping installer can emit only **0** and **100**.
Codes 101/102 are documented in the table but are **unreachable** — no code line
can ever set `CustomErrorCode` to them examine.

Also committed on this branch (prior session work): pyproject/beta3 bump history,
`shell.py` timeout 120→3600, index tool removal, stdio/terminal refactor, Windows
stability fixes. `tests/unit/test_pyinstaller_compat.py` exists in the tree.

## What is PENDING and uncommitted / unpushed (working-tree dirty state)

The following are untracked or modified and NOT committed — this is the unshipped
half, exactly matching the "no commits/pushes for local fixes" constraint:

- **Working tree**: `git status` shows 30 untracked files + 5 tracked-modified + 1 deleted.
- **Modified (tracked)**:
  - `pyproject.toml` — version `0.2.1-beta2` → `0.2.1-beta4`
  - `src/prism/__init__.py` — `__version__` `0.2.1-beta2` → `0.2.1-beta3`
  - `src/prism/mcp/shell.py` — shell timeout max `120` → `3600`
  - `vagrant/scripts/tests/01-help.ps1` — command-list regression guard
  - `vagrant/scripts/tests/06-ws.ps1` — `$ZVersion` + syntax-error cases
  - `vagrant/scripts/tests/13-test.ps1` — `-m` runner assert corrected
  - `vagrant/scripts/tests/05-terminal.ps1` — **deleted** (terminal command removed)
- **Untracked (30)** — the exit-code reproduction work-in-progress:
  - `prism-installer/` — the CI suite: `run-installer-tests.ps1`, `test-exit-code-contract.ps1`, upgrade/matrix/downgrade/prerelease/future/help/install/uninstall tests, `_invoke-child.ps1`, `shared/installer-common.ps1`, `static/*` analyzers, `tests/`
  - `.github/workflows/installer-verification.yml` — the PR/branch gate workflow (ubuntu consistency job + Windows build+suite job)
  - `docs/plans/2026-09-07-exit-code-reproduction.md` (exit-code plan) + `2026-09-07-installer-ci-verification.md`
  - `vagrant/repro-core.ps1` — the repro harness
  - `vagrant/drive-repro.py` — driver
  - `vagrant/diag-launch.ps1` — launch-route diagnostic
  - `vagrant/repro-exit-codes.ps1`, `vagrant/smoke-helpers.ps1`
  - ~14 `probe-*.ps1` / `probe-*census*.py` scripts + `repair-suite.py`, `pack-suite.py`, `fix-guest-found.py`, `strip-decorative-attrs.py`, `gate-parse.ps1`, `implement-runner-fixes.py`, `drive-guest.py`, `extract-suite.ps1`, `census-guest.py`

## VM state

`vagrant status` in `vagrant/`: `default (libvirt)` — **running**, box
`jborean93/WindowsServer2022`, hostname `prism-win`. Guest PowerShell is **5.1**
(`powershell.exe`), Inno 6 installed at `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`.

## CI state (the honest part)

`gh api .../commits/feat/store-exit-codes/status` on branch tip `a9062ca` returns
`{"state":"pending","statuses":[],"total_count":0}` — **no check runs attached to
the branch tip**. The committed `test-linux.yml` / `test-windows.yml` workflows run
only on `development` (per AGENTS.md: "All workflows target `development`, promoted
to `main`"), and `installer-verification.yml` is untracked — so nothing has actually
exercised the exit-code suite in CI yet. Hosted runners are the GitHub-hosted ones;
self-hosted count is 0 out of necessity.

## The reproduction goal — NOT achieved yet (honest)

The running VM and the harness are in place, but **no exit code has been genuinely
measured from the guest yet**. The base probe `.iss` compiles to ISCC `exit=1` with
an empty log, and the harness cannot yet explain it. This session pinned the causes
to three stacked harness defects (all harness plumbing, none in the shipping
installer):

1. `$( ... )` capture — compile diagnostics were computed inside a subexpression,
   then **discarded** (that's why BASE_COMPILE_FAIL was empty for rounds).
2. Empty `$baseExe` in the compile-fail branch → `Test-Path -LiteralPath ''` throws
   on PS 5.1 (empty literal-path), silenced by `-ErrorAction SilentlyContinue`; the
   throw was the missing row for code 0.
3. The capture route — `Invoke-Capture` uses the harness's own launcher; the diag
   proved routes 1 (`-PassThru`+manual `WaitForExit`) and 2 (cmd.exe shim) return real
   codes, while `-Wait -RedirectStandardOutput` returns NOCODE and the 1-arg .NET
   `Process` overload THREW. But the log capture still returns empty at the source,
   so ISCC's rejection reason is unobserved.

Measured launch-route table (diag-launch.ps1 on the guest):

| route | result |
|---|---|
| 1 `‑PassThru` + manual `WaitForExit` | **OK → 42**, real exit code |
| 2 cmd.exe shim + `>file 2>&1` | **OK → 42**, log written |
| 3 `‑Wait ‑RedirectStandardOutput` | NOCODE (dead route) |
| 4 `New‑Object Diagnostics.Process $psi` | THREW (no 1‑arg overload) |

Patching the empty-LiteralPath throw moved past line 216 but the guard at 224 can
still trip on an empty `$baseExe`; the fix that actually sticks is to never call
`Test-Path` with an empty string (guard `$baseExe.Length -gt 0`).

### The code universe, on purpose

Reachable on the shipped installer: **0, 100** (run-to-completion / re-install over
existing) plus **1, 4, 7, 8** if the probe harness can be made to stage them.
Not reachable by any script today and so are NOT claimable as "reproduced":

| code | why unreachable |
|---|---|
| 2 | defined as human cancels *before* install — needs a human on the dialog |
| 3 | out of memory/resources — extreme machine exhaustion, unsafe to stage |
| 5 | defined as human cancels *during* install — needs a human/debugger |
| 6 | defined as debugger killed the process — needs a debugger |
| 101 | no network phase in this installer; `CustomErrorCode` has no writer → unreachable by construction |
| 102 | same — no writer, unreachable by construction |

## MEASURED (2026-09-12) — full matrix reproduced on the VM

All 12 codes are accounted for with honest verdicts; every reachable code shows a
real integer from the guest, and every unreachable one carries the proof.

| code | verdict | observed | evidence |
|------|---------|----------|----------|
| 0 | observed | `0` | fresh silent install (`/VERYSILENT /NORESTART /SUPPRESSMSGBOXES`) of the real setup exe ran to completion |
| 1 | unreachable-static | — | `prism.iss` has **no `SetupMutex` directive** (the only Inno single-instance mechanism) and `InitializeSetup` always returns True; the second instance runs freely — measured 0/100, never 1. The mapping block's "second instance blocked by the single-instance mutex" claim is **falsified** |
| 2 | blocked | — | cancel-before-start is user input by Inno's definition; no wizard exists under `/VERYSILENT` — needs the interactive UI lane |
| 3 | not-in-store-map | — | Inno-defined (out of memory/resources); no Prism mapping — docs decision pending |
| 4 | observed | `4` | probe `.iss` derived from `prism.iss` with `DefaultDirName` → `{autopf}\Probe4Collision` and a regular FILE staged where the dir must be created → fatal mid-install |
| 5 | not-in-store-map | — | Inno-defined (cancel during install); no Prism mapping — docs decision pending |
| 6 | not-in-store-map | — | Inno-defined (debugger terminate); no Prism mapping — docs decision pending |
| 7 | observed | `7` | probe `.iss` with `PrepareToInstall` returning a non-empty string → Preparing-to-Install stage stops; dedicated exit code 7 |
| 8 | observed | `8` | probe `.iss` with `PrepareToInstall` setting `NeedsRestart := True` alongside the non-empty string → stage stops + restart; measured with `/NORESTART` |
| 100 | observed | `100` | re-install over the registered copy — `WasPreviouslyInstalled` → `GetCustomSetupExitCode` returns 100 |
| 101 | unreachable-static | — | `CustomErrorCode` has **zero assignment sites** in `prism.iss` (declared, read, never written) — unreachable by construction |
| 102 | unreachable-static | — | same — no writer, unreachable by construction |

The full chain is proven end-to-end on the VM:
- real `prism.iss` + real assets (`logo.ico`, wizard BMPs) compile → ISCC exit 0, 77-line log, setup exe produced
- probes are DERIVED from the shipping `prism.iss` (copied + one minimal real-directive/event change + `/DAppSource=payload`), never hand-authored — the hand-authored base failed with `Required parameter "DestDir" not specified`
- capture route proven: cmd shim (`cd /d` into the probe dir + `>log 2>&1`, both streams), route 1 exit code (`-PassThru` + manual `WaitForExit`)
- `/SUPPRESSMSGBOXES` (plural) is required: a probe install that fails shows an error box that hangs headlessly — measured as a 900s TIMEOUT before the switch was added
- the shipping file uses LF line endings; probe `$Change` pairs must use `` `n `` or the literal match fails silently

## CI pipeline (built, after the measured codes)

- code-set gate `prism-installer/static/analyze-exit-code-set.ps1` derives the claimed
  set from `prism.iss` (verified: `[0,1,2,4,7,8,100,101,102]`, no duplicates) and goes
  red on a deleted row, a falsified code, or a duplicate value — wired into the
  `consistency` job of `.github/workflows/installer-verification.yml`
- Actions `windows-latest` verify job runs `prism-installer/run-installer-tests.ps1`,
  which asserts the exercised installer codes (0, 100) and declares 1/2/4/7/8/101/102
  not-exercised with reasons (hosted runners cannot stage UI/reboot/resource codes,
  and the shipping installer wires no SetupMutex and no CustomErrorCode writer)
- commit/push scope — probe/repair scripts stay out of the repo

## Next steps (in dependency order)

1. ✅ Measurement complete — all 12 codes accounted for (observed / blocked /
   not-in-store-map / unreachable-static).
2. ✅ CI pipeline built — gate + suite + workflow wired.
3. Commit/push scope — keep the ~14 probe/repair scripts out of the repo; ship the
   gate + suite + workflow when you say go.

Nothing in the pipeline changes the shipping installer; all is harness/CI plumbing.
No commits or pushes have been made for any of it, per the constraint.
