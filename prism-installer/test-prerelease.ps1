# prism-installer/test-prerelease.ps1 - covers RG-012, RG-013
# Acquires the published installer the upgrade matrix upgrades FROM. Two shipped
# defects close here: (RG-012) /releases/latest EXCLUDES pre-releases, and on
# this repo every release since v0.2.1 is a pre-release -- that endpoint 404s
# (measured 2026-09-07), so selection walks the full list newest-first instead;
# (RG-013) gh --pattern is a GLOB, not a regex, and a silent miss would let the
# upgrade matrix run zero scenarios and still print green.
param(
    [Parameter(Mandatory = $true)][string] $Repo,
    [Parameter(Mandatory = $true)][string] $SourceVersion,
    [string] $OutDir = './dist',
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'test-prerelease.ps1',
    [string] $Baseline = 'fetch',
    [string] $SuiteLogFile = '',
    # Newest overall by default -- Prism ships pre-releases off dev. Stable-only is
    # the explicit opt-in, precisely because /releases/latest hides the betas.
    [switch] $StableOnly
)
. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')
$script:SuiteLogFile = $SuiteLogFile
$ErrorActionPreference = 'Stop'

if ($Repo -notmatch '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$') {
    Write-Output "##[FAIL] RG-012 invalid -Repo '$Repo' (expected 'owner/name'; an unexpanded workflow placeholder never reaches here)"
    exit 1
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Output '##[SKIP] RG-012 gh is not installed; the published baseline cannot be acquired'
    exit 0
}

# The FULL list, not /releases/latest. GitHub orders releases newest-first by
# created_at; do NOT re-sort with a [version] cast -- it throws on '0.2.2-beta7'.
$json = gh api "repos/$Repo/releases" --jq '[.[] | select(.draft == false)]' 2>&1
if ($LASTEXITCODE -gt 1) { Write-Output "##[FAIL] RG-012 gh api failed (exit $LASTEXITCODE): $($json -join ' ')"; exit 1 }
$releases = @($json | Out-String | ConvertFrom-Json)
if ($releases.Count -eq 0) { Write-Output '##[SKIP] RG-012 the repository has no releases yet'; exit 0 }

$candidates = $releases
if ($StableOnly) { $candidates = @($candidates | Where-Object { $_.prerelease -eq $false }) }
if ($candidates.Count -eq 0) {
    Write-Output "##[FAIL] RG-012 no release qualifies under -StableOnly (found $($releases.Count) releases, all pre-releases?)"
    exit 1
}

$want = ('v' + $SourceVersion)
$pickedTag = $null; $pickedAsset = $null
foreach ($release in $candidates) {
    $tag = [string]$release.tag_name
    if ($tag -eq $want -or $tag -eq $SourceVersion) { continue }   # never the build itself
    $asset = @($release.assets | Where-Object { $_.name -like '*-setup.exe' }) | Select-Object -First 1
    if ($asset) { $pickedTag = $tag; $pickedAsset = $asset; break }
}
if (-not $pickedTag) {
    Write-Output '##[SKIP] RG-012 no published release carries a setup.exe asset (nothing to upgrade from)'
    exit 0
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$target = Join-Path $OutDir 'prism-old-setup.exe'
if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }   # always re-fetch; a stale file masks a moved upload

# RG-013: --pattern is a GLOB and is never quoted.
$null = gh release download $pickedTag --repo $Repo --clobber --dir $OutDir --pattern '*-setup.exe' 2>&1
if ($LASTEXITCODE -gt 0) {
    Write-Output "##[FAIL] RG-013 gh release download $($pickedTag) exited $LASTEXITCODE with no matching asset"
    exit 1
}
$landed = @(Get-ChildItem -Path $OutDir -Filter '*-setup.exe' -File -Force |
           Where-Object { $_.Name -ne 'prism-old-setup.exe' }) | Select-Object -First 1
if (-not $landed) {
    Write-Output "##[FAIL] RG-013 $($pickedTag) lists a setup.exe asset but the download wrote none"
    exit 1
}
if ($landed.Length -lt 1MB) {
    Write-Output "##[FAIL] RG-013 the downloaded baseline is only $($landed.Length) bytes -- a truncated fetch"
    exit 1
}
Move-Item -LiteralPath $landed.FullName -Destination $target -Force

Set-Content -LiteralPath (Join-Path $OutDir 'baseline-tag.txt') -Value $pickedTag
$sha = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower()
Set-Content -LiteralPath (Join-Path $OutDir 'baseline-sha256.txt') -Value $sha
Write-Output "##[PASS] baseline $pickedTag acquired from $Repo ($($landed.Length) bytes, sha256 $sha)"
exit 0
