# `prism compile` -- raw Atelier shape: status.errors is empty on success,
# populated on failure. The CLI exits 0 either way (errors are in JSON).

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "compile"

$fixtures = Get-FixturesDir

function Test-CompileSucceeded($r) {
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-HasProperty $data "status"
    if ($data.status.errors -and $data.status.errors.Count -gt 0) {
        throw "compile reported errors: $($data.status.errors | ConvertTo-Json -Compress)"
    }
}

Test-Case "compile single class" {
    $r = Invoke-Prism compile Test.MCPUtils.cls
    Test-CompileSucceeded $r
}

Test-Case "compile multiple classes" {
    $null = Invoke-Prism put-doc Test.MCPAddress.cls  (Join-Path $fixtures "Test.MCPAddress.cls")
    $null = Invoke-Prism put-doc Test.MCPEmployee.cls (Join-Path $fixtures "Test.MCPEmployee.cls")
    $r = Invoke-Prism compile Test.MCPAddress.cls Test.MCPEmployee.cls
    Test-CompileSucceeded $r
}

Test-Case "compile a routine" {
    $r = Invoke-Prism compile Test.MCPRoutine.mac
    Test-CompileSucceeded $r
}

Test-Case "compile with custom --flags" {
    $r = Invoke-Prism compile --flags ck Test.MCPUtils.cls
    Test-CompileSucceeded $r
}

Test-Case "compile with -n USER namespace" {
    $r = Invoke-Prism compile -n USER Test.MCPUtils.cls
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "compile non-existent class reports an error in JSON" {
    $r = Invoke-Prism compile Test.NoSuchClass99999.cls
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    $combined = $r.Stdout + $r.Stderr
    Assert-Match $combined "(?i)(not found|does not exist|error)"
}