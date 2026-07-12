# `prism list-docs` -- raw Atelier shape: result.content is an array of
# { name, cat, ts, upd, db, gen } entries.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "list-docs"

Test-Case "list-docs unfiltered" {
    $r = Invoke-Prism list-docs
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-HasProperty $data.result "content"
    Assert-True ($data.result.content.Count -gt 0) "expected at least one document"
}

Test-Case "list-docs -t cls" {
    $r = Invoke-Prism list-docs -t cls
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    $hasCls = $false
    foreach ($d in $data.result.content) {
        if ($d.name -match "\.cls$") { $hasCls = $true; break }
    }
    Assert-True $hasCls "no .cls in cls-filtered list"
}

Test-Case "list-docs -t mac succeeds" {
    $r = Invoke-Prism list-docs -t mac
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-HasProperty $data.result "content"
}

Test-Case "list-docs -f % finds % namespace docs" {
    $r = Invoke-Prism list-docs -f "%"
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-True ($data.result.content.Count -gt 0) "expected % docs in USER namespace"
}

Test-Case "list-docs --generated includes generated docs" {
    $r = Invoke-Prism list-docs --generated
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "explicit -n USER" {
    $r = Invoke-Prism list-docs -n USER -t cls
    Assert-ExitCode 0 $r.ExitCode
}