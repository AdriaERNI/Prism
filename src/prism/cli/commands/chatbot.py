"""`prism chatbot` — interactive AI agent that orchestrates Prism tools.

The chatbot connects to an OpenAI-compatible LLM API and exposes all
Prism MCP tools as function-calling capabilities.  The LLM decides which
tools to call and in what order based on the user's natural-language
request.

In interactive REPL mode, the agent is created once and reused across
turns, preserving conversation history for multi-turn interactions.

Configuration:
    The API URL, key, model, and skills path are read from (in order):
    1. Command-line flags (``--api-url``, ``--api-key``, ``--model``, ``--skills-path``)
    2. Environment variables (``CHATBOT_API_URL``, ``CHATBOT_API_KEY``, …)
    3. ``config.json`` (written by ``prism config --chatbot-api-url …``)
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from prism.settings import settings, save_config

_ANSI_RESET = "\x1b[0m"
_ANSI_BOLD = "\x1b[1m"
_ANSI_DIM = "\x1b[2m"
_ANSI_CYAN = "\x1b[36m"
_ANSI_GREEN = "\x1b[32m"
_ANSI_RED = "\x1b[31m"

# Local commands for the interactive REPL
_EXIT_COMMANDS = {"exit", "quit", "q", "/exit", "/quit"}
_HELP_COMMANDS = {"help", "?", "/help"}
_CLEAR_COMMANDS = {"clear", "/clear", "/reset"}


def _print_banner() -> None:
    """Print the startup banner."""
    version = _get_version()
    typer.echo(
        f"{_ANSI_CYAN}{_ANSI_BOLD}Prism {_ANSI_RESET}"
        f"{_ANSI_CYAN}{version}{_ANSI_RESET} — Chatbot Agent"
    )

    # Show connection info
    api_url = settings.chatbot_api_url or "(not set)"
    model = settings.chatbot_model or "gpt-4o"
    skills = settings.chatbot_skills_path or "(not set)"

    typer.echo(f"{_ANSI_DIM}  LLM API: {api_url}{_ANSI_RESET}")
    typer.echo(f"{_ANSI_DIM}  Model:   {model}{_ANSI_RESET}")
    typer.echo(f"{_ANSI_DIM}  Skills:  {skills}{_ANSI_RESET}")
    typer.echo(
        f"{_ANSI_DIM}  Type 'help' for commands, 'clear' to reset context, 'exit' to quit.{_ANSI_RESET}\n"
    )


def _get_version() -> str:
    from prism import __version__

    return __version__


def _print_help() -> None:
    """Print help text for REPL commands."""
    typer.echo(f"\n{_ANSI_BOLD}Prism Chatbot — Commands{_ANSI_RESET}")
    typer.echo(f"  {'Command':<12} {'Description'}")
    typer.echo(f"  {'-' * 12} {'-' * 40}")
    typer.echo(f"  {'exit':<12} Exit the chatbot session")
    typer.echo(f"  {'help':<12} Show this help message")
    typer.echo(f"  {'clear':<12} Clear conversation history (reset context)")
    typer.echo()
    typer.echo("  Type any natural-language request and the agent will use the")
    typer.echo("  available Prism tools to fulfil it.\n")


def _save_config_from_flags(
    api_url: str | None,
    api_key: str | None,
    model: str | None,
    skills_path: str | None,
) -> bool:
    """Persist any provided flags to config.json. Returns True if anything was saved."""
    updates: dict[str, object] = {}
    if api_url is not None:
        updates["chatbot_api_url"] = api_url.rstrip("/")
    if api_key is not None:
        updates["chatbot_api_key"] = api_key
    if model is not None:
        updates["chatbot_model"] = model
    if skills_path is not None:
        updates["chatbot_skills_path"] = skills_path

    if updates:
        save_config(updates)
        return True
    return False


async def _run_agent_once(
    user_message: str,
    api_url: str | None,
    api_key: str | None,
    model: str | None,
    skills_path: str | None,
) -> str:
    """Run a single agent turn (one-shot mode) and return the response.

    Creates a fresh agent with no conversation history.
    """
    from prism.chatbot.agent import ChatbotAgent

    agent = ChatbotAgent(
        api_url=api_url,
        api_key=api_key,
        model=model,
        skills_path=skills_path,
    )
    return await agent.run(user_message)


def chatbot(
    message: str | None = typer.Argument(
        None,
        help="One-shot message. If omitted, starts an interactive REPL.",
    ),
    api_url: str | None = typer.Option(
        None,
        "--api-url",
        help="OpenAI-compatible API base URL (e.g. https://api.openai.com/v1).",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="API key for the LLM provider.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Model name (default: gpt-4o).",
    ),
    skills_path: str | None = typer.Option(
        None,
        "--skills-path",
        help="Path to a folder of markdown skill files to inject into the system prompt.",
    ),
    save: bool = typer.Option(
        True,
        "--save/--no-save",
        help="Persist provided --api-url/--api-key/--model/--skills-path to config.json (default: save).",
    ),
    list_skills: bool = typer.Option(
        False,
        "--list-skills",
        help="List skill files found in the configured skills path and exit.",
    ),
) -> None:
    """Start an AI chatbot agent that orchestrates Prism's MCP tools.

    The agent connects to an OpenAI-compatible LLM API and provides all
    Prism MCP tools (SQL, documents, terminal, testing, etc.) as
    function-calling capabilities.  The LLM decides which tools to call
    and in what order.

    \b
    Examples:
        # Interactive mode (REPL with conversation memory)
        prism chatbot --api-url https://api.openai.com/v1 --api-key sk-... --skills-path ./skills

        # One-shot mode
        prism chatbot "What tables exist in the USER namespace?"

        # List loaded skills
        prism chatbot --list-skills

    \b
    Configuration is read from (in order of precedence):
    1. Command-line flags (--api-url, --api-key, --model, --skills-path)
    2. Environment variables (CHATBOT_API_URL, CHATBOT_API_KEY, CHATBOT_MODEL, CHATBOT_SKILLS_PATH)
    3. config.json (written by: prism config --chatbot-api-url <url> ...)
    """
    # Resolve effective values for display
    effective_api_url = api_url or settings.chatbot_api_url
    effective_api_key = api_key or settings.chatbot_api_key
    effective_skills = skills_path or settings.chatbot_skills_path

    # --list-skills: list and exit
    if list_skills:
        from prism.chatbot.skills import list_skills as _list_skills_func

        skills_list = _list_skills_func(effective_skills)
        if not skills_list:
            typer.echo("No skills found.")
            if not effective_skills:
                typer.echo(
                    "No skills path configured. Set one with --skills-path "
                    "or: prism config --chatbot-skills-path <dir>",
                    err=True,
                )
            raise typer.Exit()

        typer.echo(f"Skills folder: {effective_skills}")
        typer.echo(f"Found {len(skills_list)} skill(s):\n")
        for s in skills_list:
            typer.echo(f"  {s['name']:<30} {s['size']}")
        raise typer.Exit()

    # Save provided flags to config.json for future runs
    if save:
        _save_config_from_flags(api_url, api_key, model, skills_path)

    # Validate configuration before starting
    if not effective_api_url:
        typer.echo(
            "Error: No chatbot API URL configured.\n"
            "Set it with:\n"
            "  prism config --chatbot-api-url <url>\n"
            "  CHATBOT_API_URL=<url> prism chatbot\n"
            "  prism chatbot --api-url <url>",
            err=True,
        )
        raise typer.Exit(code=1)

    if not effective_api_key:
        typer.echo(
            "Error: No chatbot API key configured.\n"
            "Set it with:\n"
            "  prism config --chatbot-api-key <key>\n"
            "  CHATBOT_API_KEY=<key> prism chatbot\n"
            "  prism chatbot --api-key <key>",
            err=True,
        )
        raise typer.Exit(code=1)

    # One-shot mode: send a single message and print the response
    if message:
        try:
            response = asyncio.run(
                _run_agent_once(message, api_url, api_key, model, skills_path)
            )
            typer.echo(response)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)
        return

    # Interactive REPL mode
    _print_banner()
    _run_interactive(api_url, api_key, model, skills_path)


def _run_interactive(
    api_url: str | None,
    api_key: str | None,
    model: str | None,
    skills_path: str | None,
) -> None:
    """Run the interactive chatbot REPL loop.

    Creates a single ChatbotAgent that persists across all turns,
    preserving conversation history for multi-turn interactions.
    The MCP connection, tool discovery, and HTTP client are all
    performed once inside a single asyncio.run() call so that
    httpx connections share the same event loop.
    """
    asyncio.run(_async_repl(api_url, api_key, model, skills_path))


async def _async_repl(
    api_url: str | None,
    api_key: str | None,
    model: str | None,
    skills_path: str | None,
) -> None:
    """Async REPL loop — runs in a single event loop for the whole session."""
    from prism.chatbot.agent import ChatbotAgent

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.history import FileHistory

        from platformdirs import user_data_path

        data_dir = user_data_path("prism", appauthor=False)
        data_dir.mkdir(parents=True, exist_ok=True)
        history_file = data_dir / "chatbot_history"

        prompt_session: PromptSession | None = PromptSession(
            history=FileHistory(str(history_file)),
        )
        prompt_html: Any = HTML
    except ImportError:
        prompt_session = None
        prompt_html = None

    agent = ChatbotAgent(
        api_url=api_url,
        api_key=api_key,
        model=model,
        skills_path=skills_path,
    )

    async with agent:
        typer.echo(
            f"{_ANSI_DIM}  Connected to MCP server, "
            f"{len(agent._tools)} tools available.{_ANSI_RESET}\n"
        )

        while True:
            try:
                if prompt_session is not None:
                    user_input = await prompt_session.prompt_async(
                        prompt_html("<b><ansigreen>you> </ansigreen></b>")
                    )
                else:
                    # Fallback: input() is blocking but works outside PTY
                    user_input = input(f"{_ANSI_BOLD}{_ANSI_GREEN}you> {_ANSI_RESET}")
            except (EOFError, KeyboardInterrupt):
                typer.echo(f"\n{_ANSI_DIM}Goodbye.{_ANSI_RESET}")
                return

            text = user_input.strip()
            if not text:
                continue

            # Local commands
            if text.lower() in _EXIT_COMMANDS:
                typer.echo(f"{_ANSI_DIM}Goodbye.{_ANSI_RESET}")
                return
            if text.lower() in _HELP_COMMANDS:
                _print_help()
                continue
            if text.lower() in _CLEAR_COMMANDS:
                agent.messages = [agent.messages[0]] if agent.messages else []
                typer.echo(f"{_ANSI_DIM}  Conversation history cleared.{_ANSI_RESET}\n")
                continue

            # Run the agent turn (preserves conversation history)
            typer.echo(f"{_ANSI_DIM}  thinking...{_ANSI_RESET}", nl=True)
            try:
                response = await agent.run(text)
                typer.echo(
                    f"\n{_ANSI_BOLD}{_ANSI_CYAN}agent> {_ANSI_RESET}{response}\n"
                )
            except ValueError as exc:
                typer.echo(f"\n{_ANSI_RED}Error: {exc}{_ANSI_RESET}\n", err=True)
            except KeyboardInterrupt:
                typer.echo(f"\n{_ANSI_DIM}Interrupted.{_ANSI_RESET}\n")
            except Exception as exc:
                typer.echo(f"\n{_ANSI_RED}Error: {exc}{_ANSI_RESET}\n", err=True)
