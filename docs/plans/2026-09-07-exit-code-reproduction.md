# Installer Exit-Code Reproduction Plan (Microsoft Store package step)

Date: 2026-09-07 · Branch: `feat/store-exit-codes` · Owner: Hermes Agent (paired)
Status: **IN PROGRESS — measured columns are filled only by real VM runs**

## Goal

The Microsoft Store "EXE return codes" package step rejects a submission whose
scenario→code mapping contains duplicates, and the certification tests submit the
installer under conditions that are supposed to produce each declared code. For that
to mean anything, every code `prism.iss` publishes must be **reachable**, and
reachable-by-construction is not the same claim as reachable-by-accident. This plan
separates those two claims and refuses to let one substitute for the other.

## Authoritative sources (read, not remembered)

* `prism.iss` lines 90–205 — the shipped mapping and the `[Code]` implementation.
* Inno Setup 6 *Setup Exit Codes* (`jrsoftware.org/ishelp/topic_setupexitcodes.htm`),
  fetched 2026-09-07 — the table below is copied from that page, which is what the
  `.iss` comment block itself cites as its reference.
* The VM: Inno Setup 6 is present at
  `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` (verified `ISCC_SEEN`).

Inno's own table, verbatim in meaning:

| Code | Inno's documented trigger |
|---|---|
| 0 | ran to completion (or `/HELP`, `/?`) |
| 1 | **failed to initialize** |
| 2 | user clicked Cancel **before** the actual installation started, or chose "No" on the opening "This will install…" box |
| 3 | fatal error preparing to move to the next phase (out of memory / resources) |
| 4 | fatal error **during** the actual installation |
| 5 | user clicked Cancel **during** the installation, or chose *Abort* at an Abort-Retry-Ignore box |
| 6 | setup **forcefully terminated by the debugger** |
| 7 | the *Preparing to Install* stage determined setup cannot proceed |
| 8 | same as 7 **and** the system needs a restart |

Two consequences the current mapping does not state: codes **3, 5, 6 exist and are
not in our map**, and **5 ≠ 2** (cancel during vs cancel before). A Store mapping
that omits them is not wrong per se, but the test suite must say so on purpose
rather than discover it by luck.

## What the shipped installer can actually emit (static evidence)

`CustomErrorCode` is **declared and read but never assigned**:

```pascal
var CustomErrorCode: Integer;        { line 129 }
...
function GetCustomSetupExitCode: Integer;   { line 200 }
begin
  Result := CustomErrorCode;   { always 0 -- no writer exists }
  if WasPreviouslyInstalled then
    Result := 100;
end;
```

So, as shipped, the installer is capable of exactly **0** and **100**. Codes 101
and 102 are declared "reserved — set by your own failure checks if used" and no such
check exists. That is a *static* finding; the VM run is asked to corroborate it
dynamically, because a code can also be produced by Inno itself through a path I
have not enumerated.

Also found while reading: `NeedRestart()` returns **`False`** while its comment
claims "Request restart so PATH changes propagate" (lines 152–156). Either the
comment or the code is wrong; a `False` there also forecloses the natural 8 path.
Deferred to the RG-011/gate batch per instruction (do not commit those).

## Claim taxonomy — the discipline this plan is built on

For every code, exactly one of these must be reported, and they are not
interchangeable:

| Verdict | Meaning | Evidence required |
|---|---|---|
| `reproduced` | the real condition occurred and the installer returned the declared code | the condition is staged, the observed code is printed by the harness |
| `plumbing-only` | the reporter path transmits the code, but the real condition was not staged | a build-time fault-injection, clearly labelled, **never** counted as behavioural coverage |
| `blocked` | the trigger could not be staged in this environment | the staging step's own failure is printed |
| `unreachable` | no condition in the program can produce it | static (no writer / no code path) **and** a negative dynamic attempt |

`blocked` and `unreachable` are honest outcomes. A green with no mechanism behind
it is not: `##[PASS]` with nothing executed is forbidden, so each row must carry
its observed code or its failure text.

## Repro matrix — design, to be filled by measurement

`trigger kind` `headless` = can be staged without a human or an interactive window
station. `ci` = can be staged on a hosted `windows-latest` runner (no self-hosted
runners exist in this repo — verified earlier via `gh api`).

| Code | Declared scenario | Staged condition (probe) | Headless | CI | Expected | Observed |
|---|---|---|---|---|---|---|
| 0 | Installation successful | clean machine, single `/VERYSILENT` install | yes | yes | 0 | _pending_ |
| 1 | Installation already in progress | two concurrent setups, same `AppId` mutex | yes | yes | 1 | _pending_ |
| 2 | Cancelled by user | non-silent + `UsePreviousPrivileges` "This will install…" box answered No | **no** (UI) | **no** | 2 | _pending_ |
| 3 | *(not in our map)* | out-of-memory at phase transition | no | no | — | _pending_ |
| 4 | Miscellaneous install failure | target path occupied by a **file** where a directory must be created | yes | yes | 4 | _pending_ |
| 5 | *(not in our map)* | Cancel during install | no (UI) | no | — | _pending_ |
| 6 | *(not in our map)* | debugger terminate | no | no | — | _pending_ |
| 7 | Disk space is full | `Abort()` in `InitializePrepare`; separately a size-limited VHD | yes | yes | 7 | _pending_ |
| 8 | Reboot required | `Abort()` in `InitializePrepare` + restart-pending | yes | yes | 8 | _pending_ |
| 100 | Application already exists | reinstall over a registered copy | yes | yes | 100 | _pending_ |
| 101 | Network failure | **no code path exists**; plumbing-injection only | n/a | n/a | 101 | _pending_ |
| 102 | Package rejected | **no code path exists**; plumbing-injection only | n/a | n/a | 102 | _pending_ |

