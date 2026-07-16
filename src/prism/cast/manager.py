"""Cast — manage and run custom command repositories.

Cast repos are plain Git repositories cloned into the user's Prism data
directory under a ``cast/`` subfolder.  Each repo can contain one or more
executable scripts (shell, Python, etc.).  Users run them with
``prism cast <repo>.<command>``.

Repository layout (example)::

    <user-data>/prism/cast/
    ├── template/                    # cloned repo (folder = slug or alias)
    │   ├── commands/
    │   │   ├── weather.sh           # shell script
    │   │   ├── uuid.py              # bare Python script
    │   │   └── ip/                  # Python package directory
    │   │       ├── __init__.py
    │   │       ├── __main__.py      # entry point — run via `python -m ip`
    │   │       └── core.py          # sub-module with real logic
    │   └── cast.json               # optional metadata

``cast.json`` (optional)::

    {
      "name": "template",
      "description": "Useful everyday tools",
      "commands": {
        "weather": "Show current weather (wttr.in)",
        "ip": "Show public IP address",
        "uuid": "Generate a UUID"
      }
    }

The ``name`` field lets a repo self-alias.  If absent, the slug is
derived from the repo URL (e.g. ``Prism-CastTemplate.git`` →
``casttemplate``).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from platformdirs import user_data_path

# ── Path helpers ─────────────────────────────────────────────────────


def cast_dir() -> Path:
    """Return the directory where cast repos are cloned."""
    d = user_data_path("prism", appauthor=False) / "cast"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cast_registry_path() -> Path:
    """Return the path to ``cast.json`` registry file."""
    return cast_dir() / "registry.json"


# ── Registry ────────────────────────────────────────────────────────


@dataclass
class CastRepo:
    """A single registered cast repository."""

    name: str  # alias used in `prism cast <name>.<cmd>`
    url: str  # original Git URL
    path: Path  # local clone path
    description: str = ""


def _load_registry() -> list[dict[str, str]]:
    """Load the registry JSON (list of ``{name, url}`` dicts)."""
    p = cast_registry_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_registry(repos: list[dict[str, str]]) -> None:
    """Atomically write the registry."""
    p = cast_registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(repos, f, indent=2)
        f.write("\n")
    tmp.replace(p)


def _slug_from_url(url: str) -> str:
    """Derive a default slug from a Git URL.

    ``https://github.com/user/Prism-CustomCastTemplate.git`` →
    ``customcasttemplate``

    Rules:
    - Strip protocol / host / user path
    - Strip ``.git`` suffix
    - Strip a leading ``Prism-`` prefix if present (convention)
    - Lowercase
    """
    parsed = urlparse(url)
    path = parsed.path or url
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    name = Path(path).name
    if name.lower().startswith("prism-"):
        name = name[len("prism-") :]
    return name.lower()


def _resolve_clone_url(url: str) -> str:
    """Resolve a URL that git can actually clone.

    For public repos, the original HTTPS URL works. For private repos,
    HTTPS will fail without credentials; convert GitHub HTTPS URLs to
    SSH form (``git@github.com:owner/repo.git``).
    """
    if url.startswith("git@") or url.startswith("ssh://"):
        return url

    parsed = urlparse(url)
    if parsed.hostname and "github.com" in parsed.hostname:
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[: -len(".git")]
        parts = path.split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            return f"git@github.com:{owner}/{repo}.git"

    return url


def _load_cast_json(repo_path: Path) -> dict[str, object]:
    """Load ``cast.json`` from *repo_path*. Returns empty dict on error."""
    meta = repo_path / "cast.json"
    if not meta.is_file():
        return {}
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_alias(repo_path: Path, url_slug: str) -> str:
    """Determine the repo alias — from ``cast.json:name`` or fallback to slug."""
    meta = _load_cast_json(repo_path)
    name = meta.get("name", "")
    if isinstance(name, str) and name.strip():
        # Sanitize: lowercase, replace spaces/dots with hyphens
        return name.strip().lower().replace(" ", "-").replace(".", "-")
    return url_slug


def list_repos() -> list[CastRepo]:
    """Return all registered cast repos (in registration order).

    The on-disk directory is always the URL-derived slug (never the
    alias), because the alias can change via cast.json but the clone
    path is fixed at registration time.
    """
    raw = _load_registry()
    result: list[CastRepo] = []
    for entry in raw:
        name = entry.get("name", "")
        url = entry.get("url", "")
        if not name:
            continue
        repo_path = cast_dir() / _slug_from_url(url)
        desc = entry.get("description", "")
        result.append(CastRepo(name=name, url=url, path=repo_path, description=desc))
    return result


def add_repo(url: str) -> CastRepo:
    """Clone *url* into the cast directory and register it.

    Raises ``RuntimeError`` if the URL or alias is already registered.
    """
    repos = list_repos()
    url_slug = _slug_from_url(url)

    # Check for duplicate URL
    for r in repos:
        if r.url == url:
            raise RuntimeError(
                f"Repository already registered as '{r.name}' (URL: {r.url})"
            )

    target = cast_dir() / url_slug
    if target.exists():
        shutil.rmtree(target)

    # Clone — try SSH for GitHub URLs (private repo support), fallback to original
    clone_url = _resolve_clone_url(url)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and clone_url != url:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(target)],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to clone {url}: {result.stderr.strip() or 'unknown error'}"
        )

    # Determine alias from cast.json or fallback to URL slug
    alias = _resolve_alias(target, url_slug)

    # Check for duplicate alias
    for r in repos:
        if r.name == alias:
            raise RuntimeError(
                f"Alias '{alias}' is already in use by '{r.url}'. "
                f"Change the 'name' field in cast.json."
            )

    desc = _load_cast_json(target).get("description", "")
    if not isinstance(desc, str):
        desc = ""

    raw = _load_registry()
    raw.append({"name": alias, "url": url, "description": desc})
    _save_registry(raw)

    return CastRepo(name=alias, url=url, path=target, description=desc)


def del_repo(index: int) -> CastRepo:
    """Remove the repo at 1-based *index* from disk and registry.

    Raises ``RuntimeError`` if *index* is out of range.
    """
    repos = list_repos()
    if index < 1 or index > len(repos):
        raise RuntimeError(f"Invalid index {index}. Available: 1..{len(repos)}")

    repo = repos[index - 1]

    if repo.path.exists():
        shutil.rmtree(repo.path)

    raw = _load_registry()
    raw = [r for r in raw if r.get("name") != repo.name]
    _save_registry(raw)

    return repo


def update_repos() -> list[tuple[str, str]]:
    """Git-pull all registered repos. Returns ``(name, status)`` tuples."""
    repos = list_repos()
    results: list[tuple[str, str]] = []
    for repo in repos:
        if not repo.path.exists() or not (repo.path / ".git").exists():
            results.append(
                (repo.name, "missing — re-add with: prism cast --add " + repo.url)
            )
            continue
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(repo.path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            results.append((repo.name, f"error: {result.stderr.strip() or 'unknown'}"))
        else:
            results.append(
                (
                    repo.name,
                    "updated"
                    if "Updating" in result.stdout
                    or "Already up to date" in result.stdout
                    else "ok",
                )
            )
            # Refresh description in registry
            desc = _load_cast_json(repo.path).get("description", "")
            if isinstance(desc, str):
                _update_registry_field(repo.name, "description", desc)
    return results


# ── Command discovery & execution ────────────────────────────────────

COMMANDS_SUBDIR = "commands"


def _update_registry_field(name: str, key: str, value: str) -> None:
    """Update a field for *name* in the registry."""
    raw = _load_registry()
    for entry in raw:
        if entry.get("name") == name:
            entry[key] = value
    _save_registry(raw)


def discover_commands(repo_path: Path) -> dict[str, str]:
    """Discover executable commands in *repo_path*.

    Looks in ``commands/`` subdirectory (or repo root if it doesn't exist).
    Returns ``{command_name: description}``.

    A command is:
    - A directory with ``__main__.py`` (Python package)
    - A regular file that is executable (POSIX) OR has a known script
      extension (.sh, .py, .ps1, .bash)
    """
    cmds_dir = repo_path / COMMANDS_SUBDIR
    if not cmds_dir.is_dir():
        cmds_dir = repo_path

    result: dict[str, str] = {}

    # Load descriptions from cast.json
    desc_map: dict[str, str] = {}
    meta = _load_cast_json(repo_path)
    if meta:
        cmds_meta = meta.get("commands", {})
        if isinstance(cmds_meta, dict):
            for cmd_name, cmd_desc in cmds_meta.items():
                desc_map[str(cmd_name)] = str(cmd_desc) if cmd_desc else ""

    known_extensions = {".sh", ".py", ".ps1", ".bash"}
    ignored = {"README", "README.md", "LICENSE", ".gitignore", "cast.json"}

    for entry in sorted(cmds_dir.iterdir()):
        if entry.name in ignored or entry.name.startswith("."):
            continue
        if entry.is_dir():
            # Python package: directory with __main__.py
            if (entry / "__main__.py").is_file():
                result[entry.name] = desc_map.get(entry.name, "")
            continue

        stem = entry.stem if entry.suffix in known_extensions else entry.name
        if stem in ignored:
            continue
        is_exec = bool(entry.stat().st_mode & stat.S_IXUSR)
        has_known_ext = entry.suffix in known_extensions
        if not is_exec and not has_known_ext:
            continue

        result[stem] = desc_map.get(stem, "")

    return result


def resolve_command(repo_slug: str, command_name: str) -> tuple[CastRepo, Path]:
    """Resolve ``repo_slug.command_name`` to a (repo, path) pair.

    *path* points to either:
    - A directory containing ``__main__.py`` (Python package command)
    - A script file (.sh, .py, .ps1, etc.)

    Raises ``RuntimeError`` if the repo or command is not found.
    """
    repos = list_repos()
    repo = next((r for r in repos if r.name == repo_slug.lower()), None)
    if repo is None:
        available = ", ".join(r.name for r in repos) or "(none)"
        raise RuntimeError(f"Cast repo '{repo_slug}' not found. Available: {available}")

    if not repo.path.exists():
        raise RuntimeError(
            f"Repository '{repo.name}' is registered but missing from disk. "
            f"Re-add it with: prism cast --add {repo.url}"
        )

    cmds_dir = repo.path / COMMANDS_SUBDIR
    if not cmds_dir.is_dir():
        cmds_dir = repo.path

    # 1. Directory with __main__.py (Python package)
    pkg_dir = cmds_dir / command_name
    if pkg_dir.is_dir() and (pkg_dir / "__main__.py").is_file():
        return repo, pkg_dir

    # 2. Exact file match, then with known extensions
    candidates = [
        cmds_dir / command_name,
        cmds_dir / f"{command_name}.sh",
        cmds_dir / f"{command_name}.py",
        cmds_dir / f"{command_name}.ps1",
        cmds_dir / f"{command_name}.bash",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return repo, candidate

    available = discover_commands(repo.path)
    names = ", ".join(sorted(available)) or "(none)"
    raise RuntimeError(
        f"Command '{command_name}' not found in repo '{repo.name}'. Available: {names}"
    )


def run_command(
    repo_slug: str, command_name: str, extra_args: list[str] | None = None
) -> int:
    """Resolve and execute ``repo_slug.command_name``.

    Returns the exit code of the executed command.
    """
    repo, script_path = resolve_command(repo_slug, command_name)
    extra = extra_args or []

    # ── Python package directory (has __main__.py) ───────────────────
    # Run via `python -m <name>` with PYTHONPATH set to commands/
    # so relative imports and sibling sub-modules work correctly.
    if script_path.is_dir() and (script_path / "__main__.py").is_file():
        cmds_dir = script_path.parent
        env = {**os.environ, "PYTHONPATH": str(cmds_dir)}
        cmd = [sys.executable, "-m", script_path.name, *extra]
        result = subprocess.run(cmd, cwd=str(repo.path), env=env)
        return result.returncode

    # ── Bare Python script (.py) ─────────────────────────────────────
    # -P prevents the script's own directory from being added to
    # sys.path[0], which avoids stdlib shadowing (e.g. uuid.py
    # shadowing the uuid module). Unlike -I, it preserves PYTHONPATH
    # and user site-packages so dependencies still work.
    if script_path.suffix == ".py":
        cmd = [sys.executable, "-P", str(script_path), *extra]

    elif script_path.suffix == ".ps1" and sys.platform == "win32":
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            *extra,
        ]
    else:
        # Shell scripts — bash on all platforms (Git Bash on Windows)
        cmd = ["bash", str(script_path), *extra]

    result = subprocess.run(cmd, cwd=str(repo.path))
    return result.returncode
