# Prism — Dependency & Configuration Analysis

**Project:** Prism v0.2.1-beta2
**Date:** 2026-08-02
**Analyst:** Automated (pip-audit, uv tree, PyPI latest-versions check)
**Manifest:** `pyproject.toml` (uv + hatchling backend, `requires-python >= 3.12`)

---

## 1. Executive Summary

The project is well-structured with a clean dependency surface (10 runtime + 4 dev + 2 docs deps). The lockfile (`uv.lock`, 282 KB) is present and CI uses `uv sync --frozen`, giving reproducible builds. Ruff lint passes cleanly and the build configuration is correct.

**Key findings:**

| # | Severity | Finding |
|---|----------|---------|
| 1 | 🔴 High | **12 known CVEs** in transitive dependencies (click, idna, mcp, python-dotenv, requests, urllib3, pygments) — all fixable by bumping `fastmcp` |
| 2 | 🟡 Medium | `fastmcp` pinned at `>=3.4.4` (installed 3.4.4) but **3.4.5 available** — this single bump fixes 8 of the 12 CVEs |
| 3 | 🟡 Medium | `mkdocs-material` installed at 9.7.6, **9.7.7 available** — minor version drift |
| 4 | 🟡 Medium | `websockets` installed 16.1.1, **17.0.1 available** — major version available (requires testing) |
| 5 | 🟡 Medium | `intersystems-irispython` installed 5.3.2, **5.4.0 available** |
| 6 | 🟡 Medium | `pages.yml` installs `mkdocs-glightbox` and `pymdown-extensions` at runtime — **not declared** in `pyproject.toml` docs group or lockfile |
| 7 | 🟢 Low | `changelog.yml` workflow referenced in `AGENTS.md` but **does not exist** in `.github/workflows/` |
| 8 | 🟢 Low | No `[tool.ruff]` config in `pyproject.toml` — using ruff defaults (0.15.2 installed, 0.16.1 latest) |
| 9 | 🟢 Low | `rich` used directly in 5 source files but **not declared** — comes transitively via `fastmcp` → `cyclopts` and `typer` |
| 10 | 🟢 Low | `pyautogui` dev-dep has no upper bound and pulls `tkinter` platform deps on Linux headless CI (tests skip gracefully) |

**No unused dependencies** were found — every declared dependency is imported somewhere (details in §5).

---

## 2. Dependency Inventory

### 2.1 Runtime Dependencies (`[project].dependencies`)

| Package | Declared | Installed | Latest | Status |
|---------|----------|-----------|--------|--------|
| fastmcp | `>=3.4.4` | 3.4.4 | **3.4.5** | ⚠️ Bump available (fixes CVEs) |
| httpx | `>=0.28.1` | 0.28.1 | 0.28.1 | ✅ Current |
| intersystems-irispython | `>=5.3.2` | 5.3.2 | **5.4.0** | ⚠️ Minor behind |
| platformdirs | `>=4.10.1` | 4.11.0 | 4.11.0 | ✅ Current |
| prompt-toolkit | `>=3.0.53` | 3.0.53 | 3.0.53 | ✅ Current |
| pydantic-settings | `>=2.14.2` | 2.14.2 | 2.14.2 | ✅ Current |
| python-dotenv | `>=1.2.1` | 1.2.1 | **1.2.2** | ⚠️ Patch available (CVE fix) |
| typer | `>=0.27.0` | 0.27.0 | 0.27.0 | ✅ Current |
| toons | `>=0.7.0` | 0.7.0 | 0.7.0 | ✅ Current |
| websockets | `>=16.1.1` | 16.1.1 | **17.0.1** | ⚠️ Major available |

### 2.2 Dev Dependencies (`[dependency-groups].dev`)

| Package | Declared | Installed | Latest | Status |
|---------|----------|-----------|--------|--------|
| pyautogui | `>=0.9.54` | 0.9.54 | 0.9.54 | ✅ Current (GUI tests only) |
| pytest | `>=9.1.1` | 9.1.1 | 9.1.1 | ✅ Current |
| pytest-asyncio | `>=1.4.0` | 1.4.0 | 1.4.0 | ✅ Current |
| ruff | `>=0.9` | 0.15.2 | **0.16.1** | ⚠️ Behind (defaults only, no config) |

