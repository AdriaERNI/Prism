#!/usr/bin/env bash
# Run the prism integration test suite inside the Vagrant Windows VM
# against the Inno Setup-installed copy of prism (in C:\Program Files\prism).
#
# Prereqs:
#   - vagrant up has been done from vagrant/
#   - the installer exists at dist/prism-<version>-setup.exe
#     (run ./vagrant/build-windows.sh first if it doesn't)
#
# Usage:
#   ./vagrant/run-integration-tests.sh                 # full suite
#   ./vagrant/run-integration-tests.sh --filter "*sql*" # subset
#   ./vagrant/run-integration-tests.sh --keep-installed # don't uninstall after
#
# Outputs:
#   exit 0 on full pass, 1 on any failure
#   logs streamed live; on failure, server logs are shown

set -euo pipefail

VAGRANT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$VAGRANT_DIR/.." && pwd)"
DIST_DIR="$PROJECT_DIR/dist"

FILTER="*"
KEEP_INSTALLED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --filter)         FILTER="$2"; shift 2 ;;
        --keep-installed) KEEP_INSTALLED=1;  shift ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *)
            echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$PROJECT_DIR"

VERSION=$(uv run python -c "
import tomllib, pathlib
d = tomllib.loads(pathlib.Path('pyproject.toml').read_text())
print(d['project']['version'])
")
INSTALLER_NAME="prism-${VERSION}-setup.exe"
INSTALLER_PATH="$DIST_DIR/$INSTALLER_NAME"

echo "==> Project version: $VERSION"

if [[ ! -s "$INSTALLER_PATH" ]]; then
    echo "ERROR: $INSTALLER_PATH not found." >&2
    echo "       Build it first: ./vagrant/build-windows.sh" >&2
    exit 1
fi

for cmd in vagrant tar; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is not installed." >&2
        exit 1
    fi
done

cd "$VAGRANT_DIR"

echo "==> Ensuring VM is running..."
vagrant up --provider=libvirt

echo "==> Staging test bundle..."
STAGE=$(mktemp -d /tmp/prism-tests-XXXXXX)
TARBALL=$(mktemp /tmp/prism-bundle-XXXXXX.tar.gz)
trap 'rm -rf "$STAGE" "$TARBALL"' EXIT

# Layout inside the bundle:
#   scripts/         (vagrant/scripts/*)
#   fixtures/        (tests/workspace/*)
mkdir -p "$STAGE/scripts" "$STAGE/fixtures"
cp -r "$VAGRANT_DIR/scripts/." "$STAGE/scripts/"
cp -r "$PROJECT_DIR/tests/workspace/." "$STAGE/fixtures/"

# Tarball is written outside $STAGE so we don't tar a file mid-write.
tar czf "$TARBALL" -C "$STAGE" .

echo "==> Uploading installer + bundle to VM..."
vagrant upload "$INSTALLER_PATH"      'C:\prism-tests\setup.exe'
vagrant upload "$TARBALL"             'C:\prism-tests\bundle.tar.gz'

echo "==> Extracting bundle inside VM..."
vagrant winrm --shell powershell --command "
    \$ErrorActionPreference = 'Stop'
    if (Test-Path C:\prism-tests\scripts)  { Remove-Item C:\prism-tests\scripts  -Recurse -Force }
    if (Test-Path C:\prism-tests\fixtures) { Remove-Item C:\prism-tests\fixtures -Recurse -Force }
    tar xzf C:\prism-tests\bundle.tar.gz -C C:\prism-tests
    Get-ChildItem C:\prism-tests | Format-Table Name,Mode -AutoSize
" | sed -e 's/^/    /'

echo "==> Installing prism in the VM..."
vagrant winrm --shell powershell --command "
    powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\install.ps1
" | tee /tmp/prism-install.log | sed -e 's/^/    /'

if ! grep -q "Install OK" /tmp/prism-install.log; then
    echo "ERROR: installer did not report success." >&2
    exit 1
fi

# Run the suite. Capture exit code; never let it abort the script so we
# can run uninstall after.
echo ""
echo "==> Running integration tests (filter: $FILTER)..."
TESTS_LOG=$(mktemp /tmp/prism-tests-XXXXXX.log)
set +e
vagrant winrm --shell powershell --command "
    powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\run-all.ps1 -Filter '$FILTER'
" | tee "$TESTS_LOG" | sed -e 's/^/    /'
TEST_RC=${PIPESTATUS[0]}
set -e

# vagrant winrm exits 0 even when the inner script exits 1 — detect
# pass/fail via the sentinel that run-all.ps1 prints at the end.
if grep -q "RUNALL_RESULT=PASS" "$TESTS_LOG"; then
    SUITE_RC=0
else
    SUITE_RC=1
fi

if [[ $KEEP_INSTALLED -eq 0 ]]; then
    echo ""
    echo "==> Uninstalling prism..."
    vagrant winrm --shell powershell --command "
        powershell -ExecutionPolicy Bypass -File C:\prism-tests\scripts\uninstall.ps1
    " | sed -e 's/^/    /' || true
fi

rm -f "$TESTS_LOG"

echo ""
if [[ $SUITE_RC -eq 0 ]]; then
    echo "==> Integration tests PASSED"
else
    echo "==> Integration tests FAILED" >&2
fi

exit $SUITE_RC