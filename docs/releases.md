# Releases

Prism follows a [Git Flow][gitflow]-inspired release workflow adapted for a
small project with one maintainer and two protected branches.

This page documents the branch model, release procedure, hotfix procedure,
and the CI pipeline that automates artifact builds.

## Quick reference

| Action | Steps |
|--------|-------|
| **Pre-release** | Tag on development: `git tag vX.Y.Z-beta.N && git push origin vX.Y.Z-beta.N`. CI auto-builds + creates GitHub Pre-release. No branch, no PR, no `gh release create`. |
| **Stable release** | 1. Cut `release/vX.Y.Z` from development → 2. PR to `main` → 3. Squash-merge via **web UI** → 4. Tag `vX.Y.Z` on main → 5. Push tag → 6. Sync main back to development → 7. Delete release branch. |
| **Hotfix** | 1. Cut `hotfix/vX.Y.Z` from main → 2. Fix + commit → 3. PR to `main` → 4. Squash-merge via **web UI** → 5. Tag → 6. Sync back to development → 7. Delete hotfix branch. |
| **Sync main→dev** | Check `git diff --stat origin/main development` first. If empty → hard-reset development to main (`git reset --hard origin/main && git push --force-with-lease origin development`; temporarily disable branch protection if `enforce_admins=true`). If diff shows real changes → `git merge main` on a sync branch + PR. Never rebase or squash-merge a sync PR when trees are identical — it creates phantom SHAs. |

**Critical rules:**

- **Merge via GitHub web UI** — `gh pr merge` is blocked by a shell wrapper
- **NEVER `gh release create`** — CI auto-creates releases from tag pushes
- **NEVER create `release/vX.Y.Z-beta.N` branches** — pre-releases are tags only
- **Use rebase, not merge** on `development` (linear history enforced)
- **Check `git diff` before rebasing** — squash merges create duplicate SHAs

## Branch model

| Branch | Purpose | Protection |
|--------|---------|------------|
| `main` | Production-ready code. Every commit on `main` is a released version. | PR required, strict CI, linear history |
| `development` | Active development. All features and fixes land here first. | PR required, strict CI, linear history |
| `feature/*` | Individual features or bug fixes. Cut from `development`, PR'd back to `development`. | None (deleted after merge) |
| `release/vX.Y.Z` | Release preparation. Cut from `development`, PR'd to `main`. | None (deleted after merge) |
| `hotfix/vX.Y.Z` | Emergency fix for a released version. Cut from `main`, PR'd to both `main` and `development`. | None (deleted after merge) |

### Branch naming conventions

- **Feature branches**: `feature/<short-description>` (e.g. `feature/cast-plugins`)
- **Release branches**: `release/vX.Y.Z` -- with `v` prefix (e.g. `release/v0.2.0`)
- **Hotfix branches**: `hotfix/vX.Y.Z` -- with `v` prefix (e.g. `hotfix/v0.2.1`)
- **Tags**: `vX.Y.Z` -- with `v` prefix (e.g. `v0.2.0`)

The `v` prefix is used consistently on release/hotfix branches and tags,
matching the tag name they produce.

## Versioning

