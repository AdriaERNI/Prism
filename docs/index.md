# Prism

**Prism lets AI see through IRIS.**

Prism is a command-line tool and MCP server for InterSystems IRIS. It gives
you (and AI assistants) a consistent way to run SQL, manage source
documents, compile classes, execute ObjectScript, run unit tests, and
drive an interactive debugger — all against a live IRIS instance via the
Atelier REST API and the IRIS SuperServer.

## Two ways to use Prism

Prism ships a single executable that you can run in two modes:

=== "Command line"

    Run commands ad-hoc from your shell. Great for quick SQL queries,
    uploading a class, or inspecting the server:

    ```
    prism info
    prism sql "SELECT TOP 3 Name FROM %Dictionary.ClassDefinition"
    prism put-doc MyApp.Hello.cls ./MyApp.Hello.cls
    prism compile MyApp.Hello.cls
    ```

=== "MCP server"

    Start Prism as a local Model Context Protocol server, then point
    Claude Code, Claude Desktop, Cursor, or any other MCP-compatible
    client at it:

    ```
    prism serve
    ```

    The server listens on `http://localhost:3000/mcp` and exposes 21
    tools covering the same operations, plus nine interactive-debugger
    tools that have no CLI equivalent.

## Install

Download the latest `prism-<version>-setup.exe` and run it. The
installer puts `prism.exe` into `C:\Program Files\prism\` and adds that
folder to the system `PATH`. Full instructions are on the
[Installation](getting-started/installation.md) page.

## What to read next

- **[Installation](getting-started/installation.md)** — Windows installer
  walkthrough and how to verify the install.
- **[Quick Start](getting-started/quick-start.md)** — a five-minute tour
  that configures Prism, runs a SQL query, and compiles a class.
- **[Configuration](getting-started/configuration.md)** — `prism config`,
  settings file location, and the full environment-variable reference.
- **[Commands](commands/index.md)** — one page per CLI command, with every
  option and a runnable example.
- **[MCP Server](mcp/index.md)** — how to connect an IDE / AI client,
  the list of MCP tools, and the interactive debugger.

## Quick `prism --help`

```
Usage: prism [OPTIONS] COMMAND [ARGS]...

  Prism — InterSystems IRIS CLI and MCP server.

Commands:
  config      Save IRIS connection settings to the platform user config directory.
  sql         Run an SQL query and print the IRIS response as JSON.
  terminal    Run an ObjectScript command via irisnative (SuperServer).
  ws          Run an ObjectScript command via the Atelier WebSocket terminal.
  compile     Compile documents on IRIS.
  get-doc     Retrieve a document from IRIS and print the response as JSON.
  list-docs   List source documents on the IRIS server.
  put-doc     Upload a local file to IRIS as the given document name.
  delete-doc  Delete a document from IRIS.
  info        Print server version, installed namespaces, and feature flags.
  test        Run a unit test class via the deployed runner.
  list-tests  List %UnitTest.TestCase classes and their Test* methods.
  serve       Start the Prism MCP server (streamable-http transport).
```