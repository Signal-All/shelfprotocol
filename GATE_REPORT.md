# Shelf Protocol Gate Report
Date: 2026-07-05 (second run)
Judge: gpt-4o via OpenAI API (stateless calls — zero shared context per call)
Gate procedure: /gate-openshelf (executed from .claude/commands/gate-openshelf.md)
Scope note: this run gates branch `chore/rename-to-shelf-protocol` (PR #5), which carries two changes: (1) a DNS-rebinding TOCTOU fix for the catalog/importer SSRF guard, pinning the validated IP for the duration of the fetch; (2) the full product rename from OpenShelf to Shelf Protocol (brand copy, DNS record convention, SDK module, env vars, domain references) — no functional change from the rename itself.

## VERDICT: PASS

The DNS-rebinding pin drew real, substantive scrutiny in Phase 1 — three findings, all requiring genuine technical counter-evidence (not just "that's by design") to refute, including empirical source inspection of dnspython. All three conceded. Both cold strangers PASS. Phase 3's cold read of the renamed docs surfaced zero leftover "OpenShelf" references (explicitly checked for) and only MINOR nitpicks.

---

## Parked deadlocks — HUMAN DECISIONS REQUIRED
None.

---

## Fixed
None as a *result* of this gate run — the DNS-rebinding pin (server/catalog.py, server/importer.py) was already implemented and tested before Phase 1 started, so no judge finding drove it. It's recorded as **Ratchet Rule 8** regardless, because it closes a risk the prior gate explicitly accepted as residual, and the underlying pattern (validate-then-fetch without pinning) is exactly the failure class worth guarding against on every future touch of these files.

---

## Refuted

### Phase 1 — all three required real technical counter-evidence, not routine dismissal
- **F1 (HIGH) — "Thread-local DNS pin may leak across requests"**: both fetch call sites (`catalog.fetch()`, `importer._fetch_json()`) set the pin immediately before entering a `try` block whose `finally` unconditionally clears it — Python guarantees `finally` runs on every exit path, so the pin's lifetime is strictly bounded within a single call and cannot survive to a later request on a reused threadpool thread. Conceded.
- **F2 (MEDIUM) — "Patching socket.getaddrinfo affects the DNS resolver in main.py's verify endpoint"**: disproved empirically, not by assertion — inspected dnspython's actual source (`inspect.getsource`). `dns.query` (the module that dispatches the real DNS wire query `Resolver().resolve()` uses) never calls `socket.getaddrinfo`; it opens raw sockets directly. `dns.resolver` does reference `getaddrinfo`, but only inside a dormant, explicitly opt-in `override_system_resolver()` feature this codebase never calls (verified via grep — zero occurrences). Conceded.
- **F3 (MEDIUM) — "Race in capturing _real_getaddrinfo if another library already patched it"**: no dependency in this stack patches `socket.getaddrinfo` at import time (confirmed for dnspython in the F2 rebuttal; none of requests/urllib3/fastapi/starlette do under normal use). Separately, even in the hypothetical case, the pinning code's fallback defers to whatever was captured — identical behavior to the pre-existing, previously gate-passed baseline that called `socket.getaddrinfo` directly with the same "whatever is bound at call time" trust model. Not a regression. Conceded.

---

## Cold pass results
Stranger 1: **PASS**
- MEDIUM: DNS resolver not pinned to specific nameservers — same note as the prior gate run, now recurring; genuine deployment-hardening candidate for the hosted-API work (pin to 1.1.1.1/8.8.8.8 or similar in production config), not a code defect.
- LOW: "global variable for socket patching... unexpected behavior in multi-threaded environments" — the patch target (`_pinned_getaddrinfo`) is what's thread-safety-relevant, and it correctly uses `threading.local()` for the pin itself, which the finding doesn't address; recorded as-is, not actioned.

Stranger 2: **PASS**
- MEDIUM: same DNS resolver note as Stranger 1.
- LOW: "`robotparser.can_fetch` is deprecated" — checked and appears **factually incorrect**: `urllib.robotparser.RobotFileParser.can_fetch` is not deprecated in current Python; it's the documented public API for exactly this purpose. Recorded for completeness, not actioned.

PHASE 2: PASSED (Stranger 1 ✓, Stranger 2 ✓)

---

## Phase 0 results
- 0a Syntax: PASS (all modules incl. renamed `sdk/shelfprotocol.py`)
- 0b Secret scan: PASS
- 0c Required files: PASS
- 0d Spec conformance: PASS
- 0e Structural invariants: all PASS
- Full repo swept for stray "openshelf" (case-insensitive) after the rename: zero hits outside historical `GATE_REPORT.md` snapshots (left untouched — they're dated records of what was true at the time)

## Ratchet rules checked
- Rules 1–7: all PASS (Rule 5's Phase 0 grep updated in-branch to the renamed `SHELF_API_KEY` env var, still passes)
- Rule 8 (new — DNS-rebinding pin): PASS by construction, added this run

## Phase 3 (walk-through)
Five steps against the renamed README/SDK, explicitly instructed to flag any leftover old-name confusion: **zero** such references found. All five frictions MINOR ("doesn't explicitly restate that the example is the exact thing to use") — none actionable.
