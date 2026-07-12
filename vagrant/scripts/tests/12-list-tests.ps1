# `prism list-tests` -- discovery of %UnitTest.TestCase classes.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "list-tests"

$fixtures = Get-FixturesDir

Test-Case "list-tests returns JSON" {
    $r = Invoke-Prism list-tests
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-True ($null -ne $data) "list-tests produced no JSON"
}

Test-Case "list-tests sees an uploaded test class" {
    $null = Invoke-Prism put-doc Test.MCPSampleTest.cls (Join-Path $fixtures "Test.MCPSampleTest.cls")
    $null = Invoke-Prism compile Test.MCPSampleTest.cls

    $r = Invoke-Prism list-tests -f Test.MCP
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "MCPSampleTest"
}

Test-Case "list-tests -f filter narrows results" {
    $r = Invoke-Prism list-tests -f Test.MCPSampleTest
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "MCPSampleTest"
}

Test-Case "list-tests -n USER" {
    $r = Invoke-Prism list-tests -n USER -f Test.MCP
    Assert-ExitCode 0 $r.ExitCode
}