"""Prism CLI — Typer app that registers all subcommands."""

from __future__ import annotations

import os
from typing import Optional

# Disable Typer's Rich-based help formatting before typer is imported.
# Must be set before ``import typer`` so the module-level ``HAS_RICH`` flag
# in ``typer.core`` picks it up.
os.environ.setdefault("TYPER_USE_RICH", "false")

import typer  # noqa: E402

from prism.cli.commands.cast import cast_app  # noqa: E402
from prism.cli.commands.compile import compile as compile_cmd  # noqa: E402
from prism.cli.commands.config import config  # noqa: E402
from prism.cli.commands.documents import (  # noqa: E402
    delete_doc,
    get_doc,
    list_docs,
    put_doc,
)
from prism.cli.commands.serve import serve  # noqa: E402
from prism.cli.commands.server_info import info  # noqa: E402
from prism.cli.commands.index import index as index_cmd  # noqa: E402
from prism.cli.commands.sql import sql  # noqa: E402
from prism.cli.commands.terminal import terminal, ws  # noqa: E402
from prism.cli.commands.testing import list_tests, test  # noqa: E402
from prism.output import set_output_format  # noqa: E402


def _get_version() -> str:
    """Return the Prism version from __init__.__version__."""
    from prism import __version__

    return __version__


app = typer.Typer(
    name="prism",
    help="Prism — InterSystems IRIS CLI and MCP server.",
    no_args_is_help=True,
    add_completion=True,
    pretty_exceptions_enable=False,
)

app.command(name="config")(config)
app.add_typer(cast_app, name="cast")


@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    fmt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--format",
        help="Output format: json (default) or toon.",
    ),
    show_version: bool = typer.Option(  # noqa: UP007
        False,
        "--version",
        "-V",
        help="Show the Prism version and exit.",
        is_eager=True,
    ),
) -> None:
    """Global options applied before any subcommand."""
    if show_version:
        typer.echo(f"Prism {_get_version()}")
        raise typer.Exit()
    if fmt is not None:
        set_output_format(fmt)


app.command(name="sql")(sql)
app.command(name="terminal")(terminal)
app.command(name="ws")(ws)
app.command(name="compile")(compile_cmd)
app.command(name="get-doc")(get_doc)
app.command(name="list-docs")(list_docs)
app.command(name="put-doc")(put_doc)
app.command(name="delete-doc")(delete_doc)
app.command(name="info")(info)
app.command(name="test")(test)
app.command(name="list-tests")(list_tests)
app.command(name="index")(index_cmd)
app.command(name="serve")(serve)


def main() -> None:
    """Entry point for the `prism` console script."""
    app()


if __name__ == "__main__":
    main()
