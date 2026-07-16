# Plan: Cast v2 — Python-native Typer plugin system with auto-completion

## Decision summary

| Question | Decision |
|----------|----------|
| Mandatory Typer? | Yes — every cast repo MUST have `__init__.py` with `app` + `__prism_name__` |
| Shell scripts | Gone — all commands are Python functions with Typer |
| Deps / pyproject.toml | No — cast repos are plain packages, deps must be in Prism's env |
| Security | Lazy import — only when a command runs, not on `--list` |
| Command syntax | Spaces: `prism cast template weather Madrid` |
| Auto-completion | Yes — via Typer sub-app groups (see below) |

## PyInstaller compatibility (confirmed)

- `importlib.util.spec_from_file_location` loads external packages from any filesystem path
- PyInstaller frozen exes do NOT restrict external imports
- Typer + Click are already bundled in the build, so `import typer` in cast `__init__.py` resolves to Prism's bundled copy
- No pyproject.toml needed — we import by path, not via pip install

## Auto-completion (investigated)

### How it works

Click 8.x + Typer have built-in shell completion (bash/zsh/fish). The mechanism:

1. Shell script calls the CLI with env var `_PRISM_COMPLETE=bash_complete`
2. CLI intercepts this BEFORE running any command
3. CLI outputs completions as text
4. Shell script parses and displays suggestions

### The problem with current `cast` design

Current: `cast` is a single Typer command (function), not a group. Click can't suggest subcommands because there are none — everything after `cast` is just positional args.

Click's `Group.shell_complete(ctx, "we")` returns `[CompletionItem("weather", help="Show current weather.")]` — but only if `weather` is a registered subcommand of a group.

### The solution: `cast` as a Typer sub-app group

Restructure so `cast` is a Typer group (not a single command):

```
prism (Group)
  └── cast (Group)
        ├── --add, --list, --del, --update  (Options on the group callback)
        ├── template (Group — dynamically registered from cast repos)
        │   ├── weather (Command with typed args + --help)
        │   ├── uuid (Command)
        │   ├── ip (Command)
        │   └── portcheck (Command)
        └── other-cast (Group)
            └── ...
```

When the CLI starts, we:
1. Read the registry (fast, no import)
2. For each registered repo: create a placeholder Typer group with the alias name
3. When the user runs a command in that group: lazy-import the cast `__init__.py` and delegate to its Typer app

### What completion looks like for the user

```bash
# Install completion (one-time, Typer built-in)
eval "$(_PRISM_COMPLETE=bash_source prism)"

# Then tab completion works:
prism cast <TAB>                    # → template, other-cast, --add, --list, --del, --update
prism cast template <TAB>           # → weather, uuid, ip, portcheck, headers
prism cast template weather <TAB>   # → --city, --help
prism cast template portcheck <TAB> # → host (positional), port (positional), --help
```

### Dynamic registration approach

```python
# In cast.py CLI setup:
cast_app = typer.Typer(name="cast", help="...", no_args_is_help=True)

@cast_app.callback()
def cast_callback(
    add: str = typer.Option(None, "--add", ...),
    list: bool = typer.Option(False, "--list", ...),
    # ...
):
    """Manage and run custom command repositories."""
    if add: ...
    if list: ...

# Dynamically register cast repos as sub-groups
for repo in manager.list_repos():
    # Create a lazy proxy group that imports on first use
    repo_group = typer.Typer(name=repo.name, help=repo.description, no_args_is_help=True)

    @repo_group.callback(invoke_without_command=True)
    def lazy_cast(ctx: typer.Context, name: str = repo.name):
        if ctx.invoked_subcommand is None:
            # Import the cast app and show its help
            app = manager.get_cast_app(name)
            # Delegate to the cast's Typer app
            ...

    cast_app.add_typer(repo_group, name=repo.name)
```

### Challenge: lazy import in completion mode

