"""
Framework-neutral definitions of the agent-facing Shelf Protocol tools.

This is the single source of truth for the tools we hand to an LLM-driven agent,
whatever framework it runs in. `langchain_tools` and `crewai_tools` are thin
adapters over `TOOL_SPECS`; adding a third framework should mean writing another
adapter, never restating the tools themselves.

Two things distinguish these from the plain SDK functions in `__init__.py`:

1. They return agent-shaped results. `lookup()` returns None for an unknown
   merchant, which an LLM reads as an empty tool result and can easily gloss
   over; the tool version returns an explicit {"found": false}.

2. They are hardened for untrusted callers. The plain SDK is called by a
   developer writing deliberate code, so `can_buy(..., require_verified=False)`
   is a legitimate escape hatch. These tools are called by a model that may be
   reading attacker-controlled text — a product title, a page the agent
   fetched, an email. Any argument that can weaken a safety decision is an
   argument prompt injection can reach, so the tool surface does not have one.
   That rule is Ratchet Rule 9, first applied to the MCP server; it binds every
   adapter built from this module.

The MCP server (`mcp_server.py`) predates this module and defines its own copy
of these wrappers, because its `def` lines are load-bearing for Rule 9's Phase 0
check. `tests/test_framework_tools.py` asserts the two surfaces stay in
lockstep, so the duplication cannot silently drift.
"""

# NOTE: deliberately no `from __future__ import annotations` here, and please
# don't add one. Framework adapters build their argument schemas by reflecting
# over these signatures: CrewAI generates a pydantic model from them, and with
# postponed evaluation the annotations arrive as the strings "Optional[str]"
# etc., which pydantic cannot resolve in its own namespace — every tool with an
# optional argument then dies at call time with "is not fully defined". The
# annotations in this module have to be real objects at runtime.
import inspect
from typing import Callable, List, NamedTuple, Optional

from . import can_buy as _can_buy
from . import catalog as _catalog
from . import lookup as _lookup
from . import products as _products
from . import search as _search


def lookup(domain: str) -> dict:
    """Look up a merchant's agent profile by domain (e.g. "acme-coffee.example").

    Returns the merchant's shelf.json profile — agent policy, checkout info,
    and verification status — or {"found": false} if the merchant isn't in
    the registry. Call this before buying from any merchant."""
    profile = _lookup(domain)
    if profile is None:
        return {"found": False, "domain": domain}
    return {"found": True, **profile}


def search(
    q: Optional[str] = None,
    category: Optional[str] = None,
    protocol: Optional[str] = None,
    verified: Optional[bool] = None,
) -> List[dict]:
    """Search the Shelf Protocol registry for merchants matching a user's request.

    q: free-text match on merchant name/description/categories.
    category: filter by category (e.g. "food.beverages.coffee").
    protocol: filter by checkout protocol ("AP2", "UCP", or "manual").
    verified: if true, only return merchants with a verified domain."""
    return _search(q=q, category=category, protocol=protocol, verified=verified)


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


def catalog(domain: str, q: Optional[str] = None) -> List[dict]:
    """List a merchant's cached product catalog, optionally filtered by q
    (matches product name, description, or category)."""
    return _catalog(domain, q=q)


def products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    verified: Optional[bool] = None,
    in_stock: Optional[bool] = None,
) -> List[dict]:
    """Search products across every merchant in the registry — use this when
    the user wants a specific item and you don't already know which merchant
    sells it. Verified merchants rank first. Filter with in_stock=true to
    exclude out-of-stock items."""
    return _products(q=q, category=category, verified=verified, in_stock=in_stock)


class ToolSpec(NamedTuple):
    """One agent-facing tool, in a form any framework adapter can consume."""

    name: str
    func: Callable
    description: str


def _spec(func: Callable) -> ToolSpec:
    doc = inspect.getdoc(func)
    if not doc:
        raise ValueError(f"{func.__name__} has no docstring; the LLM sees it as the tool description")
    return ToolSpec(name=func.__name__, func=func, description=doc)


TOOL_SPECS: List[ToolSpec] = [_spec(f) for f in (lookup, search, can_buy, catalog, products)]

# Framework tool lists are flat and unnamespaced — a bare "search" or "products"
# will collide with the web-search tool that half of all agent stacks already
# carry, and the model picks whichever description it likes. MCP doesn't have
# this problem (the server name namespaces its tools), which is why only the
# adapters prefix.
DEFAULT_PREFIX = "shelf_"


def tool_specs(prefix: str = DEFAULT_PREFIX) -> List[ToolSpec]:
    """Return the tool specs with `prefix` applied to each name.

    Pass prefix="" to get the bare names (matching the MCP server's), if you're
    certain they won't collide with the other tools in your agent."""
    return [s._replace(name=f"{prefix}{s.name}") for s in TOOL_SPECS]
