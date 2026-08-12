"""Startup-time regression tests.

These guard the lazy-import optimization for the PyInstaller frozen exe.
The heavy dependencies (pydantic_settings, rich) were previously imported
at the top of several CLI command modules, so *any* Prism invocation paid
their import cost even when the command being run didn't need them.

With the refactor, those imports moved inside the command functions:

  * ``prism.cli.commands.chatbot``  → no longer imports prism.settings
                                     (pydantic_settings) at module load
  * ``prism.cli.commands.config``   → same
  * ``prism.cli.commands.monitor``  → no longer imports rich dashboard at
                                     module load
  * ``prism.cli.errors``            → httpx imported only in the handler
  * ``prism.output``                → prism.settings imported on first read

We assert on the *import graph* (deterministic, fast) rather than wall
clock, which is noisy on CI. On Windows the real win is measured with
``Measure-Command { prism.exe --help }``.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _loaded_top_packages(code: str) -> set[str]:
    """Import the given module expression in a fresh subprocess and return
    the set of newly-loaded top-level packages."""
    script = f"""
import sys
before = set(sys.modules)
{code}
after = set(sys.modules)
tops = {{m.split('.')[0] for m in (after - before) if m}}
print(','.join(sorted(tops)))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={"PYTHONPATH": ""},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return set(proc.stdout.strip().split(",")) if proc.stdout.strip() else set()


def test_import_monitor_does_not_load_dashboard():
    """`prism monitor` is the only command that renders a rich dashboard.

    The ``prism.iris.monitor.dashboard`` module (which imports the heavy
    ``rich`` panels/tables/Live) is deferred to inside ``_run_dashboard()``.
    Note: ``rich`` itself is loaded transitively by ``typer`` (for syntax
    highlighting), so we assert on the *dashboard* module — the thing we
    actually deferred — not on ``rich``.
    """
    loaded = _loaded_top_packages("import prism.cli.commands.monitor")
    assert "dashboard" not in loaded, f"dashboard loaded by monitor import: {sorted(loaded)}"


def test_import_chatbot_does_not_load_pydantic_settings():
    """`prism chatbot` is the only command needing LLM config settings.

    ``prism.settings`` (and its pydantic_settings dependency, ~85ms) is
    imported lazily inside the chatbot command functions, so importing
    the chatbot module must not pull it.
    """
    loaded = _loaded_top_packages("import prism.cli.commands.chatbot")
    assert "pydantic_settings" not in loaded, (
        f"pydantic_settings loaded by chatbot import: {sorted(loaded)}"
    )


def test_import_config_does_not_load_pydantic_settings():
    """The `prism config` command module defers prism.settings to functions."""
    loaded = _loaded_top_packages("import prism.cli.commands.config")
    assert "pydantic_settings" not in loaded, (
        f"pydantic_settings loaded by config import: {sorted(loaded)}"
    )


def test_import_errors_does_not_load_httpx():
    """prism.cli.errors defers httpx import to inside handle_command_error.

    httpx is a ~50ms import and is only needed when an IRIS connection
    error is actually printed.
    """
    loaded = _loaded_top_packages("import prism.cli.errors")
    assert "httpx" not in loaded, f"httpx loaded by errors import: {sorted(loaded)}"


def test_import_output_does_not_load_pydantic_settings():
    """prism.output defers prism.settings to first read of the format."""
    loaded = _loaded_top_packages("import prism.output")
    assert "pydantic_settings" not in loaded, (
        f"pydantic_settings loaded by output import: {sorted(loaded)}"
    )
