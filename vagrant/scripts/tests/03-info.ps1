# `prism info` -- connect to IRIS and print server info as JSON.
#
# The CLI returns the raw Atelier response: { status, console, result.content }.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "info"

Test-Case "prism info returns JSON with namespaces" {
    $r = Invoke-Prism info
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-HasProperty $data "result"
    Assert-HasProperty $data.result "content"
    Assert-HasProperty $data.result.content "namespaces"
    $names = $data.result.content.namespaces -join ","
    Assert-Contains $names "USER" "USER namespace missing"
}

Test-Case "prism info reports a server version" {
    $r = Invoke-Prism info
    Assert-ExitCode 0 $r.ExitCode
    $data = $r.Stdout | ConvertFrom-Json
    Assert-HasProperty $data.result.content "version"
    Assert-Match $data.result.content.version "(IRIS|Cache)"
}

Test-Case "prism --format toon info renders TOON if bundled" {
    $r = Invoke-Prism --format toon info
    if ($r.ExitCode -ne 0) {
        # toons package not bundled in this build -- skip
        Assert-Match ($r.Stdout + $r.Stderr) "(toon|Traceback|RuntimeError)" "expected a clear failure if toon unavailable"
        return
    }
    $first = $r.Stdout.TrimStart()[0]
    Assert-True ($first -ne '{') "expected non-JSON output for --format toon"
}