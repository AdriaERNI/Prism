# prism-installer/test-runner-report.ps1 - RG-002 / RG-007 self-test
# Pre-flight gate: this file must go RED before anything else is trusted, because a
# gate that cannot fail is decoration. Three independent anti-vacuity checks, each of
# which would pass vacuously if its probe were stubbed out -- so each asserts on a
# property the probe had to EARN (a real exit code, a real line count).
#
# Child probes here use Start-Process -Wait -PassThru, NOT the '& exe' call operator:
# measured on the guest, the call-operator route leaves $LASTEXITCODE $null for both
# a clean and an aborted child, so a check built on it could not distinguish pass
# from fail -- precisely the un-failable gate this file exists to detect.
param(
    [string] $ArtifactsPath = '.',
    [string] $Name = 'test-runner-report.ps1',
    [string] $Baseline = 'fetch',
    [string] $Repo = '',
    [string] $SourceVersion = '',
    [string] $SuiteLogFile = ''
)
. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')
$script:SuiteLogFile = $SuiteLogFile

function Invoke-ChildProbe([string] $Target, [string[]] $ExtraArgs = @()) {
    # Returns @{ Code; Out } where Code is the child's exit code and Out its whole
    # console as one string. -Argument is a SINGLE string: an array binds onto the
    # child's first positional parameter instead of the named ones (measured).
    $argLine = '-NoProfile -ExecutionPolicy Bypass -NonInteractive -File ' + $Target
    if ($ExtraArgs.Count -gt 0) { $argLine += ' ' + ($ExtraArgs -join ' ') }
    # Start-Process -PassThru does not capture the child's console, so Out was a
    # stringification of the Process object and the gate's contract-message
    # assertion saw nothing (measured: "the failure did not surface the contract
    # message"). Redirect stdout/stderr to temp files and read them back.
    $id = [Guid]::NewGuid().ToString('N')
    $outFile = Join-Path ([IO.Path]::GetTempPath()) "prism-probe-$id.out.txt"
    $errFile = Join-Path ([IO.Path]::GetTempPath()) "prism-probe-$id.err.txt"
    $proc = Start-Process -FilePath 'powershell.exe' -Argument $argLine `
        -Wait -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    $out = ''
    if (Test-Path -LiteralPath $outFile -PathType Leaf) { $out += (Get-Content -LiteralPath $outFile -Raw) }
    if (Test-Path -LiteralPath $errFile -PathType Leaf) { $out += (Get-Content -LiteralPath $errFile -Raw) }
    Remove-Item -LiteralPath $outFile, $errFile -Force -ErrorAction SilentlyContinue
    return @{ Code = (Get-NormalizedExitCode $proc.ExitCode); Out = $out }
}

function Test-GateIsFailable {
    # A gate that accepts a known-bad check is not gating. The fixture asserts
    # 101 is in @(0): it MUST exit non-zero and MUST name the violated contract.
    $fixture = Join-Path (Join-Path $script:SuiteRoot 'tests') 'fixtures'
    $fx = Join-Path $fixture 'deliberately-broken.ps1'
    if (-not (Test-Path -LiteralPath $fx -PathType Leaf)) { throw "missing negative fixture $fx" }
    $r = Invoke-ChildProbe -Target $fx
    if ($r.Code -eq 0) { throw 'the gate accepted a known-bad check (exit 0) -- it is not gating' }
    if ($r.Out -notmatch 'contract violated') {
        throw "the failure did not surface the contract message: $($r.Out)"
    }
    Write-SuiteLine 'the gate detects a known-bad check' -Pass
}

function Test-TallyIsTruthful {
    # The shipped 2026-09-06 run: 7 [FAIL] lines reported as Failed: 0 / PASS.
    # The fixture is read here, never piped through run-all, so this check is
    # independent of the harness under test -- and Assert-NonVacuous pins that the
    # fixture really carries failures, else the comparison below proves nothing.
    $log = Join-Path (Join-Path (Join-Path $script:SuiteRoot 'tests') 'fixtures') 'false-green.log'
    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "missing fixture log $log" }
    $lines = Get-Content -LiteralPath $log
    $realFails = @($lines | Where-Object { $_ -match '^\s*\[FAIL\]' })
    $claimed   = @($lines | Where-Object { $_ -match 'Failed:\s+0\b' })
    Assert-NonVacuous -What 'false-green.log [FAIL] lines' -Count $realFails.Count -Minimum 1
    if ($realFails.Count -gt 0 -and $claimed.Count -gt 0) {
        throw "$($realFails.Count) real [FAIL] lines were reported as Failed: 0 -- the tally is untrustworthy (RG-002)"
    }
    Write-SuiteLine "tally is truthful for the log ($($realFails.Count) failures accounted for)" -Pass
}

function Test-EmptySuiteIsRefused {
    # The RG-007 class: discovering zero tests must never print PASS. Asserted on
    # the sentinel the RUNNER itself wrote plus the child's exit code, so a lost
    # console stream cannot flip this check into a vacuous pass OR a false alarm --
    # an unreadable run is treated as a refusal, which is the fail-safe direction.
    $runner = Join-Path $script:SuiteRoot 'run-installer-tests.ps1'
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw "missing runner $runner" }
    $probeLog = Join-Path (Join-Path $script:SuiteRoot 'tests') 'empty-suite-probe.log'
    if (Test-Path -LiteralPath $probeLog) { Remove-Item -LiteralPath $probeLog -Force }
    $r = Invoke-ChildProbe -Target $runner -ExtraArgs @('-Filter=nonexistent-*', ('-SuiteLogFile=' + $probeLog))
    $text = ''
    if (Test-Path -LiteralPath $probeLog) { $text = (Get-Content -LiteralPath $probeLog -Raw) }
    if ($text -match 'RUNNER_RESULT=PASS') { throw 'an empty suite reported PASS -- a vacuous green' }
    if ($r.Code -eq 0) { throw "an empty suite exited 0 instead of failing (code=$($r.Code))" }
    if ($text -notmatch 'RUNNER_RESULT=FAIL' -and $r.Out -notmatch 'RUNNER_RESULT=FAIL') {
        throw 'the empty-suite run produced no verdict at all -- a refusal must be explicit'
    }
    Write-SuiteLine 'an empty suite is refused, never a silent pass' -Pass
}

Test-GateIsFailable
Test-TallyIsTruthful
Test-EmptySuiteIsRefused
