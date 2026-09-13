# prism-installer/static/write-version-stamp.ps1
# Writes a PyInstaller version-file (VS_VERSIONINFO resource) for the built exe
# so the installed prism.exe carries a REAL numeric version resource instead of
# the 0.0.0.0 default -- RG-011, which test-install reads off the installed
# exe (Get-PrismFileVersion). ISCC /DAppVerNumeric stamps only the setup.exe
# wrapper; the embedded PyInstaller exe needs its own --version-file stamp.
param(
    [Parameter(Mandatory = $true, Position = 0)][string] $OutFile,
    # Version under test (e.g. 0.2.1-beta4); never empty -- caller passes the
    # committed $env:VERSION. Numeric head split exactly like the compile step.
    [Parameter(Mandatory = $true, Position = 1)][string] $Version
)
if ([string]::IsNullOrWhiteSpace($Version)) { throw 'write-version-stamp: missing -Version' }
# Four-part numeric; a prerelease tag never parses so head/tag are split.
$head = $Version; $tagNum = '0'
if ($Version -match '^(\d+\.\d+\.\d+)-(?:beta|alpha|rc)[._]?(\d*)$') {
    $head = $matches[1]; if ($matches[2]) { $tagNum = $matches[2] }
} elseif ($Version -match '^(\d+\.\d+\.\d+)-') { $head = $matches[1] }
$numeric = "$head.$tagNum"
$dir = Split-Path -Path $OutFile -Parent
if ($dir -and -not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Path $dir -Force -ErrorAction Stop | Out-Null
}
$text = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($verParts),
    prodvers=($verParts),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [
            StringStruct(u'CompanyName', u'Prism'),
            StringStruct(u'FileDescription', u'Prism - IRIS development CLI and MCP server'),
            StringStruct(u'FileVersion', u'$numeric'),
            StringStruct(u'InternalName', u'prism'),
            StringStruct(u'OriginalFilename', u'prism.exe'),
            StringStruct(u'ProductName', u'Prism'),
            StringStruct(u'ProductVersion', u'$numeric')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
Set-Content -LiteralPath $OutFile -Value $text -Encoding utf8
Write-Host ("version stamp: {0} (numeric {1})" -f $Version, $numeric)
