# Shelf Protocol Gate Report
Date: 2026-08-22 (second run)
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate procedure: /gate-openshelf (executed from .claude/commands/gate-openshelf.md)
Scope note: this run gates branch `chore/landing-page-deploy` (PR #9) — a GitHub Actions workflow deploying the existing `web/index.html` landing page to GitHub Pages. No application code changed. Pages enabled on the repo beforehand with `build_type=workflow` (`signal-all.github.io/shelfprotocol`).

## VERDICT: PASS

Phase 1 raised two findings that were both factually incorrect about the workflow itself — one flagged the officially-documented required permission for the deploy action as excessive, the other worried about a trigger type the workflow doesn't have. Both cold strangers PASS. Phase 3 repeated the project's most persistent recurring false-positive pattern (README missing install/register/can_buy examples that have been present, unchanged, since the very first gate run) — all conceded.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed
None — no confirmed defect survived this run.

---

## Refuted

### Phase 1
- **F1 (MEDIUM) — "id-token: write is excessive for a static site deploy"**: this is the officially documented, required permission for `actions/deploy-pages@v4` — it authenticates the deployment via OIDC token exchange; without it the deploy step fails outright. The three-permission block (`contents: read`, `pages: write`, `id-token: write`) is copied directly from GitHub's own documented Pages-via-Actions recipe. Conceded.
- **F2 (LOW) — "could be triggered by external fork PRs"**: the workflow's only triggers are `push: branches: [main]` and `workflow_dispatch` — no `pull_request` or `pull_request_target` trigger exists anywhere in the file. GitHub only runs workflows on fork PR events if such a trigger is explicitly declared; a push to `main` requires write access, which forks don't have. Conceded.

### Phase 3 (all conceded, recurring pattern across this project's entire gate history)
- "No clear pip install instruction" — contradicted by `pip install shelfprotocol` at the top of "The one line developers add."
- "No SDK registration instructions" — registration is deliberately HTTP-API-only (documented, complete curl example exists); the SDK's scope is lookup/can_buy against an already-registered merchant, not registration, by design.
- "No can_buy() example" — contradicted by the `lookup`/`can_buy(amount_usd=40)` snippet immediately following the install command in the same section.

---

## Cold pass results
Stranger 1: **PASS**
- MEDIUM: same `id-token: write` claim as Phase 1 F1 — non-blocking, not re-litigated per the rules (only mandatory on a FAIL verdict).

Stranger 2: **PASS** — zero findings.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS
- 0b Secret scan: PASS
- 0c Required files: PASS
- 0d Spec conformance: PASS
- 0e Structural invariants: all PASS
- New: workflow YAML validated with `yaml.safe_load`

## Ratchet rules checked
Rules 1–9: all PASS, no changes.
