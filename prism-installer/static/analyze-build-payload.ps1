# prism-installer/static/analyze-build-payload.ps1 - RG-010 / RG-011
# A dropped packaging flag is invisible until an installer is installed on a
# real machine and cold-starts wrong, so the flag set is a gate, not a wish.
# Measured defect behind the RG-011 line: build-release.yml passes AppVer,
# AppVerFile and AppSource but not AppVerNumeric, and prism.iss falls back to
# its 0.0.0.0 default -- every published setup.exe then reports a null file
# version to Explorer, Add/Remove Programs and the Microsoft Store ingest.
param([string] $Root = $PWD)

$fail = @()
$wfPath = Join-Path $Root '.github' 'workflows' 'build-release.yml'
if (-not (Test-Path -LiteralPath $wfPath -PathType Leaf)) {
    Write-Output '##FAIL build-release.yml - the release workflow is missing entirely'
    exit 1
}
$wf = Get-Content -LiteralPath $wfPath -Raw

# Required PyInstaller flags (each one fixes a real observed breakage).
$required = @(
    '--icon',                # logo on the exe; its absence was the 'no logo' report
    '--copy-metadata',       # .dist-info bundles; missing => PackageNotFoundError on import
    '--collect-submodules',  # prism.mcp submodules otherwise vanish from the bundle
    '--hidden-import'        # importlib.metadata must be force-included for frozen
)
foreach ($flag in $required) {
    if ($wf -notmatch [regex]::Escape($flag)) {
        $fail += "##FAIL build-release.yml - required PyInstaller flag $flag is missing from the release build"
    }
}

# --windowed suppresses the console: wrong for a CLI tool and it can glitch the
# Inno wizard's own pages.
if ($wf -match '--windowed') {
    $fail += "##FAIL build-release.yml - --windowed must not be used for a CLI tool"
}

# The moving target: an unpinned IRIS tag breaks the pipeline with no code
# change on our side (the 2026.1 post-startup regression).
if ($wf -match 'iris-community:latest' -or $wf -match 'intersystemsdc/iris-community(?![:/])') {
    $fail += "##FAIL build-release.yml - the IRIS image tag must be pinned to a tested version, never :latest"
}

# RG-011: the version-resource define. ISCC is the COMPILER: it only accepts
# /D<name>=<value>; a define the .iss never declares is silently ignored, which
# is exactly how a build can look fine and still file a null field.
if ($wf -match 'ISCC' ) {
    if ($wf -notmatch '/DAppVerNumeric\s*=') {
        $fail += "##FAIL build-release.yml - ISCC is invoked without /DAppVerNumeric, so prism.iss falls back to its 0.0.0.0 default and every published setup.exe reports a null file version (RG-011)"
    }
}

if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Output $_ }; exit 1 }
Write-Output '##[PASS] the release build carries every required packaging flag'
exit 0
