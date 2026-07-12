# `prism ws` -- WebSocket terminal backend; same shape as `terminal`.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "ws (websocket terminal)"

Test-Case "Write 1+1 prints 2 over websocket" {
    $r = Invoke-Prism ws 'Write 1+1'
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "2"
}

Test-Case 'Write "hello" prints hello' {
    $r = Invoke-Prism ws 'Write \"hello\"'
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "hello"
}

Test-Case "explicit namespace USER" {
    $r = Invoke-Prism ws -n USER 'Write 7'
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "7"
}

Test-Case "timeout flag accepted" {
    $r = Invoke-Prism ws -t 10 'Write 1'
    Assert-ExitCode 0 $r.ExitCode
}