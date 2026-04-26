"""`prism config` — store IRIS connection settings in the user data directory."""

from __future__ import annotations

import typer

from prism.settings import save_config


def config(
    username: str = typer.Argument(..., help="IRIS username (e.g. _SYSTEM)"),
    password: str = typer.Argument(..., help="IRIS password"),
    url: str = typer.Argument(
        ..., help="IRIS base URL (e.g. http://192.168.1.100:52773)"
    ),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Default namespace (defaults to USER)"
    ),
    superserver_port: int = typer.Option(
        None,
        "--superserver-port",
        "-p",
        help="SuperServer port for native terminal (defaults to 1972)",
    ),
    show: bool = typer.Option(
        False, "--show", help="Print the saved settings (password redacted)"
    ),
) -> None:
    """Save IRIS connection settings to ``config.json`` in the user data directory.

    Overrides previous values key-by-key — unspecified options keep their current value.
    """
    updates: dict[str, object] = {
        "iris_username": username,
        "iris_password": password,
        "iris_base_url": url,
    }
    if namespace is not None:
        updates["iris_namespace"] = namespace
    if superserver_port is not None:
        updates["iris_superserver_port"] = superserver_port

    path = save_config(updates)
    typer.echo(f"Saved settings to {path}")

    if show:
        redacted = {**updates, "iris_password": "***"}
        for key, value in redacted.items():
            typer.echo(f"  {key}: {value}")
