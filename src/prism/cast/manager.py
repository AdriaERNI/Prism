"""Cast — manage and run custom command repositories.

Cast repos are plain Git repositories cloned into the user's Prism data
directory under a ``cast/`` subfolder.  Each repo can contain one or more
executable scripts (shell, Python, etc.).  Users run them with
``prism cast <repo>.<command>``.

Repository layout (example)::

    <user-data>/prism/cast/
    ├── customcasttemplate/       # cloned repo (folder name = repo slug)
    │   ├── commands/
    │   │   ├── weather.sh
    │   │   ├── ip.py
    │   │   └── uuid.sh
    │   └── cast.json            # optional metadata

``cast.json`` (optional)::

    {
      "description": "Useful everyday tools",
      "commands": {
        "weather": "Show current weather (wttr.in)",
        "ip": "Show public IP address",
        "uuid": "Generate a UUID"
      }
    }
"""

from __future__ import annotations

import json
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

    name: str  # slug used in `prism cast <name>.<cmd>`
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
    """Derive a slug from a Git URL.

    ``https://github.com/user/Prism-CustomCastTemplate.git`` →
    ``customcasttemplate``

    Rules:
    - Strip protocol / host / user path
    - Strip ``.git`` suffix
    - Strip a leading ``Prism-`` prefix if present (convention)
    - Lowercase
    """
    parsed = urlparse(url)
    # pathlib works on the path portion
    path = parsed.path or url
    # Remove leading slash and trailing .git
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    # Get the last segment (the repo name)
    name = Path(path).name
    # Strip a leading "Prism-" prefix to keep slugs short
    if name.lower().startswith("prism-"):
        name = name[len("prism-") :]
    return name.lower()


def _resolve_clone_url(url: str) -> str:
    """Resolve a URL that git can actually clone.

    For public repos, the original HTTPS URL works. For private repos,
    HTTPS will fail without credentials; if ``gh`` is authenticated we
    convert to the SSH URL form (``git@github.com:owner/repo.git``).
    """
    # If it's already SSH, use as-is
    if url.startswith("git@") or url.startswith("ssh://"):
        return url

    # Try to extract owner/repo from HTTPS GitHub URLs
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


def list_repos() -> list[CastRepo]:
    """Return all registered cast repos (in registration order)."""
    raw = _load_registry()
    result: list[CastRepo] = []
    for entry in raw:
        name = entry.get("name", "")
        url = entry.get("url", "")
        if not name:
            continue
        repo_path = cast_dir() / name
        desc = entry.get("description", "")
        result.append(CastRepo(name=name, url=url, path=repo_path, description=desc))
    return result


def add_repo(url: str) -> CastRepo:
    """Clone *url* into the cast directory and register it.

    Raises ``RuntimeError`` if the URL is already registered.
    """
    repos = list_repos()
    slug = _slug_from_url(url)

    # Check for duplicate URL or slug
    for r in repos:
        if r.url == url or r.name == slug:
            raise RuntimeError(
                f"Repository already registered as '{r.name}' (URL: {r.url})"
            )

    target = cast_dir() / slug
    if target.exists():
        # Folder exists but not in registry — remove it and re-clone
        shutil.rmtree(target)

    # Clone — try the original URL first; if it fails (e.g. private repo
    # without HTTPS credentials), retry with SSH.
    clone_url = _resolve_clone_url(url)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and clone_url != url:
        # SSH fallback failed — try original URL as last resort
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(target)],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to clone {url}: {result.stderr.strip() or 'unknown error'}"
        )

    # Load description from cast.json if present
    desc = _load_description(target)

    # Register
    raw = _load_registry()
    raw.append({"name": slug, "url": url, "description": desc})
    _save_registry(raw)

    return CastRepo(name=slug, url=url, path=target, description=desc)


