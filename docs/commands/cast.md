# cast

Run custom commands from Git repositories — a plugin system for Prism.

Cast lets you add any Git repository as a "cast" (command source), then run
its scripts with `prism cast <repo>.<command>`.

## Quick start

```bash
# Add a cast repo
prism cast --add https://github.com/AdriaERNI/Prism-CastTemplate.git

# List registered repos
prism cast --list

# Run a command
prism cast template.weather

# Run a command with arguments
prism cast template.portcheck example.com 443

# Update all repos to latest
prism cast --update

# Delete repo #1
prism cast --del 1
```

## Commands

### Add a repository

```bash
prism cast --add <git-url>
```

Clones the repository (shallow clone) into Prism's user data directory.
The repo registers under the alias from `cast.json:name` if present, or the
URL-derived slug otherwise (e.g. `Prism-CastTemplate.git` → `casttemplate`,
but if `cast.json` has `"name": "template"`, it registers as `template`).

### List repositories

```bash
prism cast --list
```

Shows an indexed table with the alias, description, and original URL:

```
  #  Name                           Description                     URL
───  ────────────────────────────── ────────────────────────────── ──────────────────────────────
  1  template                       Useful everyday tools          https://github.com/.../...git
```

### Delete a repository

```bash
prism cast --del <N>
```

Removes the repo at 1-based index N (from `--list`) — both the cloned files
and the registry entry.

### Update all repositories

```bash
prism cast --update
```

Runs `git pull --ff-only` on every registered repo to fetch the latest changes.

### Run a command

```bash
prism cast <repo>.<command> [args...]
```

Resolves `<repo>` to a registered alias and `<command>` to a script inside
the repo's `commands/` directory (or repo root if no `commands/` dir exists).

Extra positional arguments after the command are passed through to the script.

Example:

```bash
prism cast template.weather
prism cast template.ip
prism cast template.portcheck example.com 443
```

## Repository structure

A cast repository is a plain Git repo with an optional `cast.json` metadata
file and a `commands/` directory containing executable scripts:

```
my-cast-repo/
├── commands/
│   ├── weather.sh          # shell script
│   ├── uuid.py             # bare Python script
│   ├── ip/                 # Python package directory
│   │   ├── __init__.py
│   │   ├── __main__.py     # entry point — run via `python -m ip`
│   │   └── core.py         # sub-module with real logic
│   └── headers.sh
└── cast.json               # optional metadata
```

### cast.json (optional)

```json
{
  "name": "template",
  "description": "Useful everyday tools",
  "commands": {
    "weather": "Show current weather (wttr.in)",
    "ip": "Show public IP address",
    "uuid": "Generate a UUID"
  }
}
```

The `name` field lets a repo self-alias. Without it, the alias is derived
from the repo URL. This avoids long or ugly names — `Prism-CastTemplate`
becomes `template` instead of `casttemplate`.

Descriptions from `cast.json` appear in `--list` output and in error
messages when a command is not found.

### Supported script types

| Type | How it runs |
|------|-------------|
| `.sh` / `.bash` | `bash script.sh [args]` |
| `.py` (bare file) | `python -P script.py [args]` — `-P` prevents stdlib shadowing |
| `dir/` with `__main__.py` | `python -m dir [args]` — full package with sub-modules |
| `.ps1` | `powershell -File script.ps1 [args]` (Windows only) |

#### Bare `.py` vs package directory

Simple scripts work fine as bare `.py` files. The `-P` flag prevents the
script's directory from being prepended to `sys.path`, so a file named
`uuid.py` won't shadow the stdlib `uuid` module.

For commands that need sub-modules, helper functions, or shared state,
use a **package directory** with `__main__.py`. Prism runs it as a proper
module (`python -m name`), so relative imports and sibling modules work
correctly:

```
commands/
└── ip/
    ├── __init__.py
    ├── __main__.py    # entry point
    └── core.py        # importable sub-module
```

`__main__.py` can do `from ip.core import get_ip` and it just works.

## Where repos are stored

Cast repos are cloned into the Prism user data directory:

| OS | Path |
|----|------|
| Linux | `~/.local/share/prism/cast/` |
| macOS | `~/Library/Application Support/prism/cast/` |
| Windows | `%LOCALAPPDATA%\prism\cast\` |

A `registry.json` file in the same directory tracks which repos are registered.
The on-disk directory is always the URL-derived slug; the alias (from
`cast.json`) is what you use in `prism cast <alias>.<command>`.
