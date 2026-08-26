# Shelf Protocol Gate Report
Date: 2026-08-26
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Change under review: merchant-first marketing site (`merchant-first-site`)

## VERDICT: PASS (with a product limitation recorded, not fixed)

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None blocking. One product decision is surfaced below under "The finding that matters".

## Context
The landing page was written for developers and, oddly, for investors: a Python
snippet, a raw JSON blob, a curl command, and a table titled "How Shelf Protocol
makes money" — on the page meant to convert store owners. A merchant landing on it
had no sentence explaining what any of it meant for their shop. This rewrites it for
merchants, moves every code sample to a new `/developers/` page, and removes the
revenue table from the public site entirely.

## Fixed
- Landing page rewritten merchant-first: plain-language premise, an inline SVG of the
  buy/walk-away decision, a store-address box that drops the owner straight into their
  own `/m/` page, and the DNS step shown as the two fields they'd paste.
- All code, JSON, curl and API reference moved to `/developers/`.
- Revenue table removed from `web/` (verified absent).
- **Phase 3 round 1 — BLOCKER.** A non-technical store owner did not understand *why
  an AI would shop at all*. The page explained the mechanism without ever establishing
  the premise. Added an "Is this really happening?" section grounding it in behaviour
  she already recognises (asking ChatGPT for a gift, telling Alexa to reorder).
- **Phase 3 round 2 — pressure regression.** The premise fix made the hero read as
  fear-selling ("it quietly buys from one it can"). Softened, and added a
  forward-to-your-web-person block so the DNS step becomes something to delegate
  rather than something to learn.
- **Phase 3 round 3, DTC persona — overclaim.** "This is happening widely already
  might be overstated, as there is no specific data or examples provided." Fair, and
  the same overclaim pattern the ratchet already polices elsewhere. The section now
  states plainly that it is early, not yet common, and that nobody can say how fast it
  grows.

## Refuted
None. Phase 1 returned `{"findings": []}` — no hypotheticals to argue with.

## Cold pass results
Stranger 1: **PASS**, zero findings.
Stranger 2: **PASS**, zero findings.

## Phase 3 — two personas, and the gap between them is the result
| Persona | Understood it | Would act |
|---|---|---|
| Solo candle shop, non-technical, no web person | **No** (3 iterations, unmoved) | No |
| DTC brand, ~20 staff, has a web contractor | **Yes** | Yes — would forward it |

The DTC founder is the audience the outreach actually targets, and she reported the
page as clear, the ask as reasonable, and explicitly "doesn't feel like a scam." Her
most-persuasive line was the core argument the page is built on.

## The finding that matters — recorded, not fixed
The solo shop owner's blocker did not move across three rewrites. It relocated
(round 1: "why would AI shop"; rounds 2–3: "I don't know what a TXT record is") but
never cleared. That is not a copy problem and further copy iteration will not shift it:
**adding a DNS TXT record is genuinely technical**, and a merchant with nobody to
delegate it to cannot complete onboarding regardless of wording.

If the long tail of small non-technical shops is ever a target, the fix is a different
verification path — a Shopify app, a file upload, or a meta tag pasted into a theme —
not better copy. Recorded here so the next person doesn't re-litigate it in prose.

## Phase 0 results
- Syntax, secret scan, required files, spec conformance, structural invariants: **OK**
- Ratchet: **OK** — all 14 rules verified
- Tests: **11/11 suites pass**

## Ratchet rules checked
| Rule | Result |
|------|--------|
| 1–3 — lock atomicity, verify auth, register 409 | PASS |
| 4–6 — README registration, no inline secrets, feed_url | PASS |
| 7 — mutations via `DB.transform`, single `db.upsert` | PASS |
| 8 — DNS pinning on merchant-supplied fetches | PASS |
| 9–11 — agent-tool hardening, no postponed annotations | PASS |
| 12 — removal enforced, not merely performed | PASS |
| 13 — no HTML sinks in `web/`, fail-closed href guard | PASS (coverage widened to all four pages) |
| 14 — CORS GET/OPTIONS only, no credentials | PASS |

## Rules added this run
None. The Phase 3 findings are calibration judgements about copy, and a ratchet rule
that cannot be checked mechanically would dilute the file rather than protect it.
Rule 13's *test* coverage was widened instead — it now binds every page under `web/`,
not just the two that fetch merchant data today, since a future page rendering a store
name is exactly the one that would be written without remembering the rule.

---

## Follow-up run — 2026-08-26, headline fix
Abbreviated gate (Phase 0 + Phase 3 only): copy-only change, no code touched, so the
adversarial and cold-stranger phases have nothing to audit.

**Was:** `Your customer asks ChatGPT to order candles.` The Phase 3 test persona was a
candle-shop owner and leaked straight into the product copy — a category-specific
headline on a page meant for every kind of store. Caught by Luis, not by the gate,
which is worth noting: a persona-driven process can bake its own persona into the
output, and no single-persona test will catch that.

**Now:** `Your customer asks ChatGPT to do the shopping. Will it pick your store?`

**Phase 3, re-run as a men's grooming brand** (deliberately a different category from
any example on the page):
- `is_this_page_for_a_store_like_mine`: **true**
- `did_i_ever_wonder_if_it_was_for_a_different_industry`: **false**
- `understood_what_it_is`: **true**, in **45 seconds** — down from 120
- would check their store: **yes**; would forward to their web person: **yes**
- One MINOR friction (the TXT record, unchanged and unfixable in copy — see above)

Phase 0: 11/11 suites pass, all 14 ratchet rules verified.

**Residual, accepted:** the persona still names the adoption claim as the least
credible thing on the page, even after the honesty calibration. That field always
returns the weakest point, so a non-empty answer isn't a failure — and the claim is
already hedged ("it is not yet common, and nobody can tell you exactly how fast it
grows"). Hedging the hero further would cost more in clarity than it gains in
accuracy.
