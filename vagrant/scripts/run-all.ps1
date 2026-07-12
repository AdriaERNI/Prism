# Run every test/*.ps1 file in alphabetical order and emit a summary.
# Exits 0 on full pass, 1 on any failure.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\run-all.ps1
#   powershell -ExecutionPolicy Bypass -File run-all.ps1 -Filter "*sql*"

[CmdletBinding()]
param(
    [string] $Filter = "*",
    [switch] $SkipSetup
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_common.ps1"

Refresh-Path

if (-not $SkipSetup) {
    & "$PSScriptRoot\setup-test-env.ps1"
}

$testsDir = Join-Path $PSScriptRoot "tests"
if (-not (Test-Path $testsDir)) {
    throw "No tests directory at $testsDir"
}

$files = Get-ChildItem -Path $testsDir -Filter "*.ps1" |
         Where-Object { $_.Name -like $Filter } |
         Sort-Object Name

if (-not $files) {
    throw "No test files found matching '$Filter' in $testsDir"
}

Write-Host ""
Write-Host "Running $($files.Count) test file(s)..." -ForegroundColor Cyan

foreach ($f in $files) {
    try {
        . $f.FullName
    } catch {
        $script:TestsTotal++
        $script:TestsFailed++
        $script:Failures += "[$($f.Name)] crashed: $($_.Exception.Message)"
        Write-Fail "Test file $($f.Name) crashed: $($_.Exception.Message)"
    }
}

# Always run teardown; do not let a teardown failure mask test failures.
try {
    & "$PSScriptRoot\teardown-test-env.ps1"
} catch {
    Write-Host "Teardown failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-FinalReport

# Sentinel for the bash runner to detect pass/fail unambiguously
# (vagrant winrm does not always propagate inner exit codes).
if ($script:TestsFailed -eq 0) {
    Write-Host "RUNALL_RESULT=PASS"
} else {
    Write-Host "RUNALL_RESULT=FAIL"
}
exit (Get-ExitCodeFromResults)