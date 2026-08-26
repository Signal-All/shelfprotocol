# Shelf Protocol Gate Report
Date: 2026-08-26
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Change under review: light redesign + animated explainer + trust section (`light-redesign`)

## VERDICT: PASS

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None. The trust section was first drafted with Luis's name and a first-person statement;
he vetoed it, so the section now makes the same case from verifiable properties of the
project (open source and auditable, no account, unconditional removal) with no personal
identity attached. Re-tested after the change: **no regression** — still 15 seconds to
understand, still trustworthy, and the section still registers as trust-*increasing*.

His email remains in three places as the removal contact. That is deliberate and
load-bearing: a removal policy nobody can reach is not a policy. It can be swapped for a
role address or GitHub issues if he prefers, but it cannot simply be deleted.

## Context
Luis's read: the site was "very futuristic and might be too much for a merchant." He
was right, and it's the same mistake as the copy one layer down. Dark navy, neon
gradients, glowing accents and monospace are the visual language of developer
infrastructure. A Shopify merchant's daily tools — Shopify admin, Klaviyo, Stripe,
Gorgias — are light, calm and conventional. Design that doesn't match what someone
already trusts creates hesitation before a word is read.

## Fixed
- **All four pages** relit to a light, high-contrast palette. Every colour pair
  verified against WCAG AA: worst case 4.63:1, best 17.78:1.
- **Animated explainer** above the fold — a looping CSS/SVG sequence that plays the
  same shop twice, refused while unverified and allowed once verified. No video, no
  play button, no hosting, no sound; honours `prefers-reduced-motion` by freezing on
  the "refused" state.
- **Trust section added.** The site previously had no name, no face, no "who made this
  and why" — the top conversion killer for an unknown domain arriving by cold email.
- **Single primary CTA** in the closing section, replacing two competing buttons.
- **Nav bar** across all four pages so they read as one site.
- **Adoption claim hedged** in both the hero and the meta description after two cold
  strangers and the merchant persona independently flagged it.

## Refuted
- **F1 (MEDIUM, "misleading claim about AI shopping")** — raised again against the
  *already-hedged* second draft, quoting "still rarely, but it is starting." A sentence
  asserting low prevalence cannot mislead a reader into believing high prevalence; the
  finding had become unfalsifiable, since any true statement that agentic purchasing is
  beginning would trigger it. The body of the page says three separate times that this
  is early, not yet common, and of unknown trajectory. The judge named no accurate
  replacement wording, and none exists — no public dataset measures autonomous purchase
  volume, which is why the page refuses to give a number.
  Conceded: *"The sentence in question already includes a qualifier indicating low
  prevalence... the lack of a specific correction suggests that the current wording is
  appropriately cautious."*

## Cold pass results
Stranger 1: **PASS** — 1 MEDIUM (the adoption claim, since fixed then refuted).
Stranger 2: **PASS** — same finding, quoting the meta description.
Re-run after the hedge: **PASS** — same finding again, refuted and conceded above.

## Phase 3 — merchant walkthrough, and the trend across the week
Same persona each time (men's grooming brand, ~20 staff, has a web contractor):

| | dark, dev-first | after copy rewrite | after this redesign |
|---|---|---|---|
| Seconds to understand | 120 | 45 | **15** |
| Looks trustworthy | — | — | **yes** |
| Looks like a tool for stores like mine | — | — | **yes** |
| Would forward to their web person | no | yes | **yes** |

Also from this run: the animation **helps**; the "Who's behind this" section
**increased** trust; nothing felt like pressure or a scam. The only friction left is
MINOR and known — the DNS record, which is a product limitation rather than a copy or
design one (see the previous report).

Biggest remaining hesitation, in her words: *"The concept is new and not widely adopted
yet, which might mean it's not urgent."* That is an accurate description of the product,
not a defect in the page.

## Phase 0 results
- Phase 1: `{"findings": []}` — zero findings on the restyle
- Syntax, secret scan, required files, spec conformance, structural invariants: **OK**
- Markup balance verified on all four pages
- Tests: **11/11 suites pass**
- Ratchet: **all 14 rules verified**

## Rules added this run
None. The palette and contrast work is design judgement; a ratchet rule that can't be
checked mechanically dilutes the file. Rule 13 already binds every page under `web/`
and caught nothing here because the restyle introduced no new sinks.
