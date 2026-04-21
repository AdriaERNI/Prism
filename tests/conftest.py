"""Root test configuration — shared MCP client fixture."""

import pytest
from fastmcp import Client

from prism.mcp.server import create_mcp


@pytest.fixture
def client():
    return Client(create_mcp())
