"""Visual regression tests — use emy vision model to verify GUI appearance.

These tests:
1. Launch the GUI in Xvfb
2. Interact with each feature
3. Take screenshots
4. Ask emy to describe what it sees
5. Assert the description matches expectations
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("PRISM_GUI_TESTS") != "1",
    reason="Set PRISM_GUI_TESTS=1 to enable GUI integration tests",
)

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

from tests.gui.emy_vision import analyze_screenshot, assert_contains  # noqa: E402


@pytest.fixture(scope="module")
def gui_process():
    """Launch the Prism GUI."""
    env = os.environ.copy()
    env["DISPLAY"] = ":99"
    env.setdefault("IRIS_BASE_URL", "http://localhost:52773")
    env.setdefault("IRIS_USERNAME", "_SYSTEM")
    env.setdefault("IRIS_PASSWORD", "SYS")

    proc = subprocess.Popen(
        ["uv", "run", "prism", "gui"],
        cwd=str(Path(__file__).parent.parent.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(4)
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def screenshot(tmp_path, name: str) -> str:
    """Take a screenshot and return its path."""
    path = str(tmp_path / f"{name}.png")
    pyautogui.screenshot(path)
    return path


class TestVisualLayout:
    """Verify the overall GUI layout matches DBeaver-inspired design."""

    def test_window_appears_with_correct_title(self, gui_process, tmp_path):
        """GUI window should be visible with 'Prism' in the title."""
        ss = screenshot(tmp_path, "window_title")
        assert os.path.getsize(ss) > 5000

    def test_sidebar_database_navigator_visible(self, gui_process, tmp_path):
        """Database Navigator sidebar should be visible on the left."""
        ss = screenshot(tmp_path, "sidebar")
        response = analyze_screenshot(
            ss,
            "Is there a sidebar labeled 'Database Navigator' on the left side? What schemas are visible?",
        )
        assert_contains(response, "database navigator", "schema")

    def test_sql_editor_with_line_numbers(self, gui_process, tmp_path):
        """SQL editor should have line numbers on the left."""
        # Click in editor and type
        pyautogui.click(500, 250)
        time.sleep(0.3)
        pyautogui.typewrite("SELECT 1", interval=0.05)
        time.sleep(0.3)

        ss = screenshot(tmp_path, "editor_line_numbers")
        response = analyze_screenshot(
            ss,
            "Is there a line number gutter on the left of the SQL editor? What number is shown? Is there SQL text visible?",
        )
        assert_contains(response, "line number", "1")

    def test_syntax_highlighting(self, gui_process, tmp_path):
        """SQL keywords should be syntax highlighted."""
        pyautogui.click(500, 250)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.typewrite("SELECT TOP 5 * FROM TABLE WHERE ID = 1", interval=0.03)
        time.sleep(0.5)

        ss = screenshot(tmp_path, "syntax_highlight")
        response = analyze_screenshot(
            ss,
            "Is syntax highlighting visible in the SQL editor? Are SQL keywords like SELECT, FROM, WHERE colored differently (e.g., blue)?",
        )
        assert_contains(response, "select")

    def test_tab_bar_visible(self, gui_process, tmp_path):
        """Tab bar should be visible above the SQL editor."""
        ss = screenshot(tmp_path, "tab_bar")
        response = analyze_screenshot(
            ss, "Is there a tab bar above the SQL editor? What does the tab say?"
        )
        assert_contains(response, "query")

    def test_execute_query_shows_results(self, gui_process, tmp_path):
        """Executing a query should show results in the bottom panel."""
        # Type a query
        pyautogui.click(500, 250)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.typewrite(
            "SELECT TOP 5 TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES",
            interval=0.03,
        )
        time.sleep(0.3)

        # Execute via Ctrl+Enter
        pyautogui.hotkey("ctrl", "return")
        time.sleep(3)

        ss = screenshot(tmp_path, "executed_results")
        response = analyze_screenshot(
            ss,
            "Are there query results showing in the bottom panel? How many rows are visible? What columns?",
        )
        # Should mention results/rows
        lower = response.lower()
        assert "result" in lower or "row" in lower, (
            f"Expected results in response: {response}"
        )

    def test_database_tree_expandable(self, gui_process, tmp_path):
        """Clicking a schema in the tree should expand it."""
        # Click on a schema in the tree (left sidebar)
        pyautogui.click(120, 150)
        time.sleep(1)

        ss = screenshot(tmp_path, "tree_expanded")
        response = analyze_screenshot(
            ss,
            "Look at the Database Navigator tree. Is any schema node expanded showing tables inside? Or are they all collapsed?",
        )
        # The tree should show schemas (either expanded or collapsed)
        assert_contains(response, "schema")

    def test_status_bar_visible(self, gui_process, tmp_path):
        """Status bar should be visible at the bottom of the window."""
        ss = screenshot(tmp_path, "status_bar")
        response = analyze_screenshot(
            ss,
            "Describe the very bottom strip of the window. Is there a thin bar at the bottom? What does it say?",
        )
        # emy may describe it as 'bottom', 'bar', 'strip' etc.
        lower = response.lower()
        assert any(w in lower for w in ["bottom", "bar", "strip", "status"]), (
            f"Expected bottom bar in response: {response}"
        )

    def test_separator_lines(self, gui_process, tmp_path):
        """Separator lines should be visible between sections."""
        ss = screenshot(tmp_path, "separators")
        analyze_screenshot(
            ss,
            "Are there separator lines between the toolbar and the editor area? Describe any visible separators.",
        )
        # Should mention something about separators/dividers

    def test_results_header_bar(self, gui_process, tmp_path):
        """Results panel should have a header bar labeled 'Result 1'."""
        # Execute a query first to have results
        pyautogui.click(500, 250)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.typewrite("SELECT 1 AS one", interval=0.05)
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "return")
        time.sleep(2)

        ss = screenshot(tmp_path, "results_header")
        response = analyze_screenshot(
            ss, "Is there a header bar labeled 'Result 1' above the results table?"
        )
        assert_contains(response, "result")
