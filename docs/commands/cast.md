# cast

Run custom commands from Git repositories — a Python-native plugin system for Prism.

Cast repos are Python packages that expose a Typer app and a `__prism_name__`
alias. Prism imports them natively (via `importlib`), so every command gets
proper argument parsing, `--help` text, and shell completion — without
installing any packages.

## Quick start

```bash
# Add the official template repo (private — requires GitHub access)
prism cast --add https://github.com/AdriaERNI/Prism-CastTemplate.git

# List registered repos
prism cast --list

# Show available commands in a repo
prism cast template --help

# Run a command
prism cast template weather

# Run a command with arguments
prism cast template portcheck example.com 443

# Update all repos to latest
prism cast --update

# Delete repo #1
prism cast --del 1
```

## How it works

```
prism cast --add <url>
    │
    ├── git clone (shallow) → <user-data>/prism/cast/<slug>/
    ├── import __init__.py via spec_from_file_location
    ├── read __prism_name__ → alias (e.g. "template")
    ├── enumerate commands from the Typer app
    └── cache {alias, description, commands} in registry.json

prism cast template weather Madrid
    │
    ├── look up "template" in registry.json (no import)
    ├── lazy-import __init__.py → get the Typer app
    └── delegate: app(["weather", "Madrid"], standalone_mode=False)
        └── Typer parses args, validates types, runs the function
```

**Lazy import:** repos are only imported when a command is actually run —
not on `--list` or Tab completion. Command metadata is cached in
`registry.json` on `--add` and `--update`.

**PyInstaller compatibility:** `importlib.util.spec_from_file_location`
loads external packages from any filesystem path, so cast works inside
frozen `prism.exe` builds on Windows. Typer and Click resolve to Prism's
bundled copy — no extra dependencies needed.

## Shell completion

