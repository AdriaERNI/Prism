---
name: prism-release-workflow
description: "Prism Git Flow release procedure: branch model, pre-releases, stable releases, hotfixes, branch protection, CI pipelines, and critical merge rules. Load when creating releases, managing release/hotfix branches, tagging, syncing main↔development, or doing branch cleanup on the Prism repo."
version: 1.0.0
author: Adria Sanchez
license: AGPL-3.0
metadata:
  hermes:
    tags: [Git, Git Flow, Releases, GitHub, Branch Protection, CI/CD, Prism]
    related_skills: [git-flow-release-workflow, github-pr-workflow]
---

# Prism Release Workflow

Git Flow release procedure for the Prism project
(`~/Projects/ERNI/Prism`, GitHub: `AdriaERNI/Prism`).

Full documentation: [docs/releases.md](../../docs/releases.md) — this skill
is a quick-reference companion, not a replacement.

## When to use

- Creating a pre-release, stable release, or hotfix for Prism
- Cutting `release/*` or `hotfix/*` branches
- Tagging releases and syncing `main` ↔ `development`
- Cleaning up stale branches after a release cycle
- Answering questions about Prism's branch model or CI

## Branch model

| Branch | Purpose | Protection |
|--------|---------|------------|
| `main` | Production-ready. Only accepts PRs from `release/*` or `hotfix/*`. | PR, CI, linear history, enforce_admins |
| `development` | Active development. Target for `feature/*` and Dependabot. | PR, CI, linear history, enforce_admins |
| `feature/*` | Cut from development, PR'd back. Deleted after merge. | None |
| `release/vX.Y.Z` | Cut from development, PR'd to main. Deleted after merge. | None |
| `hotfix/vX.Y.Z` | Cut from main, PR'd to main. Synced back to development. | None |

Branch naming: `v` prefix on release/hotfix branches and tags
(e.g. `release/v0.2.0`, `v0.2.0`). Feature branches use descriptive names.

## Quick reference

| Action | Steps |
|--------|-------|
| **Pre-release** | Tag on development: `git tag vX.Y.Z-beta.N && git push origin vX.Y.Z-beta.N`. CI auto-builds + creates GitHub Pre-release. No branch, no PR. |
| **Stable release** | Cut `release/vX.Y.Z` from development → PR to `main` → squash-merge via **web UI** → tag `vX.Y.Z` on main → push tag → sync main back to development → delete release branch. |
| **Hotfix** | Cut `hotfix/vX.Y.Z` from main → fix → PR to `main` → squash-merge via **web UI** → tag → sync back to development → delete hotfix branch. |
| **Sync main→dev** | Check `git diff --stat origin/main development` first. If empty → hard-reset development to main (`git reset --hard origin/main && git push --force-with-lease origin development`; temporarily disable branch protection if `enforce_admins=true`). If diff shows real changes → `git merge main` on a sync branch + PR. Never rebase or squash-merge a sync PR when trees are identical — it creates phantom SHAs. |

## Critical rules

1. **Merge via GitHub web UI** — `gh pr merge` is blocked by a shell wrapper at `~/.local/bin/gh`. Tell the user: "PR #N is ready — please merge via the GitHub web UI."
2. **NEVER run `gh release create`** — CI auto-creates releases from tag pushes. Manual creation races with CI.
3. **NEVER create `release/vX.Y.Z-beta.N` branches** — pre-releases are tags only, not branches.
4. **NEVER create `release/x` branches without the `v` prefix** — use `release/vX.Y.Z`.
5. **Sync main→dev with hard-reset, not rebase or merge** — squash-merge creates a new SHA on main that can never match development's history. Rebase replays phantom commits (conflict after conflict); merge+PR creates yet another phantom SHA. The correct sync is `git reset --hard origin/main && git push --force-with-lease origin development` (temporarily disable branch protection if `enforce_admins=true`). Only use merge+PR when trees actually differ.
6. **Check `git diff --stat origin/main development` before syncing** — if the diff is empty, hard-reset development to main. If the diff shows real changes, use a sync branch with `git merge main` + PR.
7. **CI syncs version from the tag** — never manually edit `pyproject.toml` or `__init__.py` version for a release.
8. **Never remove branch protection** on `main` or `development` without the user's explicit approval.

## Pre-release procedure

A pre-release is **just a tag** — no branch, no PR, no `gh release create`.

```bash
git checkout development
git pull origin development
git tag vX.Y.Z-beta.N
git push origin vX.Y.Z-beta.N
```

CI auto-builds artifacts, generates changelog via git-cliff, and creates a
GitHub Pre-release (hyphen in tag = auto pre-release).

**Re-tagging after failed CI:**

```bash
git tag -d vX.Y.Z-beta.N
git push origin :refs/tags/vX.Y.Z-beta.N
git tag vX.Y.Z-beta.N
git push origin vX.Y.Z-beta.N
```

**If tag push doesn't trigger CI:**

```bash
gh workflow run build-release.yml --ref vX.Y.Z-beta.N -f tag=vX.Y.Z-beta.N
```

## Stable release procedure

### 1. Cut release branch from development

```bash
git checkout development
git pull origin development
git checkout -b release/vX.Y.Z
```

### 2. Prepare the release

Version is synced by CI from the tag — do NOT edit `pyproject.toml` or
`__init__.py` manually. Optionally update changelog or do final docs review.

```bash
git add -A
git commit -m "release: prepare vX.Y.Z"
```

