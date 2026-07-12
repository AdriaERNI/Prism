# Verify --help works on the top-level CLI and on every subcommand.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "help"

Test-Case "prism --help lists all 13 subcommands" {
    $r = Invoke-Prism --help
    Assert-ExitCode 0 $r.ExitCode
    foreach ($cmd in @(
        "config","sql","terminal","ws","compile","get-doc","list-docs",
        "put-doc","delete-doc","info","test","list-tests","serve"
    )) {
        Assert-Contains $r.Stdout $cmd "missing subcommand '$cmd' in help"
    }
}

foreach ($sub in @(
    "config","sql","terminal","ws","compile",
    "get-doc","list-docs","put-doc","delete-doc",
    "info","test","list-tests","serve"
)) {
    $cmdName = $sub
    Test-Case "prism $cmdName --help" {
        $r = Invoke-Prism $cmdName --help
        Assert-ExitCode 0 $r.ExitCode
        # Typer help always echoes the command name in the Usage line.
        Assert-Contains $r.Stdout "Usage" "$cmdName --help has no Usage line"
    }
}