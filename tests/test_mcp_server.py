"""MCP server: tool registration, tool execution, and a real stdio subprocess
handshake against the installed console script."""
import asyncio
import json
import shutil
import subprocess
import sys

import common  # noqa: F401

from shelfprotocol import mcp_server  # noqa: E402

VERIFIED_PROFILE = {
    "merchant": {"name": "Verified Co", "domain": "verified.example"},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 50},
    "trust": {"verified_domain": True},
}


def run(coro):
    return asyncio.run(coro)


# --- tool registration ---
tools = run(mcp_server.server.list_tools())
names = {t.name for t in tools}
assert names == {"lookup", "search", "can_buy", "catalog", "products"}, names
for t in tools:
    assert t.description, f"{t.name} has no description (MCP clients show this to the LLM)"
print("PASS: all five tools registered with descriptions")

# --- lookup: stubbed found / not found ---
mcp_server._lookup = lambda domain: VERIFIED_PROFILE if domain == "verified.example" else None
r = run(mcp_server.server.call_tool("lookup", {"domain": "verified.example"}))
body = json.loads(r.content[0].text)
assert body["found"] is True and body["merchant"]["name"] == "Verified Co", body
r = run(mcp_server.server.call_tool("lookup", {"domain": "ghost.example"}))
body = json.loads(r.content[0].text)
assert body == {"found": False, "domain": "ghost.example"}, body
print("PASS: lookup tool wraps found/not-found correctly")

# --- can_buy: composite tool does lookup + can_buy internally ---
r = run(mcp_server.server.call_tool("can_buy", {"domain": "verified.example", "amount_usd": 30}))
body = json.loads(r.content[0].text)
assert body == {"allowed": True, "reason": "OK: $30.00 is within the $50.00 autonomous limit."}, body
r = run(mcp_server.server.call_tool("can_buy", {"domain": "verified.example", "amount_usd": 999}))
body = json.loads(r.content[0].text)
assert body["allowed"] is False and "exceeds" in body["reason"], body
r = run(mcp_server.server.call_tool("can_buy", {"domain": "ghost.example", "amount_usd": 5}))
body = json.loads(r.content[0].text)
assert body["allowed"] is False, body
print("PASS: can_buy tool composes lookup + can_buy, refuses over-ceiling and unknown merchants")

# --- can_buy hardening: verification is not caller-overridable on this tool,
# unlike the raw SDK's require_verified flag (gate finding F2) ---
mcp_server._lookup = lambda domain: {
    "merchant": {"name": "Unverified Co", "domain": "unverified.example"},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 10_000},
    "trust": {"verified_domain": False},
}
r = run(mcp_server.server.call_tool("can_buy", {"domain": "unverified.example", "amount_usd": 5}))
body = json.loads(r.content[0].text)
assert body["allowed"] is False and "not verified" in body["reason"], body
import inspect
assert "require_verified" not in inspect.signature(mcp_server.can_buy).parameters, (
    "can_buy must not expose a caller-settable verification override on the MCP surface"
)
print("PASS: can_buy tool cannot be talked into skipping verification (no override parameter exists)")

# --- search / catalog / products: pass-through with correct kwargs ---
# list-returning tools: structured_content['result'] preserves the full list
# shape reliably; content[0].text renders per-item (unwrapped for a single
# item), which is a framework display heuristic, not what to assert against.
mcp_server._search = lambda **kw: [{"echo": kw}]
r = run(mcp_server.server.call_tool("search", {"q": "coffee", "verified": True}))
body = r.structured_content["result"]
assert body[0]["echo"]["q"] == "coffee" and body[0]["echo"]["verified"] is True, body

mcp_server._catalog = lambda domain, **kw: [{"domain": domain, **kw}]
r = run(mcp_server.server.call_tool("catalog", {"domain": "verified.example", "q": "decaf"}))
body = r.structured_content["result"]
assert body[0]["domain"] == "verified.example" and body[0]["q"] == "decaf", body

mcp_server._products = lambda **kw: [{"echo": kw}]
r = run(mcp_server.server.call_tool("products", {"in_stock": True}))
body = r.structured_content["result"]
assert body[0]["echo"]["in_stock"] is True, body
print("PASS: search/catalog/products pass arguments through correctly")

# --- real stdio subprocess handshake against the installed console script ---
if shutil.which("shelfprotocol-mcp"):
    async def subprocess_check():
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(command="shelfprotocol-mcp")
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                return {t.name for t in listed.tools}

    live_names = run(subprocess_check())
    assert live_names == names, (live_names, names)
    print("PASS: real stdio subprocess handshake via installed console script matches in-process tools")
else:
    print("SKIP: shelfprotocol-mcp console script not on PATH (mcp[extra] not installed in this env)")

print("\nAll MCP server tests passed.")
