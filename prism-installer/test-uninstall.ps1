# prism-installer/test-uninstall.ps1 - covers RG-009
# An uninstall that leaves the exe, the PATH entry or the registry key behind is
# invisible to an install test and poisons the NEXT run's 100 baseline, so all
# three are checked, not just the files.
param(
    [string] $ArtifactsPath = './dist',
    [string] $Name = 'test-uninstall.ps1',
    [string] $Baseline = 'fetch',
    [string] $Repo = '',
    [string] $SourceVersion = '',
    [string] $SuiteLogFile = ''
)
. (Join-Path (Join-Path $PSScriptRoot 'shared') 'installer-common.ps1')
$script:SuiteLogFile = $SuiteLogFile

$unins = Join-Path $script:InstallRoot 'unins000.exe'
if (-not (Test-Path -LiteralPath $unins -PathType Leaf)) {
    Write-SuiteLine 'nothing is installed to uninstall' -Skip
    exit 0
}
$dir = New-TempDir -Name $Name
# -Argument is ONE string: an array trips PowerShell's positional binding
# (measured). /VERYSILENT implies /SILENT for the uninstaller too.
$proc = Start-Process -FilePath $unins `
    -Argument ('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' + (Join-Path $dir 'uninstall.log') + '"') `
    -Wait -PassThru -WindowStyle Hidden
Assert-ExitCode -Expected @(0) -Actual $proc.ExitCode `
    -Because 'the uninstaller reports its own success with 0 and any other value as a failure'

# Inno detaches the uninstaller process; poll for the real effect instead of
# sleeping a guess (the same reason the pre-clean helper polls).
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline -and (Test-Path -LiteralPath (Join-Path $script:InstallRoot 'prism.exe') -PathType Leaf)) {
    Start-Sleep -Milliseconds 1500
}
Assert-PrismAbsent -Because 'the uninstall completed'
Write-SuiteLine 'uninstall removed the binary, the PATH entry and the registration' -Pass
