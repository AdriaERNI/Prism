"""Test all MCP tools against a running prism serve instance.

Uses raw JSON-RPC over HTTP with proper MCP session management.
Provides https://modelcontextprotocol.io/specification/2025-06-18/basictransport

Usage: python test_mcp_tools.py [url]
"""

import json
import sys

import httpx

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:29999/mcp"


class MCPClient:
    def __init__(self, url: str):
        self.url = url
        self.session_id: str | None = None
        self.req_id = 0

    def _parse_sse(self, text: str) -> dict | None:
        """Parse SSE response and return the JSON data from 'data:' lines."""
        for block in text.split("\n\n"):
            for line in block.strip().split("\n"):
                line = line.strip()
                if line.startswith("data: "):
                    try:
                        return json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
        return None

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.req_id,
            "method": method,
            "params": params or {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        resp = httpx.post(self.url, json=payload, headers=headers, timeout=60)

        # Capture session ID from initialize response
        if self.session_id is None:
            self.session_id = resp.headers.get("mcp-session-id")

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            parsed = self._parse_sse(resp.text)
            if parsed:
                return parsed
            return {"error": "No SSE data", "raw": resp.text[:500]}

        return resp.json()

    def initialize(self) -> dict:
        return self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "prism-test", "version": "1.0"},
            },
        )

    def notify_initialized(self):
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        httpx.post(self.url, json=payload, headers=headers, timeout=10)

    def list_tools(self) -> list:
        resp = self.rpc("tools/list", {})
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name: str, args: dict) -> tuple:
        try:
            resp = self.rpc("tools/call", {"name": name, "arguments": args})
            if "error" in resp:
                return ("FAIL", json.dumps(resp["error"])[:500])
            result = resp.get("result", {})
            return ("PASS", extract_text(result)[:500])
        except Exception as e:
            return ("FAIL", str(e)[:500])


def extract_text(result: dict) -> str:
    content = result.get("content", [])
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return json.dumps(result, indent=2)[:500]


def main():
    print(f"Connecting to {URL}...")

    client = MCPClient(URL)

    # 1. Initialize
    init = client.initialize()
    proto = init.get("result", {}).get("protocolVersion", "FAIL")
    print(f"Initialize: protocol={proto}, session={client.session_id}")
    print()

    # 2. Send initialized notification
    client.notify_initialized()

    # 3. List tools
    tools = client.list_tools()
    tool_names = [t["name"] for t in tools]
    print(f"=== AVAILABLE TOOLS ({len(tool_names)}) ===")
    for name in sorted(tool_names):
        print(f"  - {name}")
    print()

    if not tool_names:
        print("ERROR: No tools available")
        return

    results = {}

    tests = [
        ("get_server_info", {}),
        ("execute_sql", {"query": "SELECT 1 AS One, 2 AS Two"}),
        ("list_documents", {"type": "cls", "filter": "%ASQ"}),
        ("get_document", {"name": "%ASQ.AST.cls"}),
        ("index_code", {"summary": True}),
        ("execute_terminal", {"command": 'WRITE "Hello from MCP",!'}),
        ("list_tests", {"filter": "%UnitTest"}),
    ]

    for tool_name, args in tests:
        if tool_name not in tool_names:
            print(f"  SKIP: {tool_name} (not registered)")
            continue
        status, output = client.call_tool(tool_name, args)
        results[tool_name] = status
        print(f"=== {tool_name} === {status}")
        print(output[:300])
        print()

    # Test put_document + compile + delete as a group
    if "put_document" in tool_names:
        cls = (
            'Class prism.MCPTest\n{\nMethod Ping() As %String\n{\n    Quit "pong"\n}\n}'
        )
        status, output = client.call_tool(
            "put_document",
            {
                "name": "prism.MCPTest.cls",
                "content": cls,
                "compile": True,
            },
        )
        results["put_document"] = status
        print(f"=== put_document === {status}")
        print(output[:300])
        print()

    if "compile_documents" in tool_names and results.get("put_document") == "PASS":
        status, output = client.call_tool(
            "compile_documents", {"documents": ["prism.MCPTest.cls"]}
        )
        results["compile_documents"] = status
        print(f"=== compile_documents === {status}")
        print(output[:300])
        print()

    if "delete_document" in tool_names and results.get("put_document") == "PASS":
        status, output = client.call_tool(
            "delete_document", {"name": "prism.MCPTest.cls"}
        )
        results["delete_document"] = status
        print(f"=== delete_document === {status}")
        print(output[:300])
        print()

    if "get_test_results" in tool_names:
        status, output = client.call_tool("get_test_results", {})
        results["get_test_results"] = status
        print(f"=== get_test_results === {status}")
        print(output[:300])
        print()

    if "run_tests" in tool_names:
        status, output = client.call_tool("run_tests", {"filter": "%UnitTest.Manager"})
        results["run_tests"] = status
        print(f"=== run_tests === {status}")
        print(output[:300])
        print()

    # Summary
    print("=== SUMMARY ===")
    passed = sum(1 for s in results.values() if s == "PASS")
    failed = sum(1 for s in results.values() if s == "FAIL")
    tested = len(results)
    skipped = len(tool_names) - tested
    print(f"  Available: {len(tool_names)}")
    print(f"  Tested:    {tested}")
    print(f"  PASS:      {passed}")
    print(f"  FAIL:      {failed}")
    print(f"  SKIP:      {skipped}")
    for name, status in sorted(results.items()):
        print(f"    {status}: {name}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
