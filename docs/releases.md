# Releases

Prism follows a [Git Flow][gitflow]-inspired release workflow adapted for a
small project with one maintainer and two protected branches.

This page documents the branch model, release procedure, hotfix procedure,
and the CI pipeline that automates artifact builds.

## Branch model

| Branch | Purpose | Protection |
|--------|---------|------------|
| `main` | Production-ready code. Every commit on `main` is a released version. | PR required, strict CI, linear history |
| `development` | Active development. All features and fixes land here first. | PR required, strict CI, linear history |
| `feature/*` | Individual features or bug fixes. Cut from `development`, PR'd back to `development`. | None (deleted after merge) |
| `release/X.Y.Z` | Release preparation. Cut from `development`, PR'd to `main`. | None (deleted after merge) |
| `hotfix/X.Y.Z` | Emergency fix for a released version. Cut from `main`, PR'd to both `main` and `development`. | None (deleted after merge) |

### Branch naming conventions

- **Feature branches**: `feature/<short-description>` (e.g. `feature/cast-plugins`)
- **Release branches**: `release/X.Y.Z` -- no `v` prefix (e.g. `release/0.2.0`)
- **Hotfix branches**: `hotfix/X.Y.Z` -- no `v` prefix (e.g. `hotfix/0.2.1`)
- **Tags**: `vX.Y.Z` -- with `v` prefix (e.g. `v0.2.0`)

The `v` prefix is used **only for tags**, never for branch names. This is
the standard Git Flow convention.

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
git checkout -b release/0.2.0
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
git push -u origin release/0.2.0
gh pr create --base main --head release/0.2.0 \
  --title "release: v0.2.0" \
  --body "Stable release v0.2.0"
```

All CI checks must pass before merging:

- **Lint** -- ruff check + format
- **Unit Tests** (Linux + Windows) -- 324 tests
- **Build and Test Frozen Executable** (Windows) -- PyInstaller build + frozen binary tests + deep MCP protocol tests (32 tests)
- **Integration Tests** (Linux) -- against a live IRIS container

### 4. Merge to main

Merge the PR using **squash merge** (linear history is enforced on `main`).

### 5. Tag the release

```bash
git checkout main
git pull origin main
git tag v0.2.0
git push origin v0.2.0
```

Pushing the tag triggers the **Build and Release** workflow, which:

1. Runs lint + tests (Linux + Windows)
2. Syncs the version from the tag into `pyproject.toml` and `__init__.py`
3. Builds the Python wheel (Linux)
4. Builds the PyInstaller exe (Windows)
5. Builds the Inno Setup installer (Windows)
6. Tests the frozen binary (`--version`, `--help`, `cast --list`, `prism serve`)
7. Creates a GitHub Release with auto-generated changelog

### 6. Sync development

After the release, merge `main` back into `development` so the release
branch changes propagate:

```bash
git checkout development
git merge main --no-edit  # or use a PR if you prefer
git push origin development
```

### 7. Clean up

Delete the release branch (local + remote):

```bash
git branch -d release/0.2.0
git push origin --delete release/0.2.0
```

## Pre-releases

Pre-releases follow a lighter process. Tag directly from `development`
or a release branch without merging to `main`:

```bash
# Tag a pre-release from development
git checkout development
git pull origin development
git tag v0.2.0-beta.1
git push origin v0.2.0-beta.1
```

GitHub automatically marks the release as a **Pre-release** when the tag
contains a hyphen. Pre-release tags do not affect the `latest` release
pointer on GitHub.

You can tag as many pre-releases as needed before cutting the stable
release. When ready, follow the full release procedure above.

## Hotfix procedure

When a critical bug is found in a released version:

### 1. Cut a hotfix branch from main

```bash
git checkout main
git pull origin main
git checkout -b hotfix/0.2.1
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
git push -u origin hotfix/0.2.1
gh pr create --base main --head hotfix/0.2.1 \
  --title "hotfix: v0.2.1" \
  --body "Critical fix for v0.2.0"
```

### 4. Merge, tag, and sync

```bash
# Merge the PR to main (squash)
git checkout main
git pull origin main
git tag v0.2.1
git push origin v0.2.1

# Sync back to development
git checkout development
git merge main --no-edit
git push origin development

# Clean up
git branch -d hotfix/0.2.1
git push origin --delete hotfix/0.2.1
```

## Visual workflow

```
development  feature/cast   release/0.2.0     main
    |              |               |            |
    |--- CUT ------|               |            |
    |              |               |            |
    |<-- MERGE ----|               |            |
    |                              |            |
    |---------- CUT ---------------|            |
    |                              |            |
    |                              |--- PR ---->|
    |                              |            |
    |                              |      MERGE |
    |                              |            |
    |                              |       TAG v0.2.0
    |                              |            |
    |<----------- SYNC (merge main into dev) ---|
    |                                           |
    |                                     DELETE release/0.2.0
```

## CI pipelines

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `test-linux.yml` | PR to `development` or `main` | Lint, unit tests, integration tests (Docker IRIS) |
| `test-windows.yml` | PR to `development` or `main` | Unit tests, PyInstaller frozen binary tests, MCP protocol tests (32 tests) |
| `build-release.yml` | Tag push (`v*`) | Full build pipeline + GitHub Release creation |
| `pages.yml` | Push to `main` | MkDocs documentation deploy to GitHub Pages |

## Branch protection rules

Both `main` and `development` are protected:

| Rule | Value |
|------|-------|
| Required PR reviews | 0 (user merges manually) |
| Required status checks | Lint, Unit Tests |
| Strict (up-to-date) | Yes |
| Linear history | Yes (squash merges only) |
| Force pushes | Disabled |
| enforce_admins | False (admin can bypass in emergencies) |

`main` only accepts PRs from `release/*` or `hotfix/*` branches.
`development` is the target for all `feature/*` branches and Dependabot PRs.

## Changelog

Release notes are auto-generated by [git-cliff](https://git-cliff.github.io/)
using the configuration in `cliff.toml`. Commits should follow
[Conventional Commits](https://www.conventionalcommits.org/) so they are
categorized correctly:

| Prefix | Category in changelog |
|--------|----------------------|
| `feat:` | Features |
| `fix:` | Bug Fixes |
| `docs:` | Documentation |
| `ci:` | CI/CD |
| `refactor:` | Refactoring |
| `test:` | Tests |

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