Prism uses [Click's built-in completion](https://click.palletsprojects.com/en/stable/shell-completion/).
Install it once per shell:

=== "Bash"

    ```bash
    # Add to ~/.bashrc
    eval "$(_PRISM_COMPLETE=bash_source prism)"
    ```

=== "Zsh"

    ```bash
    # Add to ~/.zshrc
    eval "$(_PRISM_COMPLETE=zsh_source prism)"
    ```

=== "Fish"

    ```bash
    _PRISM_COMPLETE=fish_source prism | source
    ```

=== "PowerShell"

    ```powershell
    # Add to $PROFILE
    Invoke-Expression -Command ( &_PRISM_COMPLETE=powershell_source prism )
    ```

After installing, Tab completes cast repo names, commands, and arguments:

```
prism cast <TAB>                   → template, --add, --list, --del, --update
prism cast template <TAB>          → weather, ip, uuid, portcheck, timestamp, headers
prism cast template weather <TAB>  → --help
prism cast template portcheck <TAB> → host, port
```

!!! tip "Completion reads the cache"
    Tab completion reads `registry.json` only — it does not import any cast
    repos. Run `prism cast --update` after pulling new commands to refresh
    the cache.

## Commands

### Add a repository

```bash
prism cast --add <git-url>
```

Clones the repo (shallow clone), imports its `__init__.py` to read
`__prism_name__` and enumerate commands, then caches everything in
`registry.json`. The alias comes from `__prism_name__` — if absent, the
URL-derived slug is used (e.g. `Prism-CastTemplate.git` → `casttemplate`).

Private GitHub repos are supported: HTTPS URLs are automatically converted
to SSH form for cloning.

### List repositories

```bash
prism cast --list
```

Shows an indexed table with alias, description, and cached commands:

```
  #  Name                 Description                         Commands
───  ──────────────────── ─────────────────────────────────── ────────────────────────────────────────
  1  template             Useful everyday tools for developers headers, ip, portcheck, timestamp, uuid, weather
```

Use the `#` column with `--del`.

### Delete a repository

```bash
prism cast --del <N>
```

Removes the repo at 1-based index N (from `--list`) — both the cloned
files and the registry entry.

### Update all repositories

```bash
prism cast --update
```

Runs `git pull --ff-only` on every repo and refreshes the cached command
metadata by re-importing each repo's `__init__.py`.

### Run a command

```bash
prism cast <name> <command> [args...]
```

Resolves `<name>` to a registered alias, lazy-imports the repo's
`__init__.py`, and delegates to its Typer app. Typer handles argument
parsing, type validation, and `--help` natively.

To see available commands in a repo:

```bash
prism cast template --help
```

## Creating a cast repo

A cast repo is a plain Git repository containing a Python package. The
root `__init__.py` is the entry point — it must define:

- `__prism_name__` (str) — the alias users type (e.g. `"template"`)
- `app` (typer.Typer) — a Typer instance with commands registered

No `pyproject.toml`, no `pip install` — Prism imports the package directly
by path.

### Repository structure

```
my-cast-repo/
├── __init__.py              # MANDATORY — defines __prism_name__ + app
├── commands/
│   ├── __init__.py
│   ├── weather.py           # command implementations
│   ├── ip.py
│   └── ...
├── README.md
└── LICENSE
```

### Root `__init__.py`

```python
import typer

__prism_name__ = "myrepo"

app = typer.Typer(
    name="myrepo",
    help="My custom tools",
    no_args_is_help=True,
    add_completion=False,
)

from .commands.weather import weather
from .commands.ip import ip

app.command()(weather)
app.command()(ip)
```

!!! warning "Two or more commands required"
    Typer flattens a single-command app into the app itself (no subcommand
    layer). Always register **two or more** commands so the group structure
    is preserved and `prism cast <name> <command>` works correctly.

### Command function

```python
# commands/weather.py
import typer

def weather(
    city: str = typer.Argument(None, help="City name"),
) -> None:
    """Show current weather from wttr.in."""
    # implementation
```

Each command automatically gets:

- `--help` text (from the docstring)
- Typed arguments with validation
- Named options (not just positional)
- Tab completion (via the cached metadata)

### Reference implementation

The official template repo is
[Prism-CastTemplate](https://github.com/AdriaERNI/Prism-CastTemplate) — a
private repo with 6 example commands (weather, ip, uuid, timestamp,
portcheck, headers). Use it as a starting point for your own cast repos.

## Where repos are stored

Cast repos are cloned into the same user data directory as
[`prism config`](config.md):

| OS | Path |
|----|------|
| Linux | `~/.local/share/prism/cast/` |
| macOS | `~/Library/Application Support/prism/cast/` |
| Windows | `%LOCALAPPDATA%\prism\cast\` |

The on-disk directory is the URL-derived slug (e.g. `casttemplate`).
The alias (from `__prism_name__`) is what you type in commands.

A `registry.json` file in the same directory caches repo metadata (alias,
description, commands) so `--list` and Tab completion work without
importing repos. See [Configuration](../getting-started/configuration.md)
for the full settings file location reference.

## Troubleshooting

### "Cast repo does not define `__prism_name__`"

The repo's root `__init__.py` is missing the `__prism_name__` variable.
Add it:

```python
__prism_name__ = "myrepo"
```

### "Cast repo does not define `app`"

The repo's root `__init__.py` is missing the Typer `app` instance. Add it:

```python
import typer
app = typer.Typer(name="myrepo", help="...", no_args_is_help=True)
```

### "Alias is already in use"

Two cast repos have the same `__prism_name__`. Change the `__prism_name__`
in one of the repos' `__init__.py` files, then re-add it.

### "Repository is missing from disk"

The registry entry exists but the cloned directory was deleted. Re-add the
repo:

```bash
prism cast --add <url>
```

### Command runs but Tab completion doesn't show it

The cached metadata is stale. Run `prism cast --update` to refresh the
command list in `registry.json`.

### Import error when running a command

Cast repos share Prism's Python environment. If a command uses a package
that isn't in Prism's dependencies, it will fail with `ModuleNotFoundError`.
Only use packages that Prism already bundles (standard library, `typer`,
`httpx`, `click`, `pydantic`, `websockets`, `platformdirs`).
