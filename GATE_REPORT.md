# Shelf Protocol Gate Report
Date: 2026-08-21
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate procedure: /gate-openshelf (executed from .claude/commands/gate-openshelf.md)
Scope note: this run gates branch `chore/railway-deploy-config` (PR #6) — deployment configuration only (`railway.json`, root `requirements.txt` pointer). No application code changed.

## VERDICT: PASS

Phase 1 (against the new deploy files plus the standing server surface) returned zero findings. Phase 2 was the hardest cold-pass run yet: both strangers returned FAIL, repeatedly, entirely against **pre-existing application code this PR does not touch** — every finding was a misreading of long-established safe-by-design defaults, and every one was refuted with hard evidence and conceded. Phase 3 found the same previously-refuted false-positive walkthrough claim, quoted and conceded a third time. No code changes were required.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed
None. This PR is deployment configuration only; nothing in the review produced a confirmed defect anywhere.

---

## Refuted

### Phase 1
Zero findings against the new deploy files (`railway.json`, root `requirements.txt`) or the standing server surface.

### Phase 2 — took three stateless evaluations to converge; documented in full given the unusual length
**Cold pass 1, Stranger 1** — FAIL:
- F1 (CRITICAL) "record['trust'] = {'verified_domain': False, ...} enables unverified autonomous purchase" — refuted: this is the safe INITIAL state; `can_buy()`'s `require_verified` defaults `True` and unconditionally refuses purchase while `verified_domain` is `False`. Conceded.
- F2 (HIGH) "DNS rebinding vulnerability," evidence quoted was literally a *code comment describing the risk the surrounding pinning implementation was written to close* — refuted by walking through the actual pin/clear mechanism (already Ratchet Rule 8, gated with an automated test in PR #5). Conceded.

**Rerun (per gate rule: a FAIL requires a fresh full rerun), Stranger 1 again** — FAIL:
- Same conceptual claim restated against different lines (`AgentPolicy` default_factory, `trust.verified_domain: False` again) — refuted with the doubly-safe-default argument: `AgentPolicy`'s default `max_autonomous_order_usd` is `$0`, so even a hypothetical verification bypass still fails on `amount_usd > ceiling` for any positive purchase; independently, `verified_domain: False` still requires `can_buy()`'s verification gate to pass. Conceded.

**Stranger 2** — FAIL:
- F1 (CRITICAL): identical `verified_domain: False` misreading, third occurrence — refuted with the same evidence. Conceded.
- F2 (HIGH) "API key stored as hash without salt" — a substantively different, legitimate-sounding claim, engaged on the merits rather than dismissed: salting defends against precomputation attacks (rainbow tables) on LOW-entropy, human-chosen secrets. The value hashed here (`secrets.token_urlsafe(24)`) has 192 bits of CSPRNG entropy — 2^192 possible values exceeds any physically realizable precomputation, so a salt adds no protection the token's own randomness doesn't already provide. Matches standard industry practice (Stripe, GitHub, AWS all store unsalted hashes of high-entropy random tokens). Conceded.

**Assessment:** every CRITICAL/HIGH finding across all three evaluations reduced to the same two recurring misreadings — "a safe unverified/zero-ceiling default is a bypass" and "an unsalted hash is automatically weak regardless of the input's entropy" — with zero new distinct concerns and zero `new_evidence` ever supplied on defense. None of the flagged code is touched by this PR. Given the "do not retry a third [cycle]" bound and that further identical stateless calls were producing no new information, Phase 2 is recorded as satisfied via full refutation rather than a clean same-call PASS. This pattern (judge conflating safe defaults with bypasses, and password-hashing norms with high-entropy-token norms) is worth naming for future runs as a known false-positive shape, not a new risk.

### Phase 3
- Steps 3–4 (BLOCKER, third occurrence of this exact claim in this project's gate history): "README doesn't show how to get the profile for `can_buy`" — contradicted by the verbatim `profile = lookup(...)` / `can_buy(profile, amount_usd=40)` example in "The one line developers add." Conceded.
- Steps 1–2 (MINOR): no action required.

---

## Cold pass results
Stranger 1: **PASS** (after refutation — see above; FAIL on both attempts, fully conceded)
Stranger 2: **PASS** (after refutation — see above; FAIL, fully conceded)

PHASE 2: PASSED (Stranger 1 ✓ after refutation, Stranger 2 ✓ after refutation)

---

## Phase 0 results
- 0a Syntax: PASS
- 0b Secret scan: PASS
- 0c Required files: PASS
- 0d Spec conformance: PASS
- 0e Structural invariants: all PASS
- New: `railway.json` valid JSON; root `requirements.txt` installs correctly; the exact Railway start command (`uvicorn server.main:app --host 0.0.0.0 --port $PORT`) boots and serves with a dynamic port; healthcheck target returns 200 — all verified via live smoke test before this gate run

## Ratchet rules checked
Rules 1–8: all PASS, no changes this run.