### 3. Open PR to main

```bash
git push -u origin release/vX.Y.Z
gh pr create --base main --head release/vX.Y.Z \
  --title "release: vX.Y.Z" \
  --body "Stable release vX.Y.Z"
```

### 4. Merge via GitHub web UI

Squash merge only (linear history enforced). **Do NOT use `gh pr merge`** —
it's blocked by a shell wrapper. Tell the user to merge in the web UI.

### 5. Tag the release

```bash
git checkout main
git pull origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

Tag push triggers `build-release.yml` (build + GitHub Release) and
`changelog.yml` (regenerate CHANGELOG.md).

### 6. Sync main back to development

After a squash-merge, the release commit on `main` has a new SHA that does
not exist in `development`'s history. **Rebase and merge+PR both fail here**:
rebase replays phantom commits (conflict after conflict); a sync PR
squash-merged into development creates yet another phantom SHA.

**Check if hard-reset is appropriate (trees identical):**

```bash
git diff --stat origin/main development
```

If empty, hard-reset development to main:

```bash
git checkout development
git fetch origin
git reset --hard origin/main
git push --force-with-lease origin development
```

> **Branch protection:** If `enforce_admins=true` and force pushes are
> disabled, temporarily disable protection on `development` via GitHub
> web UI, force-push, then re-enable.

**If trees differ** (hotfix on main + new commits on development):

```bash
git checkout development
git checkout -b sync/main-to-development
git merge main --no-edit
git push -u origin sync/main-to-development
gh pr create --base development --head sync/main-to-development \
  --title "chore: sync main into development" \
  --body "Sync main back to development after release vX.Y.Z."
# User merges via web UI (squash merge)
# Then hard-reset development to main to clear the phantom SHA
```

### 7. Clean up

```bash
git branch -d release/vX.Y.Z
git push origin --delete release/vX.Y.Z
git fetch --all --prune
git branch -v | grep '[gone]' | awk '{print $1}' | xargs -r git branch -D
```

## Hotfix procedure

### 1. Cut from main

```bash
git checkout main
git pull origin main
git checkout -b hotfix/vX.Y.Z
```

### 2. Fix and commit

```bash
git add -A
git commit -m "fix: critical bug description"
```

### 3. PR to main + merge via web UI

```bash
git push -u origin hotfix/vX.Y.Z
gh pr create --base main --head hotfix/vX.Y.Z \
  --title "hotfix: vX.Y.Z" \
  --body "Critical fix for vX.Y.Z"
# User merges via GitHub web UI (squash merge)
```

### 4. Tag and sync

```bash
git checkout main && git pull origin main
git tag vX.Y.Z && git push origin vX.Y.Z

# Sync back to development
# Check if trees are identical first:
git diff --stat origin/main development
# If empty → hard-reset (see "Sync main back to development" above)
# If differs → merge+PR, then hard-reset to clear phantom SHA
```

### 5. Clean up

```bash
git branch -d hotfix/vX.Y.Z
git push origin --delete hotfix/vX.Y.Z
```

## CI pipelines

| Workflow | File | Trigger | What it does |
|----------|------|---------|--------------|
| Test Linux | `test-linux.yml` | PR/push to `development` or `main` | Lint, unit tests (884), integration tests (82, Docker IRIS) |
| Test Windows | `test-windows.yml` | PR/push to `development` or `main` | Unit tests (884), PyInstaller frozen binary tests |
| Build and Release | `build-release.yml` | Tag push (`v*`) | Full pipeline: lint → tests → wheel → exe → installer → GitHub Release (git-cliff) |
| Changelog | `changelog.yml` | Tag push (`v*`) | Regenerates `CHANGELOG.md` + `docs/changelog.md`, commits to `main` |
| GitHub Pages | `pages.yml` | Push to `main` | MkDocs deploy to GitHub Pages |

Required status checks on `main`: `lint`, `test-linux`.

## Branch protection

Both `main` and `development` — identical rules:

| Rule | Value |
|------|-------|
| Required status checks | `lint`, `test-linux` |
| Strict (up-to-date) | Yes |
| Linear history | Yes (squash merges only) |
| enforce_admins | True (no bypasses, even for admins) |
| allow_force_pushes | False |
| allow_deletions | False |
| require_last_push_approval | False (sole developer) |
| required_approving_review_count | 0 (PR required, no reviews) |

## Squash-merge deduplication pitfall

After a squash merge, `git log` shows main's commits as "not in development"
because the SHA changed — even though the content is identical. **Do NOT
rebase or merge+PR to fix this** — both create phantom SHAs without
converging the branches. Instead, hard-reset development to main:

```bash
git diff --stat origin/main development   # check: empty = trees identical
git checkout development
git fetch origin
git reset --hard origin/main
git push --force-with-lease origin development
```

This makes development point to the exact same SHA as main. No phantom
commits, no divergence, no future conflict.

Rebase fails because it replays already-applied commits (conflict after
conflict). Merge+PR fails because the squash-merge of the sync PR creates
yet another new SHA — the branches never converge.

## Stale branch cleanup

After `git fetch --prune` removes deleted remote tracking refs:

```bash
git fetch --all --prune
git branch -v | grep '[gone]' | awk '{print $1}' | xargs -r git branch -D
```

Also drop stashes from deleted branches:

```bash
git stash list  # check for stashes from deleted branches
git stash drop stash@{N}
```