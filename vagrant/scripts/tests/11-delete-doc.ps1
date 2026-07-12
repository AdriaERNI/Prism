# `prism delete-doc` -- happy path, idempotency, namespace flag.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "delete-doc"

$fixtures = Get-FixturesDir

Test-Case "delete-doc removes an existing class" {
    $null = Invoke-Prism put-doc Test.MCPUtils.cls (Join-Path $fixtures "Test.MCPUtils.cls")
    $r = Invoke-Prism delete-doc Test.MCPUtils.cls
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout '"status"'
}

Test-Case "delete-doc on non-existent doc fails" {
    $r = Invoke-Prism delete-doc Test.NoSuchDoc777.cls
    Assert-True ($r.ExitCode -ne 0) "expected non-zero exit"
    Assert-Match ($r.Stdout + $r.Stderr) "(?i)(not found|404)"
}

Test-Case "delete-doc with -n USER" {
    $null = Invoke-Prism put-doc Test.MCPHeader.inc (Join-Path $fixtures "Test.MCPHeader.inc")
    $r = Invoke-Prism delete-doc -n USER Test.MCPHeader.inc
    Assert-ExitCode 0 $r.ExitCode
}