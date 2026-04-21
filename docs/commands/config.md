# prism config

Save IRIS connection settings to the platform user config directory so
subsequent `prism` invocations don't need environment variables or a
`.env` file.

## Usage

```
prism config USERNAME PASSWORD URL [OPTIONS]
```

## Arguments

| Name | Type | Description |
|------|------|-------------|
| `USERNAME` | string | IRIS username (e.g. `_SYSTEM`). |
| `PASSWORD` | string | IRIS password. |
| `URL` | string | Base URL of the IRIS web server (e.g. `http://192.168.1.100:52773`). |

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--namespace`, `-n` | — | Default namespace. If omitted, the existing value in the file is kept; new files default to `USER`. |
| `--superserver-port`, `-p` | — | SuperServer port for the native terminal. Defaults to `1972`. |
| `--show` | off | Print the saved settings after writing (password redacted). |

## Where it writes

| OS | Path |
|----|------|
| Windows | `%LOCALAPPDATA%\prism\settings.json` |
| Linux | `~/.config/prism/settings.json` (honours `XDG_CONFIG_HOME`) |

On POSIX, the file is written with mode `0600`. On Windows, it inherits
the ACLs of the user's `LOCALAPPDATA` folder.

Each invocation **merges** the given values into any existing file, so
you can change one setting at a time without losing the others.

## Examples

**First-time setup** — set everything in one shot, show the result:

```powershell
prism config _SYSTEM SYS http://192.168.1.100:52773 --namespace USER --superserver-port 1972 --show
```

```
Saved settings to C:\Users\you\AppData\Local\prism\settings.json
  namespace: USER
  password: ***
  superserver_port: 1972
  url: http://192.168.1.100:52773
  username: _SYSTEM
```

**Change only the namespace**, keep everything else:

```powershell
prism config _SYSTEM SYS http://192.168.1.100:52773 --namespace SAMPLES
```

(You still need to pass the three positional arguments; they're
required. Use the same username/password/URL you stored before.)

## Precedence

Settings from this file are the **lowest-priority** source of
configuration. Environment variables and a `.env` file in the current
directory override them. See
[Configuration](../getting-started/configuration.md) for the full
precedence table.

## Related

- [Configuration](../getting-started/configuration.md) — full settings
  and environment-variable reference.
- [`prism info`](info.md) — a good first command to confirm your saved
  settings work.