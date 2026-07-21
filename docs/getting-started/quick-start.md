# Quick Start

This is a five-minute tour of the Prism CLI: save your IRIS credentials,
check the server, run an SQL query, upload and compile a class, and run
ObjectScript. Assumes Prism is already [installed](installation.md) and
you have a running IRIS instance.

## 1. Save connection settings

Tell Prism where IRIS is and which credentials to use. The values get
written to a user-local settings file (see
[Configuration](configuration.md) for the exact path).

```powershell
prism config -u _SYSTEM -p SYS -U http://192.168.1.100:52773 -n USER
```

Output:

```
Saved 4 setting(s) to C:\Users\you\AppData\Local\prism\config.json
  iris_username: _SYSTEM
  iris_password: ***
  iris_base_url: http://192.168.1.100:52773
  iris_namespace: USER
```

Every subsequent `prism` invocation picks those up automatically.
Settings are overridable by environment variables and `.env` files — see
[Configuration](configuration.md) for the precedence rules.

## 2. Confirm the connection

```powershell
prism info
```

Prints the Atelier API response with the IRIS version, list of
namespaces, and enabled features. If this fails, fix connectivity before
moving on.

## 3. Run an SQL query

```powershell
prism sql "SELECT TOP 3 Name, Super FROM %Dictionary.ClassDefinition"
```

Output is the raw Atelier JSON response. For one-off queries you can
pipe it through your favourite tool (`jq`, `ConvertFrom-Json`, …).

## 4. Upload and compile a class

Save the following to a local file called `MyApp.Hello.cls` (use any
text editor — Notepad, VS Code, etc.):

```objectscript
Class MyApp.Hello Extends %RegisteredObject
{
ClassMethod Greet(name As %String = "world") As %String
{
  Quit "hello, " _ name
}
}
```

Upload it to IRIS and compile it:

```powershell
prism put-doc MyApp.Hello.cls .\MyApp.Hello.cls
prism compile MyApp.Hello.cls
```

## 5. Call the method

Run the new method from the terminal. `prism terminal` talks to the
IRIS SuperServer (default port `1972`) via the native driver:

```powershell
prism terminal 'Write ##class(MyApp.Hello).Greet(""Prism"")'
```

Output:

```json
{
  "namespace": "USER",
  "command": "Write ##class(MyApp.Hello).Greet(\"Prism\")",
  "output": "hello, Prism",
  "prompt": ""
}
```

If the SuperServer port isn't reachable from your machine, use `prism
ws` instead — same arguments, but runs over the Atelier WebSocket on
the HTTP port:

```powershell
prism ws 'Write ##class(MyApp.Hello).Greet(""Prism"")'
```

## 6. Clean up

```powershell
prism delete-doc MyApp.Hello.cls
```

## Where to go next

- **[Commands](../commands/index.md)** — every CLI command and its
  options.
- **[GUI](../commands/gui.md)** — the tkinter SQL editor with database
  navigator and inline-editable results grid.
- **[Cast Plugins](../commands/cast.md)** — extend Prism with custom
  commands from any Git repository. Add a repo, run commands with typed
  arguments, and get Tab completion for free.
- **[MCP Server](../mcp/index.md)** — run `prism serve` and hook an AI
  client into the same operations.
- **[Configuration](configuration.md)** — full settings and
  environment-variable reference.