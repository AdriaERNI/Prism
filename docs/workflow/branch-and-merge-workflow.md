# Branching and Merge Workflow

Prism follows a [Git Flow][gitflow]-inspired model (see [Releases](../releases.md)),
adapted to a fork with two protected branches, squash-only merging by default,
and a CI pipeline that builds artifacts from tag pushes.

This page defines the **branch conventions**, the **merge-strategy decision**,
and documents the specific trap that produces recurring "dirty" release PRs —
with the project-specific workarounds.

## Branch model

| Branch | Purpose | Parent | Protection |
|--------|---------|--------|------------|
| `main` | Production-ready code. Every commit on `main` is a released version. | — | PR required, strict CI, linear history, `enforce_admins: true` |
| `development` | Active development. All features and fixes land here first. | — | PR required, strict CI, linear history, `enforce_admins: true` |
| `feature/<desc>` | Individual features or bug fixes | `development` | None (deleted after merge) |
| `release/vX.Y.Z` | Release preparation | `development` | None (deleted after merge) |
| `hotfix/vX.Y.Z` | Emergency fix for a released version | `main` | None (deleted after merge) |

Branch and tag naming uses the `v` prefix consistently: `release/v0.2.0`,
`hotfix/v0.2.1`, tag `v0.2.0`.

### When to open a PR

1. Cut the branch from the correct parent (`feature/*` and `release/vX.Y.Z`
   from `development`; `hotfix/vX.Y.Z` from `main`).
2. Set the PR **base** to where the change lands:

   | Branch type | Base | Head |
   |-------------|------|------|
   | `feature/*` | `development` | `feature/<desc>` |
   | `release/vX.Y.Z` | `main` | `release/vX.Y.Z` |
   | `hotfix/vX.Y.Z` | `main` (then also `development`) | `hotfix/vX.Y.Z` |

3. Keep the head up to date before opening/merging — GitHub marks a PR
   `dirty` when the head is behind the base and the branches touch the same
   lines (fetch + rebase locally when needed).
4. All CI checks must pass before merging (`Lint`, `Unit Tests`,
   `Integration Tests`, `Build and Test Frozen Executable`). Release PRs
   additionally require the integration tests against a live IRIS container.

## Merge methods on GitHub

GitHub offers three merge options; which ones appear depends on the
repository settings (`allow_merge_commit`, `allow_squash_merge`,
`allow_rebase_merge`).

| Method | History produced | Choose when |
|--------|-----------------|-------------|
| **Create a merge commit** | one merge commit with two parents (head + base), full history preserved | you want an explicit merge point and the individual commits to remain meaningful |
| **Squash and merge** | all PR commits collapsed into a single commit on the base branch | a PR represents one logical change (default for Prism releases and features) |
| **Rebase and merge** | each PR commit replayed onto the base individually, linear, **new SHAs** | you want linear history and commits are already organized |

> [!WARNING]
> GitHub refuses **Rebase and merge** with *"This branch can't be rebased"*
> when the head branch contains a **merge commit**. Also, rebase-and-merge
> rewrites SHAs and always updates committer info — never use it on a merge
> commit you need to keep.

## Recommended strategy for Prism

| Scenario | Merge method | Why |
|----------|--------------|-----|
| `feature/*` → `development` | **Squash and merge** | one logical change, concise history |
| `hotfix/vX.Y.Z` → `main` | **Squash and merge** | same as features, then sync to `development` |
| `release/vX.Y.Z` → `main` | **Squash and merge** | standard Git-Flow release; CI builds from the tag. Safe as long as the trees are identical (see trap below) |
| sync `main` → `development`, trees identical | **Hard-reset sync** (not a PR) | `git reset --hard origin/main && git push --force-with-lease origin development` — temporarily disable branch protection if `enforce_admins=true` |
| sync `main` → `development`, trees diverge | sync branch + **Create a merge commit** | squash on a sync erases ancestry and re-dirties release PRs (see below) |
| local feature branch maintenance | `git rebase` locally, then push | keeps the head up to date without re-writing merged history |

## Policy decision (issue #37)

Adopted a **manual** procedure (approved 2026-09-19; the originally
planned automation — a lock-diff guard workflow plus protection scripts,
PR #39 — was dropped on 2026-09-21 to keep the repo free of agent
tooling; the knowledge below is the procedure to follow by hand):

| Part | Mechanism | How to execute |
|------|-----------|----------------|
| **A — release-PR preflight** | before opening a release PR, compare `uv.lock` / `pyproject.toml` between `origin/main` and the head; packages present on both sides with differing text (example: `fastmcp` 3.4.7 vs 4.0.0) must be aligned to the union first (see the trap below, fix 1) | manual: `git diff origin/main <head> -- uv.lock pyproject.toml` — if overlapping package blocks differ, resolve to byte-identical text before opening the PR |
| **B — temporary merge-commit window** | during sync of divergent trees: enable `allow_merge_commit=true` and relax `required_linear_history` on `development` **only**; merge the sync PR with **Create a merge commit**; then restore both settings + protection | manual, via the GitHub web UI (repo settings) or `gh api`, following the restore checklist below |
| **Never** | squash/rebase a sync PR when trees are identical; never leave a merge window open | enforced by this doc |

**Restore checklist (standing):** after any sync/merge window, put back
`allow_merge_commit=false`, `allow_rebase_merge=false`,
`allow_squash_merge=true`, and verify `development` + `main` protection is
restored exactly: `enforce_admins` true, strict required checks
(`Lint`, `Unit Tests`, `Integration Tests`, `Build and Test Frozen
Executable`), linear history, no force pushes/deletions. Check the live
state with `gh api repos/<owner>/<repo>/branches/<branch>/protection`
before and after.

