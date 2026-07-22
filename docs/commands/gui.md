# prism gui

> **Work in progress.** The GUI is under active development and not yet
> feature-complete. Expect rough edges, missing features, and potential
> changes before it stabilises.

Launch the Prism GUI — a tkinter-based SQL editor with a DBeaver-inspired
layout. Provides a database navigator, SQL editor with syntax highlighting,
results grid with inline editing, and a status bar — all connected to your
IRIS instance through the same settings as the CLI.

## Synopsis

```
prism gui [OPTIONS]
```

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--query` | `-q` | *(empty)* | SQL query to pre-fill the editor with on startup. |

## Prerequisites

The GUI requires **tkinter**, which is part of the standard Python
installation on Windows and macOS. On Linux, install it separately:

```bash
# Debian / Ubuntu
sudo apt install python3-tk

# Fedora / RHEL
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

If tkinter is not available, `prism gui` exits with a clear error message.

## Example

```bash
# Launch the GUI with an empty editor
prism gui

# Pre-fill the editor with a query
prism gui --query "SELECT TOP 10 * FROM %Dictionary.ClassDefinition"
```

## Layout

```
┌────────────────────────────────────────────────────────────┐
│  Menu Bar                                                   │
├────────┬───────────────────────────────────────────────────┤
│        │  Toolbar: [New][Open][Save] | [🔌][⏏][🔄] |     │
│        │    [SQL][▶ Execute][■ Cancel][Clear] | [NS:USER]   │
│  Tree  ├───────────────────────────────────────────────────┤
│  Nav   │  Tab Bar: [Script-1 ✕]                            │
│        ├───────────────────────────────────────────────────┤
│  +     │                                                     │
│  Search│         SQL Editor (dark, line numbers)             │
│  bar   │                                                     │
│        ├───────────────────────────────────────────────────┤
│        │  [Result 1 ✕] [🔄][💾][✕] | [Grid]                  │
│        ├───────────────────────────────────────────────────┤
│        │         Results Table (zebra striped)              │
├────────┴───────────────────────────────────────────────────┤
│  Status Bar: ● Connected | NS:USER | 37 rows | CET         │
└────────────────────────────────────────────────────────────┘
```

## Features

### Database Navigator (left sidebar)

- **Tree view** of schemas and tables in the connected IRIS namespace
- **Search bar** to filter by name
- **Click a table** to insert its name into the SQL editor at the cursor
  position
- **Refresh button** (🔄 in the toolbar) reloads the tree

### SQL Editor

- Dark-themed code editor with **line numbers**
- **Syntax highlighting** for SQL keywords
- **Multi-tab editing** — open multiple query tabs
- **Ctrl+Enter** to execute the current query (or selection)
- **Open/Save** `.sql` files via the File menu or toolbar
- **Edit menu** with Undo/Redo, Cut/Copy/Paste, Select All

### Results Table

- **Zebra-striped grid** displaying query result rows
- **Inline editing** — double-click a cell to edit; the Save button
  (💾) writes changes back to IRIS via `UPDATE` statements
- **Refresh** (🔄) re-executes the current editor query
- **Export** — copy results to clipboard
- **Source table detection** — the editor automatically detects the source
  table from the `FROM` clause to enable inline editing (system schemas like
  `%*` and `INFORMATION_SCHEMA` are excluded)

### Toolbar

| Button | Action |
|--------|--------|
| **New** | Clear editor and results for a new query |
| **Open** | Open a `.sql` file into the editor |
| **Save** | Save editor content to a `.sql` file |
| **🔌 Connect** | Re-check IRIS connection and update status |
| **⏏ Refresh Tree** | Reload the database navigator |
| **▶ Execute** | Run the current query (or selection) |
| **■ Cancel** | Cancel a running query |
| **Clear** | Clear the results panel |
| **NS dropdown** | Select the active IRIS namespace |

### Status Bar

Shows the connection status (● Connected / ○ Disconnected), active
namespace, row count from the last query, and elapsed time.

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Enter` | Execute query |
| `Ctrl+N` | New query |
| `Ctrl+S` | Save file |
| `Ctrl+Q` | Exit |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+X` | Cut |
| `Ctrl+C` | Copy |
| `Ctrl+V` | Paste |
| `Ctrl+A` | Select all |

## Connection

The GUI uses the same connection settings as the CLI —
[Configuration](../getting-started/configuration.md) applies identically.
On startup, it checks the IRIS connection and shows the status in the
status bar. If the connection fails, the status bar shows
"Cannot connect to IRIS — check settings".

Use the **Connect** button (🔌) in the toolbar to re-check the connection
after fixing settings.

## Limitations

- **Requires a display.** The GUI needs a graphical environment (X11,
  Wayland, Quartz, or Windows desktop). It does not work over SSH without
  X forwarding.
- **Single window.** The GUI opens one main window; there's no multi-window
  or detached-panel mode yet.
- **Read-write editing.** Inline cell editing generates `UPDATE`
  statements and commits changes directly to IRIS. Use with caution on
  production namespaces.

## Related

- [`prism sql`](sql.md) — the CLI equivalent for one-off queries.
- [`prism config`](config.md) — set the IRIS connection before launching.
- [Configuration](../getting-started/configuration.md) — all environment
  variables and settings.