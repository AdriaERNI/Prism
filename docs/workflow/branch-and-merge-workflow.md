# Branching and Merge Workflow

Prism follows a [Git Flow][gitflow]-inspired model (see [Releases](../releases.md)),
adapted to a fork with two protected branches, rebase-and-merge as the default
merge method, and a CI pipeline that builds artifacts from tag pushes.

This page defines the **branch conventions**, the **merge-strategy decision**,
and documents the specific trap that produces recurring "dirty" release PRs —
with the project-specific workarounds.

## Merge strategy (policy decision, updated 2026-09-21)

**Rebase-and-merge is the default for all PRs** (features → `development`,
releases and hotfixes → `main`). Rationale: every commit stays visible in the
target branch's history, and rebase-and-merge keeps history linear on
`main` (where `required_linear_history` stays on).

**Merge commits are permanently allowed on `development`** (repo setting
`allow_merge_commit=true`). They are used exactly once: the `main →
development` sync when the trees genuinely diverge, so that `main`'s
tip becomes a true ancestor of `development`. No temporary "merge window"
is needed anymore — no settings are toggled, nothing is restored.

| Repo setting | Value | Note |
|--------------|-------|------|
| `allow_rebase_merge` | `true` | default merge method for all PRs |
| `allow_merge_commit` | `true` | used only for divergent-tree syncs to `development` |
| `allow_squash_merge` | `false` | disabled — keep full commit history |
| `delete_branch_on_merge` | `true` | unchanged |

## Branch model

| Branch | Purpose | Parent | Protection |
|--------|---------|--------|------------|
| `main` | Production-ready code. | — | PR required, strict CI, linear history, `enforce_admins: true` |
| `development` | Active development. All features and fixes land here first. | — | PR required, strict CI, linear history **off** (merge-commit syncs allowed), `enforce_admins: true` |
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
4. All CI checks must pass before merging. The required status checks on
   both protected branches are: `Lint`, `Unit Tests`, `Integration Tests`,
   `Build and Test Frozen Executable`.

## Recommended merge method per scenario

| Scenario | Merge method | Why |
|----------|--------------|-----|
| `feature/*` → `development` | **Rebase and merge** | all commits kept, replayed onto the latest `development` |
| `release/vX.Y.Z` → `main` | **Rebase and merge** | standard Git-Flow release; CI builds from the tag. Safe as long as the trees are identical (see trap below) |
| `hotfix/vX.Y.Z` → `main` | **Rebase and merge** | same as features, then sync to `development` |
| sync `main` → `development`, trees identical | **Hard-reset sync** (not a PR) | `git reset --hard origin/main && git push --force-with-lease origin development` — temporarily disable branch protection on `development` in the web UI, re-enable after |
| sync `main` → `development`, trees diverge | sync branch + **Create a merge commit** | records `main`'s ancestry inside `development`; permanently allowed (see above) |
| local feature branch maintenance | `git rebase` locally, then push | keeps the head up to date without re-writing merged history |

## Release-PR preflight (manual)

Before opening a release PR, compare `uv.lock` / `pyproject.toml` between
`origin/main` and the PR head. Packages present on **both** sides with
differing text (example: `fastmcp` 3.4.7 vs 4.0.0) must be aligned to the
union first — see the trap below.

```bash
git diff --stat origin/main <head>                       # which files differ
git diff origin/main <head> -- uv.lock pyproject.toml    # do the package blocks differ?
```

Clean → open the PR. Diverging overlapping package blocks → resolve to
byte-identical text (union) on the head before opening.

## The dirty-release-PR trap (why release PRs conflict repeatedly)

> [!NOTE]
> This is the exact failure mode Prism hit on `release: v0.2.2` (PR #32):
> GitHub kept showing *"This branch has conflicts that must be resolved. Use
> the command line..."* with `pyproject.toml` and `uv.lock`, no matter how
> many sync merges were made into `development`.

1. GitHub recomputes PR mergeability with a **three-way merge from the
   merge-base**, comparing `base → base-branch` against `base → head`,
   **per file, per text line**.
2. **Both squash merges and rebase merges create commits that are never
   ancestors of `development`** (squash: a single new commit; rebase: the
   replayed SHAs do not exist on `development` either). GitHub therefore
   re-runs the merge from the old split point every time.
3. When the two branches rewrite the **same files with different text** —
   Prism's case: `development` regenerates `uv.lock` wholesale (fastmcp
   pin, resolution markers removed) while `main` carries an upstream bump
   (`mkdocs-material>=9.7.7` plus removed `pymdown-extensions`) — the
   overlapping hunks differ, Git cannot fold them automatically, and the
   PR is marked **DIRTY** ("conflicts that must be resolved").
