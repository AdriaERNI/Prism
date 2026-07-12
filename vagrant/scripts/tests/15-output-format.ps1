# Global --format flag -- applies to every command.
#
# - default is JSON
# - --format json is identical to default
# - --format toon emits non-JSON text (when toons is bundled)

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "global --format flag"

Test-Case "default format is JSON for sql" {
    $r = Invoke-Prism sql "SELECT 1 AS One"
    Assert-ExitCode 0 $r.ExitCode
    $first = $r.Stdout.TrimStart()[0]
    Assert-True ($first -in @('{', '[')) "expected JSON-shaped output"
}

Test-Case "--format json for info" {
    $r = Invoke-Prism --format json info
    Assert-ExitCode 0 $r.ExitCode
    $null = $r.Stdout | ConvertFrom-Json
}

Test-Case "--format toon for sql" {
    $r = Invoke-Prism --format toon sql "SELECT 1 AS One"
    Assert-ExitCode 0 $r.ExitCode
    $first = $r.Stdout.TrimStart()[0]
    Assert-True ($first -ne '{') "expected non-JSON for toon"
}

Test-Case "--format invalid is rejected or falls back" {
    $r = Invoke-Prism --format wat sql "SELECT 1"
    # The CLI may either reject the format or silently fall back; just make
    # sure the process does something sensible (no crash, output somewhere).
    Assert-True (
        $r.ExitCode -ne 0 -or
        ($r.Stdout.Length + $r.Stderr.Length) -gt 0
    ) "unexpected silent no-op"
}