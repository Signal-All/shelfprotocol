# OpenShelf Gate Report
Date: 2026-07-04 (second run)
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate skill: /gate-openshelf
Scope note: this run gates product-catalog feeds (branch `feat/catalog-feeds`, PR #2): `server/catalog.py` guarded fetcher, `products` table, refresh/catalog/products endpoints, SDK `catalog()`/`products()`, spec + README additions.

## VERDICT: PASS

Full gate run: Phase 0 → Phase 1 (adversarial) → Phase 2 (two cold strangers) → Phase 3 (developer walk-through). All four Phase 1 findings refuted and conceded. Both cold passes returned PASS. Phase 3 surfaced one genuine documentation gap (fixed, judge confirmed resolved) plus refutable claims that were conceded.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed

- **Phase 3 step 5 (CONFUSING) — README did not explain how to publish a catalog initially.** Real gap: the registration curl example declared no `catalog.feed_url`, but the catalog section referred to "the URL you declared." Fix (README.md): the register example now includes `"catalog": {"feed_url": "https://acme-coffee.example/.well-known/shelf-catalog.json"}`, and the catalog section opens with the two-step publishing instruction (declare feed_url at registration; host the file; then refresh). Judge: `{"resolved": true}`.

---

## Refuted

### Phase 1 (all conceded)
- **F1 (CRITICAL) — "SQL Injection in search_products()"** and **F2 (CRITICAL) — "SQL Injection in search()"**: both query builders join fixed clause templates; all user values travel via `params` to `?` placeholders; boolean filters contribute constant clauses only. Conceded in one re-evaluation.
- **F3 (HIGH) — "SSRF via catalog feed fetcher"**: the quoted `requests.get` runs only after `_assert_url_safe` (default on): https-only, port 443 only, and every resolved IP must be publicly routable (`ip.is_global` excludes loopback/private/link-local/reserved — including 169.254.169.254 cloud metadata); `allow_redirects=False`; non-200 rejected. DNS-rebinding TOCTOU acknowledged as a bounded residual (5s single request, 1MB cap, response never echoed, strict schema parse); judge conceded the risk is effectively mitigated.
- **F4 (MEDIUM) — "Race condition in rate_limit_middleware"**: `limiter.check()` increments under `threading.Lock`; N concurrent requests count exactly 1..N. Conceded.

### Phase 3
- Steps 3–4 "BLOCKERs — README doesn't show how to get the profile for can_buy": contradicted by the verbatim `profile = lookup(...)` / `can_buy(profile, amount_usd=40)` example in "The one line developers add". Both conceded.
- Steps 1–2 MINORs (wants "format is mandatory" phrasing and an explicit README lookup mention): noted, no action required.

---

## Cold pass results
Stranger 1: **PASS**
- MEDIUM: DNS resolver not pinned to specific nameservers — uses the system resolver by design; deployment concern, not a code defect.
- LOW: no User-Agent header on feed fetches — cosmetic; can add a `openshelf-registry/x.y` UA later for feed-host observability.

Stranger 2: **PASS**
- MEDIUM: "potentially unsafe URL parsing" (`urlparse(url)`) — hedged; malformed URLs fail closed (no host → CatalogError; non-https → CatalogError).
- LOW: "potential SQL injection if input not sanitized" at `execute(sql, params)` — the quoted line is the parameterized call itself.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS (including new `server/catalog.py`)
- 0b Secret scan: PASS
- 0c Required files: PASS
- 0d Spec conformance: PASS (shelf.json.example unchanged; all 9 required fields)
- 0e Structural invariants: all PASS (bump_lookup atomicity; verify auth precedes writes; register 409; can_buy default True; SQL params only — new `get_catalog`/`search_products` follow the same parameterized pattern)

## Ratchet rules checked
- Rule 1 (bump_lookup lock): PASS
- Rule 2 (verify authenticates): PASS
- Rule 3 (register 409): PASS
- Rule 4 (README registration example): PASS (grep)
- Rule 5 (README env-var api_key): PASS (grep)
- Rule 6 (added this run — see GATE_RATCHET.md): PASS by construction
