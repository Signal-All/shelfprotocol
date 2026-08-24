# Shelf Protocol Gate Report
Date: 2026-08-24
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Change under review: removal policy + enforced delisting (`removal-policy`)

## VERDICT: PASS

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

## Context
The registry seeds itself with real stores from their public product feeds without
asking them first. That is a defensible cold-start tactic only if the stores can
get out. Before this change they could not: the API had 11 endpoints and none of
them removed anything, and there was no documented route to ask. A merchant who
found their business listed had nowhere to go.

## Fixed
- **Removal was not possible at all.** Added `DB.delist()` (record + cached products
  + suppression entry, one lock acquisition, try/except with explicit rollback),
  `DB.is_delisted()`, `DB.relist()`, a `python -m server.delist <domain>` CLI, and a
  documented policy in both README and the landing page with a concrete SLA
  (acknowledged in one business day, gone within five).
- **A removal the system would silently undo.** `import_domain()` now consults
  `db.is_delisted()` before any outbound request, so a delisted store's feed is
  never fetched and the next bulk import cannot re-add it.
- **F1/F2 (MEDIUM → real bug, found by chasing them).** As stated against `db.py`
  the findings were refutable — `delist`, `relist` and `is_delisted` each hold the
  same `self._lock` for their whole duration. But the same defect existed for real
  in `server/main.py`: `register_merchant` did `db.upsert(...)` then `db.relist(...)`
  as two separate acquisitions. A `delist()` landing between them left the domain
  deleted but no longer suppressed — re-importable, the precise outcome delisting
  exists to prevent. Fixed by adding `clear_suppression` to `DB.upsert()` so both
  writes happen under one acquisition, and removing the separate `relist` call.
  `tests/test_delist.py` asserts structurally that the window cannot return.
  Judge confirmed: `{"resolved": true}`.

## Refuted
- **F3 (LOW, `time.time()` clock drift).** No distributed system exists — one
  process, one local SQLite file, one in-process lock, one clock. `delisted_at` is
  never read by any logic; `is_delisted()` is an existence check that never touches
  it. `time.time()` is already the convention for `registered_at` and `imported_at`.
  Judge conceded: `{"concede": true, "reason": "The concerns about clock drift and
  distributed systems are not applicable in this context..."}`

## Cold pass results
Stranger 1: **PASS** — 1 MEDIUM (race in `upsert`), 1 LOW (`time.time()`).
Stranger 2: **PASS** — same two, independently, same locations.

Neither is actionable. The MEDIUM's own quoted evidence shows both writes inside a
single `with self._lock:` block, which is the fix rather than the bug; the LOW was
conceded in Phase 1. Recorded as benign recurring findings alongside the unpinned
DNS resolver and the env-configurable `SHELF_URL` from prior runs.

## Phase 3 — hostile merchant walkthrough
Judged as a real store owner who found their business listed without consent and is
deciding whether to ignore it, demand removal, or escalate.

- Before this change: **`demand_removal`** — 1 BLOCKER (listed without consent),
  1 CONFUSING (removal not self-serve), 2 unanswered questions ("why was my store
  chosen?", "what stops you using my data again after removal?").
- After: **`ignore`** — 1 MINOR, **zero unanswered questions**.

The second unanswered question is what produced the suppression list. A policy
promising unconditional removal, on a system that would re-add the store on its
next import, would have been a written promise the code could not keep.

The residual MINOR — wanting a more prominent upfront notice about being listed
without consent — is honest and unresolved. No wording fixes "you listed me without
asking"; only not seeding would, and that is a strategy decision, not a gate item.

## Phase 0 results
- 0a Syntax: **OK**
- 0b Secret scan: **OK** — two pre-existing negative-test fixtures (`osk_wrong`, `osk_nope`)
- 0c Required files: **OK**
- 0d Spec conformance: **OK**
- 0e Structural invariants: **OK**
- 0f Ratchet: **OK** — all 11 pre-existing rules verified
- Tests: **9/9 suites pass**, including the new `tests/test_delist.py`

## Ratchet rules checked
| Rule | Result |
|------|--------|
| 1 — bump_lookup single-lock read-modify-write | PASS |
| 2 — verify endpoint requires api_key | PASS |
| 3 — register 409 on existing domain | PASS |
| 4 — README documents registration with POST body | PASS |
| 5 — README uses `$SHELF_API_KEY`, no inline secrets | PASS |
| 6 — README declares `feed_url`, explains two-step publish | PASS |
| 7 — mutations via `DB.transform`, single `db.upsert` in main.py | PASS (count = 1) |
| 8 — DNS pinning on merchant-supplied URL fetches | PASS |
| 9 — MCP `can_buy` exposes no `require_verified` | PASS |
| 10 — every agent-facing tool surface hardened | PASS |
| 11 — `agent_tools.py` has no postponed annotations | PASS |

## Rules added this run
- **Rule 12** — a removal must be enforced, not merely performed. Covers the
  atomicity of delisting, the importer's pre-network suppression check, and the
  requirement that any path clearing suppression does so in the same lock
  acquisition as its write.
