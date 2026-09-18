# prism-installer/_invoke-child.ps1
# Trampoline that runs ONE scenario as a child powershell.exe and lands its whole
# console output in a log file, then re-exits with the child's code.
#
# Why a trampoline instead of launching the child directly with a file redirect:
# measured on Windows PowerShell 5.1 on the pinned guest, `& powershell.exe ... *> log`
# leaves $LASTEXITCODE $null (so a parse-abort and a clean run both read as no-code),
# while `2>&1` capture into a variable and reading $LASTEXITCODE immediately does
# report 0 vs 1 correctly. So capture to a variable first, then write the file --
# the order is the whole reason this file exists; do not 'simplify' it into one line.
param(
    [Parameter(Mandatory = $true)][string] $Target,
    [Parameter(Mandatory = $true)][string] $Log,
    [string] $ChildArgs = ''
)
$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
    Set-Content -LiteralPath $Log -Value "##[FAIL] child target does not exist: $Target"
    exit 1
}
# -File's argument must be a single string; an array binds positionally onto the
# child's first positional parameter instead of onto the named ones (measured class
# of bug in this repo's harness).
$argv = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NonInteractive', '-File', $Target)
if ($ChildArgs -match '\S') { $argv += ($ChildArgs -split '\s+') }
$merged = & powershell.exe @argv 2>&1
# The console copy is the diagnostic half of the pair the runner reads; the
# scenario's own Write-SuiteLine calls have already appended the authoritative
# verdict lines to the same file, so append (--not overwrite) to keep both.
foreach ($line in @($merged)) { Add-Content -LiteralPath $Log -Value ([string]$line) -Encoding utf8 }
# The runner reads this process's exit code, so it is reduced to a BINARY contract
# here on purpose: 0 = the child reported clean, 1 = anything else, INCLUDING an
# unreadable $LASTEXITCODE. Two reasons. (1) An unreadable code must read as a
# failure, never as a silent success -- fail-safe is the only safe direction.
# (2) Forwarding the child's raw code risks values that do not survive the
# [int32] marshaling of Process.ExitCode (negative codes become 4-billion-scale
# unsigned), which is noise the classification does not need: a child is either
# clean or it is not, and the detail lives in the log anyway.
$raw = $LASTEXITCODE
if ($null -eq $raw) { exit 1 }
if ([int]$raw -eq 0) { exit 0 }
exit 1
