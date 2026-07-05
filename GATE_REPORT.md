# OpenShelf Gate Report
Date: 2026-07-04 (third run)
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate skill: /gate-openshelf
Scope note: this run gates the listing update endpoint (branch `feat/update-endpoint`, PR #3): `PUT /v1/merchants/{domain}` plus the middleware fix classifying PUT/PATCH/DELETE as rate-limited writes.

## VERDICT: PASS

Full gate run. Phase 1 produced one confirmed real bug (lost-update race, FIXED with an atomic transform — the gate's first code fix) and three refuted findings. Both cold strangers PASS. Phase 3 walk-through returned only MINOR frictions, no fixes required.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed

- **F2 (MEDIUM) — Lost-update race in read-modify-write endpoints.** `update_merchant` read the record (`db.get`), rebuilt it, then wrote it back (`db.upsert`) as separate lock acquisitions — a `/verify` landing in between would be clobbered by the stale copy, silently un-verifying the merchant. `verify_merchant` and `refresh_catalog` had the same shape, made worse by holding their stale read across multi-second DNS/HTTP I/O.
  Fix: new `DB.transform(domain, fn)` in server/db.py performs the read-modify-write atomically under one lock (via `_upsert_unlocked`); all three endpoints now do slow I/O first, then apply only their narrow mutation to the freshest record via `transform`. `db.upsert` remains in main.py only for `register_merchant` (a create).
  Verified: 50 concurrent PUTs racing one verify preserve `verified_domain` and `_meta` in every interleaving; lookup counters survive an update storm exactly (0 → 31). Judge: `{"resolved": true}`. Ratchet Rule 7 added.

---

## Refuted

### Phase 1 (all conceded)
- **F1 (HIGH) — "Privilege escalation via update endpoint"**: the quoted `updated["trust"] = current["trust"]` is the line that prevents escalation — caller-supplied trust is discarded (and ShelfDoc has no trust field, so it's dropped at parse time); `_meta` (key hash, token) is likewise copied from the stored record. Conceded.
- **F3 (MEDIUM) — "SSRF via catalog fetcher"**: `_assert_url_safe` precedes the fetch (https/443 only, all resolved IPs must be `is_global`, no redirects, 1MB cap). Conceded (second gate in a row).
- **F4 (LOW) — "Potential SQL injection (future changes)"**: quoted line appends to the params list bound to `?` placeholders; the finding rested on hypothetical future edits. Conceded.

---

## Cold pass results
Stranger 1: **PASS**
- MEDIUM: `osk_` key prefix "predictable" — public namespace marker; 192-bit CSPRNG suffix carries all entropy.
- LOW: no logging on catalog fetch errors — fair operational note; errors do surface to the caller as structured 422s. Candidate for the hosted-API work.

Stranger 2: **PASS**
- MEDIUM: "potentially unsafe URL parsing" — malformed URLs fail closed (no host / wrong scheme → CatalogError).
- LOW: "potential SQL injection if not parameterized" — the quoted call is the parameterized form.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS (all six modules)
- 0b Secret scan: PASS
- 0c Required files: PASS
- 0d Spec conformance: PASS
- 0e Structural invariants: all PASS

## Ratchet rules checked
- Rule 1 (bump_lookup lock): PASS
- Rule 2 (verify authenticates): PASS
- Rule 3 (register 409): PASS
- Rule 4 (README registration example): PASS (grep)
- Rule 5 (README env-var api_key): PASS (grep)
- Rule 6 (README catalog publishing): PASS (grep)
- Rule 7 (added this run — atomic transform for record mutations): PASS by construction

## Phase 3 (walk-through)
Five steps including the new update flow: all frictions MINOR, none actionable. Steps 3–4 reported "the process was straightforward."
