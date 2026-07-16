"""`prism config` — view and edit Prism settings stored in ``config.json``."""

from __future__ import annotations

import typer

from prism.settings import (
    Settings,
    clear_config,
    config_path,
    reset_keys,
    save_config,
)

REDACTED = "***"
SECRET_FIELDS = {"iris_password"}

# Mapping from CLI flag names to Settings field names. Keep order roughly
# grouped: connection → mode → tunables — to read nicely in --help.
_FLAG_TO_FIELD: dict[str, str] = {
    "url": "iris_base_url",
    "user": "iris_username",
    "password": "iris_password",
    "namespace": "iris_namespace",
    "workspace": "iris_workspace",
    "super_port": "iris_superserver_port",
    "output_format": "prism_output_format",
    "debug": "iris_debug_enabled",
    "api_prefix": "iris_api_prefix",
    "compile_flags": "iris_compile_flags",
    "terminal_method": "iris_terminal_method",
    "terminal_max_output": "iris_terminal_max_output_chars",
    "test_runner": "iris_test_runner_class",
    "test_method": "iris_test_runner_method",
    "test_manager": "iris_test_manager_class",
    "test_auto_deploy": "iris_test_auto_deploy",
    "debug_granularity": "iris_debug_step_granularity",
    "debug_max_data": "iris_debug_max_data",
    "debug_max_children": "iris_debug_max_children",
    "debug_max_depth": "iris_debug_max_depth",
    "debug_idle_timeout": "iris_debug_idle_timeout",
}


def _format_value(name: str, value: object) -> str:
    """Render a value for display, redacting secrets and showing empty-strings."""
    if name in SECRET_FIELDS:
        return REDACTED
    if value == "":
        return "(unset)"
    return str(value)


def _coerce(field_name: str, raw: str) -> object:
    """Coerce *raw* CLI/prompt input to the field's annotated type."""
    ann = Settings.model_fields[field_name].annotation
    raw = raw.strip()
    if ann is bool:
        if raw.lower() in {"true", "1", "yes", "y", "on"}:
            return True
        if raw.lower() in {"false", "0", "no", "n", "off"}:
            return False
        raise ValueError(f"expected boolean, got {raw!r}")
    if ann is int:
        return int(raw)
    return raw


def _show_config() -> None:
    """Print all settings with their current effective values."""
    s = Settings()
    width = max(len(n) for n in Settings.model_fields)
    typer.echo(f"Config file: {config_path()}")
    typer.echo("")
    for name, field in Settings.model_fields.items():
        current = getattr(s, name)
        cur_str = _format_value(name, current)
        line = f"  {name:<{width}}  {cur_str}"
        if name not in SECRET_FIELDS and current != field.default:
            line += f"   (default: {_format_value(name, field.default)})"
        typer.echo(line)


def _interactive() -> None:
    """Walk through every field; let the user keep, change, or reset to default.

    Handles non-interactive stdin (piped input, EOF) gracefully by falling
    back to the current values instead of crashing with an EOFError.
    """
    s = Settings()
    fields = list(Settings.model_fields.items())
    updates: dict[str, object] = {}
    resets: list[str] = []

    typer.echo(f"Editing {config_path()}")
    typer.echo("For each setting choose: [k]eep, [c]hange, [d]efault\n")

    for idx, (name, field) in enumerate(fields, 1):
        current = getattr(s, name)
        typer.echo(f"[{idx}/{len(fields)}] {name}")
        typer.echo(f"        Default: {_format_value(name, field.default)}")
        typer.echo(f"        Current: {_format_value(name, current)}")

        try:
            choice = (
                typer.prompt(
                    "        [k]eep / [c]hange / [d]efault",
                    default="k",
                    show_default=False,
                )
                .strip()
                .lower()
                or "k"
            )
        except (EOFError, typer.Abort):
            typer.echo("\n  Input ended — keeping current values.\n")
            break

        if choice.startswith("k"):
            typer.echo("")
            continue
        if choice.startswith("d"):
            resets.append(name)
            typer.echo(
                f"        → reset to default ({_format_value(name, field.default)})\n"
            )
            continue
        if choice.startswith("c"):
            try:
                new_raw = typer.prompt(
                    "        New value", default="", show_default=False
                )
            except (EOFError, typer.Abort):
                typer.echo("\n  Input ended — keeping current.\n")
                break
            try:
                updates[name] = _coerce(name, new_raw)
                typer.echo("")
            except (ValueError, TypeError) as exc:
                typer.echo(f"        Invalid value ({exc}); keeping current\n")
            continue
        typer.echo("        Unrecognized; keeping current\n")

    typer.echo("")
    if resets:
        reset_keys(resets)
        typer.echo(f"Reset {len(resets)} setting(s) to default")
    if updates:
        save_config(updates)
        typer.echo(f"Saved {len(updates)} update(s)")
    if not resets and not updates:
        typer.echo("No changes")


