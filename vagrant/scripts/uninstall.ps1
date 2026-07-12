# Silently uninstall Prism using its registered uninstaller.

[CmdletBinding()] param()

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

. "$PSScriptRoot\_common.ps1"

Write-Section "Uninstall Prism"

# Inno Setup writes its uninstaller next to the app and registers it under
# Uninstall\<AppId>_is1. AppId defaults to AppName (Prism) when not set in the iss.
$candidates = @(
    "C:\Program Files\prism\unins000.exe",
    "C:\Program Files (x86)\prism\unins000.exe"
)

# Walk the registry too in case the path differs.
$regPaths = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
)
foreach ($rp in $regPaths) {
    if (-not (Test-Path $rp)) { continue }
    Get-ChildItem $rp -ErrorAction SilentlyContinue | ForEach-Object {
        $disp = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).DisplayName
        $unin = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).UninstallString
        if ($disp -and $disp -match "^Prism" -and $unin) {
            $exe = $unin -replace '"', '' -replace ' /.*$', ''
            if (Test-Path $exe) { $candidates += $exe }
        }
    }
}

$uninstaller = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $uninstaller) {
    Write-Host "No installed Prism found -- nothing to do."
    return
}

Write-Host "Running uninstaller: $uninstaller"
$proc = Start-Process -FilePath $uninstaller `
                      -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
                      -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    Write-Host "WARNING: uninstaller exited $($proc.ExitCode)" -ForegroundColor Yellow
}

# Inno is asynchronous on uninstall; give it a moment.
Start-Sleep -Seconds 2

# Force-clean any residue.
$installRoot = Split-Path $uninstaller -Parent
if (Test-Path "$installRoot\prism.exe") {
    Write-Host "Removing leftover $installRoot\prism.exe"
    Remove-Item "$installRoot\prism.exe" -Force -ErrorAction SilentlyContinue
}
if (Test-Path $installRoot) {
    Remove-Item $installRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Refresh-Path

Write-Host "Uninstall OK." -ForegroundColor Green