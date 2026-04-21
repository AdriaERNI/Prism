"""Configuration loaded from environment / .env file / settings.json.

Precedence (highest wins):
1. Environment variables
2. ``.env`` file (via python-dotenv)
3. ``settings.json`` in the platform user config directory
"""

import os

from dotenv import load_dotenv

from prism.iris.settings import inject_settings

load_dotenv()
inject_settings()

IRIS_BASE_URL = os.getenv("IRIS_BASE_URL", "http://localhost:52773")
IRIS_USERNAME = os.getenv("IRIS_USERNAME", "_SYSTEM")
IRIS_PASSWORD = os.getenv("IRIS_PASSWORD", "SYS")
IRIS_NAMESPACE = os.getenv("IRIS_NAMESPACE", "USER")
IRIS_WORKSPACE = os.getenv("IRIS_WORKSPACE", "")
IRIS_API_PREFIX = os.getenv("IRIS_API_PREFIX", "api/atelier/v8")
IRIS_COMPILE_FLAGS = os.getenv("IRIS_COMPILE_FLAGS", "cuk")
IRIS_SUPERSERVER_PORT = int(os.getenv("IRIS_SUPERSERVER_PORT", "1972"))
IRIS_TERMINAL_METHOD = os.getenv("IRIS_TERMINAL_METHOD", "native")
IRIS_TERMINAL_MAX_OUTPUT_CHARS = int(
    os.getenv("IRIS_TERMINAL_MAX_OUTPUT_CHARS", "100000")
)

# Testing configuration
IRIS_TEST_RUNNER_CLASS = os.getenv("IRIS_TEST_RUNNER_CLASS", "MCP.TestRunner")
IRIS_TEST_RUNNER_METHOD = os.getenv("IRIS_TEST_RUNNER_METHOD", "RunTests")
IRIS_TEST_MANAGER_CLASS = os.getenv("IRIS_TEST_MANAGER_CLASS", "%UnitTest.Manager")
IRIS_TEST_AUTO_DEPLOY = os.getenv("IRIS_TEST_AUTO_DEPLOY", "true").lower() in (
    "true",
    "1",
    "yes",
)

# Output format configuration
PRISM_OUTPUT_FORMAT = os.getenv("PRISM_OUTPUT_FORMAT", "json")

# Debugging configuration
IRIS_DEBUG_ENABLED = os.getenv("IRIS_DEBUG_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
IRIS_DEBUG_STEP_GRANULARITY = os.getenv("IRIS_DEBUG_STEP_GRANULARITY", "line")
IRIS_DEBUG_MAX_DATA = int(os.getenv("IRIS_DEBUG_MAX_DATA", "8192"))
IRIS_DEBUG_MAX_CHILDREN = int(os.getenv("IRIS_DEBUG_MAX_CHILDREN", "32"))
IRIS_DEBUG_MAX_DEPTH = int(os.getenv("IRIS_DEBUG_MAX_DEPTH", "2"))
IRIS_DEBUG_IDLE_TIMEOUT = int(os.getenv("IRIS_DEBUG_IDLE_TIMEOUT", "300"))