Notes on the choices, because several are load-bearing:

* **Why a probe `.iss` instead of only Prism's own.** Mapping an Inno trigger to a
  code is Inno's behaviour, not Prism's. A tiny standalone `.iss` isolates that
  question, compiles in seconds (no PyInstaller), and keeps a probe bug from being
  mistaken for a product bug. Prism's real installer is then used for the codes that
  are genuinely Prism's own (`0`, `100`, and the injected `101/102`).
* **Why a file-occupied target for 4.** A deleted-mid-install source is a race, and
  a race that passes once is not a regression test. Creating the colliding file
  from inside `InitializePrepare` is deterministic: the collision exists before the
  copy phase begins, so it cannot intermittently not happen.
* **Why `Abort()` for 7/8 rather than filling a disk.** Filling `C:` on the guest
  risks a broken VM and is slow; a size-limited VHD is the honest disk-full test and
  is scheduled as the confirmation step *after* the `Abort()` measurement, because
  `Abort()` in the prepare stage is the documented developer route for "cannot
  proceed" and its resulting code is currently **unverified** — the whole point of
  the run is to measure it, not to assume it.
* **Why 2 and 5 are expected-blocked here.** Both are defined by Inno as *user
  input*. Under `/VERYSILENT` the wizard does not exist, so the cancel cannot occur.
  The VM does have an interactive session (auto-logon, `explorer.exe` per the
  windows-build-validation notes), so UI-driving is possible in principle; it is
  attempted, and if it does not land it is recorded `blocked` with the reason, not
  quietly dropped.
* **Why 101/102 get plumbing-only treatment at best.** `GetCustomSetupExitCode` is
  consulted **only when the code would otherwise be 0**. So injecting a value there
  proves our reporter carries 101/102; it proves nothing about Inno's own 1–8, and
  must never be presented as behavioural coverage of those.

## Fault injection (design)

`prism.iss` gains an `#ifdef TestFire` region, so a **production build is unchanged
byte-for-byte** and no test code ships:

```pascal
{#ifdef TestFire}
function TestFireCode: Integer;   { /DTestFireCode=<n> }
{#endif}
```

consulted inside `GetCustomSetupExitCode` only when the define is present. Rationale
for `#ifdef` over a separate test `.iss`: the point of the exercise is to exercise
**this** file's reporter, so the injection has to live in it, gated out of shipping
builds — the same reason Start Bits keeps `#ifdef` regions for environment-conditional
behaviour rather than forking a second installer.

## Verification gates

1. **The gate must be able to go red.** A deliberately-broken fixture asserts the
   matrix fails when a row is deleted, when an observed code is falsified, and when
   a duplicate code is introduced — the last is the exact defect the Store itself
   rejects, so it is the most important of the three.
2. **Derived, not hand-typed.** The set of checked codes is parsed out of
   `prism.iss`'s mapping block. A hand-maintained list can drift out of sync with
   the installer, and a code added to the `.iss` without a test would then pass.
   Parsing makes that an instant failure, which is the entire value of the exercise.
3. **No fabricated evidence.** A row whose staging step failed prints the staging
   failure and reports `blocked`; the suite never converts "I could not stage it"
   into "it works".
4. **Idempotence.** Each scenario resets state (uninstall, remove the `Prism_is1`
   key and the target dir) before and after; a scenario that leaves state behind
   makes the *next* row's verdict meaningless, which is how a false green gets born.

## Pipeline shape (`.github/workflows/installer-verification.yml`)

`build` (PyInstaller onefile + ISCC, `/DAppVer` **and** `/DAppVerNumeric`) →
`repro` on `windows-latest` running the same harness, so CI asserts the *identical*
observed codes the VM produced. CI and VM agreeing is the acceptance signal; a
`blocked` row is allowed to stay `blocked` in CI, and must be listed as such in the
job summary rather than omitted — an omitted row is indistinguishable from a passing
one at a glance, which is the class of bug that hid the original `Failed: 0` run.

## Open decisions (user input required)

* **101 "Network failure".** Prism's installer has no network phase: the payload is
  local and there is no download step, so there is no condition for the code to
  report. Keep it reserved-but-documented (my recommendation, and the `.iss` already
  words it that way), or wire it to a real condition — which would first require a
  network phase that does not exist.
* **Codes 3, 5, 6.** Omitted from the Store map. Should the docs record them as
  intentionally-unmapped, or be silent? I'd document them, since silence reads as
  oversight and the reader cannot tell the two apart.
* **`NeedRestart()` returning `False`** while the comment asks for a restart: fix
  the comment or the behaviour? Changing behaviour would alter when 8 can appear.

## Method log

* 2026-09-07 read `prism.iss` `[Code]` in full; grepped every assignment to
  `CustomErrorCode` / `WasPreviouslyInstalled` → no writer for the former.
* 2026-09-07 fetched Inno's Setup Exit Codes page; recorded 3/5/6 omissions and the
  2-vs-5 distinction above.
* 2026-09-07 confirmed `ISCC.exe` present on the guest before writing any trigger
  that presumes a toolchain — a trigger designed around an absent tool is worthless.
* _VM measurement log appended below by `vagrant/repro-exit-codes.ps1`._
