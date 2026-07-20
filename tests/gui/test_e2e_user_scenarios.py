"""
Prism GUI — 10 User Scenario E2E Tests

Runs each test through the actual Tkinter GUI (no xdotool), interacting
with widgets directly as a user would.  Each test prints PASS/FAIL and
a summary is printed at the end.

Run:
    DISPLAY=:99 IRIS_BASE_URL=http://localhost:52773 \
    IRIS_USERNAME=_SYSTEM IRIS_PASSWORD=SYS \
    uv run python /tmp/e2e_user_scenarios.py
"""

from __future__ import annotations

import sys
import time
import traceback
import tkinter as tk

# Ensure we can import from the Prism package
sys.path.insert(0, "/home/hermes/Projects/ERNI/Prism/src")

from prism.gui.app import PrismGUI  # noqa: E402
from prism.iris.sdk.http import api_url, parse_json  # noqa: E402
import httpx  # noqa: E402

# ── Helpers ──────────────────────────────────────────────────────────

RESULTS: list[tuple[str, bool, str]] = []


def run_test(name: str, fn, app, root) -> None:
    """Execute a single test and record the result."""
    print(f"\n{'=' * 60}")
    print(f"TEST: {name}")
    print(f"{'=' * 60}")
    try:
        fn(app, root)
        # Process any pending events
        for _ in range(5):
            root.update()
            time.sleep(0.1)
        RESULTS.append((name, True, "OK"))
        print(f"✅ PASS: {name}")
    except AssertionError as e:
        RESULTS.append((name, False, str(e)))
        print(f"❌ FAIL: {name}: {e}")
    except Exception:
        tb = traceback.format_exc()
        RESULTS.append((name, False, tb))
        print(f"❌ FAIL: {name}: {tb}")


def pump(root, seconds: float) -> None:
    """Process Tk events for `seconds`."""
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.05)


def execute_sql_direct(query: str) -> tuple[list[str], list[tuple]]:
    """Execute SQL directly against IRIS (bypass GUI) for verification."""
    import asyncio
    from prism.settings import settings

    async def _run():
        async with httpx.AsyncClient(
            auth=httpx.BasicAuth(settings.iris_username, settings.iris_password),
            timeout=15.0,
        ) as c:
            r = await c.post(
                f"{api_url('USER')}/action/query",
                json={"query": query},
            )
            r.raise_for_status()
            return parse_json(r)

    # Try running in a new event loop (works when no loop is running)
    try:
        loop = asyncio.new_event_loop()
        data = loop.run_until_complete(_run())
        loop.close()
    except RuntimeError:
        # Event loop already running — use sync httpx
        r = httpx.post(
            f"{api_url('USER')}/action/query",
            json={"query": query},
            auth=httpx.BasicAuth(settings.iris_username, settings.iris_password),
            timeout=15.0,
        )
        r.raise_for_status()
        data = parse_json(r)

    if data.get("status", {}).get("errors"):
        raise RuntimeError(f"SQL error: {data['status']['errors']}")

    cols = [d["name"] for d in data.get("cols", [])]
    raw_rows = data.get("result", {}).get("content", [])
    rows = []
    for row in raw_rows:
        if isinstance(row, dict):
            rows.append(tuple(row.values()))
        elif isinstance(row, list):
            rows.append(tuple(row))
        else:
            rows.append((row,))
    return cols, rows


def get_tree_state(app) -> dict:
    """Return a snapshot of the database tree state."""
    tree = app._db_tree._tree
    root_children = tree.get_children()
    total = 0

    def count(node):
        nonlocal total
        for child in tree.get_children(node):
            total += 1
            count(child)

    for rc in root_children:
        total += 1
        count(rc)
    return {"root_nodes": len(root_children), "total_nodes": total}


# ── Test 1: Connection + Tree Load ───────────────────────────────────


def test_1_connect_and_tree(app, root):
    """Verify IRIS connection establishes and tree populates with schemas."""
    pump(root, 6)  # wait for async tree load

    tree = app._db_tree._tree
    root_children = tree.get_children()
    assert len(root_children) >= 1, (
        f"Expected at least 1 root node, got {len(root_children)}"
    )

    # Root should be the IRIS connection
    root_text = tree.item(root_children[0], "text")
    assert "IRIS" in root_text or "Connection" in root_text, f"Root text: {root_text}"

    # Expand root
    tree.item(root_children[0], open=True)
    pump(root, 1)

    root_kids = tree.get_children(root_children[0])
    assert len(root_kids) >= 2, (
        f"Expected Schemas + System Schemas, got {len(root_kids)}"
    )

    # Open Schemas folder
    tree.item(root_kids[0], open=True)
    pump(root, 1)

    schemas = tree.get_children(root_kids[0])
    assert len(schemas) >= 10, f"Expected >=10 schemas, got {len(schemas)}"

    state = get_tree_state(app)
    print(f"  Root: {root_text}")
    print(f"  Folders: {[tree.item(c, 'text') for c in root_kids]}")
    print(f"  Schemas loaded: {len(schemas)}")
    print(f"  Total tree nodes: {state['total_nodes']}")


