# OpenShelf Gate Ratchet

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
Now required: README examples that use an api_key must set it via an environment variable first (e.g. `export OPENSHELF_API_KEY=...`) and reference the variable in the command, not a literal/placeholder value inline in the header.
Phase 0 check: `grep -q 'X-Api-Key: \$OPENSHELF_API_KEY' README.md` (and absence of `X-Api-Key: <` or `X-Api-Key: osk_` literal patterns in README.md).
