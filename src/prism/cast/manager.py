"""Cast — manage and run custom command repositories (Typer plugin system).

Each cast repo is a Python package whose root ``__init__.py`` exposes:

- ``__prism_name__``: str  — alias used in ``prism cast <name> <command>``
- ``app``: typer.Typer   — Typer instance with all commands registered

Repos are cloned into ``<user-data>/prism/cast/<slug>/``.  The on-disk
directory name is always the URL-derived slug (stable across alias changes).
The alias (from ``__prism_name__``) is what the user types.

Command metadata is cached in ``registry.json`` on ``--add`` / ``--update``
so that ``--list`` and shell completion work without importing repos.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
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
    """Return the path to the registry JSON file."""
    return cast_dir() / "registry.json"


# ── Data models ────────────────────────────────────────────────────


@dataclass
class CastCommand:
    """A single command inside a cast repo (cached metadata)."""

    name: str
    help: str = ""


@dataclass
class CastRepo:
    """A registered cast repository."""

    name: str  # alias from __prism_name__
    url: str  # original Git URL
    path: Path  # local clone path (based on URL slug)
    description: str = ""
    commands: list[CastCommand] = field(default_factory=list)


# ── Registry persistence ──────────────────────────────────────────


def _load_registry() -> list[dict]:
    """Load the registry JSON."""
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


def _save_registry(repos: list[dict]) -> None:
    """Atomically write the registry."""
    p = cast_registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(repos, f, indent=2)
        f.write("\n")
    tmp.replace(p)


# ── URL helpers ────────────────────────────────────────────────────


def _slug_from_url(url: str) -> str:
    """Derive a directory slug from a Git URL.

    ``https://github.com/user/Prism-CastTemplate.git`` → ``casttemplate``
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
    """Convert GitHub HTTPS URLs to SSH for private-repo support."""
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


# ── Import / introspection ────────────────────────────────────────


