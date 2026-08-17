"""Load the zzllkk2003/hcc project (2,344 classes) into a live IRIS USER namespace.

Used by the big-project index validation harness (tests/integration/
test_index_big_project.py) and the standalone bench script
(scripts/index_big_bench.py). The same code path is mirrored in the CI
workflow (see .github/workflows/index-validation.yml).

It clones the repo (unless --repo-dir is given), skips classes that fail to
compile clean (the handful of DeepSee HCC.Cube.* classes), and returns the
list of successfully loaded class names.

Usage:
    python scripts/hcc_loader.py [--repo-dir /tmp/hcc] [--namespace USER]
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
from pathlib import Path

REPO_URL = "https://github.com/zzllkk2003/hcc.git"
# DeepSee classes that cannot compile in IRIS Community (no DeepSee). They are
# a tiny (<1%) known-bad subset; skipping keeps the big-project load clean.
KNOWN_BAD_PREFIXES = ("HCC.Cube",)


def _normalise_class_name(path: Path, root: Path) -> str:
    """Turn a .cls file path under *root* into its class name."""
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1].endswith(".cls"):
        parts[-1] = parts[-1][: -len(".cls")]
    return ".".join(parts)


def _fetch_classes(path: Path) -> dict[str, Path]:
    """Return {class_name: path} for every .cls under *path* (recursive)."""
    found: dict[str, Path] = {}
    for p in sorted(path.rglob("*.cls")):
        name = _normalise_class_name(p, path)
        if name.startswith(KNOWN_BAD_PREFIXES):
            continue
        found[name] = p
    return found


async def _put_all(
    classes: dict[str, Path],
    namespace: str,
    concurrency: int = 16,
) -> dict:
    """PUT every class source via the Atelier API, bounded-concurrency."""
    from prism.iris.api.documents import put_document

    sem = asyncio.Semaphore(concurrency)
    results = {"put_ok": 0, "put_fail": 0, "put_failed_names": []}

    async def _one(name: str) -> None:
        src = classes[name]
        async with sem:
            try:
                await put_document(
                    name=f"{name}.cls",
                    content=src.read_text().splitlines(),
                    namespace=namespace,
                )
                results["put_ok"] += 1
            except Exception:
                results["put_fail"] += 1
                results["put_failed_names"].append(name)

    await asyncio.gather(*(_one(n) for n in classes))
    return results


async def _compile_all(loaded: list[str], namespace: str) -> list[str]:
    """Compile every loaded class through Atelier; return the successful ones."""
    from prism.iris.api.compile import compile_documents

    ok: list[str] = []
    for i in range(0, len(loaded), 200):
        batch = [f"{n}.cls" for n in loaded[i : i + 200]]
        try:
            resp = await compile_documents(batch, namespace=namespace)
            status = resp.get("status", {}) or {}
            errors = status.get("errors", []) or []
            if not errors:
                ok.extend(batch)
        except Exception:
            continue
    return ok


async def _load_from_source(src_root: Path, namespace: str) -> dict:
    classes = _fetch_classes(src_root)
    print(f"[hcc] found {len(classes)} .cls files under {src_root}", flush=True)

    result: dict = {
        "repo": str(src_root),
        "found": len(classes),
        "classes": sorted(classes),
    }

    puts = await _put_all(classes, namespace)
    result.update(
        {
            "put_ok": puts["put_ok"],
            "put_fail": puts["put_fail"],
            "put_failed_names": puts["put_failed_names"],
        }
    )

    loaded = [n for n in classes if n not in puts["put_failed_names"]]
    compiled = await _compile_all(loaded, namespace)
    result["compile_ok"] = compiled
    result["loaded"] = len(compiled)
    return result


async def load_hcc(repo_dir: str | None = None, namespace: str = "USER") -> dict:
    """Load hcc into *namespace*; return a summary dict.

    Returns ``{"classes": [...], "loaded": N, "skipped": [...], ...}``.
    """
    if repo_dir and Path(repo_dir).exists():
        root = Path(repo_dir)
    else:
        root = Path("/tmp/hcc")
        if not root.exists():
            print(f"[hcc] cloning {REPO_URL} -> {root} ...", flush=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", REPO_URL, str(root)],
                check=True,
                capture_output=True,
            )
    src_root = root / "src" if (root / "src").exists() else root
    return await _load_from_source(src_root, namespace)


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-dir", default=None, help="Local clone of hcc (optional; clones if absent)."
    )
    parser.add_argument("--namespace", default="USER")
    args = parser.parse_args()

    summary = await load_hcc(args.repo_dir, args.namespace)
    print(
        f"[hcc] loaded {summary.get('loaded')} classes (found {summary.get('found')}, "
        f"put-fail {summary.get('put_fail')})",
        flush=True,
    )
    if summary.get("put_failed_names"):
        print("[hcc] put failures:", summary["put_failed_names"][:20], flush=True)


if __name__ == "__main__":
    asyncio.run(_main())
