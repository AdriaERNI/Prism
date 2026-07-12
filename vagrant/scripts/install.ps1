# Silently install the Prism Inno Setup installer and verify the result.
#
# The runner uploads the installer to C:\prism-tests\setup.exe.
# This script runs it with /VERYSILENT and confirms prism.exe is on disk
# and reachable via PATH.

[CmdletBinding()]
param(
    [string] $Installer = "C:\prism-tests\setup.exe",
    [string] $LogFile   = "C:\prism-tests\install.log"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

. "$PSScriptRoot\_common.ps1"

Write-Section "Install Prism"

if (-not (Test-Path $Installer)) {
    throw "Installer not found at $Installer"
}

$installed = "C:\Program Files\prism\prism.exe"

if (Test-Path $installed) {
    Write-Host "Prism already installed at $installed -- uninstalling first to test fresh install"
    & "$PSScriptRoot\uninstall.ps1"
}

Write-Host "Running installer: $Installer"
$proc = Start-Process -FilePath $Installer `
                      -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$LogFile") `
                      -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    if (Test-Path $LogFile) { Get-Content $LogFile -Tail 80 | Out-Host }
    throw "Inno installer exited with code $($proc.ExitCode)"
}

if (-not (Test-Path $installed)) {
    throw "After install, $installed does not exist"
}
Write-Host "  Installed: $installed"

# Refresh PATH so `prism` resolves in this session.
Refresh-Path

$cmd = Get-Command prism.exe -ErrorAction SilentlyContinue
if (-not $cmd) {
    throw "prism.exe not on PATH after install"
}
Write-Host "  PATH resolves prism: $($cmd.Source)"

# Smoke check: prism --help must exit 0 and mention `serve`.
$r = Invoke-Prism --help
if ($r.ExitCode -ne 0) {
    throw "`prism --help` exited $($r.ExitCode); stderr: $($r.Stderr.Trim())"
}
if ($r.Stdout -notmatch "serve") {
    throw "`prism --help` output looks wrong: $($r.Stdout.Substring(0,[Math]::Min(200,$r.Stdout.Length)))"
}
Write-Host "  prism --help works"

Write-Host ""
Write-Host "Install OK." -ForegroundColor Green