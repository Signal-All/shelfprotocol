# Shelf Protocol Gate Report
Date: 2026-08-21 (second run)
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate procedure: /gate-openshelf (executed from .claude/commands/gate-openshelf.md)
Scope note: this run gates the PyPI packaging + MCP server (branch `feat/mcp-server-and-packaging`, PR #7): `sdk/shelfprotocol.py` restructured into a real package, root `pyproject.toml`, new `sdk/shelfprotocol/mcp_server.py` exposing five tools to any MCP client.

## VERDICT: PASS

This gate produced the project's second real code fix. Phase 1 raised one refutable SSRF claim and one MEDIUM worth taking seriously on its merits even though the underlying code had no live bug — `can_buy`'s verification check being caller-overridable on a tool specifically marketed as "the safety check an agent calls before spending money" was weaker defense-in-depth than the new agent-facing surface warranted, so it was tightened rather than just argued away. Both cold strangers PASS. Phase 3 found one real README gap (fixed) alongside a recurring false-positive claim.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed

- **F2 (MEDIUM) — `can_buy` MCP tool exposed a caller-settable `require_verified` argument.** Not a live bug (the merchant `profile` is always fetched fresh from the trusted registry server per call, never caller-supplied — there was no actual path to inject a falsified profile), but a real hardening opportunity specific to the new surface: this tool is explicitly documented as "the safety check — always call it before checkout," and an LLM-visible parameter capable of disabling that check is a weaker design than necessary for something meant to be invoked autonomously by an agent, where a manipulated prompt is a real threat model that doesn't apply to a developer writing code by hand.
  Fix: `sdk/shelfprotocol/mcp_server.py` — `can_buy(domain, amount_usd, require_verified=True)` → `can_buy(domain, amount_usd)`, with `require_verified=True` now hardcoded in the internal call. The raw Python SDK's `can_buy()` is untouched and still accepts the flag for developers writing deliberate code directly; only the agent-facing MCP tool was tightened.
  Verified: new test proves an unverified merchant with a $10,000 ceiling is still refused, and asserts via `inspect.signature` that `require_verified` is entirely absent from the tool's parameter schema (not just defaulted safely — structurally impossible to pass). Judge: `{"resolved": true}`. Ratchet Rule 9 added.

- **Phase 3 step 4 (CONFUSING) — README never explained how the MCP tool's `can_buy` differs from the raw SDK's.** The difference existed only in the `mcp_server.py` docstring, not in the README a developer would actually read first. Fixed: added a paragraph to the "Use it from any MCP client" section explaining the stricter, non-overridable verification on the MCP tool. Judge: `{"resolved": true}`.

---

## Refuted

### Phase 1
- **F1 (HIGH) — "SSRF via caller-controlled base_url"**: the quoted line is inside the SDK's own (pre-existing, previously-reviewed) functions, whose `base_url` parameter is for a developer's own code, not the new agent-facing surface. None of the five MCP tool functions accept or forward `base_url` to the underlying SDK calls (confirmed by `grep -n "base_url" sdk/shelfprotocol/mcp_server.py` returning zero matches) — every MCP-driven call falls through to the operator-configured `SHELF_URL`/`BASE_URL`, never something an MCP client can set. Conceded.

### Phase 3
- Step 2 (BLOCKER, recurring false positive across this project's gate history): "README doesn't show how to register a merchant or call can_buy" — contradicted by the existing "Register a merchant" curl example and "The one line developers add" `lookup`/`can_buy` snippet, both already present and unchanged by this PR. Conceded.
- Steps 1, 3 (MINOR): wants numbered steps rather than prose sections — noted, no action required.

---

## Cold pass results
Stranger 1: **PASS**
- MEDIUM: DNS lookup has a bounded timeout, described as risking "false negatives in domain verification" — this is the correct, intended fail-closed behavior for a timeout, not a defect.

Stranger 2: **PASS** — zero findings.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS (including new `sdk/shelfprotocol/mcp_server.py`, `sdk/shelfprotocol/__init__.py`)
- 0b Secret scan: PASS
- 0c Required files: PASS
- 0d Spec conformance: PASS
- 0e Structural invariants: all PASS

## Ratchet rules checked
Rules 1–8: all PASS, no changes.

## Rule 9 (new): agent-facing MCP tools must not expose safety-check overrides to the caller
Added this run — see GATE_RATCHET.md for the full rule text and Phase 0 check.
