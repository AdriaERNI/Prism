# Configure prism for the local IRIS in the VM and stage workspace fixtures.
#
# The VM's IRIS install uses default creds: _SYSTEM / SYS at port 52773.
# This script writes the user-level config.json so subsequent tests do not
# have to pass connection flags every time.

[CmdletBinding()] param()

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_common.ps1"

Write-Section "Configure prism for VM IRIS"

$workspace = "C:\prism-tests\fixtures"
if (-not (Test-Path $workspace)) {
    throw "Fixture directory not found: $workspace"
}

# Wipe any stale config from a previous run, then set known values.
$null = Invoke-Prism config --reset-all
$r = Invoke-Prism config `
        -U  "http://localhost:52773" `
        -u  "_SYSTEM" `
        -p  "SYS" `
        -n  "USER" `
        -w  $workspace
if ($r.ExitCode -ne 0) {
    throw "prism config failed (exit $($r.ExitCode)); stderr: $($r.Stderr.Trim())"
}
Write-Host "  Config written: workspace=$workspace, url=http://localhost:52773"

# Sanity ping -- the rest of the suite assumes IRIS responds.
$info = Invoke-Prism info
if ($info.ExitCode -ne 0) {
    Write-Host "WARNING: prism info failed; tests against IRIS will likely fail." -ForegroundColor Yellow
    Write-Host $info.Stderr -ForegroundColor Yellow
} else {
    Write-Host "  prism info OK"
}

Write-Host "Setup OK." -ForegroundColor Green