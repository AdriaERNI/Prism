# `prism get-doc` -- raw Atelier shape: result.content is the file body
# (lines), result.name / cat / etc. are metadata.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "get-doc"

Test-Case "get-doc returns content for an uploaded class" {
    $r = Invoke-Prism get-doc Test.MCPUtils.cls
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "MCPUtils"
    Assert-Contains $r.Stdout "Greet"
}

Test-Case "get-doc on a routine returns ROUTINE header" {
    $r = Invoke-Prism get-doc Test.MCPRoutine.mac
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "MCPRoutine"
}

Test-Case "get-doc with -n USER" {
    $r = Invoke-Prism get-doc Test.MCPUtils.cls -n USER
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "get-doc on a non-existent doc fails" {
    $r = Invoke-Prism get-doc Test.NoSuchDoc999.cls
    # API raises DocumentNotFound -> CLI exits 1 with "Document not found" stderr.
    Assert-True ($r.ExitCode -ne 0) "expected non-zero exit for missing doc"
    Assert-Match ($r.Stdout + $r.Stderr) "(?i)(not found|404)"
}