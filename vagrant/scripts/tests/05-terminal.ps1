# `prism terminal` -- native irisnative ObjectScript execution.
#
# Note on quoting: PowerShell expands $ZVersion in double quotes, so we
# pass commands as single-quoted literals. Inner double quotes need
# backslash-escaping so they survive to the executable.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "terminal (native)"

Test-Case "Write 1+1 prints 2" {
    $r = Invoke-Prism terminal 'Write 1+1'
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "2"
}

Test-Case 'Write "hello" prints hello' {
    $r = Invoke-Prism terminal 'Write \"hello\"'
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "hello"
}

Test-Case 'Write $ZVersion returns IRIS version string' {
    $r = Invoke-Prism terminal 'Write $ZVersion'
    Assert-ExitCode 0 $r.ExitCode
    Assert-Match $r.Stdout "(IRIS|Cache)"
}

Test-Case "explicit -n USER works" {
    $r = Invoke-Prism terminal -n USER 'Write 42'
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "42"
}

Test-Case "-t 5 timeout is accepted" {
    $r = Invoke-Prism terminal -t 5 'Write 1'
    Assert-ExitCode 0 $r.ExitCode
}

Test-Case "syntax error in command is reported" {
    $r = Invoke-Prism terminal 'NotAValidCommand xxx'
    # Either non-zero exit or an error string in stdout -- IRIS may report
    # the error via the response body rather than a process error.
    $combined = $r.Stdout + " " + $r.Stderr
    Assert-True (
        ($r.ExitCode -ne 0) -or
        ($combined -match "(?i)(error|undefined|syntax)")
    ) "expected error indication for invalid command"
}