def config(
    # ── Connection ──────────────────────────────────────────────────
    url: str | None = typer.Option(None, "-U", "--url", help="IRIS base URL"),
    user: str | None = typer.Option(None, "-u", "--user", help="IRIS username"),
    password: str | None = typer.Option(None, "-p", "--password", help="IRIS password"),
    namespace: str | None = typer.Option(
        None, "-n", "--namespace", help="Default IRIS namespace"
    ),
    workspace: str | None = typer.Option(
        None, "-w", "--workspace", help="Local workspace directory for file I/O tools"
    ),
    super_port: int | None = typer.Option(
        None, "-P", "--super-port", help="SuperServer port (native terminal)"
    ),
    # ── Mode ────────────────────────────────────────────────────────
    output_format: str | None = typer.Option(
        None, "-f", "--output-format", help="Persistent output format: json or toon"
    ),
    debug: bool | None = typer.Option(
        None, "--debug/--no-debug", help="Enable IRIS debugger tools"
    ),
    # ── Tunables ────────────────────────────────────────────────────
    api_prefix: str | None = typer.Option(
        None, "--api-prefix", help="Atelier REST API path prefix"
    ),
    compile_flags: str | None = typer.Option(
        None, "--compile-flags", help="Default compiler flags (e.g. cuk)"
    ),
    terminal_method: str | None = typer.Option(
        None, "--terminal-method", help="Terminal backend: native or websocket"
    ),
    terminal_max_output: int | None = typer.Option(
        None, "--terminal-max-output", help="Max chars of terminal output"
    ),
    test_runner: str | None = typer.Option(
        None, "--test-runner", help="Test runner class name"
    ),
    test_method: str | None = typer.Option(
        None, "--test-method", help="Test runner classmethod name"
    ),
    test_manager: str | None = typer.Option(
        None, "--test-manager", help="Default %UnitTest manager class"
    ),
    test_auto_deploy: bool | None = typer.Option(
        None,
        "--test-auto-deploy/--no-test-auto-deploy",
        help="Auto-deploy the test runner on first use",
    ),
    debug_granularity: str | None = typer.Option(
        None, "--debug-granularity", help="DBGp step granularity (line, statement)"
    ),
    debug_max_data: int | None = typer.Option(
        None, "--debug-max-data", help="Max bytes per debug variable value"
    ),
    debug_max_children: int | None = typer.Option(
        None, "--debug-max-children", help="Max child variables shown per object"
    ),
    debug_max_depth: int | None = typer.Option(
        None, "--debug-max-depth", help="Max recursion depth for variable display"
    ),
    debug_idle_timeout: int | None = typer.Option(
        None, "--debug-idle-timeout", help="Idle timeout for debug sessions (seconds)"
    ),
    # ── Mode flags ──────────────────────────────────────────────────
    interactive: bool = typer.Option(
        False, "-i", "--interactive", help="Walk through every setting"
    ),
    reset: list[str] = typer.Option(
        [],
        "-r",
        "--reset",
        help="Reset KEY to its default (remove from config.json). Repeatable.",
    ),
    reset_all: bool = typer.Option(
        False, "--reset-all", help="Wipe config.json entirely"
    ),
) -> None:
    """View or edit Prism settings.

    With no arguments, prints all 21 settings with their current effective
    values. Use one or more setting flags to update specific fields, ``-i``
    for an interactive walkthrough, or ``-r KEY`` to reset a single key
    to its default.
    """
    if reset_all:
        path = clear_config()
        typer.echo(f"Cleared {path}")
        return

    if reset:
        unknown = [k for k in reset if k not in Settings.model_fields]
        if unknown:
            typer.echo(f"Unknown setting(s): {', '.join(unknown)}", err=True)
            raise typer.Exit(code=1)
        path = reset_keys(reset)
        typer.echo(f"Reset {len(reset)} setting(s) in {path}")
        return

    if interactive:
        _interactive()
        return

    locals_ = locals()
    updates: dict[str, object] = {
        field: locals_[flag]
        for flag, field in _FLAG_TO_FIELD.items()
        if locals_[flag] is not None
    }

    # Validate output_format if being set
    if "prism_output_format" in updates:
        fmt_val = str(updates["prism_output_format"]).strip().lower()
        valid_formats = ("json", "toon")
        if fmt_val not in valid_formats:
            typer.echo(
                f"Error: Invalid output format '{updates['prism_output_format']}'. "
                f"Supported formats: {', '.join(valid_formats)}.",
                err=True,
            )
            raise typer.Exit(code=1)
        updates["prism_output_format"] = fmt_val

    # Validate terminal_method if being set
    if "iris_terminal_method" in updates:
        method_val = str(updates["iris_terminal_method"]).strip().lower()
        valid_methods = ("native", "websocket")
        if method_val not in valid_methods:
            typer.echo(
                f"Error: Invalid terminal method '{updates['iris_terminal_method']}'. "
                f"Supported methods: {', '.join(valid_methods)}.",
                err=True,
            )
            raise typer.Exit(code=1)
        updates["iris_terminal_method"] = method_val

    if not updates:
        _show_config()
        return

    path = save_config(updates)
    typer.echo(f"Saved {len(updates)} setting(s) to {path}")
    for key, value in updates.items():
        display = REDACTED if key in SECRET_FIELDS else value
        typer.echo(f"  {key}: {display}")