When Tab is pressed, the shell calls `prism` with `_PRISM_COMPLETE=bash_complete`. At this point:
- We need to list subcommands of cast repos (for `prism cast template <TAB>`)
- This requires knowing the commands inside each cast repo
- But we don't want to import every cast repo on every Tab press

**Two-phase approach:**
1. **Phase 1 (registration):** On `prism cast --add`, import the cast, enumerate commands, store `{name, commands, description}` in registry.json. This is the only time we import.
2. **Phase 2 (completion):** On Tab, read registry.json only (no import). Show cached commands.
3. **Phase 3 (execution):** On actual command run, lazy-import and delegate to Typer.

This means `--update` also refreshes the cached command list.

### Registry format (v2)

```json
[
  {
    "name": "template",
    "url": "https://github.com/AdriaERNI/Prism-CastTemplate.git",
    "description": "Useful everyday tools for developers",
    "slug": "casttemplate",
    "commands": [
      {"name": "weather", "help": "Show current weather from wttr.in"},
      {"name": "ip", "help": "Show your public IP address"},
      {"name": "uuid", "help": "Generate a random UUID"},
      {"name": "portcheck", "help": "Check if a port is open on a host"},
      {"name": "headers", "help": "Show HTTP response headers for a URL"},
      {"name": "timestamp", "help": "Print the current Unix timestamp"},
      {"name": "qr", "help": "Generate a QR code in the terminal"}
    ]
  }
]
```

## Architecture

### Cast repo contract (v2)

```
Prism-CastTemplate/
├── __init__.py              # MANDATORY
├── commands/
│   ├── __init__.py
│   ├── weather.py
│   ├── ip/
│   │   ├── __init__.py
│   │   ├── __main__.py       # still usable standalone
│   │   └── core.py
│   ├── uuid.py
│   └── ...
├── README.md
└── LICENSE
```

### Root `__init__.py` contract

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
from .commands.uuid import uuid
from .commands.ip import ip

app.command()(weather)
app.command()(uuid)
app.command()(ip)
```

### Command function example

```python
# commands/weather.py
import typer

def weather(
    city: str = typer.Argument(None, help="City name"),
) -> None:
    """Show current weather from wttr.in."""
    # implementation
```

## CLI surface

```
prism cast --add <url>               # clone, import, cache commands, register
prism cast --list                    # registry-only (fast, no import)
prism cast --del <N>                  # same as before
prism cast --update                   # pull + refresh cached commands
prism cast <name>                     # show Typer help (lazy import)
prism cast <name> <command> [args]    # delegate to Typer app (lazy import)
prism cast --install-completion       # Typer built-in: install shell completion
```

## Implementation steps

1. Rewrite `src/prism/cast/manager.py`
   - `add_repo()`: clone, import via `spec_from_file_location`, read `__prism_name__` + enumerate commands from Typer app, cache everything in registry
   - `list_repos()`: registry-only (fields: name, url, description, slug, commands)
   - `get_cast_app()`: lazy-import — `spec_from_file_location` + return Typer app
   - `run_command()`: import, delegate `app([command, *args], standalone_mode=False)`
   - `update_repos()`: pull, re-import, refresh cached commands
   - Remove: cast.json script discovery, subprocess runner

2. Rewrite `src/prism/cli/commands/cast.py`
   - `cast` is a Typer sub-app (group), not a single command
   - Callback handles `--add`, `--list`, `--del`, `--update`
   - Dynamically register each cast repo as a named sub-group
   - Sub-group callback lazy-imports and delegates to the cast's Typer app
   - Enable `add_completion=True` on the cast sub-app

3. Register in `app.py`: `app.add_typer(cast_app, name="cast")`

4. Rewrite Prism-CastTemplate:
   - Root `__init__.py` with Typer app + `__prism_name__ = "template"`
   - All 7 commands as Python functions with Typer decorators
   - Remove cast.json, .sh files

5. Tests: rewrite for import-based approach

6. Docs: update `docs/commands/cast.md` + add completion installation instructions
