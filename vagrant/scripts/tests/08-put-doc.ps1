# `prism put-doc` -- upload .cls / .mac / .inc fixtures.
#
# Uploads but does not delete here; later tests (compile, get-doc) rely
# on the documents existing. Final cleanup happens in teardown-test-env.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "put-doc"

$fixtures = Get-FixturesDir

Test-Case "put-doc uploads a .cls file" {
    $path = Join-Path $fixtures "Test.MCPPerson.cls"
    Assert-True (Test-Path $path) "fixture missing: $path"
    $r = Invoke-Prism put-doc Test.MCPPerson.cls $path
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout '"status"'
}

Test-Case "put-doc uploads a .mac routine" {
    $path = Join-Path $fixtures "Test.MCPRoutine.mac"
    Assert-True (Test-Path $path) "fixture missing: $path"
    $r = Invoke-Prism put-doc Test.MCPRoutine.mac $path
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "put-doc uploads a .inc include" {
    $path = Join-Path $fixtures "Test.MCPHeader.inc"
    Assert-True (Test-Path $path) "fixture missing: $path"
    $r = Invoke-Prism put-doc Test.MCPHeader.inc $path
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "put-doc overwrites an existing document" {
    $path = Join-Path $fixtures "Test.MCPUtils.cls"
    Assert-True (Test-Path $path) "fixture missing: $path"
    $null = Invoke-Prism put-doc Test.MCPUtils.cls $path
    $r = Invoke-Prism put-doc Test.MCPUtils.cls $path
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "put-doc with explicit -n USER" {
    $path = Join-Path $fixtures "Test.MCPUtils.cls"
    $r = Invoke-Prism put-doc Test.MCPUtils.cls $path -n USER
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "put-doc with missing local file fails" {
    $r = Invoke-Prism put-doc Test.NoFile.cls "C:\does\not\exist.cls"
    Assert-True ($r.ExitCode -ne 0) "expected non-zero exit for missing file"
}