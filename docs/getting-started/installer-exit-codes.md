# Installer Exit Codes

This page describes the exit codes returned by the Windows installer
(`prism-<version>-setup.exe`) for every install scenario, and the values to
submit for each scenario in the Microsoft Store package step.

Prism's installer is built with [Inno Setup 6](https://jrsoftware.org/).
Inno's `Setup.exe` terminates with a process exit code that describes how the
installation ended. The Microsoft Store package submission requires you to map
each of its install scenarios to an **EXE return code value**, and its
validation rejects a submission in which two scenarios share the same value.
Every scenario below therefore carries a distinct value.

!!! info "Who consumes these codes"
    - **Microsoft Store** — the *Installer handling* step of the package
      submission consumes the values in the mapping table below.
    - **Deployment scripts** — silent installs (`/VERYSILENT`) are usually
      driven by an orchestrator that branches on the process exit code.
    - **Users** — an interactive install reports problems in the wizard UI
      instead of relying on the exit code.

## Exit codes

The complete range of exit codes used by the Prism installer:

| Exit code | Meaning | When the installer returns it |
|-----------|---------|------------------------------|
| `0` | Installation successful | Setup ran to completion, or `/HELP` / `/?` was used. |
| `1` | Installation already in progress | Setup failed to initialize. **Not reachable in the shipping installer**: the single-instance guard is the `SetupMutex` directive, and `prism.iss` wires no `SetupMutex`, so a second instance runs freely. Kept as a reserved value for a future single-instance guard. |
| `2` | Installation cancelled by user | The user clicked **Cancel** in the wizard before the actual installation started, or chose **No** on the opening message box. |
| `3` | Miscellaneous install failure | A fatal error occurred while preparing to move to the next installation phase. Reported as a miscellaneous failure; the conditions are rare (out of memory or Windows resources). |
| `4` | Miscellaneous install failure | A fatal error occurred during the actual installation process. Errors behind an Abort/Retry/Ignore box are not fatal: choosing **Abort** there yields `5`. |
| `5` | Installation cancelled by user | The user clicked **Cancel** during the actual installation process, or chose **Abort** at an Abort/Retry/Ignore box. |
| `6` | Miscellaneous install failure | The `Setup.exe` process was terminated by the debugger. Not reachable in production. |
| `7` | Disk space is full | The *Preparing to Install* stage determined that the installation cannot continue because the target volume has insufficient free space. |
| `8` | Reboot required | The *Preparing to Install* stage determined that the installation cannot continue and that a system restart is required to correct the problem. |
| `100` | Application already exists | An earlier installation of Prism is already registered on the device. Reported via the custom exit code mechanism below. |
| `101` | Network failure | Reserved. The installer fetches no remote payload, so no condition raises this code today; it is kept so the Store scenario has a value of its own. |
| `102` | Package rejected during installation | Reserved. Set it from a device-side security-policy check when one is added; kept so the Store scenario has a value of its own. |

