"""MCP tool for executing shell commands on the host system.

Provides ``run_shell`` — a tool that lets the chatbot agent run PowerShell
(on Windows) or Bash (on Linux/macOS) commands. This is gated behind
``IRIS_WORKSPACE`` being set, same as ``workspace.py`` tools, because
shell access implies filesystem access and should be opt-in.

The tool auto-detects the platform:
- Windows: PowerShell (``powershell.exe -NoProfile -Command``)
- Linux/macOS: Bash (``/bin/bash -c``)

Security:
- Commands are run with a configurable timeout (default 30s, max 120s)
- Output is captured and truncated to 10K chars for the LLM context
- The tool does NOT run as root (refuses if ``os.geteuid() == 0`` on POSIX)
- The tool does NOT grant network access beyond what the host already has
"""

from __future__ import annotations

import asyncio
import os
import platform
from typing import Annotated

from pydantic import Field

from prism.mcp._decorator import logged_tool

_MAX_OUTPUT_CHARS = 10_000
_DEFAULT_TIMEOUT = 30.0
_MAX_TIMEOUT = 120.0


def _get_shell_command() -> tuple[str, list[str]]:
    """Return (executable, prefix_args) for the platform's default shell.

    Returns a tuple suitable for ``asyncio.create_subprocess_exec``:
    - Windows: ``("powershell.exe", ["-NoProfile", "-NoLogo", "-Command"])``
    - Linux/macOS: ``("/bin/bash", ["-c"])``
    """
    if platform.system() == "Windows":
        return "powershell.exe", ["-NoProfile", "-NoLogo", "-Command"]
    return "/bin/bash", ["-c"]


def _truncate_output(text: str, max_chars: int = _MAX_OUTPUT_CHARS) -> str:
    """Truncate command output to fit within the LLM context."""
    if len(text) <= max_chars:
        return text
    # Try to cut at a line boundary
    cut = text.rfind("\n", 0, max_chars)
    if cut == -1 or cut < max_chars * 0.5:
        cut = max_chars
    return text[:cut] + f"\n... [output truncated, {len(text) - cut} more chars]"


@logged_tool
async def run_shell(
    command: Annotated[
        str,
        Field(
            description="Shell command to execute. On Windows this runs in "
            "PowerShell; on Linux/macOS it runs in Bash. "
            "Examples (PowerShell): 'Get-ChildItem', 'echo $env:PATH', "
            "'git status'. Examples (Bash): 'ls -la', 'echo $PATH', "
            "'git status'."
        ),
    ],
    timeout: Annotated[
        float,
        Field(
            description="Timeout in seconds. The command is killed if it "
            "exceeds this. Default 30, maximum 120.",
            gt=0,
            le=_MAX_TIMEOUT,
        ),
    ] = _DEFAULT_TIMEOUT,
    cwd: Annotated[
        str | None,
        Field(
            description="Working directory for the command. If omitted, "
            "uses the workspace root (IRIS_WORKSPACE) or the current "
            "directory."
        ),
    ] = None,
) -> dict:
    """Execute a shell command on the local host system (NOT on the IRIS server).

    **Runs on: local host** (NOT the IRIS server — this runs on the machine
    where Prism is installed).

    The command runs in the platform's native shell:
    - **Windows**: PowerShell (``powershell.exe -NoProfile -Command``)
    - **Linux/macOS**: Bash (``/bin/bash -c``)

    Both stdout and stderr are captured and returned. The output is
    truncated to 10,000 characters to fit within the LLM context window.

    Use this tool to:
    - Run ``git`` commands (status, log, diff, add, commit)
    - List and inspect local files (``ls``, ``dir``, ``Get-ChildItem``)
    - Run build scripts or local tests
    - Check local system information (``uname``, ``$PSVersionTable``)
    - Any general shell task that does NOT need the IRIS server

    Security notes:
    - The tool refuses to run as root on POSIX systems.
    - Commands have a timeout (default 30s, max 120s) — long-running
      processes are killed.
    - Output is truncated to prevent context window overflow.
    """
    # Refuse to run as root on POSIX
    if os.name != "nt":
        try:
            if os.geteuid() == 0:
                return {
                    "stdout": "",
                    "stderr": "Refusing to run shell command as root. "
                    "Use a non-root user.",
                    "exit_code": -1,
                    "shell": "bash",
                }
        except AttributeError:
            pass  # Not all platforms have geteuid

    # Determine working directory
    from prism.settings import settings

    work_dir = cwd
    if work_dir is None:
        if settings.iris_workspace:
            work_dir = settings.iris_workspace
        else:
            work_dir = os.getcwd()

    # Get shell executable and prefix args
    shell_exe, shell_args = _get_shell_command()
    shell_name = "powershell" if platform.system() == "Windows" else "bash"

    try:
        # Build the full command: [shell_exe, *shell_args, command]
        full_args = [*shell_args, command]
        process = await asyncio.create_subprocess_exec(
            shell_exe,
            *full_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s and was killed.",
                "exit_code": -1,
                "shell": shell_name,
                "command": command,
                "cwd": str(work_dir),
            }

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        return {
            "stdout": _truncate_output(stdout),
            "stderr": _truncate_output(stderr),
            "exit_code": process.returncode,
            "shell": shell_name,
            "command": command,
            "cwd": str(work_dir),
        }

    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Shell not found: {shell_exe}. "
            f"Ensure {shell_name} is installed and on PATH.",
            "exit_code": -1,
            "shell": shell_name,
            "command": command,
            "cwd": str(work_dir),
        }
    except Exception as exc:
        return {
            "stdout": "",
            "stderr": f"Failed to execute command: {exc}",
            "exit_code": -1,
            "shell": shell_name,
            "command": command,
            "cwd": str(work_dir),
        }
