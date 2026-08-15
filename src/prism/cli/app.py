"""Prism CLI — Typer app that registers all subcommands."""

from __future__ import annotations

import os

# Disable Typer's Rich-based help formatting before typer is imported.
# Must be set before ``import typer`` so the module-level ``HAS_RICH`` flag
# in ``typer.core`` picks it up.
os.environ.setdefault("TYPER_USE_RICH", "false")

import typer

from prism.cli.commands.cast import cast_app
from prism.cli.commands.chatbot import chatbot
from prism.cli.commands.compile import compile as compile_cmd
from prism.cli.commands.config import config
from prism.cli.commands.documents import (
    delete_doc,
    get_doc,
    list_docs,
    put_doc,
)
from prism.cli.commands.gui import gui
from prism.cli.commands.index import (
    index as index_cmd,
)
from prism.cli.commands.index import (
    index_impact,
    index_node,
    index_path,
    index_refs,
    index_search,
    index_status,
)
from prism.cli.commands.install import install
from prism.cli.commands.monitor import monitor
from prism.cli.commands.serve import serve
from prism.cli.commands.server_info import info
from prism.cli.commands.sql import sql
from prism.cli.commands.terminal import terminal, ws
from prism.cli.commands.testing import list_tests, test
from prism.output import set_output_format


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
    fmt: str | None = typer.Option(
        None,
        "--format",
        help="Output format: json (default) or toon.",
    ),
    show_version: bool = typer.Option(
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
app.command(name="index-search")(index_search)
app.command(name="index-node")(index_node)
app.command(name="index-refs")(index_refs)
app.command(name="index-impact")(index_impact)
app.command(name="index-path")(index_path)
app.command(name="index-status")(index_status)
app.command(name="serve")(serve)
app.command(name="setup")(install)
app.command(name="gui")(gui)
app.command(name="chatbot")(chatbot)
app.command(name="monitor")(monitor)


def main() -> None:
    """Entry point for the `prism` console script."""
    # On Windows frozen exes, sys.argv[0] is "prism.exe" and Click
    # derives prog_name from it, registering Tab completion for
    # "prism.exe" instead of "prism".  Override so users can type
    # `prism` + Tab to auto-complete.
    app(prog_name="prism")


if __name__ == "__main__":
    main()