def _import_cast(repo_path: Path) -> object:
    """Import the root ``__init__.py`` of a cast repo and return the module.

    Uses ``spec_from_file_location`` with ``submodule_search_locations``
    so relative imports (``from .commands import ...``) work.

    This is the only function that executes cast code — call it lazily.
    """
    slug = repo_path.name
    init_file = repo_path / "__init__.py"
    if not init_file.is_file():
        raise RuntimeError(
            f"Cast repo at {repo_path} has no __init__.py. "
            f"Every cast repo must define __prism_name__ and app."
        )

    # Clear any stale cached module
    mod_name = f"_prism_cast_{slug}"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(
        mod_name,
        str(init_file),
        submodule_search_locations=[str(repo_path)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to create import spec for {init_file}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _read_cast_metadata(repo_path: Path) -> tuple[str, str, list[CastCommand]]:
    """Import a cast repo and extract alias, description, and commands.

    Returns ``(alias, description, commands)``.
    """
    mod = _import_cast(repo_path)

    # __prism_name__ (mandatory)
    name = getattr(mod, "__prism_name__", None)
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError(
            f"Cast repo at {repo_path} does not define __prism_name__. "
            f"Add `__prism_name__ = '...'` to the root __init__.py."
        )
    alias = name.strip().lower()

    # app (mandatory) — Typer instance
    app = getattr(mod, "app", None)
    if app is None:
        raise RuntimeError(
            f"Cast repo at {repo_path} does not define `app`. "
            f"Add `app = typer.Typer(...)` to the root __init__.py."
        )

    # Description: try app.help, then app.info.help
    description = ""
    if hasattr(app, "info"):
        description = getattr(app.info, "help", "") or ""
    if not description:
        description = getattr(app, "help", "") or ""

    # Enumerate commands via Click
    commands: list[CastCommand] = []
    try:
        import typer

        click_grp = typer.main.get_command(app)
        if hasattr(click_grp, "commands"):
            for cmd_name, cmd_obj in sorted(click_grp.commands.items()):
                help_text = cmd_obj.help or cmd_obj.short_help or ""
                commands.append(CastCommand(name=cmd_name, help=help_text))
    except Exception:
        # If introspection fails, still register without commands
        pass

    return alias, description, commands


# ── Public API ────────────────────────────────────────────────────


def list_repos() -> list[CastRepo]:
    """Return all registered cast repos (registry-only, no import)."""
    raw = _load_registry()
    result: list[CastRepo] = []
    for entry in raw:
        name = entry.get("name", "")
        url = entry.get("url", "")
        if not name:
            continue
        slug = entry.get("slug", _slug_from_url(url))
        repo_path = cast_dir() / slug
        desc = entry.get("description", "")
        cmds_raw = entry.get("commands", [])
        commands = [
            CastCommand(name=c.get("name", ""), help=c.get("help", ""))
            for c in cmds_raw
            if isinstance(c, dict) and c.get("name")
        ]
        result.append(
            CastRepo(
                name=name,
                url=url,
                path=repo_path,
                description=desc,
                commands=commands,
            )
        )
    return result


def add_repo(url: str) -> CastRepo:
    """Clone *url*, import metadata, and register the cast repo.

    Raises ``RuntimeError`` on duplicate URL/alias, clone failure, or
    missing ``__prism_name__`` / ``app``.
    """
    repos = list_repos()
    slug = _slug_from_url(url)

    # Duplicate URL check
    for r in repos:
        if r.url == url:
            raise RuntimeError(
                f"Repository already registered as '{r.name}' (URL: {r.url})"
            )

    target = cast_dir() / slug
    if target.exists():
        shutil.rmtree(target)

    # Clone (SSH for GitHub, fallback to original URL)
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

    # Import + read metadata
    alias, description, commands = _read_cast_metadata(target)

    # Duplicate alias check
    for r in repos:
        if r.name == alias:
            raise RuntimeError(
                f"Alias '{alias}' is already in use by '{r.url}'. "
                f"Change __prism_name__ in the repo's __init__.py."
            )

    # Register with cached metadata
    raw = _load_registry()
    raw.append(
        {
            "name": alias,
            "url": url,
            "slug": slug,
            "description": description,
            "commands": [{"name": c.name, "help": c.help} for c in commands],
        }
    )
    _save_registry(raw)

    return CastRepo(
        name=alias,
        url=url,
        path=target,
        description=description,
        commands=commands,
    )


def del_repo(index: int) -> CastRepo:
    """Remove the repo at 1-based *index* from disk and registry."""
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
    """Git-pull all repos and refresh cached command metadata.

    Returns ``(name, status)`` tuples.
    """
    raw = _load_registry()
    results: list[tuple[str, str]] = []

    for entry in raw:
        name = entry.get("name", "")
        url = entry.get("url", "")
        slug = entry.get("slug", _slug_from_url(url))
        repo_path = cast_dir() / slug

        if not repo_path.exists() or not (repo_path / ".git").exists():
            results.append((name, "missing — re-add with: prism cast --add " + url))
            continue

        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            results.append((name, f"error: {result.stderr.strip() or 'unknown'}"))
        else:
            # Refresh metadata
            try:
                alias, description, commands = _read_cast_metadata(repo_path)
                entry["name"] = alias
                entry["description"] = description
                entry["commands"] = [{"name": c.name, "help": c.help} for c in commands]
                status = "updated" if "Updating" in result.stdout else "ok"
            except Exception as exc:
                status = f"pulled but import failed: {exc}"
            results.append((name, status))

    _save_registry(raw)
    return results


def get_cast_app(alias: str) -> object:
    """Lazy-import a cast repo by alias and return its Typer ``app``.

    Raises ``RuntimeError`` if the repo or its ``app`` is not found.
    """
    repos = list_repos()
    repo = next((r for r in repos if r.name == alias.lower()), None)
    if repo is None:
        available = ", ".join(r.name for r in repos) or "(none)"
        raise RuntimeError(f"Cast repo '{alias}' not found. Available: {available}")
    if not repo.path.exists():
        raise RuntimeError(
            f"Repository '{repo.name}' is missing from disk. "
            f"Re-add it with: prism cast --add {repo.url}"
        )
    mod = _import_cast(repo.path)
    app = getattr(mod, "app", None)
    if app is None:
        raise RuntimeError(f"Cast repo '{repo.name}' does not define `app`.")
    return app


def run_command(alias: str, args: list[str]) -> int:
    """Lazy-import a cast repo and delegate to its Typer app.

    *args* is the full list of arguments after the alias
    (e.g. ``["weather", "Madrid"]``).
    """
    try:
        app = get_cast_app(alias)
    except RuntimeError:
        raise

    try:
        import click

        app(args, standalone_mode=False)
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except click.exceptions.UsageError as exc:
        # Click raises UsageError for bad args — print and exit non-zero
        import typer

        typer.echo(f"Error: {exc.message}", err=True)
        return 2
