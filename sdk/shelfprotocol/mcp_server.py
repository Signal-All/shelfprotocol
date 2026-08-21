"""
Shelf Protocol MCP server — exposes the registry to any MCP-speaking agent
(Claude Desktop, Claude Code, and others) as a handful of tools.

Run directly:
    python -m shelfprotocol.mcp_server

Or, once installed, via the console script:
    shelfprotocol-mcp

Add to an MCP client config (e.g. Claude Desktop's claude_desktop_config.json):
    {
      "mcpServers": {
        "shelfprotocol": {
          "command": "shelfprotocol-mcp"
        }
      }
    }

Point at a non-default registry (self-hosted, staging) with SHELF_URL, same
as the plain SDK.
"""

from __future__ import annotations

from typing import Optional

from mcp.server.mcpserver import MCPServer

from . import can_buy as _can_buy
from . import catalog as _catalog
from . import lookup as _lookup
from . import products as _products
from . import search as _search

server = MCPServer(
    "shelfprotocol",
    version="0.1.0",
    instructions=(
        "Shelf Protocol is the directory AI agents check before they buy from a "
        "merchant. Before purchasing anything on a user's behalf, look up or "
        "search for the merchant here first, then call can_buy to confirm the "
        "purchase is within the merchant's declared, agent-safe limits."
    ),
)


@server.tool()
def lookup(domain: str) -> dict:
    """Look up a merchant's agent profile by domain (e.g. "acme-coffee.example").

    Returns the merchant's shelf.json profile — agent policy, checkout info,
    and verification status — or {"found": false} if the merchant isn't in
    the registry. Call this before buying from any merchant."""
    profile = _lookup(domain)
    if profile is None:
        return {"found": False, "domain": domain}
    return {"found": True, **profile}


@server.tool()
def search(
    q: Optional[str] = None,
    category: Optional[str] = None,
    protocol: Optional[str] = None,
    verified: Optional[bool] = None,
) -> list[dict]:
    """Search for merchants matching a user's request.

    q: free-text match on merchant name/description/categories.
    category: filter by category (e.g. "food.beverages.coffee").
    protocol: filter by checkout protocol ("AP2", "UCP", or "manual").
    verified: if true, only return merchants with a verified domain."""
    return _search(q=q, category=category, protocol=protocol, verified=verified)


@server.tool()
def can_buy(domain: str, amount_usd: float) -> dict:
    """Decide whether it's safe to autonomously buy from a merchant.

    Looks the merchant up and checks its declared agent_policy: whether it
    allows agent purchases at all, whether its domain is verified, and
    whether amount_usd is within its autonomous spending ceiling. This is
    the safety check — always call it before checkout.

    Domain verification is always required here (unlike the raw SDK's
    can_buy(), which takes a require_verified flag for callers who need to
    opt out deliberately in their own code) — this tool exists specifically
    for an agent to call autonomously, so there is no argument that weakens
    the check for it.

    Returns {"allowed": bool, "reason": str}. When allowed is false, reason
    explains why (e.g. amount exceeds the merchant's ceiling) so the agent
    can decide whether to escalate to the user instead."""
    profile = _lookup(domain)
    allowed, reason = _can_buy(profile, amount_usd, require_verified=True)
    return {"allowed": allowed, "reason": reason}


@server.tool()
def catalog(domain: str, q: Optional[str] = None) -> list[dict]:
    """List a merchant's cached product catalog, optionally filtered by q
    (matches product name, description, or category)."""
    return _catalog(domain, q=q)


@server.tool()
def products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    verified: Optional[bool] = None,
    in_stock: Optional[bool] = None,
) -> list[dict]:
    """Search products across every merchant in the registry — use this when
    the user wants a specific item and you don't already know which merchant
    sells it. Verified merchants rank first. Filter with in_stock=true to
    exclude out-of-stock items."""
    return _products(q=q, category=category, verified=verified, in_stock=in_stock)


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