## The squash-only trap (why release PRs get DIRTY repeatedly)

> [!NOTE]
> This is the exact failure mode Prism hit on `release: v0.2.2` (PR #32):
> GitHub kept showing *"This branch has conflicts that must be resolved. Use
> the command line..."* with `pyproject.toml` and `uv.lock`, no matter how
> many sync merges were squashed into `development`.

1. GitHub recomputes PR mergeability with a **three-way merge from the
   merge-base**, comparing `base → base-branch` against `base → head`,
   **per file, per text line**.
2. **Squash merges create single-parent commits**, so the commit `main`
   gains after a release is **never an ancestor of `development`**. GitHub
   therefore re-runs the merge from the old split point every time.
3. When the two branches rewrite the **same files with different text** —
   Prism's case: `development` regenerates `uv.lock` wholesale (fastmcp
   pin, resolution markers removed) while `main` carries an upstream bump
   (`mkdocs-material>=9.7.7` plus removed `pymdown-extensions`) — the
   overlapping hunks differ, Git cannot fold them automatically, and the
   PR is marked **DIRTY** ("conflicts that must be resolved").
4. The fixes that work, in order:
   - **Record identical content** — resolve to a union (`pyproject.toml` with
     `mkdocs-material>=9.7.7` **and** `pymdown-extensions>=10.14`, fused
     `uv.lock`, markers removed) so both sides' overlapping lines are
     **byte-identical**; identical text folds cleanly.
   - **Record a true merge commit** (via *Create a merge commit*, or by
     pushing a two-parent commit while protection is lifted) so `main`'s
     tip becomes an **ancestor of `development`** — GitHub then recomputes
     from `main`'s tip as the merge-base and the PR flips **MERGEABLE**,
     permanently.

> [!NOTE]
> "Squash a merge onto main whose tree development already has" is **safe**
> — identical text folds even though the commit itself isn't an ancestor. The
> trap returns on the *next* release only when `development` diverges
> `uv.lock`/`pyproject` text again. Keeping those files' overlapping sections
> identical between branches, or recording a true merge commit, prevents the
> recurrence.

## Sync workflow (exact steps)

| Sync case | Steps |
|-----------|-------|
| Trees identical (fast-forward) | hard-reset `development` to `main` (`git reset --hard origin/main && git push --force-with-lease origin development`) — temporarily disable protection if `enforce_admins=true`, re-enable after |
| Trees diverge (real changes) | `git merge main` on a sync branch, resolve conflicts, open a PR, merge with **Create a merge commit** during the Option-B window | 
| Never | squash or rebase a sync PR when trees are identical — it creates phantom SHAs and keeps release PRs dirty |
| Before any release PR | preflight: `git diff --stat origin/main origin/development`, then inspect the overlapping `uv.lock` / `pyproject.toml` hunks with `git diff origin/main <head> -- uv.lock pyproject.toml` — clean → open PR; diverging package blocks → align to the union/sync first |

## Branch protection interactions

- `main` and `development` enforce: PR required, strict CI (required
  checks `Lint`, `Unit Tests`, `Integration Tests`, `Build and Test Frozen
  Executable`), linear history, `enforce_admins: true`, no force pushes,
  no deletions.
- The merge dropdown only shows the methods the repository allows
  (`allow_merge_commit`, `allow_squash_merge`, `allow_rebase_merge`).
- With `"Require approval of the most recent reviewable push"` +
  `"Dismiss stale approvals"` enabled, a manually-created merge commit
  pushed directly to a protected branch fails **unless its contents exactly
  match GitHub's generated merge**.
- GitHub's web *"Resolve conflicts"* button is unavailable when the head is
  a protected branch (`enforce_admins`) — that's why GitHub tells you to
  *"Use the command line to resolve conflicts before continuing."*
- **Merge-commit windows** (Option B): enabling `allow_merge_commit` alone
  is not enough on `main` — `required_linear_history=true` blocks
  Create-a-merge-commit there; relax linearity on `development` **only**
  during the sync window and restore immediately (restore checklist in the
  policy-decision section).

## Resolving conflicts on the command line

When GitHub asks for command-line resolution:

1. `git fetch origin <base> <head>`
2. create the sync branch, `git merge --no-ff origin/main`, resolve the
   conflict markers to the union content, regenerate the fused `uv.lock`
3. commit the merge (`git commit`), push it to a non-protected sync branch,
   open a PR to `development`
4. merge that PR with **Create a merge commit** (requires the repository to
   allow merge commits for that window) — this records `main`'s history
   inside `development` and clears the release PR

## Sources

- GitHub Docs — [About merge methods][merge-methods]
- GitHub Docs — [Pull request merges][pr-merges]
- GitHub Docs — [Managing a branch protection rule][branch-protection]
- GitHub Docs — [About protected branches][protected-branches]
- Vincent Driessen — [A successful Git branching model][gitflow]
- Atlassian — [Gitflow workflow][atlassian-gitflow]
- arXiv 2507.08943 — [Trunk-based vs. branch-based workflows][trunk-paper]
- Toptal — [Git Flow vs. Trunk Based Development][toptal]

[gitflow]: https://nvie.com/posts/a-successful-git-branching-model/
[merge-methods]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges
[pr-merges]: https://docs.github.com/en/pull-requests/reference/pull-request-merges
[branch-protection]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule
[protected-branches]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
[atlassian-gitflow]: https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow
[trunk-paper]: https://arxiv.org/html/2507.08943v1
[toptal]: https://www.toptal.com/developers/software/trunk-based-development-git-flow