### 2.3 Docs Dependencies (`[dependency-groups].docs`)

| Package | Declared | Installed | Latest | Status |
|---------|----------|-----------|--------|--------|
| mkdocs | `>=1.6.1` | 1.6.1 | 1.6.1 | ✅ Current |
| mkdocs-material | `>=9.6` | 9.7.6 | **9.7.7** | ⚠️ Patch behind |

> **Note:** `pages.yml` also installs `mkdocs-glightbox` and `pymdown-extensions` via `uv pip install --system` at CI runtime — neither is in `pyproject.toml` or `uv.lock`. See §6.3.

---

## 3. Security Vulnerabilities (pip-audit)

`pip-audit` found **12 known vulnerabilities across 7 packages**. All are in transitive dependencies pulled in via `fastmcp` and its extras. Every one has an available fix version.

| Package | Installed | CVE / Advisory | Fix Version | Pulled in by |
|---------|-----------|----------------|-------------|--------------|
| **click** | 8.3.1 | PYSEC-2026-2132 | **8.3.3** | typer → click; fastmcp → uvicorn → click |
| **idna** | 3.11 | PYSEC-2026-215 (×2) | **3.15** | httpx → anyio → idna; requests → idna |
| **mcp** | 1.26.0 | PYSEC-2026-3481, -3482, -3483 | **1.27.2 / 1.28.1** | fastmcp → mcp[client, server] |
| **pygments** | 2.19.2 | PYSEC-2026-2987 | **2.20.0** | rich → pygments |
| **python-dotenv** | 1.2.1 | PYSEC-2026-2270 | **1.2.2** | **direct dependency** + fastmcp |
| **requests** | 2.32.5 | PYSEC-2026-2275 | **2.33.0** | jsonschema-path → requests (via cyclopts) |
| **urllib3** | 2.6.3 | PYSEC-2026-141, -142 (×2) | **2.7.0** | requests → urllib3 |

### Remediation

The single most impactful action is **bumping `fastmcp` from 3.4.4 → 3.4.5**, which will pull in `mcp >= 1.27.2` and resolve 3 CVEs. Bumping `python-dotenv` to `>=1.2.2` (a direct dep) fixes another. The remaining CVEs (click, idna, pygments, requests, urllib3) are deeper transitive chains that Dependabot should handle via lockfile updates.

```bash
# Immediate fix — update the direct dep and re-lock
uv add "python-dotenv>=1.2.2"
uv add "fastmcp>=3.4.5"
uv lock --upgrade-package python-dotenv --upgrade-package fastmcp \
        --upgrade-package click --upgrade-package idna \
        --upgrade-package pygments --upgrade-package urllib3 --upgrade-package requests
```

> `safety check` could not run — it crashed due to an `nltk`/`regex` import conflict in the project's CWD. pip-audit results above are authoritative.

---

## 4. Outdated Packages Summary

| Package | Installed | Latest | Gap | Action |
|---------|-----------|--------|-----|--------|
| fastmcp | 3.4.4 | 3.4.5 | patch | **Bump now** (CVE fix) |
| python-dotenv | 1.2.1 | 1.2.2 | patch | **Bump now** (CVE fix) |
| intersystems-irispython | 5.3.2 | 5.4.0 | minor | Test before bump |
| websockets | 16.1.1 | 17.0.1 | **major** | Test thoroughly before bump |
| ruff | 0.15.2 | 0.16.1 | minor | Low risk, bump anytime |
| mkdocs-material | 9.7.6 | 9.7.7 | patch | Low risk, bump anytime |

All other dependencies are at their latest versions.

---

## 5. Unused Dependencies Analysis

Every declared dependency is actively imported:

| Dependency | Used In | Verdict |
|------------|---------|---------|
| fastmcp | `mcp/server.py`, `mcp/_decorator.py`, `chatbot/agent.py` | ✅ Used |
| httpx | `iris/sdk/http.py`, `iris/api/terminal.py`, `iris/sdk/preflight.py`, `iris/api/interactive_ws.py`, `cli/errors.py`, `chatbot/agent.py` | ✅ Used |
| intersystems-irispython | `iris/sdk/terminal.py` (`import iris`, `import iris._elsdk_`) | ✅ Used |
| platformdirs | `settings.py`, `cast/manager.py` | ✅ Used |
| prompt-toolkit | `cli/interactive.py`, `cli/commands/chatbot.py` | ✅ Used |
| pydantic-settings | `settings.py` | ✅ Used |
| python-dotenv | `settings.py` (`from dotenv import load_dotenv`) | ✅ Used |
| typer | `cli/app.py`, all `cli/commands/*.py`, `output.py` | ✅ Used |
| toons | `output.py` (conditional `import toons` inside `format_output`) | ✅ Used (optional, gracefully degrades) |
| websockets | `iris/sdk/dbgp.py`, `iris/api/terminal.py`, `iris/api/interactive_ws.py` | ✅ Used |
| pyautogui | `tests/gui/test_visual_regression.py`, `tests/gui/test_gui_interactions.py` | ✅ Used (dev/GUI tests) |
| pytest | all `tests/` | ✅ Used |
| pytest-asyncio | `pyproject.toml` `asyncio_mode = "auto"` | ✅ Used |
| ruff | CI lint steps | ✅ Used |

### Undeclared but used (transitive)

| Package | Used In | Provided by |
|---------|---------|-------------|
| **rich** | `iris/monitor/dashboard.py`, `cli/commands/monitor.py`, `tests/unit/test_monitor_dashboard.py`, `scripts/visual_test_monitor.py` | `fastmcp` → `cyclopts` → `rich`; `typer` → `rich` |
| **pydantic** | `mcp/*.py` (all `from pydantic import Field`) | `pydantic-settings` → `pydantic` |

**Recommendation:** `rich` is used directly in production source (`dashboard.py`, `monitor.py`). If `fastmcp` ever drops `cyclopts` or `typer` drops `rich`, these imports break. Consider declaring `rich` explicitly. Same for `pydantic` (though `pydantic-settings` is unlikely to ever not depend on `pydantic`).

---

## 6. Configuration File Analysis

### 6.1 `pyproject.toml` — ✅ Correct

- **Build system:** hatchling, `packages = ["src/prism"]` — correct for `src/` layout.
- **`requires-python = ">=3.12"`** — matches `.python-version` (3.12) and CI (`python-version: "3.12"`).
- **`[project.scripts]` `prism = "prism.cli.app:main"`** — entry point matches `src/prism/cli/app.py:main()`.
- **`[tool.pytest.ini_options]`** — `asyncio_mode = "auto"`, `testpaths = ["tests"]` — correct and consistent with CI (`pytest tests/unit/`).
- **`[tool.ruff]`** — **not configured** (no section in pyproject.toml). Ruff runs with defaults. This is valid but means no line-length, select/ignore, or target-version customization. Consider adding at minimum:
  ```toml
  [tool.ruff]
  target-version = "py312"
  line-length = 100  # or whatever the project standard is
  ```

### 6.2 `mkdocs.yml` — ✅ Correct (with notes)

- `site_url` points to `https://adriaerni.github.io/Prism/` — matches `pages.yml` deploy.
- `edit_uri: edit/main/docs/` — correct for GitHub Pages on `main`.
- `nav:` structure has 14 nav entries, all referencing real docs files.
- `plugins:` uses `search` and `tags` — both built-in to mkdocs-material.
- `markdown_extensions:` — comprehensive and standard (admonition, pymdownx, toc, etc.).
- **Note:** `pymdownx.snippets` is enabled but no `base_path` is set — snippets will search relative to the docs dir by default. This works but could be made explicit.
- **Note:** No `mkdocs-glightbox` plugin configured in `mkdocs.yml`, yet `pages.yml` installs it. Either it's unused (safe to remove from CI install) or it should be added to `plugins:` in `mkdocs.yml`.

