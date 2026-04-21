#!/usr/bin/env bash
# Build a Windows .exe and Inno Setup installer for prism-mcp
# using the Vagrant Windows VM with KVM/QEMU (libvirt).
# Usage: ./vagrant/build-windows.sh
#
# Prerequisites: vagrant up already done from vagrant/
# Outputs in dist/: prism-<version>.exe and prism-<version>-setup.exe

set -euo pipefail

VAGRANT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$VAGRANT_DIR/.." && pwd)"
DIST_DIR="$PROJECT_DIR/dist"

cd "$PROJECT_DIR"

VERSION=$(uv run python -c "
import tomllib, pathlib
d = tomllib.loads(pathlib.Path('pyproject.toml').read_text())
print(d['project']['version'])
")
EXE_NAME="prism-${VERSION}.exe"
INSTALLER_NAME="prism-${VERSION}-setup.exe"
echo "==> Building version: $VERSION"

echo "==> Checking prerequisites..."
for cmd in vagrant virsh curl; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is not installed." >&2
    exit 1
  fi
done

if ! vagrant plugin list | grep -q vagrant-libvirt; then
  echo "ERROR: vagrant-libvirt plugin not installed. Run: vagrant plugin install vagrant-libvirt" >&2
  exit 1
fi

# All vagrant commands run from the vagrant/ directory
cd "$VAGRANT_DIR"

echo "==> Ensuring VM is running..."
vagrant up --provider=libvirt

echo "==> Uploading project to VM..."
TARBALL=$(mktemp /tmp/prism-src-XXXXXX.tar.gz)
trap 'rm -f "$TARBALL"' EXIT
tar czf "$TARBALL" \
  --exclude='.git' \
  --exclude='dist' \
  --exclude='build' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.env' \
  --exclude='*.spec' \
  --exclude='vagrant/.vagrant' \
  --exclude='vagrant/*.exe' \
  -C "$PROJECT_DIR" .

vagrant upload "$TARBALL" 'C:\build\prism-src.tar.gz'

echo "==> Building .exe and installer inside the VM..."
BUILD_OUTPUT=$(vagrant winrm --shell powershell --command "
  \$ErrorActionPreference = 'Continue'
  \$ProgressPreference = 'SilentlyContinue'
  \$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')

  if (Test-Path C:\build\prism) { Remove-Item -Recurse -Force C:\build\prism }
  New-Item -ItemType Directory -Force -Path C:\build\prism | Out-Null
  tar xzf C:\build\prism-src.tar.gz -C C:\build\prism 2>&1 | Out-Host

  powershell -ExecutionPolicy Bypass -File C:\build\prism\vagrant\build-in-vm.ps1
" 2>&1) || true
echo "$BUILD_OUTPUT"

if ! echo "$BUILD_OUTPUT" | grep -q "BUILD_SUCCESS"; then
  echo "ERROR: Build failed inside VM." >&2
  exit 1
fi

echo "==> Downloading build artifacts..."
mkdir -p "$DIST_DIR"

VM_IP=$(vagrant ssh-config 2>/dev/null | awk '/HostName/ {print $2}')
HTTP_PORT=8888

vagrant winrm --shell powershell --command "
  New-NetFirewallRule -DisplayName TempHTTP -Direction Inbound -Protocol TCP -LocalPort $HTTP_PORT -Action Allow | Out-Null
  \$listener = New-Object System.Net.HttpListener
  \$listener.Prefixes.Add('http://+:${HTTP_PORT}/')
  \$listener.Start()
  Write-Host 'HTTP server ready'

  \$files = @{
    '/$EXE_NAME' = 'C:\build\prism\dist\\$EXE_NAME'
    '/$INSTALLER_NAME' = 'C:\build\prism\dist\\$INSTALLER_NAME'
  }

  for (\$i = 0; \$i -lt 2; \$i++) {
    \$ctx = \$listener.GetContext()
    \$path = \$ctx.Request.Url.AbsolutePath
    if (\$files.ContainsKey(\$path)) {
      \$bytes = [IO.File]::ReadAllBytes(\$files[\$path])
      \$ctx.Response.ContentType = 'application/octet-stream'
      \$ctx.Response.ContentLength64 = \$bytes.Length
      \$ctx.Response.OutputStream.Write(\$bytes, 0, \$bytes.Length)
      \$ctx.Response.Close()
      Write-Host \"Served \$path (\$(\$bytes.Length) bytes)\"
    } else {
      \$ctx.Response.StatusCode = 404
      \$ctx.Response.Close()
    }
  }

  \$listener.Stop()
  Remove-NetFirewallRule -DisplayName TempHTTP
" &
HTTP_PID=$!
sleep 5

curl -sS -o "$DIST_DIR/$EXE_NAME" "http://${VM_IP}:${HTTP_PORT}/${EXE_NAME}"
curl -sS -o "$DIST_DIR/$INSTALLER_NAME" "http://${VM_IP}:${HTTP_PORT}/${INSTALLER_NAME}"

wait $HTTP_PID 2>/dev/null || true

# Validate
for f in "$DIST_DIR/$EXE_NAME" "$DIST_DIR/$INSTALLER_NAME"; do
  if [[ ! -s "$f" ]]; then
    echo "ERROR: $f is empty or missing." >&2
    exit 1
  fi
done

echo "==> Build complete:"
ls -lh "$DIST_DIR/$EXE_NAME" "$DIST_DIR/$INSTALLER_NAME"