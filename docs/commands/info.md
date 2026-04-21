# prism info

Print the IRIS server version, Atelier API level, installed namespaces,
and feature flags. A handy first command to confirm your connection
settings work.

## Usage

```
prism info
```

Takes no arguments or options.

## Example

```powershell
prism info
```

Output (JSON pretty-printed):

```json
{
  "status": {
    "errors": [],
    "summary": ""
  },
  "console": [],
  "result": {
    "content": {
      "version": "IRIS for Windows (x86-64) 2025.3 (Build 226U) Thu Nov 13 2025 12:35:14 EST",
      "id": "474E12AF-D8F4-4C59-9AFB-B3D316397836",
      "api": 8,
      "features": [
        {"name": "DEEPSEE", "enabled": true},
        {"name": "ENSEMBLE", "enabled": true},
        {"name": "HEALTHSHARE", "enabled": false}
      ],
      "namespaces": ["%SYS", "USER"]
    }
  }
}
```

## Output fields

| Field | Type | Description |
|-------|------|-------------|
| `result.content.version` | string | Full IRIS version including platform and build. |
| `result.content.api` | int | Atelier REST API version (Prism is built against `8`). |
| `result.content.namespaces` | list[string] | Namespaces reachable via the Atelier API. |
| `result.content.features` | list[object] | Enabled IRIS feature flags (DEEPSEE, ENSEMBLE, HEALTHSHARE). |
| `status.errors` | list | Empty on success. |

## Tips

- **Connectivity check.** A successful response means URL, credentials,
  and network path are all fine. If it fails, the error message usually
  points at which one broke.
- **Namespace discovery.** Use `namespaces` to see valid values for the
  `--namespace` flag on other commands. The default namespace you set in
  [`prism config`](config.md) must appear in this list.
- **Pipe into `jq`** on Linux:

    ```bash
    prism info | jq '.result.content.namespaces'
    ```

## Related

- [`prism config`](config.md) — set the connection first.
- MCP tool: `get_server_info` (see [MCP tools](../mcp/tools.md)).