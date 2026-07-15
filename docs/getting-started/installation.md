# Installation

Prism is available as a Windows installer (recommended for end users) or
via `uv`/`pip` for Linux and development setups.

## Windows (recommended)

1. **Download** the latest setup:

      - `prism-<version>-setup.exe` — Inno Setup installer. Installs
        `prism.exe` to `C:\Program Files\prism\` and adds that folder to
        the system `PATH`.

2. **Run** the installer. You'll be prompted for admin rights (needed to
   modify the system `PATH` and write under `Program Files`).

3. **Open a new terminal** (PowerShell, Command Prompt, or Windows
   Terminal). The existing terminal sessions won't have the new `PATH`
   yet — that's why a fresh window is required.

4. **Verify** by asking Prism to show its help, then hit the server you
   plan to use:

    ```powershell
    prism --help
    prism info
    ```

    If `prism info` fails with a connection error, that's expected — you
    haven't told Prism where IRIS lives yet. Continue to
    [Configuration](configuration.md) or the [Quick Start](quick-start.md).

## Linux (development / pip)

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A reachable IRIS instance with the Atelier REST API enabled

### Install with uv

```bash
# Clone the repo
git clone https://github.com/AdriaERNI/Prism.git
cd Prism

# Install all dependencies (creates a virtualenv)
uv sync

# Verify
uv run prism --help
uv run prism info
```

### Install with pip

```bash
pip install prism-mcp

# Verify
prism --help
prism info
```

### Optional: TOON output format

```bash
pip install prism-mcp[toon]
# or with uv:
uv pip install toons
```

## Standalone executable (Windows)

If you'd rather not run an installer, grab the standalone
`prism-<version>.exe`. It's a fully self-contained PyInstaller bundle —
drop it anywhere on your `PATH` (or invoke it with a full path).

```
prism-0.1.3.exe --help
```

## Uninstall

Windows: **Settings → Apps → Installed apps → Prism → Uninstall**, or
run `unins000.exe` inside `C:\Program Files\prism\`. The uninstaller
also removes Prism from the system `PATH`.

Linux: `pip uninstall prism-mcp` or remove the cloned directory.

## Prerequisites

The only runtime requirement is a reachable IRIS instance with the
Atelier REST API enabled. The SuperServer port (default `1972`) should
also be reachable for the native `prism terminal` command; if it isn't,
`prism ws` uses the Atelier WebSocket instead.

## Next steps

- [Quick Start](quick-start.md) — a five-minute tour of the CLI.
- [Configuration](configuration.md) — save your IRIS credentials once
  with `prism config`.
- [MCP Server](../mcp/index.md) — when you want Claude Code, Claude
  Desktop, or any other MCP client to drive Prism for you.