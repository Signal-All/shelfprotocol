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

## Rule 10: every agent-facing tool surface must be hardened, not just the MCP one
Confirmed: 2026-08-24
Was: Rule 9 closed the caller-overridable verification flag on the MCP server's `can_buy`, but it is written specifically about `sdk/shelfprotocol/mcp_server.py`. The LangChain and CrewAI adapters added in PR #11 are the same threat model — an LLM that may be reading attacker-controlled text decides which tool to call with which arguments — and nothing in the ratchet bound them. A future adapter (AutoGen, LlamaIndex, a bare OpenAI function-schema export) could have reintroduced the override without tripping any check.
Now required: any module that exposes Shelf Protocol as tools to an LLM-driven caller must build them from `agent_tools.TOOL_SPECS` and must not add, re-expose, or widen an argument that weakens a safety decision (domain verification, spending ceiling, or any future equivalent). The raw Python SDK in `__init__.py` may keep such flags for developers writing deliberate code; the constraint binds only the agent-facing surfaces. New adapters must also be covered by the parity and hardening assertions in `tests/test_framework_tools.py`.
Phase 0 check: `grep -n "^def can_buy" sdk/shelfprotocol/agent_tools.py` must show a signature with no `require_verified` parameter. Then, for every `sdk/shelfprotocol/*_tools.py` adapter, verify it derives its tools from `tool_specs(...)`/`TOOL_SPECS` rather than wrapping the raw SDK directly: `grep -L "tool_specs\|TOOL_SPECS" sdk/shelfprotocol/*_tools.py` must list nothing (grep -L prints files *lacking* the pattern; `agent_tools.py` defines `TOOL_SPECS` so it is not listed either). Structurally enforced by `tests/test_framework_tools.py`.

## Rule 11: agent_tools.py must not use postponed annotation evaluation
Confirmed: 2026-08-24
Was: `sdk/shelfprotocol/agent_tools.py` was written with `from __future__ import annotations`, matching the rest of the SDK. Framework adapters build their argument schemas by reflecting over those signatures — CrewAI generates a pydantic model from them — and with postponed evaluation the annotations arrive as the strings `"Optional[str]"` etc., which pydantic cannot resolve in its own namespace. Every tool carrying an optional argument then raised `PydanticUserError: Shelf_Products is not fully defined` at call time, i.e. the moment an agent actually tried to use it. Caught by `tests/test_framework_tools.py`, not by import or by any type checker.
Now required: `sdk/shelfprotocol/agent_tools.py` must not import `annotations` from `__future__`, and the annotations on its tool functions must remain real runtime objects (`Optional[str]`, not `str | None`, while `requires-python` is >=3.9). The same applies to any future module whose function signatures are reflected over to build a tool schema. The rest of the SDK is unaffected and may keep the future import.
Phase 0 check: `grep -c '^from __future__ import annotations' sdk/shelfprotocol/agent_tools.py` must return 0. Anchor the pattern at line start — the file carries a NOTE comment naming the import verbatim to explain why it is absent, and an unanchored grep matches that comment and reports a false failure.

## Rule 12: a removal must be enforced, not merely performed
Confirmed: 2026-08-24
Was: the registry seeds itself with real stores from their public feeds, without asking them, so a merchant must be able to get out. The first cut of that path deleted the merchant record and its products but left nothing to stop the next bulk importer run from re-adding the store — a removal the system itself would undo. Worse, `register_merchant` then performed the opt-back-in as two separate lock acquisitions (`db.upsert(...)` followed by `db.relist(...)`); a `delist()` landing in that window left the domain deleted but no longer suppressed, i.e. re-importable, which is the exact outcome delisting exists to prevent. Same class as Rules 1 and 7 (read-modify-write split across acquisitions), on the one code path where the failure breaks a promise made in writing to a third party.
Now required: delisting must remove the merchant record, purge its cached products, and record the suppression entry in a single lock acquisition wrapped in try/except with explicit rollback. `import_domain()` must consult `db.is_delisted()` before any outbound request, so a suppressed domain's feed is never even fetched. Suppression lookups must normalize case and whitespace. Any path that clears suppression must do so in the same lock acquisition as the write it accompanies — never as a follow-up call. Suppression blocks the bulk importer only; a domain registering itself is opting back in deliberately and must never be locked out.
Phase 0 check: `grep -c "db.relist(" server/main.py` must return 0 (no endpoint may clear suppression as a separate call) and `grep -q "clear_suppression=True" server/main.py` must succeed. `grep -q "is_delisted" server/importer.py` must succeed, and in `import_domain` the `is_delisted` check must appear before the first `_robots_allows`/`_fetch_json` call. Structurally enforced by `tests/test_delist.py`, which asserts both the atomicity of the opt-back-in and that the importer makes no network call for a delisted domain.
