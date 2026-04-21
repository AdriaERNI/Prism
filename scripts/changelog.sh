#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git-cliff --output CHANGELOG.md "$@"
echo "CHANGELOG.md updated"
