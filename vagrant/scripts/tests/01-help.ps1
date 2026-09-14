# Verify --help works on the top-level CLI and on every subcommand.
#
# The subcommand list must mirror what `prism --help` actually advertises.
# It previously listed the `terminal` command that PR #27 removed (native /
# SuperServer terminal dropped in favour of the WebSocket `ws` command) and,
# because it only asserted a *subset* of commands, it silently kept passing
# while a shipped command went missing. Keep this list in sync with
# `src/prism/cli/app.py` -- adding a command here is the regression guard.

. "$PSScriptRoot\..\_common.ps1"

# Ground truth: the commands `prism --help` lists (src/prism/cli/app.py).
$script:ExpectedCommands = @(
    "config", "sql", "ws", "compile", "get-doc", "list-docs",
    "put-doc", "delete-doc", "info", "test", "list-tests", "serve",
    "setup", "gui", "chatbot", "monitor", "cast"
)

Begin-Suite "help"

Test-Case "prism --help lists all $($script:ExpectedCommands.Count) subcommands" {
    $r = Invoke-Prism --help
    Assert-ExitCode 0 $r.ExitCode
    foreach ($cmd in $script:ExpectedCommands) {
        Assert-Contains $r.Stdout $cmd "missing subcommand '$cmd' in help"
    }
}

Test-Case "prism --help no longer advertises the removed 'terminal' command" {
    # PR #27 removed the native terminal; `ws` is the ObjectScript surface.
    $r = Invoke-Prism --help
    Assert-ExitCode 0 $r.ExitCode
    # Match the command column, not incidental prose mentioning 'terminal'.
    Assert-True ($r.Stdout -notmatch '(?m)^\s{2}terminal\s') `
        "'terminal' must not appear as a subcommand (removed in #27)"
}

foreach ($sub in $script:ExpectedCommands) {
    $cmdName = $sub
    Test-Case "prism $cmdName --help" {
        $r = Invoke-Prism $cmdName --help
        Assert-ExitCode 0 $r.ExitCode
        # Typer help always echoes the command name in the Usage line.
        Assert-Contains $r.Stdout "Usage" "$cmdName --help has no Usage line"
    }
}
