# Shelf Protocol Gate Report
Date: 2026-08-22
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate procedure: /gate-openshelf (executed from .claude/commands/gate-openshelf.md)
Scope note: this run gates a fix for a real production incident (branch `fix/duplicate-sku-partial-write`, PR #8). Seeding production against real Shopify stores crashed the importer when graza.co's live feed turned out to have two products sharing the same SKU, leaving a merchant record whose catalog metadata claimed 80 items that were never actually written. Confirmed live via the API and manually cleaned up (direct DB delete over SSH) before this fix.

## VERDICT: PASS

Phase 1 raised two real, well-reasoned findings about the fix's own edges — not routine false positives. One (rollback doesn't restore prior state) was empirically disproven by a passing test. The other (a narrow window for orphaned, invisible, self-healing product rows) was a legitimate observation whose severity I argued down from MEDIUM to LOW rather than dismissing outright, and the judge agreed. Both cold strangers PASS. Phase 3 found one real documentation gap (fixed) alongside the now-familiar false-positive walkthrough claim.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed

**The production incident itself**, at three layers:
- `server/catalog.py` `validate()` now rejects duplicate SKUs up front with a clear, actionable error identifying which item and which SKU — protects both the importer and the live `/catalog/refresh` HTTP endpoint, which shares this same validation path.
- `server/db.py` `set_catalog()` wraps its DELETE+executemany in try/except with explicit rollback, so a partial write can never become visible from any cause, not just this one.
- `server/importer.py` `import_domain()` now writes the catalog before the merchant record, so a catalog failure of any kind can never leave a merchant record whose metadata lies about what's actually stored.

Verified three ways: reproduced the exact bug against graza.co's real live feed (confirmed the fix catches the actual duplicate SKU `GL1-DRZ500` cleanly instead of crashing), a new test proving `set_catalog` fully restores the prior catalog on a failed write (not just "no partial write" — the actual old data survives), and a new test proving the importer never creates a merchant record on a duplicate-sku feed.

**Phase 3 step 2 (CONFUSING) — README never documented catalog validation errors.** A merchant whose feed fails validation (missing fields, duplicate SKU, etc.) had no documented way to know what error they'd see. Fixed: added a paragraph to the "Catalog feeds" section explaining the validation rules and the `422` + `reason` error shape, directly referencing the duplicate-SKU case this PR just hardened against.

---

## Refuted

### Phase 1
- **F2 (LOW) — "rollback only prevents partial writes, doesn't restore prior state"**: empirically false, not just argued — `tests/test_catalog.py`'s new test seeds a catalog, triggers a failed `set_catalog` call, and asserts the ORIGINAL data survives completely intact, not just "no corruption." SQLite's `rollback()` discards the entire uncommitted transaction (the DELETE included), so the prior state was never actually removed from disk. Conceded.

### Phase 1 — engaged on the merits, not refuted, but downgraded rather than actioned
- **F1 (MEDIUM → LOW) — "orphaned products rows possible if set_catalog succeeds but the subsequent merchant-record upsert fails"**: the observation is technically accurate (a narrow window exists), but the resulting rows are invisible everywhere in the API (`search_products()`'s plain INNER JOIN structurally excludes any product row without a matching merchant row; per-merchant lookup/catalog both 404 with no merchant record) and self-healing (any future re-import for that domain wipes and rewrites cleanly). Materially safer than the actual incident this PR fixes (a merchant record with *misleading* public data), and the failure trigger (a disk-full-class error hitting the merchants table specifically, immediately after a successful products write) is narrow enough that fixing it further wasn't judged worth the added complexity right now. Judge agreed, revised severity to LOW.

### Phase 3
- Step 1 (BLOCKER, recurring false positive across this project's gate history): "no clear $40 can_buy example" — contradicted by the existing, unchanged "The one line developers add" snippet. Conceded.

---

## Cold pass results
Stranger 1: **PASS**
- MEDIUM: DNS-rebinding claim, quoting the code comment that describes the problem the existing pin mechanism (Ratchet Rule 8) already closes — same recurring pattern as prior runs, not re-litigated since severity stayed non-blocking.
- LOW: SQLite "not suitable for high-concurrency production" — accepted, documented architectural choice (db.py's own docstring: "Swap this for Postgres when you outgrow it").

Stranger 2: **PASS** — same two findings, same assessment.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS
- 0b Secret scan: PASS
- 0c Required files: PASS
- 0d Spec conformance: PASS
- 0e Structural invariants: all PASS

## Ratchet rules checked
Rules 1–9: all PASS, no changes.

## Production incident timeline (for the record)
1. Ran `server/importer.py` against 11 real Shopify store domains via `railway ssh` into the live container — 3 succeeded (382 products indexed), 7 hit the pre-existing 1MB feed-size cap (correct, safe behavior for huge catalogs).
2. Ran a second batch of 9 domains — crashed on the first domain (`graza.co`) with `sqlite3.IntegrityError` on a genuine duplicate SKU in its live feed.
3. Diagnosed via the live API: `graza.co`'s merchant record existed with `catalog.item_count: 80`, but its actual catalog was empty (0 items) — the metadata write succeeded before the crash, the catalog write did not.
4. Manually deleted the stale record via `railway ssh` + direct sqlite3 access before starting the code fix, so the live public registry was never left in a known-bad state for longer than the diagnosis took.
5. Fixed at the three layers described above, reproduced against the real trigger, gated, merged. Seeding will resume from this branch's deployed state.
