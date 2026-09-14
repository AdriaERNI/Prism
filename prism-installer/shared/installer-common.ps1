# prism-installer/shared/installer-common.ps1
# Dot-sourced by every test-*.ps1; never executed directly.
#
# Deliberate notes (each was confirmed against Windows PowerShell 5.1 on the
# pinned guest -- do not "modernise" these away, they look like slips):
#   * Set-StrictMode takes only -Version/-ErrorAction/-PassThru. There is NO
#     -OnNotLike parameter and -Version takes a System.Version, not a wildcard.
#   * No Set-Variable -Option: -Option binds the ScopedItemOption ENUM and a
#     hashtable there is a bind error, so config is plain script-scope variables.
#   * Exit-code contracts are ARRAY-valued and live at script scope. Do NOT
#     round-trip them through an environment variable: an env var is a string,
#     so @(0, 100) comes back as the single token '0 100' and every -contains
#     test silently misbehaves.
#   * No [CmdletBinding(SupportsShouldProcess = ...)] on the assert helpers: the
#     flag is a no-op there and would advertise a -WhatIf that does nothing.
Set-StrictMode -Version Latest -ErrorAction Ignore

# Exit codes that count as a successful install. 100 is returned by design on
# every re-install/upgrade over a registered copy (prism.iss GetCustomSetupExit
# Code), so 100 is never the expected code for a fresh install.
$script:PRISM_OK = @(0, 100)
$script:PRISM_UPGRADE_OK = @(0, 100)
$script:InstallRoot = 'C:\Program Files\Prism'
$script:UninstallKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Prism_is1'
$script:EnvKeyPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'

# Exit codes arrive as Int32 on the wire but a raw handle can surface a string
# or a negative value. Normalise to [int] before ANY comparison; never compare a
# raw handle and never call .ExitCode on a job object.
function Get-NormalizedExitCode {
    # NOT Mandatory, deliberately: an unreadable child exit code arrives as $null, and
    # that is the one input whose handling decides whether a broken run reads as
    # success. Under Mandatory=$true the binding threw before the null branch could
    # run, so the fail-safe sentinel was unreachable (measured on the guest). This is
    # a PARSER, not a mapper: an installer 100 STAYS 100 because the contract array
    # $PRISM_OK = @(0,100) is what blesses it via Assert-ExitCode -notin, and a
    # child's 1/2 stay non-zero. Only an unreadable value becomes negative, so
    # 'cannot confirm success' can never be mistaken for success.
    param($Result)
    if ($null -eq $Result) { return -1 }
    $asInt = 0
    if (-not [int]::TryParse([string]$Result, [ref]$asInt)) { return -1 }
    return $asInt
}

function Assert-ExitCode {
    # $Expected is the contract: $env:PRISM_OK for a fresh install,
    # $PRISM_UPGRADE_OK for an upgrade (0 or 100).
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
        throw ($lines -join [Environment]::Newline)
    }
    Write-SuiteLine "  [PASS] exit $code in {$($Expected -join ', ')} - $Because"
    return $code
}

function Get-PrismRegistryPath {
    # The single ARP registration Inno writes for AppId 'Prism' -> Prism_is1.
    return (Get-ItemProperty -Path $script:UninstallKey -ErrorAction SilentlyContinue)
}

