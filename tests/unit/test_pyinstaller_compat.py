"""Tests that verify PyInstaller compatibility — all runtime imports work.

These tests reproduce the exact import chain that triggers during
`prism serve` in a PyInstaller --onefile build. They catch:

1. Missing package metadata (importlib.metadata.version crashes)
2. Missing binary modules (lupa.lua51 not bundled)
3. Hidden imports that PyInstaller doesn't auto-detect

The tests run on all platforms (Linux + Windows CI) so Windows-specific
PyInstaller issues are caught before release.
"""

from __future__ import annotations

import importlib
import importlib.metadata

import pytest


# ── Package metadata availability ──────────────────────────────────
# PyInstaller --onefile builds must include .dist-info dirs for any
# package that calls importlib.metadata.version() at import time.


class TestPackageMetadata:
    """Verify that packages which need metadata at import time can find it."""

    @pytest.mark.parametrize(
        "package",
        [
            "fastmcp",
            "click",
            "httpx",
            "pydantic",
            "pydantic_settings",
            "typer",
            "websockets",
            "platformdirs",
            "python-dotenv",
        ],
    )
    def test_package_metadata_available(self, package):
        """importlib.metadata.version() must succeed for this package.

        In PyInstaller builds, this fails if --copy-metadata wasn't
        passed for the package. The build-release.yml workflow includes
        --copy-metadata for all of these.
        """
        try:
            v = importlib.metadata.version(package)
            assert v, f"Empty version for {package}"
        except importlib.metadata.PackageNotFoundError:
            pytest.fail(
                f"No package metadata for '{package}'. "
                f"In PyInstaller builds, add --copy-metadata {package} "
                f"to the build command."
            )

    def test_fastmcp_version_attribute(self):
        """fastmcp.__version__ must work (it calls importlib.metadata)."""
        import fastmcp

        assert hasattr(fastmcp, "__version__")
        assert fastmcp.__version__

    def test_click_version_attribute(self):
        """click.__version__ must work (it calls importlib.metadata)."""
        import click

        # Click 8.x uses importlib.metadata for __version__
        assert click.__version__  # noqa: B018


# ── Binary module availability ─────────────────────────────────────
# lupa (Lua bindings) is a transitive dependency via:
#   fastmcp -> pydocket -> fakeredis[lua] -> lupa
# PyInstaller must bundle the binary .so/.pyd files for lupa.lua*.


class TestLupaBinaryModules:
    """Verify lupa binary modules are importable.

    On Windows PyInstaller builds, lupa.lua51 is not auto-detected.
    The build must include --collect-all lupa or --hidden-import lupa.lua51.

    These tests reproduce the 'No module named lupa.lua51' crash.
    """

    def test_lupa_importable(self):
        """lupa itself must be importable."""
        import lupa

        assert lupa is not None

    @pytest.mark.parametrize(
        "module",
        [
            "lupa.lua51",
            "lupa.lua52",
            "lupa.lua53",
            "lupa.lua54",
        ],
    )
    def test_lupa_lua_module_importable(self, module):
        """Each lupa.lua* binary module must be importable.

        lupa.__init__ lazily imports these. On Windows, PyInstaller
        doesn't detect the .pyd files unless --collect-all lupa is used.
        """
        try:
            importlib.import_module(module)
        except ImportError as exc:
            pytest.fail(
                f"Cannot import '{module}': {exc}. "
                f"This is a PyInstaller hidden import issue. "
                f"Add --collect-all lupa to the build command."
            )

    def test_lupa_newest_lib_works(self):
        """lupa._import_newest_lib() must find at least one Lua module."""
        import lupa

        lib = lupa._import_newest_lib()
        assert lib is not None, (
            "lupa._import_newest_lib() returned None — no Lua binary module "
            "found. This will crash at runtime. Add --collect-all lupa to "
            "the PyInstaller build command."
        )

    def test_lupa_lua_runtime(self):
        """lupa must be able to find a Lua implementation (without segfaulting).

        We only check _import_newest_lib returns a module — actually
        creating a LuaRuntime segfaults on some CI environments due to
        binary module incompatibilities. The import check is sufficient
        to catch PyInstaller missing-module issues.
        """
        import lupa

        lib = lupa._import_newest_lib()
        assert lib is not None, (
            "lupa._import_newest_lib() returned None — no Lua binary module "
            "found. Add --collect-all lupa to the PyInstaller build command."
        )


# ── Full prism serve import chain ──────────────────────────────────
# This reproduces the exact import chain that `prism serve` triggers.


class TestServeImportChain:
    """Verify all imports in the prism serve chain work."""

    def test_import_mcp_server(self):
        """Importing the MCP server module must not crash."""
        from prism.mcp.server import create_mcp

        assert create_mcp is not None

    def test_import_serve_command(self):
        """Importing the serve command must not crash."""
        from prism.cli.commands.serve import serve

        assert serve is not None

    def test_import_fastmcp_directly(self):
        """fastmcp must be importable and functional."""
        from fastmcp import FastMCP

        assert FastMCP is not None

    def test_fastmcp_server_creation(self):
        """FastMCP server creation must work (triggers all internal imports)."""
        from fastmcp import FastMCP

        server = FastMCP("test")
        assert server is not None


# ── Version reporting ─────────────────────────────────────────────


class TestVersion:
    """Verify prism --version works."""

    def test_version_string_available(self):
        """The version must be available via prism.__version__."""
        from prism import __version__

        assert __version__, "prism.__version__ is empty"
        assert __version__ != "unknown"

    def test_version_in_pyproject(self):
        """pyproject.toml must have a version (checked via importlib.metadata)."""
        try:
            v = importlib.metadata.version("prism-mcp")
            assert v
        except importlib.metadata.PackageNotFoundError:
            pytest.skip("prism-mcp not installed as a package (dev mode)")
