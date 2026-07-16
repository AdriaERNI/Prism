#!/usr/bin/env bash
# Capture a screenshot from the Vagrant Windows VM.
# Usage: bash screenshot.sh <output.png>
set -euo pipefail
OUTPUT="${1:-/tmp/vagrant-screenshot.png}"
VAGRANT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$VAGRANT_DIR"

# Ensure dir exists on VM
vagrant winrm --shell powershell --command "New-Item -ItemType Directory -Force -Path C:\prism-tests | Out-Null" 2>/dev/null || true

# Take screenshot via PowerShell
vagrant winrm --shell powershell --command '
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$gfx.Dispose()
$bmp.Save("C:\prism-tests\screenshot.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "OK"
' 2>&1

# Download via base64 encoding through winrm
vagrant winrm --shell powershell --command '
$bytes = [System.IO.File]::ReadAllBytes("C:\prism-tests\screenshot.png")
$base64 = [System.Convert]::ToBase64String($bytes)
Write-Output $base64
' 2>/dev/null | tr -d '\r' | base64 -d > "$OUTPUT"

SIZE=$(stat -c%s "$OUTPUT" 2>/dev/null || echo 0)
if [ "$SIZE" -lt 100 ]; then
  echo "ERROR: Screenshot too small ($SIZE bytes) — VM may not have a display"
  exit 1
fi
echo "Screenshot saved to $OUTPUT ($SIZE bytes)"
