# OpenShelf Gate Report
Date: 2026-07-03 (afternoon run)
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate skill: /gate-openshelf
Scope note: this run gates the new real DNS-TXT verification in `/verify` (dnspython lookup of `_openshelf.<domain>`, `OPENSHELF_DNS_CHECK=off` demo escape hatch), plus README updates.

## VERDICT: PASS

Full gate run: Phase 0 (cheap checks) → Phase 1 (adversarial) → Phase 2 (two cold strangers) → Phase 3 (developer walk-through). Both Phase 1 findings were refuted with counter-evidence and conceded by the judge. Both Phase 2 cold passes returned PASS. All four Phase 3 frictions were audit-context artifacts (judge could not execute code / was not given spec/shelf.json.example) and were conceded on re-evaluation.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed
None. No finding in this run survived refutation, so no code changes were made by the gate. (The DNS-TXT verification feature itself was implemented and tested before the gate: stubbed-resolver positive/negative paths, live NXDOMAIN path, demo-mode skip, and 401 on bad api_key all verified.)

---

## Refuted

### Phase 1
- **F1 (HIGH) — "SQL Injection in search()"** (server/db.py). Claim: f-string builds the query. Counter-evidence: the f-string interpolates only `where`, assembled from fixed clause templates containing `?` placeholders; all user values (`q`, `category`, `protocol`, `max_order_usd`, `limit`) travel via the `params` list to `execute(sql, params)`. Judge conceded: "user input is safely parameterized... standard and secure practice."
- **F2 (MEDIUM) — "Race Condition in bump_lookup()"**. Claim: concurrent requests could lose counter updates. Counter-evidence: the entire SELECT → increment → write cycle sits inside one `with self._lock:` block and writes via `_upsert_unlocked` (no re-acquisition). Judge conceded: "no window for a lost update."

### Phase 3 (all conceded on re-evaluation)
- Step 1 "BLOCKER — shelf.json structure not detailed": README's "Register a merchant" section contains a complete working curl body; full schema referenced at spec/shelf.json.example (not pasted into the audit context).
- Steps 2–4 "BLOCKERs — cannot verify without running the server": documentation review, not an execution environment; README's "Run it locally (90 seconds)" section covers server start, seeding, and demo.

---

## Cold pass results
Stranger 1: **PASS**
- MEDIUM: "Potential SQL Injection" at `execute(sql, params)` — same claim refuted in Phase 1 (parameterized); verdict was PASS so no action required.
- LOW: hardcoded default `country: str = "US"` on the Merchant model — cosmetic default, merchant-overridable.

Stranger 2: **PASS**
- MEDIUM: "Potential SQL Injection" at `execute(sql, params)` — same as above.
- LOW: `osk_` API-key prefix "makes keys easier to identify" — intentional design (prefixes aid secret scanning, cf. `sk-`, `ghp_`); keys are 24 bytes of `secrets.token_urlsafe` entropy.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS (`py_compile` clean on server/main.py, server/db.py, sdk/openshelf.py, demo/demo_agent.py)
- 0b Secret scan: PASS (no literal tokens; only `secrets.token_urlsafe` generation and sha256 hashing)
- 0c Required files: PASS (all 10 present)
- 0d Spec conformance: PASS (spec/shelf.json.example has all 9 required fields)
- 0e Structural invariants:
  1. bump_lookup atomicity: PASS
  2. verify endpoint auth: PASS (`x_api_key: str = Header(...)` + sha256 hash check before any write, and before the DNS check)
  3. register 409 guard: PASS
  4. can_buy require_verified default True: PASS
  5. SQL params only in search(): PASS

## Ratchet rules checked
- Rule 1 (bump_lookup holds lock across read-modify-write): PASS
- Rule 2 (verify authenticates with api_key): PASS — auth check precedes the new DNS-TXT check
- Rule 3 (register blocks re-registration, 409): PASS
- Rule 4 (README documents registration with concrete POST body): PASS (grep check)
- Rule 5 (README examples use $OPENSHELF_API_KEY env var, no inline secrets): PASS (grep check)