Prism follows [semantic versioning](https://semver.org/):

| Pattern | Example | When to use |
|---------|---------|-------------|
| `vX.Y.Z` | `v0.2.0` | Stable release |
| `vX.Y.Z-beta.N` | `v0.2.0-beta.5` | Pre-release (testing before stable) |
| `vX.Y.Z-rc.N` | `v0.2.0-rc.1` | Release candidate (optional) |

The CI pipeline syncs the version from the git tag into `pyproject.toml`
and `src/prism/__init__.py` at build time. You never edit version numbers
manually for a release -- just tag and push.

## Release procedure

### 1. Cut a release branch

When `development` is ready for release, cut a release branch:

```bash
git checkout development
git pull origin development
git checkout -b release/v0.2.0
```

### 2. Prepare the release

On the release branch, do any final preparation:

- Bump version in `pyproject.toml` and `src/prism/__init__.py` (if not already set)
- Update `CHANGELOG.md` if needed
- Final documentation review

```bash
# Example: ensure version is set for stable release
# pyproject.toml: version = "0.2.0"
# src/prism/__init__.py: __version__ = "0.2.0"

git add -A
git commit -m "release: prepare v0.2.0"
```

### 3. Open PR to main

```bash
git push -u origin release/v0.2.0
gh pr create --base main --head release/v0.2.0 \
  --title "release: v0.2.0" \
  --body "Stable release v0.2.0"
```

All CI checks must pass before merging:

- **Lint** (`lint` context) -- ruff check + format
- **Unit Tests** (`test-linux` context) -- 884 unit tests (Linux) + 884 unit tests (Windows)
- **Integration Tests** (`test-linux` context) -- 82 integration tests against a live IRIS
  container (Linux only; 7 skip on CI due to IRIS Community license limits)
- **Windows Build** (`test-windows` context) -- Unit tests + PyInstaller frozen binary
  tests (`--version`, `--help`, `cast --list`, `prism serve` startup)

Required status checks on `main`: `lint`, `test-linux`. Branch protection
enforces `enforce_admins: true`, `required_linear_history: true`,
`allow_force_pushes: false`, `allow_deletions: false`.

### 4. Merge to main — via GitHub web UI

Merge the PR using **squash merge** (linear history is enforced on `main`).

> **⚠️ Merge via the GitHub web UI, NOT `gh pr merge`.**
> A shell wrapper at `~/.local/bin/gh` blocks `gh pr merge` entirely.
> This is intentional — it prevents agents and scripts from auto-merging PRs.
> All merges must be performed manually in the GitHub web UI.

### 5. Tag the release

```bash
git checkout main
git pull origin main
git tag v0.2.0
git push origin v0.2.0
```

> **⚠️ NEVER run `gh release create`.** The CI pipeline creates the GitHub
> Release automatically when the tag is pushed (see below). Running it
> manually races with CI and can create a duplicate or empty release.

Pushing the tag triggers two workflows:

**Build and Release** (`build-release.yml`):

1. Runs lint + tests (Linux + Windows)
2. Syncs the version from the tag into `pyproject.toml` and `__init__.py`
3. Builds the Python wheel (Linux)
4. Builds the PyInstaller exe (Windows)
5. Builds the Inno Setup installer (Windows)
6. Tests the frozen binary (`--version`, `--help`, `cast --list`, `prism serve`)
7. Creates a GitHub Release with changelog generated by git-cliff

**Changelog** (`changelog.yml`):

1. Runs git-cliff to regenerate `CHANGELOG.md` (full history)
2. Copies a MkDocs-friendly version to `docs/changelog.md`
3. Commits both files to `main` directly (triggers Pages deploy)

For stable releases, git-cliff uses `--ignore-tags '.*-beta\..*'` so
pre-release commits roll up into the stable release notes.

### 6. Sync main back to development

After the release, `main` has the squash-merged release commit + version
bump. Development needs those changes. With `enforce_admins: true` and
`required_linear_history: true`, you cannot push merge commits directly
### 6. Sync main back to development

After a squash-merge, the release commit on `main` has a new SHA that does
not exist in `development`'s history. **Rebase and merge+PR both fail here**:
rebase replays phantom commits causing conflict after conflict; a sync PR
squash-merged into development creates yet another phantom SHA.

**Check if a hard-reset is appropriate (trees identical):**

```bash
git diff --stat origin/main development
```

If the diff is empty, the branches are content-identical. Hard-reset
development to main:

```bash
git checkout development
git fetch origin
git reset --hard origin/main
git push --force-with-lease origin development
```

> **Branch protection:** If `enforce_admins=true` and force pushes are
> disabled, temporarily disable branch protection on `development` via
> GitHub web UI (`Settings → Branches → development → Delete rule`), do the
> force-push, then re-enable protection with the same rules.

**If trees differ** (e.g. hotfix landed on main and development has new
commits since the release branch was cut):

```bash
git checkout development
git checkout -b sync/main-to-development
git merge main --no-edit   # merge, NOT rebase
git push -u origin sync/main-to-development
gh pr create --base development --head sync/main-to-development \
  --title "chore: sync main into development" \
  --body "Sync main back to development after release vX.Y.Z."
# Merge via GitHub web UI (squash merge)
# Then hard-reset development to main to clear the phantom SHA
```

> **Squash-merge deduplication:** After a squash merge, `git log` shows
> main's commits as "not in development" because the SHA changed, even
> though the content is identical. Always check `git diff --stat` (not
> `git log`) to determine whether a sync is actually needed.

### 7. Clean up

Delete the release branch (local + remote):

```bash
git branch -d release/v0.2.0
git push origin --delete release/v0.2.0
```

Prune stale local branches that no longer have a remote counterpart:

```bash
git fetch --all --prune
git branch -v | grep '[gone]' | awk '{print $1}' | xargs -r git branch -D
```

## Pre-releases

A pre-release is **just a tag on the current branch** — no release branch,
no PR to `main`, no `gh release create`. The tag push triggers CI which
builds artifacts and creates the GitHub Release automatically.

```bash
# Tag a pre-release from development (or any feature branch)
git checkout development
git pull origin development
git tag v0.2.0-beta.1
git push origin v0.2.0-beta.1
```

GitHub automatically marks the release as a **Pre-release** when the tag
contains a hyphen (`-beta`, `-rc`). Pre-release tags do not affect the
`latest` release pointer on GitHub.

> **⚠️ NEVER run `gh release create` for pre-releases.** The CI pipeline
> creates the release automatically. Manual creation races with CI and
> can create duplicates.

> **⚠️ NEVER create a `release/vX.Y.Z-beta.N` branch.** Release branches
> are for stable releases only. Pre-releases are tags directly on the
> working branch.

You can tag as many pre-releases as needed before cutting the stable
release. When ready, follow the full release procedure above.

### Re-tagging after a failed pipeline

If CI failed and no release was created:

```bash
git tag -d v0.2.0-beta.1
git push origin :refs/tags/v0.2.0-beta.1
git tag v0.2.0-beta.1
git push origin v0.2.0-beta.1
```

If the tag push doesn't auto-trigger CI, use `workflow_dispatch`:

```bash
gh workflow run build-release.yml --ref v0.2.0-beta.1 -f tag=v0.2.0-beta.1
```

## Hotfix procedure

When a critical bug is found in a released version:

### 1. Cut a hotfix branch from main

```bash
git checkout main
git pull origin main
git checkout -b hotfix/v0.2.1
```

### 2. Fix and bump version

```bash
# Bump the patch version
# pyproject.toml: version = "0.2.1"
# src/prism/__init__.py: __version__ = "0.2.1"

git add -A
git commit -m "fix: critical bug in SQL execution"
```

### 3. PR to main

```bash
git push -u origin hotfix/v0.2.1
gh pr create --base main --head hotfix/v0.2.1 \
  --title "hotfix: v0.2.1" \
  --body "Critical fix for v0.2.0"
```

### 4. Merge, tag, and sync

```bash
# Merge the PR to main via GitHub web UI (squash merge)
git checkout main
git pull origin main
git tag v0.2.1
git push origin v0.2.1

# Sync back to development
# Check if trees are identical first:
git diff --stat origin/main development
# If empty → hard-reset (see "Sync main back to development" above)
# If differs → merge+PR, then hard-reset to clear phantom SHA

# Clean up
git branch -d hotfix/v0.2.1
git push origin --delete hotfix/v0.2.1
```

## Visual workflow

```
                ┌─── PRE-RELEASE ───────────────────────────┐
                │                                          │
  development ──┼── tag vX.Y.Z-beta.N ──> CI builds ──> GitHub Pre-release
                │   (no branch, no PR,                     (auto-created)
                │    no gh release create)
                │
                │   re-tag if CI fails: delete tag, re-tag, push
                └──────────────────────────────────────────┘

                ┌─── STABLE RELEASE ──────────────────────────────────┐
                │                                                    │
  development ──CUT── release/vX.Y.Z ──PR──> main ──SQUASH MERGE (web UI)
                │                        │         │
                │                        │         TAG vX.Y.Z ──> CI builds
                │                        │         │              + git-cliff
                │                        │         ├──> GitHub Release (auto)
                │                        │         └──> CHANGELOG.md commit
                │                        │
                │   SYNC: hard-reset dev to main (trees identical)
                │<──────── main ──────────────────────────────────┘
                │
                └── DELETE release/vX.Y.Z (local + remote)
                                                    │
                ┌─── HOTFIX ────────────────────────┘
                │
  main ──CUT── hotfix/vX.Y.Z ──PR──> main ──SQUASH MERGE (web UI)
                │                     │
                │                     TAG vX.Y.Z ──> CI builds
                │
                │   SYNC: hard-reset dev to main (trees identical)
                │<──────── main ──────────────────────┘
                │
                └── DELETE hotfix/vX.Y.Z (local + remote)
```

## CI pipelines

| Workflow | File | Trigger | What it does |
|----------|------|---------|--------------|
| Test Linux | `test-linux.yml` | PR/push to `development` or `main` | Lint (`ruff check + format`), unit tests (884), integration tests (82, Docker IRIS) |
| Test Windows | `test-windows.yml` | PR/push to `development` or `main` | Unit tests (884), PyInstaller frozen binary tests |
| Build and Release | `build-release.yml` | Tag push (`v*`) | Full pipeline: lint → tests → wheel → exe → installer → frozen binary tests → GitHub Release (git-cliff changelog) |
| Changelog | `changelog.yml` | Tag push (`v*`) | Regenerates `CHANGELOG.md` + `docs/changelog.md` via git-cliff, commits to `main` |
| GitHub Pages | `pages.yml` | Push to `main` | MkDocs documentation deploy to GitHub Pages |

## Branch protection rules

Both `main` and `development` are protected with identical rules:

| Rule | Value |
|------|-------|
| Required PR reviews | 0 (PR itself is required) |
| Required status checks | `lint`, `test-linux` |
| Strict (up-to-date) | Yes |
| Linear history | Yes (squash merges only, no merge commits) |
| Force pushes | Disabled |
| Branch deletion | Disabled |
| enforce_admins | True (no bypasses, even for admins) |
| require_last_push_approval | False (sole developer) |

`main` only accepts PRs from `release/*` or `hotfix/*` branches.
`development` is the target for all `feature/*` branches and Dependabot PRs.

With `enforce_admins: true`, all changes must go through pull requests —
even for repository admins. To sync `main` back to `development` after a
release, **hard-reset** development to main: temporarily disable branch
protection on `development`, force-push, then re-enable. Squash-merge
creates a new SHA that can never match development's history, so rebase
and merge+PR both produce phantom SHAs without converging the branches.

Dependabot is configured to target `development` (not `main`) in
`.github/dependabot.yml`.

## Changelog

Release notes are auto-generated by [git-cliff](https://git-cliff.github.io/)
using the configuration in `cliff.toml`. Two workflows handle changelog:

1. **Build and Release** (`build-release.yml`): Generates release notes
   for the GitHub Release itself (attached to the release, not committed).
2. **Changelog** (`changelog.yml`): Regenerates `CHANGELOG.md` and
   `docs/changelog.md` with full history and commits them to `main`.

Commits should follow [Conventional Commits](https://www.conventionalcommits.org/)
so they are categorized correctly:

| Prefix | Category in changelog |
|--------|----------------------|
| `feat:` | Features |
| `fix:` | Bug Fixes |
| `docs:` | Documentation |
| `ci:` | CI/CD |
| `refactor:` | Refactoring |
| `test:` | Tests |
| `chore(deps):` | Dependencies |
| `chore:` | Miscellaneous |

For stable releases, pre-release tags are excluded from the changelog
so their commits roll up into the stable release notes.

## Release artifacts

Each release includes:

| Artifact | Platform | Description |
|----------|----------|-------------|
| `prism.exe` | Windows | Standalone PyInstaller binary (~36 MB) |
| `prism-X.Y.Z-setup.exe` | Windows | Inno Setup installer with Prism branding |
| `prism-X.Y.Z-py3-none-any.whl` | Cross-platform | Python wheel (`pip install prism`) |

[gitflow]: https://nvie.com/posts/a-successful-git-branching-model/
