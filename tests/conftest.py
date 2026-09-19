"""Root test configuration — shared MCP client fixture."""

import sys
from pathlib import Path

# Expose the repo root so `scripts.*` tooling imports resolve under pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastmcp import Client

from prism.mcp.server import create_mcp


@pytest.fixture
def client():
    return Client(create_mcp())
