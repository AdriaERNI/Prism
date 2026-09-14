# prism-installer/test-upgrade-matrix.ps1 - covers RG-005, RG-008
# Published baseline -> current build, in place. The exit-code contract here is
# the counter-intuitive one: GetCustomSetupExitCode returns 100 on every
# re-install because WasPreviouslyInstalled is snapshotted in InitializeSetup,
# before Inno writes the uninstall key -- so 100 IS success and a gate asserting
# 0 would misread a working upgrade as a failure.
param(
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'test-upgrade-matrix.ps1',
    [string] $Baseline = 'fetch',
    [string] $Repo = '',
    [string] $SourceVersion = '',
    [string] $SuiteLogFile = ''
)
. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')
$script:SuiteLogFile = $SuiteLogFile
$ArtifactsPath = (Get-AbsPath $ArtifactsPath -ErrorAction SilentlyContinue)

$old = Join-Path $ArtifactsPath 'prism-old-setup.exe'
$setup = if (Test-Path -LiteralPath $ArtifactsPath) { Get-SetupArtifact -Dir $ArtifactsPath -Version '' } else { $null }
if (-not $setup) { Write-Output '##[SKIP] no installer built'; exit 0 }
if (-not (Test-Path -LiteralPath $old -PathType Leaf)) {
    if ($Baseline -eq 'runner') {
        # The build job owns acquisition; a silent skip here would let the whole
        # upgrade matrix run zero scenarios and still report green (RG-013 class).
        Write-Output "##FAIL RG-013 the build job was to supply $old (Baseline=runner) but it is absent"
        exit 1
    }
    Write-Output '##[SKIP] no published baseline to upgrade from'; exit 0
}

$version = $SourceVersion
if ([string]::IsNullOrWhiteSpace($version) -or $version -eq '0.0.0') {
    $vf = Join-Path $ArtifactsPath 'version.txt'
    if (Test-Path -LiteralPath $vf -PathType Leaf) { $version = (Get-Content -LiteralPath $vf -Raw).Trim() }
    else { $version = Get-SourceVersion -ProjectRoot (Split-Path $PSScriptRoot -Parent) }
}
$version = $version.TrimStart('v')

$dir = New-TempDir -Name $Name
Remove-PrismInstall
$baseline = Invoke-PrismSilent -Installer $old -LogFilePath (Join-Path $dir 'baseline.log')
Assert-ExitCode -Expected $script:PRISM_OK -Actual $baseline `
    -Because 'the published baseline must install cleanly first'

# Orphan comparison uses the SAME manifest path on both sides (Get-ChildItemProbe),
# with Inno's bookkeeping excused on both, so the sets cannot disagree by shape.
$before = @(Get-InstalledManifest)
Assert-NonVacuous -What 'pre-upgrade manifest' -Count $before.Count

$code = Invoke-PrismSilent -Installer $setup -LogFilePath (Join-Path $dir 'upgrade.log')
Assert-ExitCode -Expected $script:PRISM_UPGRADE_OK -Actual $code `
    -Because 'a re-install over a registered copy returns 100 by design, never 0 (RG-005)'

Assert-PrismInstalled -Version $version
$after = @(Get-InstalledManifest)
Assert-NonVacuous -What 'post-upgrade manifest' -Count $after.Count
Assert-NoOrphan -Before $before -After $after

# Exactly one registration, pointing at the NEW version: two AppIds would leave
# both versions coexisting -- the failure mode an 'is prism.exe present' check
# cannot see (RG-008).
$keys = @(Get-ChildItem -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
          Where-Object {
              $dn = (Get-ItemProperty -Path $_.PSPath -Name 'DisplayName' -ErrorAction SilentlyContinue).DisplayName
              $dn -like 'Prism*'
          })
if ($keys.Count -ne 1) {
    Write-Output "##FAIL RG-008 $($keys.Count) Prism uninstall registrations found, expected exactly 1 (no side-by-side)"
    exit 1
}
$disp = (Get-ItemProperty -Path $keys[0].PSPath -Name 'DisplayVersion' -ErrorAction SilentlyContinue).DisplayVersion
if ($null -eq $disp -or ([string]$disp) -notmatch [regex]::Escape($version)) {
    Write-Output "##FAIL RG-008 the upgrade did not replace the versioned registration (DisplayVersion='$disp', want '$version')"
    exit 1
}
Write-Output "  [PASS] upgrade path: baseline -> $version, one registration, no orphans"
