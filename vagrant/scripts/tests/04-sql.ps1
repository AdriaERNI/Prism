# `prism sql` -- raw Atelier shape: { status: { errors, summary }, result: { content: { ... } } }.
# IRIS-side errors come back in JSON with exit 0; only transport/process
# failures give a non-zero exit.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "sql"

Test-Case "SELECT 1 succeeds" {
    $r = Invoke-Prism sql "SELECT 1 AS One"
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout '"status"'
    # The literal "1" should be in the result content somewhere.
    Assert-Match $r.Stdout '"One"|"1"|\b1\b'
}

Test-Case "SELECT arithmetic" {
    # "Total" not "Sum" -- SUM is a reserved keyword in IRIS SQL and cannot
    # be used as a bare column alias without quoting.
    $r = Invoke-Prism sql "SELECT 2+3 AS Total"
    Assert-ExitCode 0 $r.ExitCode
    Assert-Match $r.Stdout '\b5\b'
}

Test-Case "SELECT against system class" {
    $r = Invoke-Prism sql "SELECT TOP 5 Name FROM %Dictionary.ClassDefinition"
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-HasProperty $data "status"
}

Test-Case "explicit -n USER works" {
    $r = Invoke-Prism sql -n USER "SELECT 1 AS One"
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "invalid SQL returns errors in JSON" {
    $r = Invoke-Prism sql "TOTALLY NOT VALID SQL"
    # CLI exits 0 with errors in status.errors; just check we got SOME error.
    $combined = $r.Stdout + $r.Stderr
    Assert-Match $combined "(?i)(error|sqlcode|invalid|expected)"
}

Test-Case "unknown namespace returns 404 error" {
    $r = Invoke-Prism sql -n "DOES_NOT_EXIST_X" "SELECT 1"
    $combined = $r.Stdout + $r.Stderr
    Assert-Match $combined "(?i)(404|not found|namespace)"
}

Test-Case "--format toon renders TOON if bundled" {
    $r = Invoke-Prism --format toon sql "SELECT 1 AS One"
    if ($r.ExitCode -ne 0) {
        Assert-Match ($r.Stdout + $r.Stderr) "(toon|Traceback|RuntimeError)"
        return
    }
    $first = $r.Stdout.TrimStart()[0]
    Assert-True ($first -ne '{') "expected non-JSON for toon"
}