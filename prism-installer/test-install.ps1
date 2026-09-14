# prism-installer/test-install.ps1 - covers RG-001, RG-010, RG-011
# The fresh-install path, with the artifact's own version resource asserted.
# Explorer, Add/Remove Programs and the Microsoft Store ingest all read
# FileVersion, so a build that drops an ISCC define and files 0.0.0.0 must fail
# HERE, not in Partner Center days later.
param(
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'test-install.ps1',
    [string] $Baseline = 'fetch',
    [string] $Repo = '',
    [string] $SourceVersion = '',
    [string] $SuiteLogFile = ''
)
. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')
$script:SuiteLogFile = $SuiteLogFile

$ArtifactsPath = (Get-AbsPath $ArtifactsPath -ErrorAction SilentlyContinue)
if (-not (Test-Path -LiteralPath $ArtifactsPath)) {
    Write-SuiteLine 'no installer was built (the build job failed or was skipped)' -Skip
    exit 0
}
$setup = Get-SetupArtifact -Dir $ArtifactsPath -Version ''
if (-not $setup) { Write-SuiteLine "no prism-*-setup.exe in $ArtifactsPath" -Skip; exit 0 }

# The version under test is DERIVED, never pinned: a literal would go stale on
# the next release and then assert the wrong thing while staying green.
$version = $SourceVersion
if ([string]::IsNullOrWhiteSpace($version) -or $version -eq '0.0.0') {
    $vf = Join-Path $ArtifactsPath 'version.txt'
    if (Test-Path -LiteralPath $vf -PathType Leaf) { $version = (Get-Content -LiteralPath $vf -Raw).Trim() }
    else { $version = Get-SourceVersion -ProjectRoot (Split-Path $PSScriptRoot -Parent) }
}
$version = $version.TrimStart('v')
Write-SuiteLine "version under test: $version"

Remove-PrismInstall                     # a stale registration makes the 100 baseline ambiguous
Assert-PrismAbsent -Because 'a fresh install starts from a clean machine'

$dir = New-TempDir -Name $Name
$log = Join-Path $dir 'install.log'
$code = Invoke-PrismSilent -Installer $setup -LogFilePath $log
Assert-ExitCode -Expected $script:PRISM_OK -Actual $code `
    -Because 'a fresh silent install must succeed cleanly (0; 100 only with a prior registration)'

# The log is the post-mortem artifact: it must exist and say success. A silent
# run with no log left no evidence the installer actually executed.
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "no /LOG was written to $log" }
$logText = Get-Content -LiteralPath $log -Raw
if ($logText -notmatch 'Installation process succeeded') {
    throw "the installer log does not report success -- inspect $log"
}
if ($logText -match 'Setup Failed|return code [1-9]') {
    throw "the installer log records a failure -- inspect $log"
}

# RG-011: the version resource must be real and match the build. Compare against
# the four-part numeric head, because Inno stores a numeric VersionInfoVersion
# ('0.2.1.0') where the file NAME and --version keep the pre-release tag
# ('0.2.1-beta3'). A bare [version] cast would throw on that suffix.
$fv = Get-PrismFileVersion -LiteralPath $setup
if ($null -eq $fv) {
    Write-SuiteLine "RG-011 the published setup.exe reports no usable FileVersion (null / 0.0.0.0) at $setup" -Fail
    exit 1
}
if ('0.0.0.0' -eq $fv.ToString()) {
    Write-SuiteLine 'RG-011 the published setup.exe carries the 0.0.0.0 fallback version -- an ISCC define was dropped' -Fail
    exit 1
}
$head = $version
if ($version -match '^(\d+\.\d+\.\d+)-') { $head = $matches[1] }
if ($fv.ToString() -notmatch ('^' + [regex]::Escape($head))) {
    Write-SuiteLine "RG-011 FileVersion '$($fv.ToString())' does not match the build version '$head' (a define was dropped from the ISCC call)" -Fail
    exit 1
}
Write-SuiteLine "setup.exe FileVersion $($fv.ToString()) matches the build head $head"

# File-count guard: identical manifest shape on both sides, and non-vacuous or it
# proves nothing (an empty-vs-empty compare is the vacuous-green trap).
$fcf = Join-Path $ArtifactsPath 'file-count.txt'
if (Test-Path -LiteralPath $fcf -PathType Leaf) {
    $expected = [int]((Get-Content -LiteralPath $fcf -Raw).Trim())
    $installed = @(Get-InstalledManifest)
    Assert-NonVacuous -What 'installed manifest' -Count $installed.Count
    if ($installed.Count -ne $expected) {
        Write-SuiteLine "RG-010 installed $($installed.Count) files, the build produced $expected" -Fail
        exit 1
    }
    Write-SuiteLine "$expected payload files present (excused: $($script:ExcludedInstallLeafNames -join ', '))"
}

Assert-PrismInstalled -Version $version
Write-SuiteLine "fresh install verified: $version" -Pass