def del_repo(index: int) -> CastRepo:
    """Remove the repo at 1-based *index* from disk and registry.

    Raises ``RuntimeError`` if *index* is out of range.
    """
    repos = list_repos()
    if index < 1 or index > len(repos):
        raise RuntimeError(f"Invalid index {index}. Available: 1..{len(repos)}")

    repo = repos[index - 1]

    # Remove from disk
    if repo.path.exists():
        shutil.rmtree(repo.path)

    # Remove from registry
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
            # Update description in case it changed
            desc = _load_description(repo.path)
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
            _update_registry_description(repo.name, desc)
    return results


# ── Command discovery & execution ────────────────────────────────────

COMMANDS_SUBDIR = "commands"


def _load_description(repo_path: Path) -> str:
    """Load description from ``cast.json`` if it exists."""
    meta = repo_path / "cast.json"
    if not meta.is_file():
        return ""
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("description", "")
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def _update_registry_description(name: str, desc: str) -> None:
    """Update the description for *name* in the registry."""
    raw = _load_registry()
    for entry in raw:
        if entry.get("name") == name:
            entry["description"] = desc
    _save_registry(raw)


def discover_commands(repo_path: Path) -> dict[str, str]:
    """Discover executable commands in *repo_path*.

    Looks in ``commands/`` subdirectory (or repo root if it doesn't exist).
    Returns ``{command_name: description}``.

    A file is considered a command if:
    - It is a regular file (not a directory)
    - It is executable (POSIX) OR has a known script extension (.sh, .py, .ps1)
    """
    cmds_dir = repo_path / COMMANDS_SUBDIR
    if not cmds_dir.is_dir():
        cmds_dir = repo_path

    result: dict[str, str] = {}

    # First, try to load descriptions from cast.json
    desc_map: dict[str, str] = {}
    meta = repo_path / "cast.json"
    if meta.is_file():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for cmd_name, cmd_desc in data.get("commands", {}).items():
                    desc_map[cmd_name] = cmd_desc
        except (OSError, json.JSONDecodeError):
            pass

    known_extensions = {".sh", ".py", ".ps1", ".bash"}
    ignored = {"README", "README.md", "LICENSE", ".gitignore", "cast.json"}

    for entry in sorted(cmds_dir.iterdir()):
        if entry.is_dir():
            continue
        name = entry.name
        if name in ignored or name.startswith("."):
            continue

        stem = entry.stem if entry.suffix in known_extensions else name
        if stem in ignored:
            continue
        # Skip non-executable, non-script files
        is_exec = bool(entry.stat().st_mode & stat.S_IXUSR)
        has_known_ext = entry.suffix in known_extensions
        if not is_exec and not has_known_ext:
            continue

        result[stem] = desc_map.get(stem, "")

    return result


def resolve_command(repo_slug: str, command_name: str) -> tuple[CastRepo, Path]:
    """Resolve ``repo_slug.command_name`` to a (repo, file_path) pair.

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

    # Try exact match, then with known extensions
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

    # List available commands for helpful error
    available = discover_commands(repo.path)
    names = ", ".join(sorted(available)) or "(none)"
    raise RuntimeError(
        f"Command '{command_name}' not found in repo '{repo.name}'. Available: {names}"
    )


def run_command(repo_slug: str, command_name: str) -> int:
    """Resolve and execute ``repo_slug.command_name``.

    Returns the exit code of the executed command.
    """
    repo, script_path = resolve_command(repo_slug, command_name)

    # Determine how to run the script
    if script_path.suffix == ".py":
        # -I: isolated mode — prevents the script's directory from
        # shadowing stdlib modules (e.g. a script named ``uuid.py``).
        cmd = [sys.executable, "-I", str(script_path)]
    elif script_path.suffix == ".ps1" and sys.platform == "win32":
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
    else:
        # Shell scripts — use bash on Windows too (Git Bash)
        cmd = ["bash", str(script_path)]

    result = subprocess.run(cmd, cwd=str(repo.path))
    return result.returncode
