# prism-installer/test-downgrade.ps1 - covers RG-015
# The guard in the other direction. prism.iss [Files] installs with
# Flags: ignoreversion, so Setup overwrites a NEWER file without asking: an older
# installer dropped on a newer install SUCCEEDS and Windows records it as a
# normal upgrade. This pins the contract so a future change that drops
# ignoreversion cannot quietly turn a downgrade into a half-applied tree with
# new files stranded behind an old version number.
param(
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'test-downgrade.ps1',
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
    Write-Output "##[SKIP] RG-015 the PyInstaller onedir payload ($payload) is not present; downgrade needs the build job"
    exit 0
}

$version = $SourceVersion
if ([string]::IsNullOrWhiteSpace($version) -or $version -eq '0.0.0') {
    $version = Get-SourceVersion -ProjectRoot $repoRoot
}
$version = $version.TrimStart('v')
$lower = (Get-NextVersion -Version $version -Bump patch -Direction down) -replace '-.*$', ''
if ($lower -notmatch '^\d+\.\d+\.\d+$') { throw "derived downgrade version '$lower' is not dotted-numeric" }
if ($lower -eq ($version -replace '-.*$', '')) {
    # patch 0 -> would build the same head; bump minor down instead so the
    # fixture is genuinely older rather than a misleading same-version reinstall.
    $lower = (Get-NextVersion -Version $version -Bump minor -Direction down) -replace '-.*$', ''
}

Remove-PrismInstall
$setup = Get-SetupArtifact -Dir $ArtifactsPath -Version ''
if (-not $setup) { Write-Output '##[SKIP] RG-015 no built installer'; exit 0 }
$dir = New-TempDir -Name $Name
$code = Invoke-PrismSilent -Installer $setup -LogFilePath (Join-Path $dir 'newer.log')
Assert-ExitCode -Expected $script:PRISM_OK -Actual $code `
    -Because 'the newer version must be present before an older one can replace it'
Assert-PrismInstalled -Version $version

$older = New-PrismSetup -Version $lower -SourcePath $payload `
    -OutDirectory (Join-Path $ArtifactsPath 'downgrade\latest') -IssPath (Join-Path $repoRoot 'prism.iss')
$rv = Get-PrismFileVersion -LiteralPath $setup
$ov = Get-PrismFileVersion -LiteralPath $older
if ($null -eq $ov -or $ov.ToString() -eq ($rv.ToString())) {
    Write-Output "##[FAIL] RG-015 the older build did not take the lowered version (got $($ov))"
    exit 1
}
$codeDown = Invoke-PrismSilent -Installer $older -LogFilePath (Join-Path $dir 'downgrade.log')
Assert-ExitCode -Expected $script:PRISM_UPGRADE_OK -Actual $codeDown `
    -Because 'ignoreversion makes Setup overwrite the newer files without asking'

# Consistency, not just success: the tree must match the payload manifest exactly
# (no stale newer files behind the old version) and hold ONE registration.
$expectedFiles = @(Get-PayloadManifest -Root $payload)
$installed = @(Get-InstalledManifest)
Assert-NonVacuous -What 'installed manifest' -Count $installed.Count
if ($installed.Count -ne $expectedFiles.Count) {
    Write-Output "##[FAIL] RG-015 the downgrade left the newer files behind (installed $($installed.Count), expected $($expectedFiles.Count))"
    exit 1
}
$keys = @(Get-ChildItem -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
          Where-Object { (Get-ItemProperty -Path $_.PSPath -Name 'DisplayName' -ErrorAction SilentlyContinue) -like 'Prism*' })
if ($keys.Count -ne 1) {
    Write-Output "##[FAIL] RG-015 the downgrade left duplicate registrations (found $($keys.Count))"
    exit 1
}
Write-Output "##[PASS] RG-015 $version -> $lower stays consistent (one registration, no stale files)"
exit 0