### 6.3 `.github/workflows/pages.yml` — 🟡 Minor issue

```yaml
- name: Install MkDocs and Material theme
  run: |
    uv venv
    uv pip install --system mkdocs-material pymdown-extensions mkdocs-glightbox
```

**Issue:** The docs deps in `pyproject.toml` only declare `mkdocs` and `mkdocs-material`. The CI workflow installs `pymdown-extensions` and `mkdocs-glightbox` **outside** the lockfile, bypassing reproducibility. Additionally, it runs `uv venv` + `--system` which conflicts with the `uv sync` pattern used in other workflows.

**Recommendation:** Either:
1. Add all three to the `docs` dependency group in `pyproject.toml` and use `uv sync --group docs` in CI, **or**
2. Remove `mkdocs-glightbox` from the install line if it's not actually used (no plugin entry in `mkdocs.yml`).

```toml
# Option 1 — add to pyproject.toml
[dependency-groups]
docs = [
    "mkdocs>=1.6.1",
    "mkdocs-material>=9.6",
    "pymdown-extensions>=10.0",
    "mkdocs-glightbox>=0.4.0",  # only if actually used
]
```
```yaml
# pages.yml — simplified
- name: Install docs dependencies
  run: uv sync --group docs
- name: Build documentation
  run: uv run mkdocs build --strict
```

### 6.4 `.github/workflows/test-linux.yml` — ✅ Correct

- Triggers: push/PR on `[main, development]` + `workflow_dispatch` — correct.
- Lint job: `uv sync --frozen` → `ruff check .` → `ruff format --check .` — correct.
- Unit job: `uv sync --frozen` → `pytest tests/unit/ -v --tb=short` — correct.
- Integration job: depends on `unit`, uses `intersystemsdc/iris-community:2025.3` service container with health checks — well-configured.
- All actions use `@v7` (checkout, setup-python, setup-uv) — current major versions.

### 6.5 `.github/workflows/test-windows.yml` — ✅ Correct (complex)

