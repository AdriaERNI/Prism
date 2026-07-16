"""Prism CLI — Typer app that registers all subcommands."""

from __future__ import annotations

import os
from typing import Optional

# Disable Typer's Rich-based help formatting before typer is imported.
# Must be set before ``import typer`` so the module-level ``HAS_RICH`` flag
# in ``typer.core`` picks it up.
os.environ.setdefault("TYPER_USE_RICH", "false")

import typer  # noqa: E402

from prism.cli.commands.cast import cast  # noqa: E402
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
from prism.cli.commands.sql import sql  # noqa: E402
from prism.cli.commands.terminal import terminal, ws  # noqa: E402
from prism.cli.commands.testing import list_tests, test  # noqa: E402
from prism.output import set_output_format  # noqa: E402


def _main_callback(
    ctx: typer.Context,
    fmt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--format",
        help="Output format: json (default) or toon.",
    ),
) -> None:
    """Global options applied before any subcommand."""
    if fmt is not None:
        set_output_format(fmt)


app = typer.Typer(
    name="prism",
    help="Prism — InterSystems IRIS CLI and MCP server.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    callback=_main_callback,
)

app.command(name="config")(config)
app.command(name="cast", context_settings={"allow_extra_args": True})(cast)
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
app.command(name="serve")(serve)


def main() -> None:
    """Entry point for the `prism` console script."""
    app()


if __name__ == "__main__":
    main()
