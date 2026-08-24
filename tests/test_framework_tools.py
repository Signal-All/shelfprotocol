"""Framework adapters (LangChain, CrewAI): tool construction, argument
pass-through, safety hardening, and parity with the MCP surface.

The adapter suites skip when their framework isn't installed. The parity and
hardening checks against `agent_tools` itself never skip — those are the ones
that protect Ratchet Rule 9, so they must run in every environment.
"""
import asyncio
import inspect

import common  # noqa: F401

from shelfprotocol import agent_tools  # noqa: E402

VERIFIED_PROFILE = {
    "merchant": {"name": "Verified Co", "domain": "verified.example"},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 50},
    "trust": {"verified_domain": True},
}

UNVERIFIED_PROFILE = {
    "merchant": {"name": "Unverified Co", "domain": "unverified.example"},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 10_000},
    "trust": {"verified_domain": False},
}


def stub_lookup(profile_by_domain):
    agent_tools._lookup = lambda domain: profile_by_domain.get(domain)


stub_lookup({"verified.example": VERIFIED_PROFILE, "unverified.example": UNVERIFIED_PROFILE})


# --- the shared spec itself ---
names = {s.name for s in agent_tools.TOOL_SPECS}
assert names == {"lookup", "search", "can_buy", "catalog", "products"}, names
for s in agent_tools.TOOL_SPECS:
    assert s.description, f"{s.name} has no description (the LLM sees this)"
    assert s.description == inspect.getdoc(s.func)
print("PASS: five tool specs, each with a description")

prefixed = {s.name for s in agent_tools.tool_specs()}
assert prefixed == {f"shelf_{n}" for n in names}, prefixed
assert {s.name for s in agent_tools.tool_specs(prefix="")} == names
print("PASS: tool_specs applies (and can drop) the shelf_ prefix")


# --- parity with the MCP server surface ---
# agent_tools and mcp_server deliberately hold parallel copies of these wrappers
# (mcp_server's `def` lines are load-bearing for Rule 9's Phase 0 grep). This is
# the check that keeps the copies honest.
#
# Guarded because crewai pins mcp~=1.28, so the env that can exercise the CrewAI
# adapter cannot import our mcp>=2.0 server. Parity runs in the default test env
# (system python, mcp 2.x), which is the one that matters.
try:
    from shelfprotocol import mcp_server  # noqa: E402
except ImportError:
    print("SKIP: mcp>=2.0 not importable here, skipping MCP parity (see crewai's mcp~=1.28 pin)")
else:
    mcp_names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert mcp_names == names, (mcp_names, names)
    for name in names:
        spec_sig = inspect.signature(getattr(agent_tools, name))
        mcp_sig = inspect.signature(getattr(mcp_server, name))
        assert spec_sig.parameters.keys() == mcp_sig.parameters.keys(), (
            f"{name}: agent_tools {list(spec_sig.parameters)} != mcp_server {list(mcp_sig.parameters)}"
        )
    # Descriptions are deliberately NOT asserted equal: the MCP server's tools are
    # namespaced by the server name, the adapters' aren't, so the adapter wording
    # says "the Shelf Protocol registry" where MCP can just say "merchants".
    # Names and signatures are the contract; prose is allowed to differ.
    print("PASS: agent_tools and mcp_server expose identical tool names and signatures")


# --- Ratchet Rule 9, generalized to every agent-facing surface ---
assert "require_verified" not in inspect.signature(agent_tools.can_buy).parameters, (
    "can_buy must not expose a caller-settable verification override on an agent-facing surface"
)
result = agent_tools.can_buy("unverified.example", 5)
assert result["allowed"] is False and "not verified" in result["reason"], result
print("PASS: can_buy refuses unverified merchants and has no override parameter")

assert agent_tools.can_buy("verified.example", 30) == {
    "allowed": True,
    "reason": "OK: $30.00 is within the $50.00 autonomous limit.",
}
assert agent_tools.can_buy("verified.example", 999)["allowed"] is False
assert agent_tools.can_buy("ghost.example", 5)["allowed"] is False
print("PASS: can_buy honors the ceiling and refuses unknown merchants")

