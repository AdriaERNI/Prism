# prism-installer/static/analyze-install-consistency.ps1 - RG-001 / RG-010
# Textual gate: a silent installer run that can pop a dialog hangs a headless
# runner forever, so the exact Inno switch set is a contract, not a style note.
#
# Scoping matters: docs/plans/** and prism-installer/** quote the WRONG switch
# while explaining why it is wrong (that is the RG-001 write-up itself), and
# the shared library carries the same cautionary comment. Scanning them would
# make the gate red forever -- a permanently-red gate is as useless as a green
# that cannot fail. Excluded from the scan, deliberately and permanently.
param([string] $Root = $PWD)

$fail = @()
$excludes = @('docs\plans', 'docs/plans', 'prism-installer', 'site', '.venv', 'node_modules')

function Test-Excluded([string] $path) {
    foreach ($e in $excludes) { if ($path -like ('*' + $e + '*')) { return $true } }
    return $false
}

$targets = @()
$iss = Join-Path $Root 'prism.iss'
if (Test-Path -LiteralPath $iss -PathType Leaf) { $targets += (Get-Item -LiteralPath $iss) }
$targets += @(Get-ChildItem -Path $Root -Recurse -Include '*.ps1' -File -Force |
              Where-Object { -not (Test-Excluded $_.FullName) })
foreach ($wfDir in @('.github\workflows', '.github/workflows')) {
    $full = Join-Path $Root $wfDir
    if (Test-Path -LiteralPath $full) {
        $targets += @(Get-ChildItem -Path $full -Include '*.yml' -File -Force)
    }
}
$docsRoot = Join-Path $Root 'docs'
if (Test-Path -LiteralPath $docsRoot) {
    $targets += @(Get-ChildItem -Path $docsRoot -Recurse -Include '*.md' -File -Force |
                  Where-Object { -not (Test-Excluded $_.FullName) })
}

foreach ($t in $targets) {
    $text = Get-Content -LiteralPath $t.FullName -Raw
    $rel  = $t.FullName.Substring($Root.Length).TrimStart('\','/')

    # /VERYSILENT implies /NoRestart and /Quiet, but be explicit: an implicit
    # restart turns a clean install into a 3010 on a machine you no longer own.
    if ($text -match '/VERYSILENT' -and $text -notmatch '/NORESTART') {
        $fail += "##FAIL $rel - /VERYSILENT must be paired with /NORESTART"
    }
    # The singular form is not an Inno parameter at all, so dialogs stay up.
    if ($text -match '/SUPPRESSMSGBOX(?![Ee])') {
        $fail += "##FAIL $rel - '/SUPPRESSMSGBOX' is not an Inno switch; use the plural '/SUPPRESSMSGBOXES' or a dialog hangs the runner (RG-001)"
    }
    # Silent runs are unsupervised: without a log there is no post-mortem. Scoped
    # to SETUP invocations -- the uninstaller (unins000.exe) legitimately runs
    # without one and is not a scenario whose failure needs a post-mortem trail.
    if ($text -match '/VERYSILENT' -and $text -match 'setup\.exe|-setup' -and $text -notmatch '/LOG') {
        $fail += "##FAIL $rel - silent installer runs must emit a per-test /LOG"
    }
}

# prism.iss [Code] is single-pass Pascal: ';' line comments are invalid there
# and Inno's compiler rejects the script. Only the [Code] body is checked --
# ';' IS the correct comment character everywhere else in the file.
if (Test-Path -LiteralPath $iss -PathType Leaf) {
    $issText = Get-Content -LiteralPath $iss -Raw
    $start = $issText.IndexOf('[Code]')
    if ($start -ge 0) {
        if ($issText.Substring($start) -match '(?m)^\s*;\s*\w') {
            $fail += "##FAIL prism.iss - ';' line comments inside [Code] are invalid Pascal comments; use { } braces"
        }
    }
}

if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Output $_ }; exit 1 }
Write-Output ("##[PASS] installer scripts are consistent ({0} file(s) scanned)" -f $targets.Count)
exit 0
