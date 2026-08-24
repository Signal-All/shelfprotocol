# Shelf Protocol Gate Report
Date: 2026-08-24
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Change under review: PR #11 — LangChain and CrewAI tool adapters (`framework-tools`)

## VERDICT: PASS

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

## Fixed
No findings raised by the judge required a fix. Two defects were found and fixed
by the EDITOR's own tests during implementation, before Phase 1:

- **CrewAI tools with optional arguments crashed at call time.** `agent_tools.py`
  used `from __future__ import annotations`; CrewAI reflects over those signatures
  to build a pydantic args schema and received the string `"Optional[str]"`, which
  it cannot resolve — `PydanticUserError: Shelf_Products is not fully defined`,
  raised the moment an agent invoked the tool. Fixed by removing the future import
  from `sdk/shelfprotocol/agent_tools.py` and commenting the constraint at the
  import block. Now Ratchet Rule 11.
- **`crewai>=1.0` allowed a silent downgrade to an untested release.** With that
  floor, `pip install --dry-run "shelfprotocol[mcp,crewai]"` resolved successfully
  by backtracking crewai to 1.6.1 rather than erroring. Floor raised to
  `crewai>=1.15` in `pyproject.toml`, which converts the silent downgrade into an
  explicit `ResolutionImpossible`. Verified by re-running the dry-run.

## Refuted
- **F1 (HIGH, pyproject.toml, "Dependency Resolution Conflict")** — judge quoted
  the EDITOR's own explanatory comment as the evidence of the defect, and stated an
  impact containing both the conflict *and* "silent downgrades to untested
  versions" as though they co-occur. They are mutually exclusive: the silent
  downgrade is what the rejected loose floor produced (measured via
  `pip install --dry-run`, which selected crewai 1.6.1), and the current floor
  eliminates that path in favor of a loud resolver error. No environment requires
  both extras — the MCP server and the CrewAI adapter are two transports for the
  same five tools. Severity HIGH is also unreachable for an install-time message
  that fails closed before any code runs.
  Judge conceded: `{"concede": true, "reason": "The evidence provided was a
  misinterpretation of an intentional comment in the code, not an actual defect...
  The issue is a deliberate trade-off decision, not a defect."}`

## Cold pass results
Stranger 1: **PASS** — 1 MEDIUM: `SHELF_URL` is environment-configurable
(`sdk/shelfprotocol/__init__.py`), so an attacker controlling the process
environment could redirect lookups to a malicious registry.
Stranger 2: **PASS** — same MEDIUM, independently raised, same location.

Not fixed, and not introduced by this change. `SHELF_URL` is a documented feature
for self-hosted and staging registries, present since the SDK's first version. An
attacker who can set environment variables in the agent's process already controls
the process outright and needs no registry redirect. Recorded here as a benign
recurring MEDIUM, alongside the unpinned DNS resolver noted in prior runs.

## Phase 0 results
- 0a Syntax (paths updated for the post-rename layout): **OK** — 10 modules compiled
- 0b Secret scan: **OK** — two hits, `osk_wrong` / `osk_nope` in `tests/test_catalog.py`
  and `tests/test_verify.py`, both deliberately-invalid fixtures asserting rejection.
  Pre-existing, not literal credentials.
- 0c Required files: **OK** — all 10 present
- 0d Spec conformance: **OK** — all 9 required `shelf.json` fields present
- 0e Structural invariants: **OK** — bump_lookup atomicity, verify-endpoint auth,
  register 409 guard, `can_buy(require_verified=True)` default, parameterized SQL
- 0f Ratchet: **OK** — all 9 pre-existing rules verified

## Ratchet rules checked
| Rule | Result |
|------|--------|
| 1 — bump_lookup single-lock read-modify-write | PASS |
| 2 — verify endpoint requires api_key | PASS |
| 3 — register 409 on existing domain | PASS |
| 4 — README documents registration with POST body | PASS |
| 5 — README uses `$SHELF_API_KEY`, no inline secrets | PASS |
| 6 — README declares `feed_url`, explains two-step publish | PASS |
| 7 — mutations via `DB.transform`, single `db.upsert` | PASS (upsert count = 1) |
| 8 — DNS pinning on merchant-supplied URL fetches | PASS |
| 9 — MCP `can_buy` exposes no `require_verified` | PASS |

## Rules added this run
- **Rule 10** — every agent-facing tool surface must be hardened, not just the MCP
  one. Rule 9 was written specifically about `mcp_server.py`; the new adapters share
  its threat model and were unbound by the ratchet.
- **Rule 11** — `agent_tools.py` must not use postponed annotation evaluation.
  Codifies the CrewAI schema crash above.

The dependency-floor lesson is deliberately *not* a ratchet rule: a stable Phase 0
check for it would need a network dry-run rather than a grep, which does not belong
in the cheap-checks phase. It is documented in `pyproject.toml` and the README
instead.

## Test evidence
- 8/8 suites pass under system python3 (mcp 2.0.0): MCP-parity and hardening
  assertions execute, adapter blocks skip.
- `tests/test_framework_tools.py` passes in a venv with langchain-core 1.6.0 +
  crewai 1.15.17: adapter blocks execute, MCP parity skips (crewai's `mcp~=1.28`
  pin makes both impossible in one environment).
- Clean-venv installs of the built wheel for `[langchain]` and `[crewai]`
  separately, each exercised against the live registry at `api.shelfprotocol.com`:
  `shelf_lookup("gfuel.com")` returns the real record; `shelf_can_buy` refuses it
  as unverified.
- `[mcp,crewai]` confirmed to fail resolution by dry-run after the floor change.
