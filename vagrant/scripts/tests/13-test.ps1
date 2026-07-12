# `prism test` -- run a unit test class via the deployed runner.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "test (run unit tests)"

$fixtures = Get-FixturesDir

# Make sure the sample test class is on the server.
$null = Invoke-Prism put-doc Test.MCPSampleTest.cls (Join-Path $fixtures "Test.MCPSampleTest.cls")
$null = Invoke-Prism compile Test.MCPSampleTest.cls

Test-Case "run all methods in Test.MCPSampleTest" {
    $r = Invoke-Prism test Test.MCPSampleTest
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-True ($null -ne $data) "no JSON returned"
    Assert-Match ($r.Stdout) "(passed|success|methods|TestAddition|MCPSampleTest)"
}

Test-Case "run a single test method via -m" {
    $r = Invoke-Prism test Test.MCPSampleTest -m TestAddition
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "TestAddition"
}

Test-Case "run with explicit -n USER" {
    $r = Invoke-Prism test -n USER Test.MCPSampleTest
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "test on non-existent class is reported" {
    $r = Invoke-Prism test Test.DoesNotExist99999
    $combined = $r.Stdout + $r.Stderr
    Assert-Match $combined "(?i)(error|fail|not found|does not exist|invalid)"
}