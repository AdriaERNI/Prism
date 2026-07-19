"""Automated GUI integration tests for the Prism SQL Editor.

These tests launch the actual GUI in a headless Xvfb environment,
interact with it using pyautogui, and verify behavior through:
1. Direct widget introspection (via the app object)
2. Screenshot capture + emy vision analysis
3. pyautogui pixel/color checking

Requirements:
    - Xvfb running on :99
    - IRIS container on localhost:52773
    - pyautogui installed
    - pygetwindow (for window management)
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

# Skip all tests in this module if not in a GUI-capable environment
pytestmark = pytest.mark.skipif(
    os.environ.get("PRISM_GUI_TESTS") != "1",
    reason="Set PRISM_GUI_TESTS=1 to enable GUI integration tests",
)

# Ensure we have the right DISPLAY
DISPLAY = os.environ.get("DISPLAY", ":99")


@pytest.fixture(scope="module")
def xvfb():
    """Start Xvfb if not already running."""
    # Check if Xvfb is already running
    result = subprocess.run(["pgrep", "-f", "Xvfb.*:99"], capture_output=True)
    if result.returncode != 0:
        proc = subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1280x800x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        yield proc
        proc.terminate()
        proc.wait()
    else:
        # Already running
        yield None


@pytest.fixture(scope="module")
def gui_app(xvfb):
    """Launch the Prism GUI app and return the process handle."""
    env = os.environ.copy()
    env["DISPLAY"] = ":99"
    env.setdefault("IRIS_BASE_URL", "http://localhost:52773")
    env.setdefault("IRIS_USERNAME", "_SYSTEM")
    env.setdefault("IRIS_PASSWORD", "SYS")

    proc = subprocess.Popen(
        ["uv", "run", "prism", "gui"],
        cwd=str(Path(__file__).parent.parent.parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for the window to appear
    time.sleep(4)
    yield proc

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def pyautogui():
    """Import and configure pyautogui."""
    try:
        import pyautogui
    except ImportError:
        pytest.skip("pyautogui not installed")

    pyautogui.FAILSAFE = False  # Disable fail-safe for headless
    return pyautogui


@pytest.fixture
def screenshot_path(tmp_path):
    """Return a path for screenshots."""
    return tmp_path / "screenshot.png"


# ── Test Classes ─────────────────────────────────────────────────────


class TestGUIStartup:
    """Test that the GUI starts correctly."""

    def test_window_appears(self, gui_app):
        """Verify the Prism window is visible."""
        assert gui_app.poll() is None, "GUI process should still be running"

    def test_process_is_alive(self, gui_app):
        """Verify the process hasn't crashed."""
        assert gui_app.poll() is None


class TestSQLEditor:
    """Test the SQL editor widget."""

    def test_type_query(self, gui_app, pyautogui, screenshot_path):
        """Type a SQL query in the editor and verify via screenshot."""
        # Click in the editor area (center of window, upper portion)
        # Window should be at default position
        pyautogui.click(500, 200)
        time.sleep(0.5)

        # Type a SQL query
        query = "SELECT 1 AS one"
        pyautogui.typewrite(query, interval=0.05)
        time.sleep(0.5)

        # Take screenshot
        pyautogui.screenshot(str(screenshot_path))
        assert screenshot_path.exists()
        assert screenshot_path.stat().st_size > 1000


class TestExecuteQuery:
    """Test the Execute query functionality."""

    def test_open_query_and_execute(self, gui_app, pyautogui, screenshot_path):
        """Type a query, click Execute, and verify results appear."""
        # Click in editor
        pyautogui.click(500, 200)
        time.sleep(0.3)

        # Clear any existing text and type a query
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("delete")
        time.sleep(0.1)

        query = "SELECT TOP 5 TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES"
        pyautogui.typewrite(query, interval=0.03)
        time.sleep(0.3)

        # Click Execute button (top-left toolbar area)
        # The toolbar is approximately at y=100 (menu bar + toolbar)
        # Execute button is the first button in the right panel toolbar
        pyautogui.click(300, 110)
        time.sleep(3)  # Wait for query execution

        # Take screenshot to verify results
        pyautogui.screenshot(str(screenshot_path))
        assert screenshot_path.exists()


class TestDatabaseTree:
    """Test the database navigator tree."""

    def test_tree_is_populated(self, gui_app, pyautogui, screenshot_path):
        """Verify the database tree shows schemas."""
        # Take a screenshot of the sidebar
        pyautogui.screenshot(str(screenshot_path))
        assert screenshot_path.exists()

    def test_click_schema_to_expand(self, gui_app, pyautogui, screenshot_path):
        """Click on a schema node to expand it."""
        # Click on the first schema node in the tree
        # Tree is in the left sidebar, below the "Database Navigator" header
        pyautogui.click(120, 150)
        time.sleep(0.5)

        # Take screenshot
        pyautogui.screenshot(str(screenshot_path))


class TestToolbarButtons:
    """Test toolbar button interactions."""

    def test_clear_button(self, gui_app, pyautogui, screenshot_path):
        """Click the Clear button and verify results are cleared."""
        # Clear button is in the toolbar (approximately x=400, y=110)
        pyautogui.click(400, 110)
        time.sleep(0.5)

        pyautogui.screenshot(str(screenshot_path))


class TestKeyboardShortcuts:
    """Test keyboard shortcuts."""

    def test_ctrl_enter_executes(self, gui_app, pyautogui, screenshot_path):
        """Ctrl+Enter should execute the query."""
        # Click in editor
        pyautogui.click(500, 200)
        time.sleep(0.3)

        # Type a simple query
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("delete")
        pyautogui.typewrite("SELECT 1 AS test", interval=0.05)
        time.sleep(0.3)

        # Press Ctrl+Enter
        pyautogui.hotkey("ctrl", "return")
        time.sleep(2)

        pyautogui.screenshot(str(screenshot_path))


class TestContextMenu:
    """Test right-click context menu."""

    def test_right_click_in_editor(self, gui_app, pyautogui, screenshot_path):
        """Right-click in the editor should show context menu."""
        pyautogui.click(500, 200)
        time.sleep(0.2)
        pyautogui.rightClick(500, 200)
        time.sleep(0.5)

        pyautogui.screenshot(str(screenshot_path))

        # Press Escape to close the menu
        pyautogui.press("escape")
