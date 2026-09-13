# prism-installer/run-installer-tests.ps1
# Suite entry point: discovers test-*.ps1, runs each in its OWN process, and
# prints a truthful summary. It REFUSES to report PASS when the run tested
# nothing (the RG-007 false-green class).
#
# Rules, each measured on Windows PowerShell 5.1 on the pinned guest (the local
# shell is a different parser and proves nothing about the target):
#   * Classification reads the child's per-test SENTINEL LOG, written by the child
#     itself through Write-SuiteLine -> Add-Content (a plain file write). Nothing
#     depends on capturing the child's console: a lost or unredirectable stream
#     can only make a run look MORE suspicious, never greener.
#   * Exit code comes from Start-Process -Wait -PassThru. Measured 2026-09-07 on
#     the guest: that route reports 0 for a clean child and 1 for a child aborted
#     by a parse error, while the '& exe *> file' + '$LASTEXITCODE = $null' idiom
#     returns $null for BOTH -- which read as -1 here and would have turned every
#     test red, or green if defaulted. Do not 'simplify' back to that idiom.
#   * A clean exit with NO verdict line is a FAILURE, not a pass: a run that
#     recorded nothing tested nothing (RG-007), and 'tested nothing' never earns
#     a green in this suite.
#   * The suite root is shared with the library ($script:SuiteRoot), so runner and
#     children can never drift to different directories; that drift is exactly how
#     a suite reports green while testing nothing.
#   * Child paths are passed unquoted in one -Argument string (an array trips
#     PowerShell's positional binding). Keep them free of spaces; the guard below
#     rejects the call rather than launch a mis-parsed child.
param(
    [string] $Filter = '*',
    # Comma-separated EXCLUDE patterns. The deliberately-failing anti-vacuity probe
    # (test-runner-report.ps1 spawns a fixture meant to be red) must not ride the
    # main pass; CI passes it here. Discovery that ignored this would make the
    # suite permanently red on a file designed to fail, so it is honoured always.
    [string] $Not = '',
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'all-tests',
    # 'runner' = the caller (build job) already fetched the baseline;
    # 'fetch'  = test-prerelease.ps1 acquires it itself.
    [ValidateSet('runner', 'fetch')]
    [string] $Baseline = 'fetch',
    [string] $Repo = '',
    [string] $SourceVersion = '',
    [switch] $Continue,
    [switch] $SkipSetup
)

# $ErrorActionPreference is the real automatic variable; the doubled suffix made this
# a plain custom variable that PowerShell never reads, so strict mode silently never
# engaged and the run reported results it had not actually guarded.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')

# An unexpanded '${{ ... }}' placeholder must never reach gh as a repo name --
# that literal-brace no-op is RG-012's root cause, so reject the shape here.
function Test-Real([string] $v) {
    return (-not [string]::IsNullOrWhiteSpace($v)) -and ($v -notmatch '\$\{') -and ($v -notmatch '^\{\{')
}
if (-not (Test-Real $Repo)) {
    foreach ($cand in @($env:GITHUB_REPOSITORY, $env:GH_REPO)) {
        if (Test-Real $cand) { $Repo = $cand; break }
    }
}
if (-not (Test-Real $SourceVersion)) {
    foreach ($cand in @($env:PRISM_SOURCE_VERSION)) {
        if (Test-Real $cand) { $SourceVersion = $cand; break }
    }
    if (-not (Test-Real $SourceVersion)) {
        try { $SourceVersion = Get-SourceVersion -ProjectRoot (Split-Path $PSScriptRoot -Parent) } catch { }
    }
}

