# prism config

View or edit Prism settings stored in `config.json` under the platform
user data directory.

## Usage

```
prism config                       # show all settings
prism config [SETTING-FLAGS]...    # update one or more settings
prism config -i                    # interactive walkthrough
prism config -r KEY [-r KEY...]    # reset specific keys to defaults
prism config --reset-all           # wipe config.json
```

With no arguments, the command prints all 21 settings together with
their **current effective values** — env vars and `.env` are merged in,
so what you see is what Prism will actually use. The password is
always displayed redacted as `***`.

## Setting flags

Each flag updates a single field in `config.json`; unspecified fields
keep their current value. The 8 most-used settings have a short flag.

### Connection

| Flag | Long | Type | Default |
|------|------|------|---------|
| `-U` | `--url` | string | `http://localhost:52773` |
| `-u` | `--user` | string | `_SYSTEM` |
| `-p` | `--password` | string | `SYS` |
| `-n` | `--namespace` | string | `USER` |
| `-w` | `--workspace` | string | *(empty)* |
| `-P` | `--super-port` | int | `1972` |

### Mode

| Flag | Long | Type | Default |
|------|------|------|---------|
| `-f` | `--output-format` | `json` \| `toon` | `json` |
|      | `--debug` / `--no-debug` | bool | `false` |

### Tunables (long flags only)

| Long | Type | Default |
|------|------|---------|
| `--api-prefix` | string | `api/atelier/v8` |
| `--compile-flags` | string | `cuk` |
| `--terminal-method` | `native` \| `ws` | `native` |
| `--terminal-max-output` | int | `100000` |
| `--test-runner` | string | `MCP.TestRunner` |
| `--test-method` | string | `RunTests` |
| `--test-manager` | string | `%UnitTest.Manager` |
| `--test-auto-deploy` / `--no-test-auto-deploy` | bool | `true` |
| `--debug-granularity` | string | `line` |
| `--debug-max-data` | int | `8192` |
| `--debug-max-children` | int | `32` |
| `--debug-max-depth` | int | `2` |
| `--debug-idle-timeout` | int | `300` |

### Mode flags

| Flag | Description |
|------|-------------|
| `-i`, `--interactive` | Walk through every setting; for each, choose **k**eep, **c**hange, or **d**efault. |
| `-r KEY`, `--reset KEY` | Remove a single key from `config.json` so its default takes over. Repeatable. |
| `--reset-all` | Delete `config.json` entirely. |

## Where it writes

| OS | Path |
|----|------|
| Windows | `%LOCALAPPDATA%\prism\config.json` |
| Linux | `~/.local/share/prism/config.json` (honours `XDG_DATA_HOME`) |

On POSIX, the file is written with mode `0600`. On Windows, it inherits
the ACLs of the user's `LOCALAPPDATA` folder.

Updates **merge** into any existing file, so you can change one setting
at a time without losing the others. Resets remove individual keys, so
the field reverts to its env var or built-in default.

## Examples

**Show the current config:**

```
$ prism config
Config file: /home/you/.local/share/prism/config.json

  iris_base_url                   http://localhost:52773
  iris_username                   _SYSTEM
  iris_password                   ***
  iris_namespace                  USER
  iris_workspace                  (unset)
  iris_superserver_port           1972
  ...
```

**First-time setup** — three flags, one shot:

```bash
prism config -u _SYSTEM -p SYS -U http://192.168.1.100:52773
```

**Change just the namespace:**

```bash
prism config -n SAMPLES
```

**Enable the debugger:**

```bash
prism config --debug
```

**Reset the password back to the default**, but keep everything else:

```bash
prism config -r iris_password
```

**Wipe the file:**

```bash
prism config --reset-all
```

**Interactive review** — useful for first-time setup or after upgrading:

```
$ prism config -i
Editing /home/you/.local/share/prism/config.json
For each setting choose: [k]eep, [c]hange, [d]efault

[1/21] iris_base_url
        Default: http://localhost:52773
        Current: http://localhost:52773
        [k]eep / [c]hange / [d]efault: c
        New value: http://192.168.1.100:52773

[2/21] iris_username
        Default: _SYSTEM
        Current: _SYSTEM
        [k]eep / [c]hange / [d]efault:

...
```

## Precedence

Settings from `config.json` are the **lowest-priority** source.
Environment variables and a `.env` file in the current directory
override them. See
[Configuration](../getting-started/configuration.md) for the full
precedence table.

## Related

- [Configuration](../getting-started/configuration.md) — full settings
  and environment-variable reference.
- [`prism info`](info.md) — a good first command to confirm your saved
  settings work.
