$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Refresh PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Extract source
Write-Host "Extracting source..."
if (Test-Path C:\build\prism) { Remove-Item -Recurse -Force C:\build\prism }
New-Item -ItemType Directory -Force -Path C:\build\prism | Out-Null
tar xzf C:\build\prism-src.tar.gz -C C:\build\prism 2>&1 | Out-Host

Set-Location C:\build\prism

Write-Host "Syncing dependencies..."
uv sync 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: uv sync failed"; exit 1 }

uv pip install pyinstaller 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: pyinstaller install failed"; exit 1 }

# Extract version from pyproject.toml
$ver = (Select-String -Path C:\build\prism\pyproject.toml -Pattern '^version\s*=\s*"(.+)"').Matches[0].Groups[1].Value
Write-Host "Build version: $ver"
$parts = $ver.Split('.')
$major = $parts[0]; $minor = $parts[1]; $patch = $parts[2]

# Generate version-info file for PyInstaller
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($major, $minor, $patch, 0),
    prodvers=($major, $minor, $patch, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('FileDescription', 'Prism Server'),
        StringStruct('FileVersion', '$ver'),
        StringStruct('InternalName', 'prism'),
        StringStruct('OriginalFilename', 'prism.exe'),
        StringStruct('ProductName', 'Prism'),
        StringStruct('ProductVersion', '$ver'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
Set-Content -Path C:\build\prism\version-info.py -Value $versionInfo

Write-Host "Running PyInstaller..."

# Find the intersystems native DLLs directory for bundling
$irisLibs = uv run python -c "import os,iris; print(os.path.join(os.path.dirname(os.path.dirname(iris.__file__)),'intersystems_irispython.libs'))" 2>$null
$addBinary = @()
if ($irisLibs -and (Test-Path $irisLibs)) {
  Write-Host "Found IRIS native libs: $irisLibs"
  $addBinary = @("--add-binary", "$irisLibs;intersystems_irispython.libs")
}

uv run pyinstaller --noconfirm --onefile --name prism --clean `
  --paths src `
  --hidden-import prism `
  --hidden-import prism.cli `
  --hidden-import prism.mcp `
  --hidden-import prism.iris `
  --hidden-import prism.iris.api `
  --hidden-import prism.iris.sdk `
  --collect-all iris `
  --collect-all irisnative `
  --collect-submodules prism `
  --collect-submodules fastmcp `
  --copy-metadata fastmcp `
  --copy-metadata python-dotenv `
  --copy-metadata toons `
  --collect-all fakeredis `
  --collect-submodules lupa `
  --collect-binaries lupa `
  --version-file version-info.py `
  @addBinary `
  main.py 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: PyInstaller failed"; exit 1 }

if (-not (Test-Path C:\build\prism\dist\prism.exe)) {
  Write-Host "ERROR: exe not found after build"
  exit 1
}

# Rename exe to include version
Rename-Item C:\build\prism\dist\prism.exe "prism-$ver.exe"
Write-Host "Build successful: prism-$ver.exe"

Write-Host "Building Inno Setup installer..."
Write-Host "Installer version: $ver"

$issContent = Get-Content C:\build\prism\vagrant\prism.iss -Raw
$issContent = $issContent -replace 'C:\\vagrant', 'C:\build\prism'
Set-Content -Path C:\build\prism\vagrant\prism-build.iss -Value $issContent

& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "/DAppVer=$ver" C:\build\prism\vagrant\prism-build.iss 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: Inno Setup failed"; exit 1 }

if (-not (Test-Path "C:\build\prism\dist\prism-$ver-setup.exe")) {
  Write-Host "ERROR: installer not found after build"
  exit 1
}
Write-Host "Installer built: prism-$ver-setup.exe"
Write-Host "BUILD_VERSION=$ver"
Write-Host "BUILD_SUCCESS"