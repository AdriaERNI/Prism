"""`prism config` — store IRIS connection settings in the user config directory."""

from __future__ import annotations

import typer

from prism.iris.settings import load_settings, save_settings


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
    """Save IRIS connection settings to the platform user config directory.

    Overrides previous values key-by-key — unspecified options keep their current value.
    """
    data = load_settings()
    data["username"] = username
    data["password"] = password
    data["url"] = url
    if namespace is not None:
        data["namespace"] = namespace
    if superserver_port is not None:
        data["superserver_port"] = superserver_port

    path = save_settings(data)
    typer.echo(f"Saved settings to {path}")

    if show:
        redacted = {**data, "password": "***"}
        for key, value in redacted.items():
            typer.echo(f"  {key}: {value}")
