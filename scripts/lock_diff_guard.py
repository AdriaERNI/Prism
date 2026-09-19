"""Detect textual divergence in uv.lock between two branches (main vs head)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_PACKAGE_NAME = re.compile(r'^name = "([^"]+)"')


def _block_map(path: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    cur: dict[str, str] | None = None
    cur_name: str | None = None
    for line in _path_lines(path):
        m = _PACKAGE_NAME.match(line.strip())
        if m:
            cur_name = m.group(1)
            cur = {}
            out[cur_name] = cur
            continue
        if cur is None or cur_name is None:
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            if key.strip() == "version":
                cur["version"] = value.strip().strip('"')
            elif key.strip() == "source":
                cur["source"] = value.strip()
    return out


def _path_lines(path: str) -> list[str]:
    return Path(path).read_text(encoding="utf-8").splitlines()


def find_divergent_packages(base_lock: str, head_lock: str) -> list[str]:
    """Return package names present in both locks whose text differs."""
    base = _block_map(base_lock)
    head = _block_map(head_lock)
    divergent: list[str] = []
    for name in sorted(set(base) & set(head)):
        if base[name] != head[name]:
            divergent.append(name)
    return divergent


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        sys.stderr.write(
            "usage: lock_diff_guard.py --base-file <main uv.lock> "
            "--head-file <PR-head uv.lock> [--json]\n"
        )
        return 2
    args = {"base": None, "head": None, "json": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--base-file":
            i += 1
            args["base"] = argv[i]
        elif a == "--head-file":
            i += 1
            args["head"] = argv[i]
        elif a == "--json":
            args["json"] = True
        i += 1
    if not args["base"] or not args["head"]:
        sys.stderr.write("missing --base-file or --head-file\n")
        return 2
    divergent = find_divergent_packages(args["base"], args["head"])
    if args["json"]:
        print(json.dumps({"divergent": divergent}))
    elif divergent:
        sys.stderr.write(
            "DIVERGENT uv.lock packages (align to the union or sync first): "
            + ", ".join(divergent)
            + "\n"
        )
        return 1
    else:
        print("OK: uv.lock overlapping packages identical on both sides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
