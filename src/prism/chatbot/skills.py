"""Skill folder reader — loads markdown skill files into a system prompt.

A "skill" is simply a ``.md`` file inside a directory.  Each file's
content is loaded and concatenated into the agent's system prompt so the
LLM knows how to approach specific tasks (e.g. "how to create a REST
API class in IRIS", "how to run unit tests", etc.).

The skills path can be set via:

1. ``--skills-path`` CLI flag on ``prism chatbot``
2. ``CHATBOT_SKILLS_PATH`` environment variable
3. ``chatbot_skills_path`` in ``config.json``

The directory is scanned recursively for ``*.md`` files.  Each file is
prefixed with a header indicating the skill name (derived from the
relative file path) so the LLM can reference them.
"""

from __future__ import annotations

from pathlib import Path


def load_skills(skills_path: str | Path | None) -> str:
    """Load all markdown skill files from *skills_path*.

    Returns a formatted string suitable for inclusion in the system
    prompt.  Returns an empty string if the path is ``None``, empty, or
    does not exist.
    """
    if not skills_path:
        return ""

    root = Path(skills_path)
    if not root.is_dir():
        return ""

    # Collect all .md files recursively, sorted for deterministic order.
    md_files = sorted(root.rglob("*.md"))
    if not md_files:
        return ""

    blocks: list[str] = []
    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if not content.strip():
            continue

        # Derive a skill name from the relative path without extension.
        # e.g. "sql/rest-apis.md" -> "sql/rest-apis"
        # Use forward slashes for cross-platform consistency.
        skill_name = md_file.relative_to(root).with_suffix("").as_posix()
        blocks.append(f"## Skill: {skill_name}\n\n{content}")

    if not blocks:
        return ""

    header = "# Skills\n\nBelow are skill files that provide guidance on how to use the available tools. Follow these instructions when they are relevant to the user's request.\n"
    return header + "\n\n".join(blocks)


def list_skills(skills_path: str | Path | None) -> list[dict[str, str]]:
    """Return a list of skill metadata (name, path, size).

    Useful for the ``--list-skills`` CLI flag.
    """
    if not skills_path:
        return []

    root = Path(skills_path)
    if not root.is_dir():
        return []

    skills: list[dict[str, str]] = []
    for md_file in sorted(root.rglob("*.md")):
        try:
            size = md_file.stat().st_size
        except OSError:
            size = 0
        skill_name = md_file.relative_to(root).with_suffix("").as_posix()
        skills.append(
            {
                "name": skill_name,
                "path": str(md_file),
                "size": f"{size} bytes",
            }
        )
    return skills
