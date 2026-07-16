"""`prism cast` — manage and run custom command repositories.

Usage::

    prism cast --add <git-url>       Clone a cast repo
    prism cast --list                List registered repos
    prism cast --del <N>             Delete repo #N
    prism cast --update              Pull latest for all repos
    prism cast <repo>.<command>      Run a command from a repo
    prism cast <repo>.<cmd> args...  Pass extra arguments to the command
"""

from __future__ import annotations

import sys

import typer

from prism.cast import manager


def cast(
    ctx: typer.Context,
    target: str | None = typer.Argument(
        None,
        help="Command to run as '<repo>.<command>' (e.g. template.weather)",
    ),
    add: str | None = typer.Option(
        None,
        "--add",
        help="Clone a Git repository as a cast repo.",
    ),
    list_repos: bool = typer.Option(
        False,
        "--list",
        help="List all registered cast repos.",
    ),
    delete: int | None = typer.Option(
        None,
        "--del",
        help="Delete repo by 1-based index (see --list).",
    ),
    update: bool = typer.Option(
        False,
        "--update",
        help="Pull latest changes for all repos.",
    ),
) -> None:
    """Manage and run custom command repositories (casts).

    Repos are Git repos with scripts in a ``commands/`` directory.
    Each repo can include a ``cast.json`` with a custom ``name`` alias,
    descriptions, and command metadata.

    \b
    Examples:
      prism cast --add https://github.com/user/Prism-CastTemplate.git
      prism cast --list
      prism cast template.weather
      prism cast template.portcheck example.com 443
      prism cast --del 1
    """
    extra_args: list[str] = list(ctx.args)

    # ── Mutating options take priority ───────────────────────────────

    if add is not None:
        try:
            repo = manager.add_repo(add)
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
            sys.exit(1)
        typer.echo(f"Added '{repo.name}' from {repo.url}")
        typer.echo(f"  Path: {repo.path}")
        if repo.description:
            typer.echo(f"  Description: {repo.description}")
        cmds = manager.discover_commands(repo.path)
        if cmds:
            typer.echo(f"  Commands: {', '.join(sorted(cmds))}")
        else:
            typer.echo("  (no commands found)")
        return

    if list_repos:
        repos = manager.list_repos()
        if not repos:
            typer.echo("No cast repos registered. Add one with: prism cast --add <url>")
            return
        typer.echo(f"{'#':>3}  {'Name':<30} {'Description':<30} URL")
        typer.echo(f"{'─' * 3}  {'─' * 30} {'─' * 30} {'─' * 40}")
        for i, repo in enumerate(repos, 1):
            desc = repo.description or ""
            typer.echo(f"{i:>3}  {repo.name:<30} {desc:<30} {repo.url}")
        return

    if delete is not None:
        try:
            repo = manager.del_repo(delete)
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
            sys.exit(1)
        typer.echo(f"Deleted '{repo.name}' (was {repo.url})")
        return

    if update:
        results = manager.update_repos()
        if not results:
            typer.echo("No cast repos to update.")
            return
        for name, status in results:
            typer.echo(f"  {name:<30} {status}")
        return

    # ── Run mode: target must be <repo>.<command> ────────────────────

    if target is None:
        typer.echo(
            "Usage: prism cast <repo>.<command>\n"
            "      prism cast --add <url>\n"
            "      prism cast --list\n"
            "      prism cast --del <N>\n"
            "      prism cast --update\n"
            "\nRun 'prism cast --help' for details.",
            err=True,
        )
        sys.exit(1)

    if "." not in target:
        typer.echo(
            f"Error: '{target}' must be '<repo>.<command>' (e.g. template.weather)",
            err=True,
        )
        sys.exit(1)

    repo_slug, command_name = target.rsplit(".", 1)

    try:
        exit_code = manager.run_command(repo_slug, command_name, extra_args)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    sys.exit(exit_code)
