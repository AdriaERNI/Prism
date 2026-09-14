# prism-installer/test-help-contract.ps1 - covers RG-003
# The --help surface is the shipped product's public contract. When PR #27
# deleted 'prism terminal', the fixtures kept asserting it and CI stayed green
# while a shipped command had gone missing -- the drift was only visible once
# someone paid VM minutes to run the suite. This gate pins BOTH directions.
param(
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'test-help-contract.ps1',
    [string] $Baseline = 'fetch',
    [string] $Repo = '',
    [string] $SourceVersion = '',
    [string] $SuiteLogFile = ''
)
. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')
$script:SuiteLogFile = $SuiteLogFile

# The CONTRACT, deliberately literal: deriving the expected surface from the
# same binary under test would be a self-comparison that passes vacuously
# against a build that lost a command -- which is the exact defect class here.
$expected = @(
    'config', 'sql', 'ws', 'compile', 'get-doc', 'list-docs', 'put-doc',
    'delete-doc', 'info', 'test', 'list-tests', 'serve', 'setup', 'gui',
    'chatbot', 'monitor', 'cast'
)
# Removed by PR #27 and must STAY gone; its fixtures produced the 7 false
# failures reported as PASS in the 2026-09-06 rehearsal.
$mustNotAdvertise = @('terminal')

$exe = Join-Path $script:InstallRoot 'prism.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    $exe = Join-Path (Join-Path $ArtifactsPath 'prism') 'prism.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        Write-SuiteLine 'no prism binary available (test-install.ps1 must run first)' -Skip
        exit 0
    }
}

$help = (& $exe --help 2>&1) | Out-String
if ($LASTEXITCODE -ne 0) { Write-SuiteLine "RG-003 prism --help exited $LASTEXITCODE" -Fail; exit 1 }

# Measured 2026-09-07: Typer prints 'Usage: prism [OPTIONS] COMMAND [ARGS]...'
# and a 'Commands:' block with two-space-indented verbs; there is no
# 'Available Commands' heading (that is a Click 7 string). Match both spellings
# so the gate does not depend on one library layout.
$parsed = @()
foreach ($line in ($help -split "`r?`n")) {
    if ($line -match '^\s{2}(?<n>[a-z][a-z0-9-]+)\s{2,}\S') { $parsed += $matches['n'] }
}
$parsed = @($parsed | Sort-Object -Unique)
Assert-NonVacuous -What 'parsed --help command surface' -Count $parsed.Count -Minimum 5

$missing = @($expected | Where-Object { $parsed -notcontains $_ })
if ($missing.Count -gt 0) {
    Write-SuiteLine "RG-003 the shipped surface lost '$($missing -join ', ')' -- update the contract or restore the command" -Fail
    exit 1
}
foreach ($verb in $mustNotAdvertise) {
    if ($parsed -contains $verb) {
        Write-SuiteLine "RG-003 '$verb' is advertised but was removed by a shipped PR" -Fail
        exit 1
    }
}
$extra = @($parsed | Where-Object { $expected -notcontains $_ })
if ($extra.Count -gt 0) {
    Write-SuiteLine "RG-003 undeclared command(s) advertised: $($extra -join ', ') -- update the contract list" -Fail
    exit 1
}
Write-SuiteLine "all $($expected.Count) subcommands advertised, '$($mustNotAdvertise -join '/')' stays gone, no undeclared extras" -Pass
