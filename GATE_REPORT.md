# OpenShelf Gate Report
Date: 2026-07-04
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate skill: /gate-openshelf
Scope note: this run gates the per-IP rate limiting feature (branch `feat/rate-limiting`, PR #1): `server/ratelimit.py` fixed-window limiter + `/v1/*` middleware (120 reads/min, 10 writes/min per IP, 429 + Retry-After), env-tunable, `OPENSHELF_RATE_LIMIT=off` off-switch.

## VERDICT: PASS

Full gate run: Phase 0 (cheap checks) → Phase 1 (adversarial) → Phase 2 (two cold strangers) → Phase 3 (developer walk-through). All four Phase 1 findings were refuted with counter-evidence and conceded. Stranger 1 returned a clean PASS with zero findings; Stranger 2 PASS with one moot MEDIUM. Phase 3's two BLOCKER claims were contradicted by verbatim README content and conceded on re-evaluation.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed
None. No finding in this run survived refutation. (The rate limiting feature itself was implemented and tested before the gate: reads and writes capped in independent buckets, 429 shape with Retry-After + structured detail, window reset, off-switch, and a live uvicorn run showing 200/200/200/429.)

---

## Refuted

### Phase 1 (all conceded by the judge)
- **F1 (HIGH) — "Potential SQL Injection in search()"**: recurring claim, third concession. `where` is assembled from fixed clause templates; all user values travel via the `params` list to parameterized `?` placeholders.
- **F2 (MEDIUM) — "Lack of Authentication on Merchant Registration"**: open registration is documented design. New records always start `verified_domain: false`; the flag only flips via /verify (api_key hash + live DNS TXT proof of ownership); can_buy() defaults require_verified=True; re-registration of existing domains 409s (Ratchet Rule 3); writes now rate-limited 10/min/IP. Judge conceded the trust model addresses the poisoning concern.
- **F3 (MEDIUM) — "Hardcoded Secrets in API Key Generation"**: the quoted line is `secrets.token_urlsafe(24)` — a CSPRNG generating 192 bits of entropy. The `osk_` prefix is a public namespace marker (cf. Stripe `sk_`, GitHub `ghp_`). Server stores only the SHA-256 hash. Judge conceded the finding was incorrect.
- **F4 (LOW) — "Rate Limit Bypass via Client IP Spoofing"**: `request.client.host` is the TCP peer address — a spoofed source IP cannot complete the handshake, and the code deliberately does not trust X-Forwarded-For (trusting XFF unallowlisted would be the actual vulnerability). Behind a reverse proxy the failure mode is stricter limiting, never bypass. Judge conceded.

### Phase 3 (both conceded on re-evaluation)
- Steps 3–4 "BLOCKERs — cannot test can_buy without DNS verification": the README's Local demo note (`OPENSHELF_DNS_CHECK=off`) and the seeded pre-verified merchants in the 90-second flow provide exactly this; the demo agent itself runs the $40/$400 can_buy cases.
- Steps 1–2 MINORs (wants an explicit "this is the required format" sentence and a README lookup-by-domain example): noted, no action required by the gate.

---

## Cold pass results
Stranger 1: **PASS** — zero findings.
Stranger 2: **PASS**
- MEDIUM: API keys stored as SHA-256 hashes "could be brute-forced if the hash is compromised" — moot: keys carry 192 bits of CSPRNG entropy; brute-forcing the preimage is infeasible. Recorded, no action.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS (`py_compile` clean, including new `server/ratelimit.py`)
- 0b Secret scan: PASS (no literal tokens)
- 0c Required files: PASS (all 10 present)
- 0d Spec conformance: PASS (spec/shelf.json.example unchanged; all 9 required fields)
- 0e Structural invariants: all PASS —
  1. bump_lookup atomicity (db.py unchanged)
  2. verify endpoint auth (`Header(...)` + sha256 check precedes DNS check and any write)
  3. register 409 guard
  4. can_buy require_verified default True (sdk unchanged)
  5. SQL params only in search()

## Ratchet rules checked
- Rule 1 (bump_lookup holds lock across read-modify-write): PASS
- Rule 2 (verify authenticates with api_key): PASS
- Rule 3 (register blocks re-registration, 409): PASS
- Rule 4 (README documents registration with concrete POST body): PASS (grep check)
- Rule 5 (README examples use $OPENSHELF_API_KEY env var, no inline secrets): PASS (grep check)
