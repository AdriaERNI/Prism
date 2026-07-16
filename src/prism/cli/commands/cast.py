"""`prism cast` — manage and run custom command repositories.

Cast repos are Python packages that expose a Typer ``app`` and
``__prism_name__`` in their root ``__init__.py``.  They are registered
as dynamic sub-groups of this sub-app, so each command gets proper
arg parsing, ``--help``, and shell completion.

Usage::

    prism cast --add <url>            Clone + register a cast repo
    prism cast --list                  List registered repos
    prism cast --del <N>               Delete repo #N
    prism cast --update               Pull latest + refresh metadata
    prism cast <name>                  Show help for a cast repo
    prism cast <name> <cmd> [args]     Run a command
"""

from __future__ import annotations

import sys

import typer

from prism.cast import manager

# ── Cast sub-app (a Typer group, not a single command) ──────────────

cast_app = typer.Typer(
    name="cast",
    help="Manage and run custom command repositories (casts).",
    no_args_is_help=False,
    add_completion=False,
)


@cast_app.callback(invoke_without_command=True)
def cast_callback(
    ctx: typer.Context,
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
        help="Pull latest changes + refresh metadata.",
    ),
) -> None:
    """Manage and run custom command repositories (casts)."""
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
        if repo.commands:
            typer.echo(f"  Commands: {', '.join(c.name for c in repo.commands)}")
        else:
            typer.echo("  (no commands found)")
        return

    if list_repos:
        repos = manager.list_repos()
        if not repos:
            typer.echo("No cast repos registered. Add one with: prism cast --add <url>")
            return
        typer.echo(f"{'#':>3}  {'Name':<20} {'Description':<35} Commands")
        typer.echo(f"{'-' * 3}  {'-' * 20} {'-' * 35} {'-' * 40}")
        for i, repo in enumerate(repos, 1):
            desc = repo.description or ""
            cmds = ", ".join(c.name for c in repo.commands) or "(none)"
            typer.echo(f"{i:>3}  {repo.name:<20} {desc:<35} {cmds}")
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
            typer.echo(f"  {name:<20} {status}")
        return


# ── Dynamic registration of cast repos as sub-groups ────────────────


def _register_cast_repos() -> None:
    """Register each cast repo as a lazy sub-group of cast_app.

    Called once at import time.  Reads the registry only (no imports).
    Each sub-group delegates to the cast's Typer app on first invocation.
    """
    for repo in manager.list_repos():
        _register_lazy_repo(repo.name, repo.description, repo.commands)


def _register_lazy_repo(name: str, description: str, commands: list) -> None:
    """Register a single cast repo as a lazy Typer sub-group."""
    # Skip re-registration (e.g. on hot reload)
    registered = {grp.name for grp in cast_app.registered_groups}
    if name in registered:
        return

    repo_typer = typer.Typer(
        name=name,
        help=description or f"Cast repo: {name}",
        no_args_is_help=True,
        add_completion=False,
    )

    # If we have cached commands, register stub functions so --help and
    # completion work without importing the repo.
    for cmd_info in commands:
        cmd_name = cmd_info.name if hasattr(cmd_info, "name") else cmd_info["name"]
        cmd_help = (
            cmd_info.help if hasattr(cmd_info, "help") else cmd_info.get("help", "")
        )
        _register_lazy_command(repo_typer, name, cmd_name, cmd_help)

    cast_app.add_typer(repo_typer, name=name)


def _register_lazy_command(
    repo_typer: typer.Typer,
    repo_name: str,
    cmd_name: str,
    cmd_help: str,
) -> None:
    """Register a stub command that lazy-imports and delegates on execution."""

    @repo_typer.command(name=cmd_name, help=cmd_help or None)
    def _lazy_cmd(
        ctx: typer.Context,
        args: list[str] = typer.Argument(
            None, help="Arguments passed to the command.", metavar="..."
        ),
    ) -> None:
        """{cmd_help}"""
        extra = list(ctx.args) if ctx.args else []
        all_args = [cmd_name] + (args or []) + extra
        exit_code = manager.run_command(repo_name, all_args)
        if exit_code != 0:
            sys.exit(exit_code)

    # Pyright complains about the __doc__ assignment; use setattr
    setattr(_lazy_cmd, "__doc__", cmd_help or None)


# Register on import
_register_cast_repos()
