# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Conventional Commits](https://www.conventionalcommits.org/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Bug Fixes

- Resolve PyInstaller runtime issues with iris native API and terminal([c29e482](https://github.com/AdriaERNI/Prism/commit/c29e48223b546dc2387c4913179a733b85012af6))

- Move _connect inside try/except for license error retry (#14)([95b96f2](https://github.com/AdriaERNI/Prism/commit/95b96f286200b1b66355900b74c90b08097914a2))

- Set dependabot target-branch to development (#18)([51be909](https://github.com/AdriaERNI/Prism/commit/51be909bb03704262bfdb130a9373743a7e8253d))

- Use project logo.svg instead of placeholder, remove fake assets([bb9e0ea](https://github.com/AdriaERNI/Prism/commit/bb9e0ea344f3d14d9ca908a5846de37cee8ece36))


### CI/CD

- Add GitHub Actions workflow for lint and tests([d4778ab](https://github.com/AdriaERNI/Prism/commit/d4778ab475af585444413d663899e11e3e26e6a0))

- Add GitHub Pages workflow for MkDocs documentation([e1cb8cc](https://github.com/AdriaERNI/Prism/commit/e1cb8cc4936a09d609ad1ef631be10551bc8c915))

- Add security policy, dependabot, issue/PR templates([f3296ff](https://github.com/AdriaERNI/Prism/commit/f3296ff21f5680c8208e705d6a2e6bb40e15a9eb))

- Add GitHub Actions workflows for testing and releases (#1)([3cbbff5](https://github.com/AdriaERNI/Prism/commit/3cbbff515ef3557ffa83dea1b8559cb0d0f78e06))

- Bump actions/upload-pages-artifact from 3 to 5 (#4)([ef7882c](https://github.com/AdriaERNI/Prism/commit/ef7882c06bd01d5cb0a3d7b33cdc984fc71b0924))

- Bump actions/download-artifact from 4 to 8 (#7)([e15f2dc](https://github.com/AdriaERNI/Prism/commit/e15f2dc71fae41792955630afdcf59069b8cc6c4))


### Dependencies

- **deps:** Bump GitHub Actions and pydantic-settings (#17)([9d094d5](https://github.com/AdriaERNI/Prism/commit/9d094d58cecdfeae14b6463591f15b621b41ebf6))

- **deps:** Bump cryptography from 46.0.5 to 48.0.1 (#9)([955807a](https://github.com/AdriaERNI/Prism/commit/955807afc42574caa35d854e89b448ce4180064c))

- **deps:** Bump python-multipart from 0.0.22 to 0.0.31 (#11)([8b635d0](https://github.com/AdriaERNI/Prism/commit/8b635d0c942cc8fc03619aee14c763bcf44b11a9))


### Documentation

- Add PowerShell quoting guide to prism-iris-tools skill([9182867](https://github.com/AdriaERNI/Prism/commit/9182867a3027651e18e889fa606109e6cbd11887))

- Add comprehensive testing guide([23060ea](https://github.com/AdriaERNI/Prism/commit/23060ea461c1eccfd14876143b2066f1c55121af))

- Review and update documentation, add integration tests([5cc798d](https://github.com/AdriaERNI/Prism/commit/5cc798dd932349bc4ed2ef7757701920d5d3a3b1))

- Add LICENSE, remove .claude, professional mkdocs theme([6643192](https://github.com/AdriaERNI/Prism/commit/6643192ca4af0f6426dcac4a8724c59fe8d682d0))

- Update AGENTS.md with CI, license, tool counts, test patterns([6038ad9](https://github.com/AdriaERNI/Prism/commit/6038ad997c5c57fae639d46c9e23046e0eebc391))

- Add logo header to README for professional look([c5d7f70](https://github.com/AdriaERNI/Prism/commit/c5d7f70f2a86049b20969adb0e6b32dd5067c700))

- Move license section to bottom of README([f0c4378](https://github.com/AdriaERNI/Prism/commit/f0c43787d9aeb994dc87b764e2bb2e1cbcefda7d))

- Switch to PolyForm Noncommercial License 1.0.0 + Share-Alike([460cfe9](https://github.com/AdriaERNI/Prism/commit/460cfe99d1f19b57c60426a1c6b81c0f2ef79a90))

- Switch to AGPL-3.0 license([af38e1c](https://github.com/AdriaERNI/Prism/commit/af38e1cacddc444ccd6cbc2de28433fadc0f2e8e))

- Professional README rewrite([b5d44ca](https://github.com/AdriaERNI/Prism/commit/b5d44ca47bbe85b371b14f9c99dec1f388c4aaec))


### Features

- Add TOON output format support for CLI and MCP tools([1c8c799](https://github.com/AdriaERNI/Prism/commit/1c8c7997b78050b8bad743667ded15290fd41320))

- **config:** Expand `prism config` with full setting coverage and reset modes([d1aaf5a](https://github.com/AdriaERNI/Prism/commit/d1aaf5a6be65deeb6f6e7728699a99d8e90a124a))


### Miscellaneous

- Bump version to 0.1.5([26174b2](https://github.com/AdriaERNI/Prism/commit/26174b2821f141aff5eebd384d0067b4e8d7111c))

- Update PyInstaller build script for iris native modules([24d9004](https://github.com/AdriaERNI/Prism/commit/24d900454d1ee645d2f9f0e2952db34a9055fe8b))


### Refactoring

- Consolidate settings on pydantic-settings([210fb4a](https://github.com/AdriaERNI/Prism/commit/210fb4a9bc5a8035ffce3b972ec4704e91a8bef7))


### Sync

- Native terminal retry fix + development updates (#15)([1b9d5c6](https://github.com/AdriaERNI/Prism/commit/1b9d5c6c2b1f9b2375cb43af0e4cebf20f47690a))


### Testing

- Add Vagrant Windows integration test suite([f6052ed](https://github.com/AdriaERNI/Prism/commit/f6052ed29795c9c3340fb2ebd1c94c15beb794c5))


### Deps

- Bump pyjwt from 2.11.0 to 2.13.0 (security release) (#19)([335a70f](https://github.com/AdriaERNI/Prism/commit/335a70fe191875f0cb8ab959b12e750719e8766c))


### Merge

- Resolve conflict in terminal.py (keep conn=None guard from development)([4a6b301](https://github.com/AdriaERNI/Prism/commit/4a6b301067d94f7e4495e15d9815e741da407882))


## [0.1.3] - 2026-04-21

<!-- generated by git-cliff -->
