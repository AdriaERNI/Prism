# Best-effort cleanup: wipe config, drop test docs, clear test SQL data.

[CmdletBinding()] param()

$ErrorActionPreference = "Continue"   # never fail teardown

. "$PSScriptRoot\_common.ps1"

Write-Section "Teardown"

$testDocs = @(
    "Test.MCPPerson.cls",
    "Test.MCPUtils.cls",
    "Test.MCPAddress.cls",
    "Test.MCPEmployee.cls",
    "Test.MCPRoutine.mac",
    "Test.MCPHeader.inc",
    "Test.MCPSampleTest.cls",
    "Test.MCPFailingTest.cls",
    "Test.MCPBgHelper.cls"
)
foreach ($doc in $testDocs) {
    $null = Invoke-Prism delete-doc $doc 2>$null
}
Write-Host "  Cleared test documents."

# Drop SQL data left over from end-to-end SQL tests.
$null = Invoke-Prism sql "DELETE FROM Test.MCPPerson"   2>$null
$null = Invoke-Prism sql "DELETE FROM Test.MCPEmployee" 2>$null

# Reset config last so config tests can be re-run cleanly.
$null = Invoke-Prism config --reset-all
Write-Host "  Reset config.json."

Write-Host "Teardown OK." -ForegroundColor Green