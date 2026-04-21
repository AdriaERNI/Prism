# MCP Server

Prism doubles as a local [Model Context Protocol](https://modelcontextprotocol.io/)
server. Running `prism serve` on your workstation exposes every IRIS
operation as an MCP tool that AI assistants (Claude Code, Claude
Desktop, Cursor, GitHub Copilot, …) can call on your behalf.

## Why MCP?

The CLI is great for ad-hoc, one-off operations. MCP mode is how you
let an AI assistant:

- write a class, upload it, compile it, and iterate on compile errors,
- run a SQL query, interpret the rows, suggest a follow-up query,
- step through ObjectScript with breakpoints,
- run unit tests after every edit.

All of that uses the same underlying code paths as the CLI, so the
behaviour is consistent — the assistant simply calls `execute_sql`
instead of you typing `prism sql`.

## Start the server

```powershell
prism serve
```

```
Prism ready at http://localhost:3000/mcp | workspace: off
```

The server blocks in the foreground. Use `Ctrl+C` to stop it.

- Transport: **streamable-http** over HTTP.
- Default port: `3000` (override with `prism serve --port 4000`).
- Default URL: `http://localhost:3000/mcp`.

See [`prism serve`](../commands/serve.md) for all options.

## Next

- **[Client setup](client-setup.md)** — point Claude Code, Claude
  Desktop, Cursor, or Copilot at the running server.
- **[Tool reference](tools.md)** — every MCP tool Prism exposes, with
  the shape of its input and return values.
- **[Interactive debugger](debugging.md)** — the nine `debug_*` tools
  that have no CLI equivalent.
- **[Configuration](../getting-started/configuration.md)** — env vars
  that change server behaviour (workspace mode, debug mode, terminal
  backend).
