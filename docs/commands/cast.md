# cast

Run custom commands from Git repositories — a Python-native plugin system for Prism.

Cast repos are Python packages that expose a Typer app and a `__prism_name__`
alias. Prism imports them natively, so every command gets proper argument
parsing, `--help` text, and shell completion.

## Quick start

```bash
# Add a cast repo
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

## Shell completion

Prism uses Click's built-in completion. Install it once per shell:

```bash
# Bash (add to ~/.bashrc)
eval "$(_PRISM_COMPLETE=bash_source prism)"

# Zsh (add to ~/.zshrc)
eval "$(_PRISM_COMPLETE=zsh_source prism)"

# Fish
_PRISM_COMPLETE=fish_source prism | source
```

After that, Tab completes cast repo names, commands, and arguments:

```
prism cast <TAB>                  → template, --add, --list, --del, --update
prism cast template <TAB>         → weather, ip, uuid, portcheck, timestamp, headers
prism cast template weather <TAB>  → --help
prism cast template portcheck <TAB> → host, port
```

## Commands

### Add a repository

```bash
prism cast --add <git-url>
```

Clones the repo, imports its `__init__.py` to read `__prism_name__` and
enumerate commands, then caches everything in the registry. Future `--list`
and completion calls read the cache only — no imports.

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

### Delete a repository

```bash
prism cast --del <N>
```

Removes repo at 1-based index N (from `--list`) — cloned files and registry.

### Update all repositories

```bash
prism cast --update
```

Runs `git pull --ff-only` on every repo and refreshes cached command metadata
by re-importing each repo's `__init__.py`.

### Run a command

```bash
prism cast <name> <command> [args...]
```

Resolves `<name>` to a registered alias, lazy-imports the repo's `__init__.py`,
and delegates to its Typer app. Typer handles argument parsing, validation,
and `--help` natively.

## Creating a cast repo

A cast repo is a Python package with a root `__init__.py` that defines:

- `__prism_name__` — the alias users type (e.g. `"template"`)
- `app` — a `typer.Typer` instance with commands registered

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

__prism_name__ = "template"

app = typer.Typer(
    name="template",
    help="Useful everyday tools for developers",
    no_args_is_help=True,
    add_completion=False,
)

from .commands.weather import weather
from .commands.ip import ip

app.command()(weather)
app.command()(ip)
```

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

Each command automatically gets `--help`, typed arguments, and Tab completion.

## Where repos are stored

| OS | Path |
|----|------|
| Linux | `~/.local/share/prism/cast/` |
| macOS | `~/Library/Application Support/prism/cast/` |
| Windows | `%LOCALAPPDATA%\prism\cast\` |

The on-disk directory is the URL-derived slug (e.g. `casttemplate`).
The alias (from `__prism_name__`) is what you type in commands.

A `registry.json` file caches repo metadata (alias, description, commands)
so `--list` and completion work without importing repos.