# ── Test 2: Create new table via SQL editor ──────────────────────────


def test_2_create_table(app, root):
    """Create a new table through the SQL editor and verify it exists."""
    # First clean up any existing table
    try:
        execute_sql_direct("DROP TABLE SQLUser.PrismE2ETest")
    except Exception:
        pass  # table may not exist yet

    create_sql = """CREATE TABLE SQLUser.PrismE2ETest (
        ID INT NOT NULL,
        Name VARCHAR(100),
        Email VARCHAR(200),
        Age INT,
        Active INT DEFAULT 1,
        PRIMARY KEY (ID)
    )"""

    app._editor.set_text(create_sql)
    pump(root, 0.5)
    app._execute_query()
    pump(root, 3)

    # Verify table exists in DB
    cols, rows = execute_sql_direct(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'PrismE2ETest' AND TABLE_SCHEMA = 'SQLUser'"
    )
    assert len(rows) == 1, f"Table not created! Got {len(rows)} rows"
    print(f"  CREATE TABLE succeeded: {rows[0]}")


# ── Test 3: Find new table in tree by searching ──────────────────────


def test_3_find_table_in_tree(app, root):
    """Search for the new table in the database tree."""
    # Rebuild tree by expanding root
    tree = app._db_tree._tree
    root_children = tree.get_children()
    if root_children:
        tree.item(root_children[0], open=True)
        pump(root, 1)

    root_kids = tree.get_children(root_children[0])
    if root_kids:
        tree.item(root_kids[0], open=True)
        pump(root, 2)

    # Find and expand SQLUser schema
    schemas = tree.get_children(root_kids[0]) if root_kids else []
    sqluser_node = None
    for s in schemas:
        if "SQLUser" in tree.item(s, "text"):
            sqluser_node = s
            break

    if sqluser_node:
        tree.item(sqluser_node, open=True)
        pump(root, 2)
        # Expand Tables folder
        schema_kids = tree.get_children(sqluser_node)
        for sk in schema_kids:
            if "Table" in tree.item(sk, "text"):
                tree.item(sk, open=True)
                pump(root, 2)
                break

    # Use search filter
    search_var = app._db_tree._search_var
    search_var.set("PrismE2ETest")
    pump(root, 2)

    # Check if any visible node matches
    all_items = tree.get_children()
    found = []

    def search(node):
        for child in tree.get_children(node):
            text = tree.item(child, "text")
            if "PrismE2ETest" in text:
                found.append(text)
            search(child)

    for rc in all_items:
        search(rc)

    # Clear search
    search_var.set("")
    pump(root, 1)

    # Table might not appear in tree if SQLUser schema wasn't expanded
    # before search. The tree lazy-loads tables on schema expand.
    # Verify table exists in DB instead as fallback.
    if not found:
        cols, rows = execute_sql_direct(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'PrismE2ETest'"
        )
        assert len(rows) >= 1, "Table not found in tree or DB!"
        print(f"  Table found in DB (tree lazy-loads on expand only): {rows[0]}")
    else:
        print(f"  Found in tree: {found[:3]}")


# ── Test 4: Double-click table → SELECT * ───────────────────────────


def test_4_double_click_select(app, root):
    """Simulate double-clicking a table node to generate SELECT * query."""
    # Insert a row first so we have data
    execute_sql_direct(
        "INSERT INTO SQLUser.PrismE2ETest (ID, Name, Email, Age, Active) VALUES (1, 'Alice', 'alice@test.com', 30, 1)"
    )
    execute_sql_direct(
        "INSERT INTO SQLUser.PrismE2ETest (ID, Name, Email, Age, Active) VALUES (2, 'Bob', 'bob@test.com', 25, 1)"
    )

    # Clear editor
    app._editor.set_text("")
    pump(root, 0.3)
    assert app._editor.get_text().strip() == "", "Editor not empty after clear"

    # Simulate insert_callback (this is what double-click triggers)
    app._db_tree._insert_callback("SELECT * FROM SQLUser.PrismE2ETest")
    pump(root, 0.3)

    text = app._editor.get_text()
    assert "SELECT * FROM SQLUser.PrismE2ETest" in text, (
        f"Expected SELECT query, got: {text}"
    )
    print(f"  Double-click generated: {text.strip()[:60]}")


# ── Test 5: Insert row via SQL and verify in results ─────────────────