!!! note "Before returning `1`, `3`, `4`, `7` or `8`, an error message
    explaining the problem is normally displayed — see Inno Setup's
    [Setup exit codes](https://jrsoftware.org/ishelp/topic_setupexitcodes.htm).
    Any exit code other than `0` means the installation was not run to
    completion. Future versions of Inno Setup may add exit codes, so callers
    must handle unexpected values as a failure rather than matching only the
    list above."

## Microsoft Store package submission

Enter these values in the *Installer handling* step of Partner Center. The
documentation URL required for the miscellaneous return codes is Inno Setup's
exit-code reference: `https://jrsoftware.org/ishelp/topic_setupexitcodes.htm`

| Store scenario | EXE return code | Origin of the value |
|----------------|-----------------|---------------------|
| Installation cancelled by user | `2` | Inno Setup |
| Application already exists | `100` | Prism installer (custom) |
| Installation already in progress | `1` | Inno Setup |
| Disk space is full | `7` | Inno Setup |
| Reboot required | `8` | Inno Setup |
| Network failure | `101` | Prism installer (custom, reserved) |
| Package rejected during installation | `102` | Prism installer (custom, reserved) |
| Installation successful | `0` | Inno Setup |
| Miscellaneous install failure | `4` | Inno Setup |

!!! warning "Duplicate values are rejected"
    Each scenario must carry its own value. `0`/`1`/`2`/`4`/`7`/`8` are
    already occupied by Inno Setup, so the three scenarios Inno has no
    dedicated code for — *application already exists*, *network failure* and
    *package rejected during installation* — use the custom codes `100`,
    `101` and `102`. Do not reuse an Inno code for a different scenario.

## Reporting a custom exit code

Exit codes above the documented Inno range are reported by the installer
script in `prism.iss`, so a caller can distinguish a scenario Inno itself
does not encode. The `[Code]` section keeps the snapshot that decides the
`100` case *before* the installation writes to the filesystem and to the
registry, because `CreateUninstallRegKey` registers the application under

```text
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Prism_is1
```

during the installation itself.

```pascal
[Code]
var
  CustomErrorCode: Integer;        { 0 -> success; 101/102 reserved }
  WasPreviouslyInstalled: Boolean; { snapshot taken in InitializeSetup }

function DetectApplicationExists(): Boolean;
var
  S: String;
begin
  Result := RegQueryStringValue(
    HKLM,
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Prism_is1',
    'DisplayName', S);
end;

function InitializeSetup(): Boolean;
begin
  { Take the snapshot BEFORE the installation registers the application. }
  WasPreviouslyInstalled := DetectApplicationExists();
  Result := True;
end;

function GetCustomSetupExitCode: Integer;
begin
  Result := CustomErrorCode;  { 0 -> Installation successful }
  if WasPreviouslyInstalled then
    Result := 100;            { Application already exists on the device }
end;
```

Notes on the implementation:

- `GetCustomSetupExitCode` is called by Setup only when the exit code would
  otherwise be `0`, so returning a non-zero value from it is the supported
  way to report a custom code on an otherwise successful run.
- A process exit code on Windows is an unsigned 32-bit value: never set a
  negative code.
- The Inno `[Code]` section is a single-pass Pascal script without forward
  references — every helper (`DetectApplicationExists`) must be defined
  before its first use, and comments inside the section use `{ }` rather
  than the `;` line-comment token, which is only valid outside `[Code]`.
- The uninstaller reports its own success with exit code `0` and any
  non-zero value as a failure; do not match a specific non-zero value.

## Checking exit codes

Example session — a silent install followed by a check of the exit code:

=== "PowerShell"

    ```powershell
    $p = Start-Process -FilePath .\prism-0.2.1-beta2-setup.exe `
        -ArgumentList @('/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES',
                        '/LOG=C:\prism-tests\install.log') `
        -Wait -PassThru
    "exit code = $($p.ExitCode)"
    ```

=== "cmd"

    ```bat
    prism-0.2.1-beta2-setup.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES
    echo exit code = %ERRORLEVEL%
    ```

The `/LOG=<file>` option writes an installation log that is useful when an
exit code other than `0` has to be diagnosed; see
[Installation](installation.md) for the installer's other options.

## Validated matrix

The matrix was exercised on the packaged installer in the Windows Server
2022 Vagrant VM (`prismdefault`), building `prism-0.2.1-beta2-setup.exe`
with Inno Setup 6 / `ISCC.exe` and running it with `/VERYSILENT
/SUPPRESSMSGBOXES /NORESTART`.

| Scenario | Command run | Expected | Observed |
|----------|-------------|----------|----------|
| Uninstaller, no arguments | `unins000.exe /VERYSILENT` | `0` | `0` |
| Fresh install (no earlier registration) | `prism-…-setup.exe /VERYSILENT` | `0` | `0` |
| Install over an existing installation | `prism-…-setup.exe /VERYSILENT` | `100` | `100` |
| Installation in progress (second instance) | second `Setup.exe` while one runs | `1` | unreachable — no `SetupMutex` in `prism.iss` |
| Disk space is full | install onto a filled volume | `7` | not exercised on the VM (probe-staged `PrepareToInstall` stop observed as `7` in the repro harness) |
| Reboot required | install requiring a restart | `8` | not exercised on the VM (probe-staged `PrepareToInstall` + `NeedsRestart` stop observed as `8` in the repro harness) |
| Cancel before installation | wizard, press Cancel | `2` | not exercised (needs interactive UI) |

The `0` and `100` rows are confirmed by the VM run above; `7` and `8` are
confirmed by probe `.iss` files derived from the shipping installer (the
`PrepareToInstall` stop lane) in the repro harness. The `1` row is unreachable
by construction — `prism.iss` wires no `SetupMutex`. The `2` row needs an
interactive wizard the automated lane cannot stage, so its value is taken from
Inno's documented exit-code range.

!!! tip "Related pages"
    [Installation](installation.md) — how to install and verify the packaged
    installer · [Releases](../releases.md) — how the installer is built and
    published by CI.
