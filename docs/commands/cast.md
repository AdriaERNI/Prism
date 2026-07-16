# cast

Run custom commands from Git repositories — a plugin system for Prism.

Cast lets you add any Git repository as a "cast" (command source), then run
its scripts with `prism cast <repo>.<command>`.

## Quick start

```bash
# Add a cast repo
prism cast --add https://github.com/AdriaERNI/Prism-CustomCastTemplate.git

# List registered repos
prism cast --list

# Run a command
prism cast customcasttemplate.weather

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

Clones the repository (shallow clone) into Prism's user data directory under
`cast/<slug>/`. The slug is derived from the repo name:

- `Prism-CustomCastTemplate.git` → `customcasttemplate`
- `my-tools.git` → `my-tools`

### List repositories

```bash
prism cast --list
```

Shows an indexed table:

```
  #  Name                           Description                     URL
───  ────────────────────────────── ────────────────────────────── ──────────────────────────────
  1  customcasttemplate             Useful everyday tools          https://github.com/.../...git
```

Use the `#` column with `--del`.

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
prism cast <repo>.<command>
```

Resolves `<repo>` to a registered slug and `<command>` to a script file inside
the repo's `commands/` directory (or repo root if no `commands/` dir exists).

Example:

```bash
prism cast customcasttemplate.weather
prism cast customcasttemplate.ip
prism cast customcasttemplate.uuid
```

## Repository structure

A cast repository is a plain Git repo with an optional `cast.json` metadata
file and a `commands/` directory containing executable scripts:

```
my-cast-repo/
├── commands/
│   ├── weather.sh          # executable shell script
│   ├── ip.py               # Python script
│   └── uuid.sh
└── cast.json               # optional metadata
```

### cast.json (optional)

```json
{
  "description": "Useful everyday tools",
  "commands": {
    "weather": "Show current weather (wttr.in)",
    "ip": "Show public IP address",
    "uuid": "Generate a UUID"
  }
}
```

Descriptions from `cast.json` appear in `--list` output and in error messages
when a command is not found.

### Supported script types

| Extension | Runner |
|-----------|--------|
| `.sh` / `.bash` | `bash` |
| `.py` | `python` (same interpreter as Prism) |
| `.ps1` | `powershell` (Windows only) |
| (no extension, executable) | `bash` |

## Where repos are stored

Cast repos are cloned into the Prism user data directory:

| OS | Path |
|----|------|
| Linux | `~/.local/share/prism/cast/` |
| macOS | `~/Library/Application Support/prism/cast/` |
| Windows | `%LOCALAPPDATA%\prism\cast\` |

A `registry.json` file in the same directory tracks which repos are registered.