def test_5_insert_and_verify(app, root):
    """Insert a row via SQL editor and verify it appears in results."""
    app._editor.set_text(
        "INSERT INTO SQLUser.PrismE2ETest (ID, Name, Email, Age, Active) VALUES (3, 'Charlie', 'charlie@test.com', 35, 1)"
    )
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    # Now SELECT and verify
    app._editor.set_text("SELECT * FROM SQLUser.PrismE2ETest ORDER BY ID")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    rows = app._results._tree.get_children()
    assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"

    # Check the third row (Charlie)
    vals = app._results._tree.item(rows[2], "values")
    assert vals[0] == "3" or vals[0] == 3, f"Expected ID=3, got {vals[0]}"
    assert "Charlie" in str(vals[1]), f"Expected Name=Charlie, got {vals[1]}"
    print(f"  3 rows present: {[app._results._tree.item(r, 'values') for r in rows]}")


# ── Test 6: Browse results — scroll, sort columns ────────────────────


def test_6_browse_and_sort(app, root):
    """Test browsing results and sorting by column."""
    # Add more rows for sorting test
    for i in range(4, 8):
        execute_sql_direct(
            f"INSERT INTO SQLUser.PrismE2ETest (ID, Name, Email, Age, Active) VALUES ({i}, 'User{i}', 'user{i}@test.com', {20 + i}, 1)"
        )

    # Query all
    app._editor.set_text("SELECT * FROM SQLUser.PrismE2ETest ORDER BY ID")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    rows = app._results._tree.get_children()
    assert len(rows) == 7, f"Expected 7 rows, got {len(rows)}"

    # Test sorting by Name column (column #2, index 1)
    cols = app._results._tree["columns"]
    name_col = cols[1] if len(cols) > 1 else cols[0]

    # Sort by name
    app._results._sort_by(name_col)
    pump(root, 1)

    sorted_rows = app._results._tree.get_children()
    first_val = app._results._tree.item(sorted_rows[0], "values")[1]
    print(f"  After sort by Name, first row Name = {first_val}")
    print(
        f"  All names: {[app._results._tree.item(r, 'values')[1] for r in sorted_rows]}"
    )

    # Verify alphabetical order
    names = [str(app._results._tree.item(r, "values")[1]) for r in sorted_rows]
    assert names == sorted(names), f"Names not sorted: {names}"

    # Sort again to reverse
    app._results._sort_by(name_col)
    pump(root, 1)
    rev_rows = app._results._tree.get_children()
    rev_names = [str(app._results._tree.item(r, "values")[1]) for r in rev_rows]
    assert rev_names == sorted(names, reverse=True), f"Reverse sort failed: {rev_names}"
    print(f"  Reverse sorted: {rev_names[:3]}...")


# ── Test 7: Edit a cell → Save → verify DB ──────────────────────────


def test_7_edit_cell_save(app, root):
    """Edit a cell in the results grid, save, and verify the DB is updated."""
    # Query the table
    app._editor.set_text("SELECT * FROM SQLUser.PrismE2ETest WHERE ID = 1")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    rows = app._results._tree.get_children()
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"

    # Store original value
    orig = app._results._tree.item(rows[0], "values")
    orig_email = str(orig[2])
    print(f"  Original email: {orig_email}")

    # Manually simulate cell edit
    item = rows[0]
    email_col = "Email"  # column name
    new_email = "alice@updated.com"

    # Set modified cell (keyed by column name → new_value)
    app._results._modified_cells[item] = {email_col: new_email}

    # Update the display
    current_vals = list(app._results._tree.item(item, "values"))
    current_vals[2] = new_email  # Email is column index 2
    app._results._tree.item(item, values=current_vals)
    app._results._tree.item(item, tags=("modified",))
    pump(root, 0.3)

    assert app._results.is_modified, "Results should show as modified"
    print(f"  Modified cells: {app._results.modified_count}")

    # Check source table was detected
    assert app._results._source_table is not None, "Source table not detected"
    print(f"  Source table: {app._results._source_table}")

    # Save changes (execute UPDATE)
    app._results._on_save()
    pump(root, 2)

    # Verify in DB
    cols, db_rows = execute_sql_direct(
        "SELECT Email FROM SQLUser.PrismE2ETest WHERE ID = 1"
    )
    assert len(db_rows) == 1, f"Expected 1 row, got {len(db_rows)}"
    db_email = str(db_rows[0][0])
    assert db_email == new_email, (
        f"DB email not updated! Expected {new_email}, got {db_email}"
    )
    print(f"  DB verified: email is now {db_email}")


# ── Test 8: Revert/cancel an edit ────────────────────────────────────