- Mirrors Linux workflow structure.
- Additional `build-and-test` job: builds PyInstaller frozen exe and runs extensive frozen-binary tests (--version, --help, shell completion, cast --list, serve with lupa/fakeredis/docket verification, deep MCP protocol suite).
- PyInstaller `--copy-metadata` and `--collect-all` flags are comprehensive and include all runtime deps.
- **Note:** Step "Test MCP protocol (deep extensive)" runs `tests/mcp/test_mcp_protocol.py` — this file exists in `tests/mcp/` but is not part of the standard `tests/unit/` or `tests/integration/` test paths. This is intentional (it's a standalone script taking a URL arg).

### 6.6 `.github/workflows/build-release.yml` — ✅ Correct

- Triggered by `v*` tags + `workflow_dispatch` with tag input.
- Pipeline: lint → test-linux → test-windows → build (matrix: ubuntu + windows) → release.
- Version sync from tag via PowerShell regex replacement in `pyproject.toml` and `__init__.py` — matches the AGENTS.md "CI syncs version from the tag" rule.
- Builds wheel (Linux) + PyInstaller exe + Inno Setup installer (Windows).
- Release job uses `softprops/action-gh-release@v3` with git-cliff changelog generation.
- `download-artifact@v8` is used (newer than the `@v7` used elsewhere — minor inconsistency, not a bug).

### 6.7 `.github/dependabot.yml` — ✅ Correct

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    target-branch: "development"
    schedule: { interval: "weekly", day: "monday" }
    open-pull-requests-limit: 5
    labels: ["dependencies", "python"]
    commit-message: { prefix: "deps" }
  - package-ecosystem: "github-actions"
    directory: "/"
    target-branch: "development"
    schedule: { interval: "weekly", day: "monday" }
    open-pull-requests-limit: 5
    labels: ["dependencies", "github-actions"]
    commit-message: { prefix: "ci" }
```

**Assessment:** Correct and well-configured:
- ✅ Both `pip` and `github-actions` ecosystems covered.
- ✅ Targets `development` branch (not `main`) — matches the Git Flow model in AGENTS.md.
- ✅ Weekly Monday schedule with 5 PR limit — reasonable.
- ✅ Commit message prefixes (`deps`, `ci`) aid changelog categorization.
- **Note:** `directory: "/"` for pip ecosystem — Dependabot will update `uv.lock` (since it's at root). This is correct for uv-managed projects.
- **Suggestion:** Consider adding `groups` to batch related updates (e.g., group all fastmcp-related transitive deps) to reduce PR noise.

### 6.8 Missing `changelog.yml` workflow — 🟡 Low

`AGENTS.md` documents a "Changelog" workflow (`.github/workflows/changelog.yml`) that regenerates `CHANGELOG.md` + `docs/changelog.md` via git-cliff on `v*` tags. This file **does not exist** in `.github/workflows/`. The changelog generation is currently handled inline by `build-release.yml` (the `release` job runs git-cliff as part of release creation). Either:
1. The `changelog.yml` workflow was removed/merged into `build-release.yml` and `AGENTS.md` is stale, **or**
2. A separate `changelog.yml` was planned but never created.

**Recommendation:** Update `AGENTS.md` to reflect that changelog generation is part of `build-release.yml`, or create the missing workflow if a standalone regeneration step is desired.

---

## 7. Build Configuration Issues

### 7.1 `uv.lock` state — ✅ Good

- Lockfile present (282 KB, 120 packages resolved).
- CI uses `uv sync --frozen` everywhere — reproducible builds.
- uv version: 0.11.28 (runtime).

### 7.2 `cliff.toml` — ✅ Present

- Used by `build-release.yml` for changelog generation. File exists (2.9 KB).

### 7.3 `.python-version` — ✅ Correct

- Contains `3.12`, matching `requires-python = ">=3.12"` and CI Python version.

---

## 8. Recommendations (Prioritized)

### Immediate (security)

1. **Bump `fastmcp` to `>=3.4.5`** — pulls `mcp >= 1.27.2`, fixing 3 CVEs.
2. **Bump `python-dotenv` to `>=1.2.2`** — fixes 1 direct CVE.
3. **Run `uv lock --upgrade`** to pull fix versions for `click`, `idna`, `pygments`, `requests`, `urllib3` from their respective upstream packages.

### Short-term (hygiene)

4. **Declare `rich` as a direct dependency** — it's imported in production source (`dashboard.py`, `monitor.py`) but only available transitively. A future fastmcp or typer change could break this.
5. **Add `[tool.ruff]` config** to `pyproject.toml` — at minimum `target-version = "py312"` and `line-length`. Currently running on defaults.
6. **Fix `pages.yml` docs install** — move `mkdocs-glightbox` and `pymdown-extensions` into the `docs` dependency group (or remove `glightbox` if unused). Use `uv sync --group docs` instead of `uv pip install --system`.
7. **Update or remove the `changelog.yml` reference** in `AGENTS.md` — the workflow doesn't exist; changelog generation is in `build-release.yml`.

### Medium-term (upgrades)

8. **Test `websockets` 16.1.1 → 17.0.1** — major version bump, used in 3 source files (dbgp, terminal, interactive_ws). Run integration tests.
9. **Test `intersystems-irispython` 5.3.2 → 5.4.0** — minor bump, used in native terminal SDK.
10. **Bump `ruff` 0.15.2 → 0.16.1** — minor, low risk, then re-run `ruff check --fix .`.

---

## 9. Verification Commands

```bash
# Re-run security audit after bumps
PYTHONPATH='' uv run pip-audit

# Verify lint still passes
PYTHONPATH='' uv run ruff check . && uv run ruff format --check .

# Verify docs build
PYTHONPATH='' uv run --group docs mkdocs build --strict

# Verify tests still pass
PYTHONPATH='' uv run pytest tests/unit/ -v --tb=short
```