assert agent_tools.lookup("ghost.example") == {"found": False, "domain": "ghost.example"}
assert agent_tools.lookup("verified.example")["found"] is True
print("PASS: lookup reports not-found explicitly rather than returning nothing")


# --- LangChain adapter ---
try:
    from shelfprotocol import langchain_tools
except ImportError:
    print("SKIP: langchain-core not installed")
else:
    lc = langchain_tools.get_tools()
    by_name = {t.name: t for t in lc}
    assert set(by_name) == {f"shelf_{n}" for n in names}, set(by_name)
    for t in lc:
        assert t.description, f"{t.name} has no description"

    assert set(by_name["shelf_can_buy"].args) == {"domain", "amount_usd"}, by_name["shelf_can_buy"].args
    assert "require_verified" not in by_name["shelf_can_buy"].args, (
        "LangChain surface must not expose the verification override to the model"
    )

    out = by_name["shelf_can_buy"].invoke({"domain": "unverified.example", "amount_usd": 5})
    assert out["allowed"] is False and "not verified" in out["reason"], out
    out = by_name["shelf_can_buy"].invoke({"domain": "verified.example", "amount_usd": 30})
    assert out["allowed"] is True, out

    # optional args must stay optional — the model will omit them
    agent_tools._search = lambda **kw: [{"echo": kw}]
    out = by_name["shelf_search"].invoke({"q": "coffee", "verified": True})
    assert out[0]["echo"]["q"] == "coffee" and out[0]["echo"]["verified"] is True, out
    out = by_name["shelf_search"].invoke({})
    assert out[0]["echo"] == {"q": None, "category": None, "protocol": None, "verified": None}, out

    # async agents call ainvoke; StructuredTool has to handle a sync func there
    out = asyncio.run(by_name["shelf_search"].ainvoke({"q": "tea"}))
    assert out[0]["echo"]["q"] == "tea", out

    agent_tools._catalog = lambda domain, **kw: [{"domain": domain, **kw}]
    out = by_name["shelf_catalog"].invoke({"domain": "verified.example", "q": "decaf"})
    assert out[0]["domain"] == "verified.example" and out[0]["q"] == "decaf", out

    assert {t.name for t in langchain_tools.get_tools(prefix="")} == names
    print("PASS: LangChain tools build, pass arguments through, and keep can_buy hardened")


# --- CrewAI adapter ---
try:
    from shelfprotocol import crewai_tools
except ImportError:
    print("SKIP: crewai not installed")
else:
    crew = crewai_tools.get_tools()
    by_name = {t.name: t for t in crew}
    assert set(by_name) == {f"shelf_{n}" for n in names}, set(by_name)
    for t in crew:
        assert t.description, f"{t.name} has no description"
        assert t.description == dict(
            (s.name, s.description) for s in agent_tools.tool_specs()
        )[t.name], f"{t.name} description drifted from the shared spec"

    schema_fields = set(by_name["shelf_can_buy"].args_schema.model_fields)
    assert schema_fields == {"domain", "amount_usd"}, schema_fields
    assert "require_verified" not in schema_fields, (
        "CrewAI surface must not expose the verification override to the model"
    )

    out = by_name["shelf_can_buy"].run(domain="unverified.example", amount_usd=5)
    assert out["allowed"] is False and "not verified" in out["reason"], out
    out = by_name["shelf_can_buy"].run(domain="verified.example", amount_usd=30)
    assert out["allowed"] is True, out

    agent_tools._products = lambda **kw: [{"echo": kw}]
    out = by_name["shelf_products"].run(q="beans", in_stock=True)
    assert out[0]["echo"]["q"] == "beans" and out[0]["echo"]["in_stock"] is True, out

    assert {t.name for t in crewai_tools.get_tools(prefix="")} == names
    print("PASS: CrewAI tools build, pass arguments through, and keep can_buy hardened")


print("\nAll framework tool tests passed.")
