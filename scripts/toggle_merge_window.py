"""Toggle the Option-B merge-commit window on development with auto-restore guard.

Usage:
  python scripts/toggle_merge_window.py begin
  python scripts/toggle_merge_window.py end
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from scripts.apply_protection import branches, development_window_payload, full_protection_payload, restore_repo_settings_ops

REPO = "AdriaERNI/Prism"
WINDOW_MAX_MINUTES = int(os.environ.get("PRISM_WINDOW_MAX_MINUTES", "5"))


def _gh(args: list[str]) -> None:
    subprocess.run(["gh", "api", *args], check=True)


def begin() -> None:
    _gh(["--method", "PATCH", f"/repos/{REPO}", "-f", "allow_merge_commit=true"])
    for branch in branches():
        payload = development_window_payload() if branch == "development" else full_protection_payload()
        from json import dumps
        _gh(["--method", "PUT", f"/repos/{REPO}/branches/{branch}/protection", "--input", "-"], input=dumps(payload))
    sys.stderr.write(f"window open — restore within {WINDOW_MAX_MINUTES} min\n")


def end() -> None:
    from json import dumps

    for key, value in restore_repo_settings_ops():
        _gh(["--method", "PATCH", f"/repos/{REPO}", "-f", f"{key}={str(value).lower()}"])
    for branch in branches():
        _gh(
            ["--method", "PUT", f"/repos/{REPO}/branches/{branch}/protection", "--input", "-"],
            input=dumps(full_protection_payload()),
        )
    sys.stderr.write("window closed; settings + protection restored\n")


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: toggle_merge_window.py begin|end\n")
        return 2
    if sys.argv[1] == "begin":
        begin()
        return 0
    if sys.argv[1] == "end":
        end()
        return 0
    sys.stderr.write("unknown command\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
