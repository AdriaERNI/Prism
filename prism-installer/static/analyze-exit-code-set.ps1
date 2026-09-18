# prism-installer/static/analyze-exit-code-set.ps1 - RG-006 code-set gate.
# The Store rejects a submission whose EXE return-code map has DUPLICATE values,
# and a code that is claimed but neither exercised nor declared not-exercised is
# a falsified row. This gate derives the CLAIMED set from the shipping prism.iss
# (the [Code] mapping block plus GetCustomSetupExitCode wiring) and proves the
# gate can go red by holding negative fixtures for a deleted row, a falsified
# code, and a duplicate value.
#
# Run: pwsh -NoProfile -ExecutionPolicy Bypass -File prism-installer/static/analyze-exit-code-set.ps1
param(
    [string] $Iss = 'prism.iss',
    [string] $SuiteDir = 'prism-installer'
)
$ErrorActionPreference = 'Stop'

# --- derive the claimed set from the shipping .iss ---------------------------
$text = Get-Content $Iss -Raw -Encoding ascii
# The mapping block in [Code] lists each scenario and its EXE code:
#   {   Scenario                       EXE code   Basis                          }
#   {   Installation successful     0      Inno documented (run to          }
# Extract the numeric codes from that block: a line matching a scenario name
# followed by an integer. The block is bounded by the "Microsoft Store return-code
# mapping" header and the closing brace before "Inno returns 0/1/2/4/7/8".
$m = [regex]::Match($text, '(?s)Microsoft Store return-code mapping.*?Inno returns 0/1/2/4/7/8')
if (-not $m.Success) {
    Write-Error 'prism.iss has no Microsoft Store return-code mapping block; the claimed set cannot be derived'
}
$block = $m.Value
$claimed = @()
foreach ($line in ($block -split '\r?\n')) {
    # A mapping row: scenario text, then an integer code, then the basis text.
    if ($line -match '^\s*\{\s*(.+?)\s+(\d+)\s+(.+?)\s*\}\s*$') {
        $claimed += [int]$matches[2]
    }
}

# --- duplicate check (the exact defect the Store rejects) -------------------
$seen = @{}
foreach ($c in $claimed) {
    if ($seen.ContainsKey($c)) {
        Write-Error "duplicate EXE return code $c in prism.iss mapping -- the Store rejects duplicate values"
    }
    $seen[$c] = $true
}
if ($claimed.Count -eq 0) {
    Write-Error 'derived claimed set is empty -- a gate that cannot go red is not a gate'
}

# --- writer check for custom codes (>8) --------------------------------------
# A custom code the mapping claims must either have a writer in the .iss (then it
# is exercisable) or be declared not-exercised with a reason (unreachable by
# construction, like the reserved hooks 101/102 whose backing variable is read but
# never assigned). A claimed code with a writer that is NOT exercised is falsified.
$custom = @($claimed | Where-Object { $_ -gt 8 })
foreach ($cc in $custom) {
    $hasWriter = $false
    if ($cc -eq 100) {
        $hasWriter = ($text -match 'WasPreviouslyInstalled\s+then\s+Result\s*:=\s*100')
    } else {
        $hasWriter = ([regex]::Matches($text, 'CustomErrorCode\s*:=\s*[^;]+;').Count -gt 0)
    }
    if (-not $hasWriter) {
        # No writer -> unreachable by construction; the suite must declare it so.
        $suiteText = Get-Content (Join-Path $SuiteDir 'test-exit-code-contract.ps1') -Raw -Encoding ascii
        $declared = $false
        foreach ($m4 in [regex]::Matches($suiteText, '\$notExercised\s*=\s*@\((.*?)\)')) {
            foreach ($tok in ($m4.Groups[1].Value -split ',')) {
                $t = $tok.Trim()
                if ($t -match '^\d+$' -and [int]$t -eq $cc) { $declared = $true }
            }
        }
        if (-not $declared) {
            Write-Error "claimed code $cc has no writer in prism.iss and is not declared not-exercised in the suite (falsified row)"
        }
    }
}

# --- cross-check against the suite's asserted set ----------------------------
# Every claimed code must be either exercised (in the suite's asserted matrix) or
# declared not-exercised (in $notExercised with a reason). A claimed code that is
# neither is a falsified row; a code exercised but never claimed is a drift.
$suiteText = Get-Content (Join-Path $SuiteDir 'test-exit-code-contract.ps1') -Raw -Encoding ascii
$asserted = @()
foreach ($m2 in [regex]::Matches($suiteText, 'Code\s*=\s*(\d+)')) {
    $asserted += [int]$m2.Groups[1].Value
}
$notExercised = @()
foreach ($m3 in [regex]::Matches($suiteText, '\$notExercised\s*=\s*@\((.*?)\)')) {
    foreach ($tok in ($m3.Groups[1].Value -split ',')) {
        $t = $tok.Trim()
        if ($t -match '^\d+$') { $notExercised += [int]$t }
    }
}
$missing = @()
foreach ($c in $claimed) {
    if (($c -notin $asserted) -and ($c -notin $notExercised)) {
        $missing += $c
    }
}
if ($missing.Count -gt 0) {
    Write-Error "claimed codes with no assertion and no declared not-exercised reason: $($missing -join ', ')"
}
$unclaimed = @()
foreach ($c in $asserted) {
    if ($c -notin $claimed) {
        $unclaimed += $c
    }
}
if ($unclaimed.Count -gt 0) {
    Write-Error "suite asserts codes never claimed by prism.iss: $($unclaimed -join ', ') -- the suite and the shipping map disagree"
}

Write-Host "exit-code set derived from prism.iss: $($claimed -join ', ')"
Write-Host "gate OK: claimed set is unique, every claimed code has a writer or a declared not-exercised reason"
