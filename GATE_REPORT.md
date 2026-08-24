# Shelf Protocol Gate Report
Date: 2026-08-24
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Change under review: merchant UI + registry browse page + CORS (`merchant-ui`)

## VERDICT: PASS

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

## Context
Showing a merchant their listing previously meant sending them a curl command or a
raw JSON URL, which no store owner will act on. This adds `/m/?d=<domain>` ("what AI
agents see about your store"), `/registry/` (browse everything), and the CORS header
that lets a static page on shelfprotocol.com read api.shelfprotocol.com at all.

Every field these pages display is authored by a third party — merchant names,
descriptions, product titles, prices and product URLs all come from imported store
feeds. That makes the whole surface attacker-controlled, and it is shown to other
merchants and to the public.

## Fixed
Nothing raised by the judge required a fix. One issue was found and fixed by the
EDITOR before Phase 1: the live registry contains `deploy-smoketest.example`, a
leftover deploy-verification record that would have appeared on the public browse
page. Rather than mutate production data, `/registry/` now filters domains under the
RFC 2606/6761 reserved TLDs (`.example`, `.test`, `.invalid`, `.localhost`), which can
never be a real store. Verified in node that `examplestore.com` is correctly kept.

## Refuted
All four Phase 1 findings, each conceded explicitly.

- **F1 (CRITICAL, "DOM XSS via attacker-controlled data")** — the quoted evidence was
  the EDITOR's own source comment describing the defense, and the impact was stated
  conditionally ("IF any attacker-controlled data is mistakenly interpolated"), which
  concedes no such interpolation was found. There is no HTML sink on either page to
  interpolate into; `tests/test_web_pages.py` fails the build if `innerHTML`,
  `outerHTML`, `document.write`, `insertAdjacentHTML` or `eval(` appears.
  Conceded: *"There is no demonstrated path where attacker-controlled data is
  interpolated into HTML without proper sanitization."*
- **F2 (HIGH, "unsafe URL schemes in product links")** — quoted `safeHref` in full,
  then hypothesized its failure. The guard is fail-closed and tested in node against
  `javascript:`, `JaVaScRiPt:`, leading-whitespace `javascript:`, `data:`, `vbscript:`,
  `file:`, empty and null — all rejected.
  Conceded: *"There is no demonstrated input string that bypasses the URL scheme check."*
- **F3 (MEDIUM, "CORS allows all origins")** — the finding's own impact statement
  noted the policy is GET/OPTIONS-only without credentials. CORS is not an access
  control on public data: every endpoint it exposes is unauthenticated and already
  world-readable by curl. Writes authenticate with an `X-Api-Key` header, not a cookie,
  and are not in the allowed methods.
  Conceded: *"The CORS policy does not expose any additional assets that are not
  already publicly accessible via curl."*
- **F4 (LOW, "open redirect")** — there is no redirect anywhere in the codebase. The
  cited URL is a same-origin relative link with a literal prefix and a
  `encodeURIComponent`-escaped parameter, re-validated on read against a strict regex.
  Conceded: *"There is no actual redirect occurring in the codebase."*

## Cold pass results
Stranger 1: **PASS** — 1 MEDIUM (conditional XSS on the `safeHref` call site), 1 LOW
(public merchant data is scrapable — it is a public registry).
Stranger 2: **PASS** — 2 findings whose quoted evidence describes the mitigations
working ("textContent is used for setting text, preventing script injection").

Neither is actionable; both restate the Phase 1 concessions. Recorded alongside the
standing benign MEDIUMs (unpinned DNS resolver, env-configurable `SHELF_URL`).

## Phase 3 — merchant walkthrough
Judged as the founder of G FUEL, cold, mildly suspicious, having received a link to
their own listing — with the page source and the *live* API data it renders.

- **Reaction: `claim_it`** (from `claim_it | ignore | demand_removal | escalate`)
- **Understood in 10 seconds**
- 1 MINOR friction: a brief "Loading…" flash before data arrives
- Most persuasive: *"claiming the listing is free, takes about five minutes, and
  allows control over what agents can see and do"*
- Least credible: the product name *"Onions & Waffles"* — which is a real G FUEL
  product, so that is the live data being accurate rather than a defect

That is the outcome this page exists for: the previous Phase 3 merchant, shown only
the README, said `demand_removal`.

## Phase 0 results
- 0a Syntax: **OK** — all server and SDK modules compile
- 0b Secret scan: **OK** — pre-existing negative-test fixtures only
- 0c/0d Required files, spec conformance: **OK**
- 0e Structural invariants: **OK**
- 0f Ratchet: **OK** — all 12 pre-existing rules verified
- Tests: **11/11 suites pass**, including new `tests/test_cors.py` and
  `tests/test_web_pages.py`

## Ratchet rules checked
| Rule | Result |
|------|--------|
| 1–3 — lock atomicity, verify auth, register 409 | PASS |
| 4–6 — README registration, no inline secrets, feed_url | PASS |
| 7 — mutations via `DB.transform`, single `db.upsert` | PASS (count = 1) |
| 8 — DNS pinning on merchant-supplied fetches | PASS |
| 9 — MCP `can_buy` has no `require_verified` | PASS |
| 10 — every agent-facing tool surface hardened | PASS |
| 11 — `agent_tools.py` has no postponed annotations | PASS |
| 12 — removal enforced, not merely performed | PASS |

## Rules added this run
- **Rule 13** — browser pages must never route merchant data through an HTML sink;
  merchant URLs pass a fail-closed scheme guard.
- **Rule 14** — CORS stays `GET`/`OPTIONS` only with `allow_credentials=False`; a real
  cross-origin write need gets an explicit allowlist and its own gate run, never a
  widened wildcard.

## Known and accepted
The "Loading…" flash is real and unfixed — the pages fetch on load rather than being
server-rendered, which is the cost of keeping the site static on GitHub Pages. At one
round trip it is not worth a backend.