4. The fixes that work, in order:
   - **Record identical content** — resolve to a union (`pyproject.toml`
     with `mkdocs-material>=9.7.7` **and** `pymdown-extensions>=10.14`,
     fused `uv.lock`, markers removed) so both sides' overlapping lines
     are **byte-identical**; identical text folds cleanly. This is the
     release-PR preflight above.
   - **Record a true merge commit** — the divergent-tree sync (Create a
     merge commit, permanently allowed on `development`) makes `main`'s
     tip an **ancestor of `development`**, so GitHub recomputes from
     `main`'s tip as the merge-base and the PR flips **MERGEABLE**,
     permanently.

> [!NOTE]
> Rebase-merge does **not** cure the trap by itself: it keeps history,
> but the ancestry problem in point 2 remains. The cure is the preflight
> (point 4, fix 1) plus the merge-commit sync (point 4, fix 2).

## Sync workflow (exact steps)

| Sync case | Steps |
|-----------|-------|
| Trees identical (fast-forward) | hard-reset `development` to `main` (`git reset --hard origin/main && git push --force-with-lease origin development`) — temporarily disable protection on `development` in the web UI if `enforce_admins=true`, re-enable after |
| Trees diverge (real changes) | `git merge main` on a sync branch, resolve conflicts, open a PR to `development`, merge with **Create a merge commit** (no window, no setting toggles — merge commits are permanently allowed on `development`) |
| Never | squash a sync PR — it erases ancestry and re-dirties release PRs; rebase a sync PR — GitHub refuses "Rebase and merge" when the head contains a merge commit, which the sync branch does by construction |
| Before any release PR | the release-PR preflight above |

## Branch protection (verified 2026-09-21)

Both branches are protected with:

- PR required, `enforce_admins: true` (no bypasses, even for admins)
- strict up-to-date required status checks: `Lint`, `Unit Tests`,
  `Integration Tests`, `Build and Test Frozen Executable`
  (`Unit Tests` appears in both the Linux and Windows workflows — GitHub
  requires **all** same-named check runs to pass, which is the intent)
- no force pushes, no deletions, no restrictions, no PR-review requirements
- `required_linear_history`: **on** for `main`, **off** for `development`
  (so merge-commit sync PRs merge cleanly)

Check the live state any time with:

```bash
gh api repos/AdriaERNI/Prism/branches/main/protection
gh api repos/AdriaERNI/Prism/branches/development/protection
```

> [!NOTE]
> The required-checks context names must match the **check-run names**
> exactly (the job `name:` in the workflow YAML, case-sensitive). A
> mismatch — e.g. requiring `test-linux` (a workflow name) instead of
> `Integration Tests` (a job name) — makes **every** PR permanently
> `BLOCKED` even with green CI. This exact misconfiguration existed and
> was fixed on 2026-09-21.

## Resolving conflicts on the command line

When GitHub asks for command-line resolution:

1. `git fetch origin <base> <head>`
2. create the sync branch, `git merge --no-ff origin/main`, resolve the
   conflict markers to the union content, regenerate the fused `uv.lock`
3. commit the merge (`git commit`), push it to a non-protected sync branch,
   open a PR to `development`
4. merge that PR with **Create a merge commit** — this records `main`'s
   history inside `development` and clears the release PR

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
[merge-methods]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-merge-methods
[pr-merges]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/merging-a-pull-request
[branch-protection]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule
[protected-branches]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
[atlassian-gitflow]: https://www.atlassian.com/git/tutorials/gitflow-workflow
[trunk-paper]: https://arxiv.org/html/2507.08943v1
[toptal]: https://www.toptal.com/developers/git-flow-vs-trunk-based-development