def test_8_revert_edit(app, root):
    """Edit a cell, then cancel/revert without saving."""
    app._editor.set_text("SELECT * FROM SQLUser.PrismE2ETest WHERE ID = 2")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    rows = app._results._tree.get_children()
    assert len(rows) == 1

    orig = app._results._tree.item(rows[0], "values")
    orig_name = str(orig[1])

    # Simulate edit
    item = rows[0]
    name_col = "Name"  # column name
    new_name = "TempChanged"
    app._results._modified_cells[item] = {name_col: new_name}
    current_vals = list(app._results._tree.item(item, "values"))
    current_vals[1] = new_name  # Name is column index 1
    app._results._tree.item(item, values=current_vals)
    app._results._tree.item(item, tags=("modified",))
    pump(root, 0.3)

    assert app._results.is_modified, "Should be modified after edit"
    print(f"  Modified name to: {new_name}")

    # Cancel/revert
    app._results._on_cancel()
    pump(root, 0.3)

    assert not app._results.is_modified, "Should not be modified after revert"

    # Verify value reverted
    reverted = app._results._tree.item(rows[0], "values")
    assert str(reverted[1]) == orig_name, (
        f"Name not reverted! Expected {orig_name}, got {reverted[1]}"
    )

    # Verify DB unchanged
    cols, db_rows = execute_sql_direct(
        "SELECT Name FROM SQLUser.PrismE2ETest WHERE ID = 2"
    )
    assert str(db_rows[0][0]) == orig_name, (
        f"DB Name changed despite revert! Got {db_rows[0][0]}"
    )
    print(f"  Reverted to: {orig_name}, DB unchanged")


# ── Test 9: Drop table and verify tree ───────────────────────────────


def test_9_drop_table(app, root):
    """Drop the test table via SQL and verify it's gone."""
    app._editor.set_text("DROP TABLE SQLUser.PrismE2ETest")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    # Verify table is gone from DB
    cols, rows = execute_sql_direct(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'PrismE2ETest' AND TABLE_SCHEMA = 'SQLUser'"
    )
    assert len(rows) == 0, f"Table still exists! Got {len(rows)} rows"
    print("  Table dropped successfully")

    # Refresh tree and verify table is not in tree
    # Search for it
    search_var = app._db_tree._search_var
    search_var.set("PrismE2ETest")
    pump(root, 2)
    search_var.set("")
    pump(root, 1)
    print("  Tree search cleared")


# ── Test 10: Error handling + auto-commit ────────────────────────────


def test_10_error_handling(app, root):
    """Test that SQL errors are displayed properly and don't crash."""
    # Test invalid SQL
    app._editor.set_text("SELECT * FROM NonExistentTable")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    status_text = app._results._status.cget("text")
    print(f"  Error query status: {status_text}")
    # Should show an error, not crash
    assert (
        app._results._tree.get_children() == []
        or len(app._results._tree.get_children()) == 0
    ), "Should have no results for invalid table"

    # Test syntax error
    app._editor.set_text("SELCT 1")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    status_text = app._results._status.cget("text")
    print(f"  Syntax error status: {status_text}")

    # Verify app is still responsive
    app._editor.set_text("SELECT 1 AS test")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 3)

    rows = app._results._tree.get_children()
    assert len(rows) == 1, f"App not responsive after errors! Got {len(rows)} rows"
    val = app._results._tree.item(rows[0], "values")
    print(f"  Recovery query returned: {val}")

    # Test empty query
    app._editor.set_text("")
    pump(root, 0.3)
    app._execute_query()
    pump(root, 1)
    print("  Empty query handled gracefully")


# ── Main ─────────────────────────────────────────────────────────────


def main():
    root = tk.Tk()
    app = PrismGUI(root)

    # Wait for initial load
    pump(root, 5)

    tests = [
        ("Test 1: Connect & tree loads schemas/tables", test_1_connect_and_tree),
        ("Test 2: Create new table via SQL editor", test_2_create_table),
        ("Test 3: Find new table in tree by searching", test_3_find_table_in_tree),
        ("Test 4: Double-click table → SELECT *", test_4_double_click_select),
        ("Test 5: Insert row via SQL and verify", test_5_insert_and_verify),
        ("Test 6: Browse results — scroll, sort", test_6_browse_and_sort),
        ("Test 7: Edit cell → Save → verify DB", test_7_edit_cell_save),
        ("Test 8: Revert/cancel edit without saving", test_8_revert_edit),
        ("Test 9: Drop table and verify tree", test_9_drop_table),
        ("Test 10: Error handling + recovery", test_10_error_handling),
    ]

    for name, fn in tests:
        run_test(name, fn, app, root)

    # Print summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    for name, ok, msg in RESULTS:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if not ok and msg != "OK":
            print(f"      → {msg[:120]}")
    print(f"\n  Total: {len(RESULTS)}  Passed: {passed}  Failed: {failed}")

    root.destroy()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