function Get-PrismVersion {
    # Resolves prism the way a fresh shell would, via the machine PATH the
    # installer writes, so this doubles as the PATH-integration check.
    # Returns the resolved COMMAND PATH (or $null when nothing resolves). Do
    # not return --version's text here: the shipped binary prints 'Prism
    # 0.2.1-beta3' (measured 2026-09-07), and returning it from a function
    # named 'version' invites the 'is it on PATH?' null-test to reject a
    # correct install whose banner differs from the bare number -- and it
    # would pollute the parent scope with an unexpected value. The version
    # comparison lives in Assert-PrismInstalled, which compares deliberately.
    $env:PATH = [Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('PATH', 'User')
    $cmd = Get-Command -Name 'prism.exe' -CommandType Application -ErrorAction SilentlyContinue |
          Select-Object -First 1
    if ($null -eq $cmd) { return $null }
    return $cmd.Source
}

function Get-PrismVersionOutput {
    # --version output of the resolved binary, for the assertions that compare
    # text deliberately (Assert-PrismInstalled). Kept apart from Get-PrismVersion
    # so no caller confuses 'resolved on PATH' with 'reported this version'.
    $path = Get-PrismVersion
    if ([string]::IsNullOrWhiteSpace($path)) { return $null }
    return ((& $path --version 2>&1) | Out-String).Trim()
}

function Get-InstalledVersion {
    # (Get-Item).Version is the FILE version, not the product version, so read
    # the version resource instead of inferring it.
    $exe = Join-Path $script:InstallRoot 'prism.exe'
    if (-not (Test-Path -LiteralPath $exe)) { return $null }
    return (Get-Item -LiteralPath $exe).VersionInfo
}

function Get-PrismFileVersion {
    # The version a PE file reports about itself, four dotted fields, read from
    # the version resource. Returns $null when the binary carries no version
    # info (the RG-011 shipped-installer case), so callers must test for $null
    # before dereferencing -- .VersionInfo is nullable.
    param(
        [Parameter(Mandatory = $true, Position = 0)]

        [string] $LiteralPath
    )
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) { throw "not a file: $LiteralPath" }
    $info = (Get-Item -LiteralPath $LiteralPath).VersionInfo
    if ($null -eq $info) { return $null }
    if ([string]::IsNullOrWhiteSpace($info.FileVersion) -or $info.FileVersion -like '*,*') { return $null }
    # Measured on the guest: ISCC pads the field, so '0.2.1.0  ' would fail TryParse
    # and read as 'no version info' -- trim first so a real version cannot masquerade
    # as the RG-011 null case.
    $v = $null
    if (-not [version]::TryParse($info.FileVersion.Trim(), [ref] $v)) { return $null }
    return $v
}

# The suite root is the DIRECTORY CONTAINING shared/: $PSScriptRoot inside this
# library is shared/ itself, NOT prism-installer/. A function that joined
# $PSScriptRoot 'tests' here made children write their sentinel logs under
# shared/tests/ while the runner read prism-installer/tests/, so the runner saw
# an empty log, classified every test as a clean pass and reported a GREEN suite
# that had tested nothing -- the exact RG-007 false-green class this suite exists
# to kill. Derive it once, here, and let the runner use the same value.
$script:SuiteRoot = Split-Path -Path $PSScriptRoot -Parent

function New-TempDir {
    # Every run gets its own temp dir under the suite root, never the system
    # temp, so a crashed scenario cannot leak into a sibling run or collide on a
    # shared path. Only this scenario's own directory is removed -- the parent
    # dir is shared with in-flight siblings, so wiping it would delete another
    # test's log mid-run.
    param([string] $Name = 'run')
    $dir = Join-Path (Join-Path $script:SuiteRoot 'tests') ('temp-{0}' -f $Name)
    if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    return $dir
}

