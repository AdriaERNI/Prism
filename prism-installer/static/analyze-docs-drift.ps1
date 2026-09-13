# prism-installer/static/analyze-docs-drift.ps1 - RG-004 / RG-003 (static half)
# Stale documentation and stale fixtures are the #1 false-failure source in this
# repo: a command deleted by a shipped PR keeps being asserted by a test until
# somebody pays the VM minutes to find the whole suite red. These are cheap
# textual pins for the classes already observed.
param([string] $Root = (Get-Location -Current))

$fail = @()
$excludes = @('docs\plans', 'docs/plans', 'prism-installer', 'site', '.venv', 'node_modules')
function Test-Excluded([string] $path) {
    foreach ($e in $excludes) { if ($path -like ('*' + $e + '*')) { return $true } }
    return $false
}

# Verbs deleted by shipped PRs that must not come back into docs or fixtures.
$removedVerbs = @('prism terminal', 'iris -i', '--no-login')

$scan = @()
$readme = Join-Path $Root 'README.md'
if (Test-Path -LiteralPath $readme -PathType Leaf) { $scan += (Get-Item -LiteralPath $readme) }
foreach ($d in @('docs', 'vagrant\scripts', 'vagrant/scripts', 'tests')) {
    $full = Join-Path $Root $d
    if (Test-Path -LiteralPath $full) {
        $scan += @(Get-ChildItem -Path $full -Recurse -Include '*.md','*.ps1' -File -Force |
                   Where-Object { -not (Test-Excluded $_.FullName) })
    }
}
$mk = Join-Path $Root 'mkdocs.yml'
if (Test-Path -LiteralPath $mk -PathType Leaf) { $scan += (Get-Item -LiteralPath $mk) }

foreach ($f in $scan) {
    $text = Get-Content -LiteralPath $f.FullName -Raw
    $rel  = $f.FullName.Substring($Root.Length).TrimStart('\','/')
    foreach ($verb in $removedVerbs) {
        if ($text -match [regex]::Escape($verb)) {
            $fail += "##FAIL $rel - references '$verb', removed by a shipped PR"
        }
    }
    # A hardcoded subcommand count goes stale on the next added command; the
    # help-contract test derives the surface from the binary instead.
    if ($text -match '\b\d+ subcommands?\b') {
        $fail += "##FAIL $rel - hardcodes a subcommand count; derive the surface from prism --help (test-help-contract.ps1)"
    }
}

# The standalone prism-<ver>.exe was dropped in favour of the setup bundle.
$dist = Join-Path $Root 'dist'
if (Test-Path -LiteralPath $dist) {
    $loose = @(Get-ChildItem -Path $dist -Filter 'prism-*.exe' -File -Force |
               Where-Object { $_.Name -notlike '*-setup.exe' })
    foreach ($l in $loose) {
        $fail += "##FAIL dist\$($l.Name) - the standalone prism-<ver>.exe no longer ships; only prism-<ver>-setup.exe does"
    }
}

if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Output $_ }; exit 1 }
Write-Output ("##[PASS] docs and fixtures match the shipped surface ({0} file(s) scanned)" -f $scan.Count)
exit 0
