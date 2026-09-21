"""Detect textual divergence in uv.lock between two branches (main vs head).

The guard compares the FULL text of each `[[package]]` block, not just the
version line: any overlapping hunk that differs (version, source,
requires-python, dependency lists) can produce a three-way merge conflict on
a release PR, so any of those must be flagged.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_PACKAGE_NAME = re.compile(r'^name = "([^"]+)"')


def _block_map(path: str) -> dict[str, str]:
    """Map each package name to the full normalized text of its block."""
    blocks: dict[str, str] = {}
    cur_name: str | None = None
    cur: list[str] = []
    for line in _path_lines(path):
        stripped = line.strip()
        if stripped == "[[package]]":
            if cur_name is not None:
                blocks[cur_name] = "\n".join(cur)
            cur_name, cur = None, []
            continue
        if cur_name is None:
            m = _PACKAGE_NAME.match(stripped)
            cur_name = m.group(1) if m else None
            if cur_name is None:
                continue
        cur.append(line.rstrip("\n"))
    if cur_name is not None:
        blocks[cur_name] = "\n".join(cur)
    return blocks


def _path_lines(path: str) -> list[str]:
    return Path(path).read_text(encoding="utf-8").splitlines()


def find_divergent_packages(base_lock: str, head_lock: str) -> list[str]:
    """Return package names present in both locks whose block text differs."""
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
    args: dict[str, object] = {"base": None, "head": None, "json": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--base-file", "--head-file"):
            i += 1
            if i >= len(argv):
                sys.stderr.write(f"missing value for {a}\n")
                return 2
            args["base" if a == "--base-file" else "head"] = argv[i]
        elif a == "--json":
            args["json"] = True
        else:
            sys.stderr.write(f"unknown argument: {a}\n")
            return 2
        i += 1
    base, head = args["base"], args["head"]
    if not base or not head:
        sys.stderr.write("missing --base-file or --head-file\n")
        return 2
    divergent = find_divergent_packages(str(base), str(head))
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
