# OpenShelf Gate Report
Date: 2026-07-05
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate procedure: /gate-openshelf (executed from .claude/commands/gate-openshelf.md)
Scope note: this run gates unclaimed listings + claim flow + public-feed importer (branch `feat/claim-flow`, PR #4), including the _meta stripping hardening and the test suites moving into tests/.

## VERDICT: PASS

Full gate run. All four Phase 1 findings refuted with explicit concessions. Both cold strangers PASS. Phase 3 walk-through (five steps including the claim journey and registry seeding) returned only MINOR frictions — no fixes required.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed
None this run. (The PR itself contains a proactive hardening fix worth recording: public lookup/search responses previously returned the full record including `_meta` — leaking `api_key_hash` and `verification_token`. They now strip `_meta` and surface only a `claimed` flag. Done before the gate, so no judge finding to attribute it to.)

---

## Refuted

### Phase 1 (all conceded)
- **F1 (HIGH) — "Claim squatting: attacker could claim an unindexed domain"**: the judge's own evidence quote is the 404 that refuses claims on unindexed domains. For indexed-unclaimed domains, claiming issues credentials but zero control: edit/catalog routes 403 until /verify passes DNS, which only the domain owner can do; the real owner can always rotate a squatter's pending credentials by re-claiming. Conceded.
- **F2 (MEDIUM) — "API key returned in the response"**: one-time credential issuance is the industry-standard pattern; the server stores only the hash, and no endpoint ever returns the key again. Conceded.
- **F3 (MEDIUM) — "SSRF in importer _fetch_json"**: the fetch runs behind the same `_assert_url_safe` guard as the catalog crawler, and the importer is an operator-run offline CLI with no attacker-controlled input path. Conceded.
- **F4 (LOW) — "Credential rotation race"**: rotation writes the new hash atomically via `DB.transform`; accepting the old key before rotation lands is correct serialization, not a race; rotation only applies to unclaimed listings whose edit routes are 403 regardless. Conceded.

---

## Cold pass results
Stranger 1: **PASS**
- MEDIUM: DNS resolver uses the system default nameserver — deployment/environment concern; noted for the hosted-API work (could pin resolvers there).
- LOW: hedged dynamic-SQL note at the parameterized `execute(sql, params)` call.

Stranger 2: **PASS**
- MEDIUM: same DNS resolver note.
- LOW: SQLite path "hardcoded" — it is env-configurable via `OPENSHELF_DB` in the same quoted line.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS (seven modules incl. new `server/importer.py`)
- 0b Secret scan: PASS
- 0c Required files: PASS
- 0d Spec conformance: PASS
- 0e Structural invariants: all PASS (register still 409-guards both claimed and unclaimed collisions; verify auth unchanged; can_buy default unchanged; SQL parameterized throughout)

## Ratchet rules checked
- Rule 1 (bump_lookup lock): PASS
- Rule 2 (verify authenticates): PASS
- Rule 3 (register 409): PASS
- Rule 4 (README registration example): PASS (grep)
- Rule 5 (README env-var api_key): PASS (grep)
- Rule 6 (README catalog publishing): PASS (grep)
- Rule 7 (atomic transform; db.upsert in main.py only for register create): PASS — the claim endpoint mutates via `db.transform`; the importer's `db.upsert` is a create in importer.py, outside the rule's scope

## Phase 3 (walk-through)
Five steps including "take control of a listing you never registered" and "seed a local registry": all frictions MINOR, none actionable (the flagged domains.txt format is documented inline in the README's seeding command).