function Invoke-PrismSilent {
    # The ONLY sanctioned way to run an installer in CI.
    # /VERYSILENT implies /NoRestart (never a 3010) and /Quiet.
    # /SUPPRESSMSGBOXES is plural and mandatory: the singular form is not a real
    # Inno switch, so dialogs stay unsuppressed and hang a headless runner.
    param(
        [Parameter(Mandatory = $true)] [string] $Installer,
        [string] $LogFilePath,
        [string] $ExtraArgs = ''
    )
    if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) { throw "installer not found: $Installer" }
    $argList = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -join ' '
    if ($LogFilePath) {
        $logDir = Split-Path -Path $LogFilePath -Parent
        if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        $argList = $argList + ' /LOG="' + $LogFilePath + '"'
    }
    if ($ExtraArgs) { $argList = $argList + ' ' + $ExtraArgs }
    # -Wait is required: without it the returned handle is already exited and the
    # exit code is meaningless. -Argument is a single string; passing an array
    # here trips PowerShell's positional binding.
    $proc = Start-Process -FilePath $Installer -Argument $argList `
        -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop
    return (Get-NormalizedExitCode $proc.ExitCode)
}

function Remove-PrismInstall {
    # Pre-clean so a leftover registration does not make the 100 baseline
    # ambiguous and so the uninstall scenarios start from a clean machine.
    $unins = Join-Path $script:InstallRoot 'unins000.exe'
    if (Test-Path -LiteralPath $unins -PathType Leaf) {
        Start-Process -FilePath $unins -Argument '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' `
            -Wait -PassThru -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
    }
    $deadline = (Get-Date).AddSeconds(90)   # Inno detaches; poll, never a blind fixed sleep
    while ((Get-Date) -lt $deadline -and
           (Test-Path -LiteralPath (Join-Path $script:InstallRoot 'prism.exe') -PathType Leaf)) {
        Start-Sleep -Milliseconds 500
    }
    if (Test-Path -LiteralPath $script:InstallRoot) {
        Remove-Item -LiteralPath $script:InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-PrismPathEntries {
    # The machine PATH entries the installer owns, as a plain array. Counting
    # these is the duplicate-PATH check; never hardcode the expected count.
    $machinePath = [Environment]::GetEnvironmentVariable('PATH', 'Machine')
    if ([string]::IsNullOrWhiteSpace($machinePath)) { return @() }
    return @($machinePath -split ';' | Where-Object { $_ -like '*Prism*' -and $_ -ne '' })
}

function Assert-PrismInstalled {
    # No SupportsShouldProcess: it is a no-op on an assertion helper and would
    # promise a -WhatIf that nothing honours.
    param([Parameter(Mandatory = $true)] [string] $Version)
    $exe = Join-Path $script:InstallRoot 'prism.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "prism.exe missing under $($script:InstallRoot)" }
    $info = Get-InstalledVersion
    if ($null -eq $info) { throw 'installed exe exposes no version resource' }
    # FileVersion is the Windows PE version resource: the stamp always derives
    # the numeric four-part form (0.2.1.4) from head+prerelease, so it can never
    # carry the user-facing pre-release string '0.2.1-beta4'. Compare it against
    # the numeric head (like test-install RG-011), not the product string -- a
    # real stamp passes and the 0.0.0.0 fallback is already caught upstream.
    $head = $Version
    if ($Version -match '^(\d+\.\d+\.\d+)-') { $head = $matches[1] }
    if ($info.FileVersion -notmatch ('^' + [regex]::Escape($head))) {
        throw "FileVersion '$($info.FileVersion)' does not match the build head '$head' (product version '$Version')"
    }
    $reported = Get-PrismVersionOutput
    if ($null -eq $reported) { throw 'prism.exe is not on the machine PATH after install' }
    if ($reported -notmatch [regex]::Escape($Version)) {
        throw "prism --version reports '$reported', expected to contain '$Version'"
    }
    $reg = Get-PrismRegistryPath
    if ($null -eq $reg) { throw 'Prism_is1 uninstall key absent after install' }
    if ([string]$reg.DisplayVersion -notmatch [regex]::Escape($Version)) {
        throw "registry DisplayVersion '$($reg.DisplayVersion)' does not match '$Version'"
    }
    $hits = @(Get-PrismPathEntries)
    if ($hits.Count -ne 1) { throw "expected exactly one PATH entry, found $($hits.Count): $($hits -join ', ')" }
    Write-SuiteLine "  [PASS] installed $reported (exe, version resource, PATH, registry)"
}

function Assert-PrismAbsent {
    param([string] $Because = 'the machine must be left clean')
    $exe = Join-Path $script:InstallRoot 'prism.exe'
    if (Test-Path -LiteralPath $exe -PathType Leaf) { throw "prism.exe survived uninstall at $exe -- $Because" }
    if ($null -ne (Get-PrismRegistryPath)) { throw "Prism_is1 key survived uninstall -- $Because" }
    $hits = @(Get-PrismPathEntries)
    if ($hits.Count -ne 0) { throw "PATH entry survived uninstall: $($hits -join ', ') -- $Because" }
    Write-SuiteLine "  [PASS] machine clean (no exe, no registry, no PATH) -- $Because"
}

function Assert-NoOrphan {
    # Compares two file manifests; a leftover from the previous version is an
    # orphan, which is how a two-AppId install coexists instead of replacing.
    param(
        [Parameter(Mandatory = $true)] [string[]] $Before,
        [Parameter(Mandatory = $true)] [string[]] $After,
        [string[]] $AllowList = @('prism.exe', 'unins000.dat')
    )
    $orphans = @($Before | Where-Object { ($_ -notin $After) -and ($_ -notin $AllowList) })
    if ($orphans.Count -gt 0) {
        throw "orphaned files after upgrade: $($orphans -join ', ')"
    }
    Write-SuiteLine "  [PASS] no orphans across $($After.Count) files"
}

function Get-PrismManifest {
    # Every file the installer dropped, relative to the install root -- the
    # manifest the orphan and retention checks compare.
    if (-not (Test-Path -LiteralPath $script:InstallRoot)) { return @() }
    return @(Get-ChildItem -LiteralPath $script:InstallRoot -Recurse -File -Force |
             ForEach-Object { $_.FullName.Substring($script:InstallRoot.Length).TrimStart('\') })
}

function Get-NextVersion {
    # Derives the adjacent release for the future-version and downgrade
    # scenarios. Never a [version] cast: that throws on a '0.2.2-beta7' suffix,
    # so the numeric head is split from the pre-release tag first.
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string] $Version,
        [Parameter(Mandatory = $true)]
        [string] $Bump,
        # 'up' gives the next release, 'down' the previous one. The downgrade
        # scenario needs the latter and it is not the same call.
        [string] $Direction = 'up'
    )
    if ($Bump -notin @('major', 'minor', 'patch')) { throw "-Bump '$Bump' is not major, minor or patch" }
    if ($Direction -notin @('up', 'down')) { throw "-Direction '$Direction' is not up or down" }
    if ([string]::IsNullOrWhiteSpace($Version)) { throw 'missing -Version' }
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

function Get-SourceVersion {
    # The version under test, read from pyproject.toml rather than hardcoded --
    # the single source of truth the whole suite derives its expectations from.
    param([string] $ProjectRoot = '.')
    $pyproject = Join-Path $ProjectRoot 'pyproject.toml'
    if (-not (Test-Path -LiteralPath $pyproject -PathType Leaf)) { throw "no pyproject.toml at $pyproject" }
    $text = Get-Content -LiteralPath $pyproject -Raw
    if ($text -notmatch '(?m)^\s*version\s*=\s*"([^"]+)"') {
        throw "pyproject.toml has no version = `"x.y.z`" line to derive a version from"
    }
    return $matches[1]
}

function New-PrismSetup {
    # Recompiles the installer for a different advertised version, REUSING the
    # already-built payload. Only the version defines change; the binaries are
    # not rebuilt, so the artifact stays the genuine compiled output with one
    # field overridden. Used by the future-version and downgrade scenarios.
    #
    # ISCC.exe is the COMPILER: it accepts /D<name>=<value> defines only. The
    # runtime switches (/VERYSILENT /NORESTART) belong to the produced setup.exe
    # and are rejected by the compiler, so never pass them here. The define
    # names are fixed by prism.iss (AppVer, AppVerFile, AppVerNumeric, AppSource)
    # and a define the script does not read is silently ignored, which compiles a
    # build that looks fine but tests the wrong version -- so copy them verbatim.
    param(
        [Parameter(Mandatory = $true)]
        [string] $Version,
        [Parameter(Mandatory = $true)]
        [string] $OutDirectory,
        [Parameter(Mandatory = $true)]
        [string] $SourcePath,
        [Parameter(Mandatory = $true)]
        [string] $IssPath
    )
    # Inno needs a four-part numeric for VersionInfoVersion (prism.iss:52); a
    # pre-release suffix would fail the compile outright, so reject it here
    # rather than let ISCC emit a misleading error.
    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        throw "-Version '$Version' must be dotted numeric 'M.N.P' (no pre-release tag, no 'v' prefix)"
    }
    if (-not (Test-Path -LiteralPath $IssPath -PathType Leaf)) { throw "no installer script at '$IssPath'" }
    if (-not (Test-Path -LiteralPath $SourcePath)) { throw "no payload to package at '$SourcePath'" }
    if (-not (Test-Path -LiteralPath $OutDirectory)) {
        New-Item -ItemType Directory -Path $OutDirectory -Force | Out-Null
    }
    $numeric = '{0}.0' -f $Version
    $iscc = @(Get-ChildItem 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
                            'C:\Program Files\Inno Setup 6\ISCC.exe' -ErrorAction SilentlyContinue) |
             Select-Object -First 1
    if (-not $iscc) { throw 'ISCC.exe not found (install Inno Setup 6, or run under Vagrant)' }

    # OutputDir is the LITERAL '.' at prism.iss:38, NOT a {#OutputDir} define, so
    # /DOutputDir= is silently ignored and the artifact lands BESIDE the .iss.
    # Compile a copy placed in $OutDirectory, the same move build-release.yml makes
    # when it copies prism.iss into dist/.
    $issCopy = Join-Path $OutDirectory 'prism.iss'
    Copy-Item -LiteralPath $IssPath -Destination $issCopy -Force
    # [Files]/[Setup] resolve these relative to the .iss, so the siblings must sit
    # beside the copy or the compiler aborts on a missing source. The wizard
    # images live under docs\assets\ (prism.iss:64-65), the icon at the repo root
    # (:60), so mirror both layouts and create the sub-directory.
    $repoRoot = Split-Path -Path $IssPath -Parent
    foreach ($asset in @('logo.ico', 'license.txt', 'docs\assets\wizard-sidebar.bmp',
                         'docs\assets\wizard-header.bmp')) {
        $src = Join-Path $repoRoot $asset
        if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { continue }
        $dst = Join-Path $OutDirectory $asset
        $dstDir = Split-Path -Path $dst -Parent
        if ($dstDir -and -not (Test-Path -LiteralPath $dstDir)) {
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
    ) -join ' '
    $stdout = & $iscc.FullName $argList $issCopy 2>&1
    if ($LASTEXITCODE -ne 0) { throw "ISCC failed for ${Version} (exit $LASTEXITCODE): $stdout" }
    # OutputBaseFilename is prism-{#AppVerFile}-setup (prism.iss:39), so the name
    # follows the version; never a fixed literal that could drift from it.
    $setup = Join-Path $OutDirectory ('prism-' + $Version + '-setup.exe')
    if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) { throw "ISCC exit 0 but produced no $setup" }
    return $setup
}

# --- Manifest comparison (probe-grounded 2026-09-07, VM prism-wsl-0-4-7) ---
# Measured on the installed tree vs the PyInstaller payload the installer packs:
#   installed = 1137 files, payload = 1135 files, delta = 2, and the ONLY two
#   files present in the install but not in the payload are Inno's own
#   unins000.exe / unins000.dat. prism.exe is in BOTH (it comes from the
#   payload), so it is deliberately NOT excused -- excusing it would hide a
#   missing entry-point binary, the one file a cold start actually needs.
# The list is a measurement, not a guess; it is kept MINIMAL and the default
# is empty for callers that want a raw comparison, so an unexpected extra file
# fails loudly instead of being silently excused.
$script:ExcludedInstallLeafNames = @('unins000.exe', 'unins000.dat')

function Get-ChildItemProbe {
    # Counted/compared manifests must be produced by ONE code path or the two
    # sides can disagree by construction. Thin wrapper so both callers are
    # literally the same call.
    param(
        [Parameter(Mandatory = $true)][string] $Root,
        [string[]] $Exclude = @()
    )
    if (-not (Test-Path -LiteralPath $Root)) { return @() }
    $ex = @($Exclude)
    return @(Get-ChildItem -Path $Root -Recurse -File -Force |
             ForEach-Object { $_.FullName.Substring($Root.Length).TrimStart('\') } |
             Where-Object { $ex -notcontains $_ } | Sort-Object)
}

function Get-InstalledManifest {
    param([string] $Root = $script:InstallRoot)
    return (Get-ChildItemProbe -Root $Root -Exclude $script:ExcludedInstallLeafNames)
}

function Get-PayloadManifest {
    param([Parameter(Mandatory = $true)][string] $Root)
    # Same exclusion set: the payload dir never carries them, so applying it on
    # both sides is a no-op there and keeps the two shapes identical by
    # construction.
    return (Get-ChildItemProbe -Root $Root -Exclude $script:ExcludedInstallLeafNames)
}

function Assert-NonVacuous {
    # A comparison over an empty set is a VACUOUS PASS: the gate proved nothing.
    # Fail loudly -- a green that tested nothing is the RG-007 class of defect.
    param(
        [Parameter(Mandatory = $true)][string] $What,
        [Parameter(Mandatory = $true)][int] $Count,
        [int] $Minimum = 1
    )
    if ($Count -lt $Minimum) {
        throw "vacuous result: '$What' yielded only $Count item(s); at least $Minimum is required, so the check proved nothing"
    }
}

function Get-SetupArtifact {
    # The installer artifact for a given advertised version, named exactly as
    # prism.iss emits it (OutputBaseFilename=prism-{#AppVerFile}-setup, and
    # OutputDir is the LITERAL '.', so the file lands beside the compiled .iss
    # -- proven by vagrant/build-in-vm.ps1:108-116, which builds in place and
    # Move-Item's the result into dist/).
    #
    # Resolution is deliberate: first the file named from the REQUESTED
    # version (so a build that ignored the version override is a MISS, not a
    # silent fallback onto a stale same-named artifact), then any setup.exe in
    # the directory. A missing/ambiguous match is a hard failure, never a
    # silent pick: RG-013/RG-011 document the trap where an upload carries a
    # stale (pre-stamp) artifact and verify reads 0.0.0.0 while the build
    # claimed numeric=0.2.1.4.
    param(
        [Parameter(Mandatory = $true)][string] $Dir,
        # Pass the version to pin the lookup to the artifact the caller EXPECTS;
        # pass '' to accept whatever setup.exe is in the directory.
        [AllowEmptyString()]
        [string] $Version = ''
    )
    if ([string]::IsNullOrWhiteSpace($Dir) -or -not (Test-Path -LiteralPath $Dir)) { return $null }
    if (-not [string]::IsNullOrWhiteSpace($Version)) {
        $exact = @(Get-ChildItem -Path $Dir -Filter ('prism-' + $Version + '-setup.exe') -File -Force |
                  Select-Object -First 1) | Select-Object -First 1
        # A named-but-absent artifact is a MISS, reported by the caller's own
        # non-vacuity assertion -- never quietly fall back to a stale same-named
        # file, which is how a no-op version override could masquerade as built.
        if ($exact) { return $exact.FullName }
        return $null
    }
    $any = @(Get-ChildItem -Path $Dir -Filter 'prism-*-setup.exe' -File -Force) | Select-Object -First 1
    if ($any) { return $any.FullName }
    return $null
}

# --- Sentinel reporting ---------------------------------------------------
# The runner classifies from these lines AND the exit code, so a lost output
# stream can never turn a red scenario green: a missing sentinel falls back to
# the exit code, and a nonzero exit is always a failure whatever the log says.
$script:SuiteLogFile = $null

function Write-SuiteLine {
    # One line into this scenario's own sentinel log (the file the runner reads)
    # AND onto stdout for the live console. Write-Output alone would depend on
    # the caller's redirection surviving; a file write does not.
    param(
        [Parameter(Mandatory = $true, Position = 0)][string] $Line,
        [switch] $Pass, [switch] $Fail, [switch] $Skip
    )
    $text = $Line
    if ($Pass) { $text = '[PASS] ' + $Line }
    elseif ($Fail) { $text = '##[FAIL] ' + $Line }
    elseif ($Skip) { $text = '##[SKIP] ' + $Line }
    Write-Output $text
    if ($script:SuiteLogFile) {
        Add-Content -LiteralPath $script:SuiteLogFile -Value $text -Encoding utf8
    }
}

# === canonical 5.1-safe helpers (written by vagrant/repair-suite.py) ===

# ---------------------------------------------------------------------------
# 5.1-safe infrastructure helpers. Resolve-Path / Get-FileHash are PowerShell 6+
# cmdlets; the suite runs under powershell.exe (5.1) on the pinned guest AND on the
# CI windows-latest job, where those names parse and then throw at run time. Only
# the target interpreter can see that class of defect, so these replacements are
# pinned to constructs the .NET 4.x runtime 5.1 hosts certainly provides.
# ---------------------------------------------------------------------------

# === canonical 5.1-safe helpers (written by vagrant/repair-suite.py) ===

# ---------------------------------------------------------------------------
# 5.1-safe infrastructure. Resolve-Path / Get-FileHash are PowerShell 6+ cmdlets;
# every job in this suite runs under powershell.exe (Windows PowerShell 5.1) on both
# the pinned guest and the CI windows-latest runner, where those names parse clean
# and then throw at run time -- a defect class NO static gate can see, so the fix is
# pinned to constructs the .NET 4.x runtime that 5.1 hosts certainly provides, and
# the proof is a RUN on the guest (probe wins), not a parse.
# ---------------------------------------------------------------------------

# === canonical 5.1-safe helpers (written by vagrant/repair-suite.py) ===

# ---------------------------------------------------------------------------
# 5.1-safe infrastructure. Resolve-Path / Get-FileHash are PowerShell 6+ cmdlets;
# every job in this suite runs under powershell.exe (Windows PowerShell 5.1) on both
# the pinned guest and the CI windows-latest runner, where those names parse clean
# and then throw at run time -- a defect class NO static gate can see, so the fix is
# pinned to constructs the .NET 4.x runtime that 5.1 hosts certainly provides, and
# the proof is a RUN on the guest (probe wins), not a parse.
# ---------------------------------------------------------------------------

function Get-AbsPath {
    # Absolute path for a possibly-relative input: no provider semantics, no PS6+
    # cmdlet. [IO.Directory]::GetCurrentDirectory() is the process working directory
    # and exists on the framework runtime, unlike Get-Location which can be $null
    # when the current provider is not the file system. Returns a STRING, so call
    # sites must not append .Path/.ProviderPath.
    #
    # A single positional parameter, ON PURPOSE. An earlier version carried a
    # ValueFromRemainingArgs sink to swallow a leftover -ErrorAction, but that
    # named-property syntax is not legal on this interpreter either (5.1 reports
    # 'Property ValueFromRemainingArgs cannot be found for type
    # CmdletBindingAttribute'), and the whole point of this helper is to stay within
    # the 5.1-safe subset -- the same trap as declaring [string] $ErrorAction, which
    # collides with the reserved common parameter. So the signature is minimal and the
    # call sites were normalised to pass ONLY the path (see vagrant/fix-round2.py); a
    # stray common parameter here is a bug at the call site, and it fails loud.
    param(
        [Parameter(Mandatory = $true, Position = 0)][string] $Path
    )
    if ([string]::IsNullOrWhiteSpace($Path)) {
        # The cmdlet this replaces threw on empty input and some callers depended on
        # that being observable, so keep the loud failure instead of returning a root.
        throw 'Get-AbsPath: an empty path was given.'
    }
    $candidate = $Path
    $rooted = ($candidate -match '^[A-Za-z]:[\\/]') -or $candidate.StartsWith('\\')
    if (-not $rooted) {
        $candidate = [System.IO.Path]::Combine(
            [System.IO.Directory]::GetCurrentDirectory(), $candidate)
    }
    return [System.IO.Path]::GetFullPath($candidate)
}

function Get-FileHash {
    # Replaces the PS6+ Get-FileHash cmdlet for 5.1, returning the same
    # @{ Hash = ... } shape so callers keep reading .Hash (test-prerelease does).
    # Candidate crypto types are tried through the type system then New-Object,
    # because which is constructible differs between the framework runtime 5.1 runs
    # on and the Core runtime pwsh uses. If NONE constructs it THROWS: a placeholder
    # digest would let an integrity check pass on a value never computed -- the exact
    # false-green this whole suite exists to prevent.
    param(
        [Parameter(Mandatory = $true, Position = 0)][string] $LiteralPath,
        [string] $Algorithm = 'SHA256'
    )
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
        throw "Get-FileHash: not a file: $LiteralPath"
    }
    $types = @{
        'SHA256' = @('System.Security.Cryptography.SHA256Managed',
                     'System.Security.Cryptography.SHA256Crypto')
        'SHA1'   = @('System.Security.Cryptography.SHA1Managed',
                     'System.Security.Cryptography.SHA1Crypto')
        'MD5'    = @('System.Security.Cryptography.MD5Managed',
                     'System.Security.Cryptography.MD5Crypto')
    }
    if (-not $types.ContainsKey($Algorithm)) {
        throw "Get-FileHash: unsupported algorithm '$Algorithm'"
    }
    $bytes = [System.IO.File]::ReadAllBytes($LiteralPath)
    $obj = $null
    foreach ($tn in $types[$Algorithm]) {
        if ($null -eq $obj) {
            try {
                $t = [System.Type]::GetType($tn, $true)
                if ($null -ne $t) { $obj = $t::Create() }
            } catch { $obj = $null }
        }
        if ($null -eq $obj) {
            try { $obj = New-Object -TypeName $tn -ErrorAction Stop } catch { $obj = $null }
        }
        if ($null -ne $obj) { break }
    }
    if ($null -eq $obj) {
        throw ("Get-FileHash: no {0} provider could be constructed on this runtime; " +
               'refusing to emit a placeholder digest.') -f $Algorithm
    }
    $raw = $obj.ComputeHash($bytes)
    # Per-byte ToString('x2') builds the hex: avoids relying on a remembered
    # BitConverter overload spelling, and yields lowercase like the cmdlet renders.
    return @{ Hash = (-join ($raw | ForEach-Object { $_.ToString('x2') })) }
}
