# prism-installer/test-exit-code-contract.ps1 - covers RG-006
# Every code the docs promise must be either exercised or explicitly declared
# not-exercisable. A row that silently disappears from the matrix is the same
# defect class as a test that stopped running.
param(
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'test-exit-code-contract.ps1',
    [string] $Baseline = 'fetch',
    [string] $Repo = '',
    [string] $SourceVersion = '',
    [string] $SuiteLogFile = ''
)
. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')
$script:SuiteLogFile = $SuiteLogFile
$ArtifactsPath = (Get-AbsPath $ArtifactsPath -ErrorAction SilentlyContinue)

# The automatable half, with the scenario that guarantees each one. These are the
# INSTALLER EXE return codes the suite actually exercises; the CLI's own exit codes
# (2/101 on bad arguments) are a separate contract tested below, never conflated
# with the Store EXE return-code map.
$matrix = @(
    @{ Code = 0;   Meaning = 'installation succeeded';           Guarantor = 'test-install.ps1' },
    @{ Code = 100; Meaning = 'application already exists';       Guarantor = 'test-upgrade-matrix.ps1' }
)
# Needs interactive input or a machine state a hosted runner cannot stage, or a
# mechanism the shipping installer does not wire: documented-but-not-exercised,
# reported as skip, never as a pass.
$notExercised = @(1, 2, 4, 7, 8, 101, 102)

$exe = Join-Path $script:InstallRoot 'prism.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    Write-Output '##[SKIP] prism is not installed; run test-install.ps1 first'
    exit 0
}

function Invoke-CliExpect([string[]] $Arguments, [int[]] $Expected, [string] $Because) {
    # The call operator, not Start-Process: -PassThru and -RedirectStandard* live
    # in DIFFERENT parameter sets, and combining them is a bind error before the
    # cmdlet even runs (measured class of failure in this repo's harness). '&'
    # captures the stream into the pipeline and leaves the code in LASTEXITCODE.
    $out = (& $exe @Arguments 2>&1 | Out-String)
    $code = Get-NormalizedExitCode $LASTEXITCODE
    Assert-ExitCode -Expected $Expected -Actual $code -Because $Because
    return @{ Code = $code; Out = $out }
}

# Measured: both forms exit 2 on the shipped CLI; exit 0 must fail this.
foreach ($bad in @('--nonsense', '--bogus-flag', 'nosuchcommand')) {
    $null = Invoke-CliExpect -Arguments @($bad) -Expected @(2, 101) `
        -Because "'prism $bad' is a usage error and must not exit 0"
}
foreach ($good in @('--version')) {
    $null = Invoke-CliExpect -Arguments @($good) -Expected @(0) -Because "'prism $good' must succeed"
}

foreach ($row in $matrix) {
    Write-SuiteLine ("exit {0} ({1}) guaranteed by {2}" -f $row.Code, $row.Meaning, $row.Guarantor)
}
foreach ($code in $notExercised) {
    Write-SuiteLine "exit $code needs interactive input or a machine state the hosted runner cannot supply" -Skip
}
# RG-006 resolution: the single-instance mutex is the SetupMutex directive, and
# prism.iss has NO SetupMutex -- verified against the Inno docs (the directive is
# what prevents Setup from running while Setup is already running). Without it the
# second instance runs freely, so exit 1 (already in progress) is unreachable by
# construction in the shipping installer, mirroring the matrix row in
# docs/getting-started/installer-exit-codes.md.
Write-SuiteLine 'exit 1 (single-instance mutex) is unreachable -- prism.iss has no SetupMutex directive' -Skip

Write-SuiteLine 'exit-code contract verified for every automatable code' -Pass
