# prism-installer/test-future-version.ps1 - covers RG-014
# The case a release bump cannot reach: install a SYNTHETIC HIGHER version that
# has never been published over the real one. Proves the upgrade mechanism
# generalises beyond the single version CI happens to be building.
#
# Ground truth that shapes the assertions (measured 2026-09-07 on the VM):
#   * the registry DisplayVersion and prism --version come from the PAYLOAD
#     binary's own file version -- New-PrismSetup recompiles only the installer and
#     reuses the payload, so those stay at the real version no matter what the
#     defines say;
#   * the field a version override ACTUALLY changes is the setup artifact's own
#     PE file version. That is what step 5 compares: an override that silently
#     did not apply leaves the two setup exes reporting the same version, and a
#     byte/hash equality check could miss it -- an embedded PE timestamp makes
#     hashes differ spuriously and whole-file compares equal-by-accident is the
#     trap the repo's probe-honesty rule warns about. Compare the version
#     RESOURCE, not bytes.
param(
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'test-future-version.ps1',
    [string] $Baseline = 'fetch',
    [string] $Repo = '',
    [string] $SourceVersion = '',
    [int] $TimeoutSec = 600
)
. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')
$repoRoot = Split-Path -Path $script:SuiteRoot -Parent
$ArtifactsPath = (Get-AbsPath $ArtifactsPath -ErrorAction SilentlyContinue)
if (-not (Test-Path -LiteralPath $ArtifactsPath)) { Write-Output '##[SKIP] no artifacts dir'; exit 0 }

$payload = Join-Path $ArtifactsPath 'prism'
if (-not (Test-Path -LiteralPath $payload)) {
    Write-Output "##[SKIP] RG-014 the PyInstaller onedir payload ($payload) is not present; future-version needs the build job"
    exit 0
}

$real = $SourceVersion
if ([string]::IsNullOrWhiteSpace($real) -or $real -eq '0.0.0') {
    $real = Get-SourceVersion -ProjectRoot $repoRoot
}
$real = $real.TrimStart('v')
# New-PrismSetup takes a strict M.N.P; Get-NextVersion keeps the pre-release tag,
# so strip to the head for the compiler while the real string stays for logging.
$higherFull = Get-NextVersion -Version $real -Bump patch -Direction up
$higher = $higherFull -replace '-.*$', ''
if ($higher -notmatch '^\d+\.\d+\.\d+$') { throw "derived future version '$higherFull' is not dotted-numeric" }

Remove-PrismInstall
$setup = Get-SetupArtifact -Dir $ArtifactsPath -Version ''
if (-not $setup) { Write-Output '##[SKIP] RG-014 no built installer to upgrade'; exit 0 }
$future = New-PrismSetup -Version $higher -SourcePath $payload `
    -OutDirectory (Join-Path $ArtifactsPath 'future\latest') -IssPath (Join-Path $repoRoot 'prism.iss')

$dir = New-TempDir -Name $Name
# 1. the real build lands first -- it cannot be upgraded if it never installed.
$codeReal = Invoke-PrismSilent -Installer $setup -LogFilePath (Join-Path $dir 'real.log')
Assert-ExitCode -Expected $script:PRISM_OK -Actual $codeReal `
    -Because 'the base version must install before it can be upgraded'

# 2. the never-published higher version installs OVER it.
$codeUp = Invoke-PrismSilent -Installer $future -LogFilePath (Join-Path $dir 'upgrade.log')
Assert-ExitCode -Expected $script:PRISM_UPGRADE_OK -Actual $codeUp `
    -Because "v$higherFull is not published anywhere, so the upgrade must still complete"

# 3. the machine ends consistent: one registration, payload-complete tree. The
#    installed BINARY still reports $real (it is the same payload); that is the
#    honest expectation, not the synthetic number -- asserting $higher here would
#    test the defines against a field they do not influence.
Assert-PrismInstalled -Version $real
$expectedFiles = @(Get-PayloadManifest -Root $payload)
$installed = @(Get-InstalledManifest)
Assert-NonVacuous -What 'installed manifest' -Count $installed.Count
if ($installed.Count -ne $expectedFiles.Count) {
    Write-Output "##[FAIL] RG-014 the future-version upgrade left an orphan (installed $($installed.Count), payload $($expectedFiles.Count))"
    exit 1
}
$keys = @(Get-ChildItem -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
          Where-Object { (Get-ItemProperty -Path $_.PSPath -Name 'DisplayName' -ErrorAction SilentlyContinue) -like 'Prism*' })
if ($keys.Count -ne 1) {
    Write-Output "##[FAIL] RG-014 duplicate registrations after a future-version upgrade (found $($keys.Count), expected 1)"
    exit 1
}

# 4. the override actually moved the field it owns -- the setup's own PE version.
#    Equal versions here mean the define was ignored and the "future" build is a
#    cosmetic copy: the gate must go red, never pass on trust.
$rv = Get-PrismFileVersion -LiteralPath $setup
$fv = Get-PrismFileVersion -LiteralPath $future
if ($null -eq $rv -or $null -eq $fv) {
    Write-Output "##[FAIL] RG-014 a setup artifact reported no usable file version (real=$($rv) future=$($fv))"
    exit 1
}
if ($rv.ToString() -eq $fv.ToString()) {
    Write-Output "##[FAIL] RG-014 the future build carries the real version $($fv.ToString()) -- the override was not applied"
    exit 1
}
if ($fv.ToString() -notmatch ('^' + [regex]::Escape($higher))) {
    Write-Output "##[FAIL] RG-014 the future build reports $($fv.ToString()), expected the $higher head"
    exit 1
}
Write-Output "##[PASS] RG-014 $real -> synthetic $higherFull (never published) upgrades cleanly; setup versions $($rv.ToString()) vs $($fv.ToString())"
exit 0
