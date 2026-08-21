# Shelf Protocol Gate Ratchet

Confirmed failures that must never re-ship. Phase 0 checks every rule here on every run.
Rules are append-only. Do not delete or edit past rules.

---

<!-- Rules are added here automatically after each gate run. -->
<!-- Format:
## Rule N: short title
Confirmed: YYYY-MM-DD
Was: exact description of the bug
Now required: what the code must always do
Phase 0 check: what to verify to catch a regression
-->

## Rule 1: bump_lookup must hold lock across full read-modify-write
Confirmed: 2026-06-28
Was: `bump_lookup()` called `self.get()` then `self.upsert()` as separate lock acquisitions. Between the two calls, another thread could modify the record, causing a lost counter update.
Now required: `bump_lookup` must hold `self._lock` across the entire read + increment + write cycle without releasing it. Use `_upsert_unlocked()` internally.
Phase 0 check: Read `server/db.py`. Verify `bump_lookup` opens a `with self._lock:` block that contains both the SELECT and the write, and does NOT call `self.get()` or `self.upsert()` (which acquire their own locks).

## Rule 2: verify endpoint must authenticate with api_key
Confirmed: 2026-06-28
Was: `POST /v1/merchants/{domain}/verify` accepted no credentials. Any caller could set `verified_domain: true` for any merchant they don't own, breaking the entire trust model.
Now required: The verify endpoint must require `X-Api-Key` header and validate it against the `api_key_hash` stored at registration before setting `verified_domain: true`.
Phase 0 check: Read `server/main.py`. Verify `verify_merchant` function signature includes `x_api_key: str = Header(...)` and the body checks `hashlib.sha256(x_api_key.encode()).hexdigest() != stored_hash` before writing.

## Rule 3: register must block re-registration of existing domains
Confirmed: 2026-06-28
Was: `POST /v1/merchants` accepted any domain and upserted over existing records with no auth. A bad actor could overwrite a competitor's `agent_policy`, `name`, and `checkout.endpoint` fields silently.
Now required: `register_merchant` must call `db.get(domain)` and raise HTTP 409 if the domain is already registered.
Phase 0 check: Read `server/main.py`. Verify `register_merchant` checks `db.get(domain)` and raises `HTTPException(409, ...)` before proceeding with token and key generation.

## Rule 4: README must document merchant registration with a concrete POST body example
Confirmed: 2026-07-03
Was: README described the registry conceptually but never showed the actual `POST /v1/merchants` request body. A developer walk-through (Phase 3) hit a BLOCKER at step 1 — nothing to copy to register a merchant.
Now required: README must contain a "Register a merchant" section with a working curl example showing a full JSON body (merchant.name, merchant.domain, merchant.categories, agent_policy, checkout), and must reference `spec/shelf.json.example` for the full schema.
Phase 0 check: `grep -q "Register a merchant" README.md && grep -q "POST http://localhost:8080/v1/merchants" README.md`.

## Rule 5: README code examples must not inline secrets as literal header values
Confirmed: 2026-07-03
Was: the `/verify` curl example in README passed the api_key as a raw literal in `-H "X-Api-Key: <the api_key from registration>"`, encouraging copy-paste of secrets directly into shell commands.
Now required: README examples that use an api_key must set it via an environment variable first (e.g. `export SHELF_API_KEY=...`) and reference the variable in the command, not a literal/placeholder value inline in the header.
Phase 0 check: `grep -q 'X-Api-Key: \$SHELF_API_KEY' README.md` (and absence of `X-Api-Key: <` or `X-Api-Key: osk_` literal patterns in README.md).

## Rule 6: README register example must declare catalog.feed_url and the catalog section must explain initial publishing
Confirmed: 2026-07-04
Was: the README's registration curl example declared no `catalog.feed_url`, while the catalog section referred to "the URL you declared in catalog.feed_url" — a developer following the register example had never declared one, and there is no update endpoint to add it later. A cold walk-through (Phase 3) flagged catalog publishing as CONFUSING.
Now required: the README "Register a merchant" curl example must include a `catalog.feed_url` field, and the catalog section must state the two-step publish flow (declare feed_url at registration, host shelf-catalog.json at that URL, then POST /catalog/refresh).
Phase 0 check: `grep -q '"feed_url"' README.md && grep -q "Publishing a catalog is two steps" README.md`.

## Rule 7: merchant record mutations must be atomic via DB.transform
Confirmed: 2026-07-04
Was: `update_merchant` (and `verify_merchant`, `refresh_catalog`) did `db.get(domain)` then `db.upsert(domain, record)` as separate lock acquisitions, holding the stale read across slow I/O. An update racing /verify could write back a stale trust block, silently un-verifying a merchant; catalog counters and lookup counts could likewise be clobbered.
Now required: any endpoint that mutates an existing merchant record must apply its mutation through `DB.transform(domain, fn)` (single-lock read-modify-write against the freshest record), with slow I/O (DNS lookups, feed fetches) performed before the transform. `db.upsert` in server/main.py is allowed only for creating records in `register_merchant`.
Phase 0 check: `grep -q "def transform" server/db.py` and `grep -c "db.upsert(" server/main.py` returns 1 (the register_merchant create path only).

## Rule 8: catalog/importer fetches must pin DNS resolution against rebinding TOCTOU
Confirmed: 2026-07-05
Was: `_assert_url_safe()` validated the resolved IP is public, but the subsequent `requests.get()` independently re-resolved DNS when opening the connection — a malicious nameserver could answer public on the validation lookup and private/internal on the connection lookup moments later, defeating the SSRF guard entirely (classic DNS-rebinding TOCTOU). The prior gate had accepted this as a "bounded residual risk"; it is no longer acceptable now that a fix exists.
Now required: any fetch of a merchant-supplied URL (`server/catalog.py`, `server/importer.py`) must pin the IP validated by `_assert_url_safe()` (thread-local, via the `socket.getaddrinfo` patch) for the duration of the fetch, then clear the pin in a `finally` block — never a bare `requests.get()` straight after validation with no pinning.
Phase 0 check: `grep -q "_pin_local.pin = " server/catalog.py` and `grep -q "_clear_pin()" server/importer.py` (both fetch call sites clear the pin).

## Rule 9: agent-facing MCP tools must not expose safety-check overrides to the caller
Confirmed: 2026-08-21
Was: the MCP server's `can_buy` tool (sdk/shelfprotocol/mcp_server.py) accepted a `require_verified: bool = True` argument, mirroring the raw SDK's `can_buy()` signature. Not a live bug (the merchant profile is always fetched fresh server-side, never caller-supplied), but this tool is specifically marketed as "the safety check an agent calls before spending money" and exposed to untrusted, LLM-driven callers where prompt injection is a real threat model that doesn't apply to a developer writing code directly — an LLM-visible parameter capable of disabling the verification check was weaker defense-in-depth than the surface warranted.
Now required: MCP tools that gate an autonomous/agent-facing safety decision (domain verification, spending ceilings, or any future equivalent) must not expose an argument that weakens that decision to the calling MCP client. The raw Python SDK may keep such flags for developers writing deliberate code; only the MCP-tool wrapper is constrained.
Phase 0 check: `grep -n "^def can_buy" sdk/shelfprotocol/mcp_server.py` must show a signature with no `require_verified` parameter (the docstring may still mention it in prose, comparing to the raw SDK — check the `def` line specifically, not the whole file). Structurally enforced by `tests/test_mcp_server.py` via `inspect.signature`.
