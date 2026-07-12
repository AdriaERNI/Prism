# Shared helpers for prism integration test scripts.
# Dot-source this file from each test:  . "$PSScriptRoot\..\_common.ps1"

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

# --- State ----------------------------------------------------------
$script:TestsTotal  = 0
$script:TestsPassed = 0
$script:TestsFailed = 0
$script:Failures    = @()
$script:CurrentSuite = "(unset)"

# --- Paths ----------------------------------------------------------
function Get-PrismRoot {
    # The runner extracts the bundle to C:\prism-tests
    if (Test-Path "C:\prism-tests\scripts") { return "C:\prism-tests" }
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-FixturesDir {
    return (Join-Path (Get-PrismRoot) "fixtures")
}

function Get-PrismExe {
    # Prefer the installed copy in Program Files, fall back to PATH.
    $installed = "C:\Program Files\prism\prism.exe"
    if (Test-Path $installed) { return $installed }

    $cmd = Get-Command prism.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    throw "prism.exe not found -- is the installer installed and PATH refreshed?"
}

# --- Output helpers -------------------------------------------------
function Write-Section($text) {
    Write-Host ""
    Write-Host "=== $text ===" -ForegroundColor Cyan
}

function Write-Pass($text) {
    Write-Host "  [PASS] $text" -ForegroundColor Green
}

function Write-Fail($text) {
    Write-Host "  [FAIL] $text" -ForegroundColor Red
}

function Write-Info($text) {
    Write-Host "         $text" -ForegroundColor DarkGray
}

# --- Test framework -------------------------------------------------
function Begin-Suite($name) {
    $script:CurrentSuite = $name
    Write-Section $name
}

function Test-Case {
    param(
        [Parameter(Mandatory)] [string]    $Name,
        [Parameter(Mandatory)] [scriptblock] $Body
    )
    $script:TestsTotal++
    try {
        & $Body
        $script:TestsPassed++
        Write-Pass $Name
    } catch {
        $script:TestsFailed++
        $script:Failures += "[$script:CurrentSuite] $Name :: $($_.Exception.Message)"
        Write-Fail "$Name"
        Write-Info $_.Exception.Message
        if ($script:LastPrismOutput) {
            Write-Info "stdout: $($script:LastPrismOutput -replace "`r?`n", ' / ')"
        }
        if ($script:LastPrismError) {
            Write-Info "stderr: $($script:LastPrismError -replace "`r?`n", ' / ')"
        }
    }
}

# --- prism wrapper --------------------------------------------------
# Runs the installed prism.exe, capturing stdout, stderr and exit code.
# Uses the call operator (&) with array splatting because Start-Process
# -ArgumentList does not reliably escape inner quotes for native exes.
# Returns a [pscustomobject] with .Stdout .Stderr .ExitCode .
# Default per-call timeout (seconds). prism calls should return in well under
# this; if one hangs (e.g. orphaned `prism serve` holding IRIS connections),
# fail the test fast instead of wedging the whole suite behind WinRM.
if (-not $script:PrismTimeoutSec) { $script:PrismTimeoutSec = 120 }

function Invoke-Prism {
    # Simple (non-advanced) function: no [CmdletBinding], no [Parameter()]
    # attributes, so PowerShell does not inject common params like
    # -WarningAction/-WarningVariable. Otherwise -w would be ambiguous when
    # we pass `prism config -w ...`. We use the automatic $args variable.
    if ($args.Count -eq 0) { throw "Invoke-Prism: no arguments given" }
    $Arguments  = @($args | ForEach-Object { "$_" })
    $exe        = Get-PrismExe
    $stdout     = ""
    $stderr     = ""
    $exitCode   = -1
    $timedOut   = $false

    # Drive prism via System.Diagnostics.Process so we can enforce a hard
    # timeout. The call operator (&) blocks forever on a hung child, which
    # wedges the whole test run behind WinRM. A hung process is killed and
    # reported as a failure rather than an infinite wait.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $exe
    $psi.UseShellExecute        = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.CreateNoWindow         = $true
    # .NET Framework (Windows PowerShell 5.1) has no ArgumentList property;
    # build the arg string manually with Windows quoting. Quote any arg
    # containing whitespace; escape embedded quotes by doubling them.
    $argParts = @()
    foreach ($a in $Arguments) {
        $escaped = $a -replace '"', '""'
        if ($escaped -match '\s') { $argParts += "`"$escaped`"" }
        else                     { $argParts += $escaped }
    }
    $psi.Arguments = ($argParts -join ' ')

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi

    # Read stdout/stderr synchronously with ReadToEnd. Async event handlers
    # (BeginOutputReadLine) race the process exit and drop the last lines for
    # fast-exiting commands like `prism --help`; ReadToEnd blocks until EOF
    # and cannot lose data. prism's output is small, so a 4 KB pipe cannot
    # fill and deadlock the child before we drain it.
    try {
        [void]$proc.Start()
        if (-not $proc.WaitForExit($script:PrismTimeoutSec * 1000)) {
            $timedOut = $true
            try { $proc.Kill() } catch {}
            $proc.WaitForExit(5000) | Out-Null
        }
        # Read after exit: the streams are at EOF, so ReadToEnd returns
        # immediately with everything the process wrote.
        $stdout   = $proc.StandardOutput.ReadToEnd()
        $stderr   = $proc.StandardError.ReadToEnd()
        $exitCode = $proc.ExitCode
        if ($timedOut) {
            $stderr = "Invoke-Prism timed out after $($script:PrismTimeoutSec)s on: $exe $($Arguments -join ' ')`n$stderr"
        }
    } finally {
        $proc.Close()
    }

    $script:LastPrismOutput = $stdout
    $script:LastPrismError  = $stderr

    return [pscustomobject]@{
        Stdout   = $stdout
        Stderr   = $stderr
        ExitCode = $exitCode
    }
}

# Same as Invoke-Prism but throws on non-zero exit and returns parsed JSON.
function Invoke-PrismJson {
    if ($args.Count -eq 0) { throw "Invoke-PrismJson: no arguments given" }
    $r = Invoke-Prism @args
    if ($r.ExitCode -ne 0) {
        throw "prism exited $($r.ExitCode); stderr: $($r.Stderr.Trim())"
    }
    if (-not $r.Stdout.Trim()) {
        throw "prism produced no stdout"
    }
    try {
        return $r.Stdout | ConvertFrom-Json
    } catch {
        $preview = $r.Stdout.Substring(0, [Math]::Min(200, $r.Stdout.Length))
        throw "stdout is not valid JSON: $preview"
    }
}

# --- Assertions -----------------------------------------------------
function Assert-True($cond, $msg = "expected condition to be true") {
    if (-not $cond) { throw $msg }
}

function Assert-Equal($expected, $actual, $msg = $null) {
    if ($expected -ne $actual) {
        $m = if ($msg) { $msg } else { "expected '$expected', got '$actual'" }
        throw $m
    }
}

function Assert-Contains([string] $text, [string] $needle, $msg = $null) {
    if ($null -eq $text -or $text.IndexOf($needle) -lt 0) {
        $m = if ($msg) { $msg } else { "expected text to contain '$needle'" }
        throw $m
    }
}

function Assert-NotContains([string] $text, [string] $needle, $msg = $null) {
    if ($null -ne $text -and $text.IndexOf($needle) -ge 0) {
        $m = if ($msg) { $msg } else { "expected text NOT to contain '$needle'" }
        throw $m
    }
}

function Assert-Match([string] $text, [string] $pattern, $msg = $null) {
    if ($null -eq $text -or $text -notmatch $pattern) {
        $m = if ($msg) { $msg } else { "expected text to match '$pattern'" }
        throw $m
    }
}

function Assert-ExitCode([int] $expected, [int] $actual, $msg = $null) {
    if ($expected -ne $actual) {
        $m = if ($msg) { $msg } else { "expected exit code $expected, got $actual" }
        throw $m
    }
}

function Assert-HasProperty($obj, [string] $prop, $msg = $null) {
    if ($null -eq $obj -or -not ($obj.PSObject.Properties.Name -contains $prop)) {
        $m = if ($msg) { $msg } else { "expected object to have property '$prop'" }
        throw $m
    }
}

# --- Reporting ------------------------------------------------------
function Write-FinalReport {
    Write-Host ""
    Write-Host "------------------------------------------" -ForegroundColor Cyan
    Write-Host "Total:  $script:TestsTotal"
    Write-Host "Passed: $script:TestsPassed" -ForegroundColor Green
    if ($script:TestsFailed -gt 0) {
        Write-Host "Failed: $script:TestsFailed" -ForegroundColor Red
        Write-Host ""
        Write-Host "Failures:" -ForegroundColor Red
        foreach ($f in $script:Failures) { Write-Host "  - $f" -ForegroundColor Red }
    } else {
        Write-Host "Failed: 0"
    }
    Write-Host "------------------------------------------" -ForegroundColor Cyan
}

function Get-ExitCodeFromResults {
    if ($script:TestsFailed -gt 0) { return 1 }
    return 0
}

# Refresh PATH from the registry -- call after installing.
function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
}