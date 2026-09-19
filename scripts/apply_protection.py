"""Reproduce Prism's exact branch-protection payloads (verified shapes)."""

from __future__ import annotations


def full_protection_payload(require_linear_history: bool = True) -> dict:
    """The standing protection for main + development."""
    return {
        "enforce_admins": True,
        "required_pull_request_reviews": None,
        "required_status_checks": {
            "strict": True,
            "contexts": ["lint", "test-linux"],
        },
        "restrictions": None,
        "required_linear_history": require_linear_history,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def development_window_payload() -> dict:
    """development during a merge-commit window: linearity relaxed, checks kept."""
    payload = full_protection_payload()
    payload["required_linear_history"] = False
    return payload


def restore_repo_settings_ops() -> list[tuple[str, object]]:
    """Repo-level merge settings to restore after a window."""
    return [
        ("allow_merge_commit", False),
        ("allow_rebase_merge", False),
        ("allow_squash_merge", True),
        ("delete_branch_on_merge", True),
    ]


def branches() -> list[str]:
    return ["development", "main"]