# Deterministic execution order. The runtime scenarios depend on each other
# (install before help-contract, everything before uninstall). Left to
# alphabetical discovery, test-help-contract would run BEFORE test-install and
# skip vacuously with no binary on disk, so the RG-003 gate could never fire.
# Discovery still governs MEMBERSHIP; names not listed here run after, sorted.
$orderedNames = @(
    # Baseline FIRST: test-upgrade-matrix reads dist\prism-old-setup.exe, and an
    # unacquired baseline would make the matrix skip -- a zero-scenario 'pass'
    # is the vacuous-green class this suite exists to kill.
    'test-prerelease.ps1',
    'test-install.ps1',
    'test-upgrade-matrix.ps1',
    'test-help-contract.ps1',
    'test-exit-code-contract.ps1',
    'test-future-version.ps1',
    'test-downgrade.ps1',
    'test-runner-report.ps1',
    'test-uninstall.ps1'
)
$discovered = @(Get-ChildItem -Path $PSScriptRoot -Filter 'test-*.ps1' -File -Force |
                Where-Object { $_.Name -notlike '*.bak*' } |
                Where-Object {
                    # Match the file NAME and the BASE NAME, and accept a comma list.
                    # BaseName drops '.ps1', so a filter written 'test-foo.ps1' -- which is
                    # exactly what CI, the plan and the docs all pass -- matched NOTHING
                    # under a BaseName-only test, and the whole suite collapsed to 'no test
                    # files matched'. A run that discovers nothing must never look clean.
                    $patterns = @($Filter -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
                    if ($patterns.Count -eq 0) { $patterns = @('*') }
                    $n = $_.Name
                    $b = $_.BaseName
                    @(foreach ($p in $patterns) {
                        if (($n -like $p) -or ($b -like $p) -or ($n -like ($p + '.ps1')) -or ($b -like ($p -replace '\.ps1$', ''))) { $p }
                    }).Count -gt 0
                })
$have = @($discovered | ForEach-Object { $_.Name })
if (-not [string]::IsNullOrWhiteSpace($Not)) {
    $exc = @($Not -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($exc.Count -gt 0) {
        $before = $have.Count
        $have = @($have | Where-Object { $n = $_; @($exc | Where-Object { $n -like $_ }).Count -eq 0 })
        # An exclusion that removes nothing usually means the pattern did not match any
        # discovered name -- say so, because a silently-ignored -Not is how a designed
        # to fail file ends up back in the pass and CI goes red for the wrong reason.
        if ($have.Count -eq $before) { Write-Output "##[WARN] -Not matched nothing to exclude: $($exc -join ', ')" }
    }
}
$listed = @($orderedNames | Where-Object { $have -contains $_ })
$rest   = @($have | Where-Object { $orderedNames -notcontains $_ } | Sort-Object)
$tests  = @($listed + $rest)

# An empty suite is a failure, never a silent green (RG-007).
if ($tests.Count -eq 0) {
    Write-Output "RESULT: FAIL - no test files matched filter '$Filter'"
    Write-Output 'RUNNER_RESULT=FAIL'
    exit 1
}

# One shared run directory per suite run, like a platform cache. Per-test
# New-TempDir cleans only its own temp-<name> child and never this parent, so a
# sibling cannot be deleted under an in-flight run.
$runDir = Join-Path $script:SuiteRoot ('tests\temp-' + ($Name -replace '[^A-Za-z0-9._-]', '_'))
if (Test-Path -LiteralPath $runDir) { Remove-Item -LiteralPath $runDir -Recurse -Force }
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
if ($SkipSetup) {
    $shared = Join-Path $runDir 'setup-notes'
    if (-not (Test-Path -LiteralPath $shared)) { New-Item -ItemType Directory -Path $shared -Force | Out-Null }
}
$sentinel = Join-Path $runDir 'runner-result.log'

$resolvedArt = (Get-AbsPath $ArtifactsPath -ErrorAction SilentlyContinue)
if ([string]::IsNullOrWhiteSpace($resolvedArt)) { $resolvedArt = $ArtifactsPath }
# The child command line is unquoted; a space would split it into two arguments and
# the child would die on a bogus path. Fail loudly here rather than launch that.
if ($resolvedArt -match '\s') { throw "-ArtifactsPath contains a space ('$resolvedArt'): the child invocation is unquoted; use a space-free path" }

$total = 0; $passed = 0; $failed = 0; $skipped = 0; $failures = @()
foreach ($name in $tests) {
    # With Baseline=runner the build job ran acquisition and uploaded the artifact;
    # re-fetching would only burn quota. The upgrade matrix then HARD-FAILS on a
    # missing baseline instead of skipping, so dropping the fetch cannot smuggle a
    # zero-scenario pass through.
    if ($Baseline -eq 'runner' -and $name -eq 'test-prerelease.ps1') {
        Write-Output "##[SKIP] $name (baseline supplied by the build job)"
        continue
    }
    $total++
    # Each file runs in its own process so no helper can reset another file's
    # tally -- the defect behind the false-green run-all.ps1 (RG-002).
    $tLog = Join-Path $runDir ($name + '.log')
    if (Test-Path -LiteralPath $tLog) { Remove-Item -LiteralPath $tLog -Force }
    $child = Join-Path $PSScriptRoot $name
    if ($child -match '\s') { throw "child path contains a space ('$child'); the unquoted child invocation would break" }
    $childArgs = @(
        ('-ArtifactsPath=' + $resolvedArt),
        ('-Name=' + $name),
        ('-Baseline=' + $Baseline),
        ('-SourceVersion=' + $SourceVersion),
        ('-SuiteLogFile=' + $tLog)
    )
    if (Test-Real $Repo) { $childArgs += ('-Repo=' + $Repo) }
    # Launch through the trampoline, which runs the child, appends its console to
    # the SAME log the child's own Write-SuiteLine verdicts went to, and re-exits
    # with the child's code. Start-Process -Wait -PassThru is the one route that
    # reported the code reliably for a parse-abort AND a clean run on 5.1 (the '&
    # *>' idiom returned $null for both). Classification therefore reads the UNION
    # of the sentinel lines the child wrote and the console the trampoline captured
    # -- stream-independent, so a lost console can only make a run look worse.
    $tramp = Join-Path $PSScriptRoot '_invoke-child.ps1'
    $proc = Start-Process -FilePath 'powershell.exe' `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -File ' + $tramp + ' -Target ' + $child + ' -Log ' + $tLog + ' -ChildArgs "' + ($childArgs -join ' ') + '"') `
        -Wait -PassThru -WindowStyle Hidden
    # Raw, deliberately NOT Get-NormalizedExitCode: that helper is for installer
    # re-installs and maps 100 -> 0, which for a CHILD would launder a real
    # failure into a pass. An unreadable code is forced negative so it can only
    # ever read as worse, never as success.
    $code = if ($null -eq $proc.ExitCode) { -1 } else { [int]$proc.ExitCode }
    $out = ''
    if (Test-Path -LiteralPath $tLog) { $out = (Get-Content -LiteralPath $tLog -Raw) }

    # Classification. The exit code is always authoritative for failure: a nonzero
    # exit is a failure whatever the log claims, so a missing log can only ever
    # make a run look worse, never better. Only on a clean exit do the sentinel
    # lines decide pass vs skip, and a clean exit with no verdict line at all is a
    # failure -- an incomplete run must not be read as a pass.
    if ($code -ne 0) {
        $failed++; $failures += "[$name] exited $code"
        Write-Output "##[FAIL] $name (exit $code)"
    } elseif ($out -match '##\[FAIL\]') {
        $failed++; $failures += "[$name] reported ##[FAIL] while exiting 0"
        Write-Output "##[FAIL] $name (exit 0 but the log reports a failure)"
    } elseif ($out -notmatch '##\[SKIP\]|\[PASS\]') {
        $failed++; $failures += "[$name] exited 0 but recorded no verdict line -- an incomplete run is not a pass"
        Write-Output "##[FAIL] $name (no verdict recorded)"
    } elseif ($out -match '##\[SKIP\]' -and $out -notmatch '\[PASS\]') {
        $skipped++
        $why = @($out -split "`n" | Where-Object { $_ -match '##\[SKIP\]' })
        Write-Output ("##[SKIP] {0} -- {1}" -f $name, ($why -join ' | '))
    } else {
        $passed++
        Write-Output "##[PASS] $name"
    }
    # Echo the scenario's own lines: they are the post-mortem evidence, and the
    # installer log paths in them are what a human opens next.
    foreach ($line in ($out -split "`r?`n")) { if ($line -ne '') { Write-Output ('    ' + $line) } }
    Add-Content -LiteralPath $sentinel -Value ('{0} :: exit {1}' -f $name, $code) -Encoding utf8
    if ($failed -gt 0 -and -not $Continue) { break }
}

Write-Output ('TOTAL: {0} (passed {1}, failed {2}, skipped {3})' -f $total, $passed, $failed, $skipped)
$failures | ForEach-Object { Write-Output ('  - ' + $_) }

# The gate: a run that tested nothing, or reported any failure, is FAIL.
if ($total -eq 0 -or $failed -gt 0) {
    Write-Output 'RESULT: FAIL'
    Add-Content -LiteralPath $sentinel -Value 'RUNNER_RESULT=FAIL' -Encoding utf8
    Write-Output 'RUNNER_RESULT=FAIL'
    exit 1
}
# Anti-vacuity self-check: the headline may claim PASS only when it agrees with the
# independent per-test classification. A disagreement means one side is lying, and
# the gate goes RED on the mismatch rather than green.
if (-not (($passed -gt 0) -and (($passed + $skipped) -eq $total))) {
    Write-Output ('RESULT: FAIL - outcome self-check cannot support PASS (passed={0} failed={1} skipped={2} total={3})' -f `
        $passed, $failed, $skipped, $total)
    Add-Content -LiteralPath $sentinel -Value 'RUNNER_RESULT=FAIL' -Encoding utf8
    Write-Output 'RUNNER_RESULT=FAIL'
    exit 1
}
Write-Output ('RESULT: PASS ({0} passed, {1} skipped)' -f $passed, $skipped)
Add-Content -LiteralPath $sentinel -Value ('RUNNER_RESULT=PASS tested=' + $total) -Encoding utf8
Write-Output 'RUNNER_RESULT=PASS'
exit 0
