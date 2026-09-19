from scripts.apply_protection import (
    branches,
    development_window_payload,
    full_protection_payload,
    restore_repo_settings_ops,
)


def test_full_payload_matches_verified_shape() -> None:
    p = full_protection_payload()
    assert p["enforce_admins"] is True
    assert p["required_status_checks"] == {"strict": True, "contexts": ["lint", "test-linux"]}
    assert p["required_linear_history"] is True
    assert p["allow_force_pushes"] is False
    assert p["allow_deletions"] is False


def test_window_payload_relaxes_only_linearity() -> None:
    p = development_window_payload()
    assert p["required_linear_history"] is False
    assert p["required_status_checks"] == {"strict": True, "contexts": ["lint", "test-linux"]}
    assert p["enforce_admins"] is True


def test_restore_settings_match_squash_only() -> None:
    ops = dict(restore_repo_settings_ops())
    assert ops["allow_merge_commit"] is False
    assert ops["allow_rebase_merge"] is False
    assert ops["allow_squash_merge"] is True
    assert ops["delete_branch_on_merge"] is True


def test_branches_are_protected_set() -> None:
    assert branches() == ["development", "main"]
