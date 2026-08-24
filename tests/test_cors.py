"""CORS: the static site must be able to read the registry from a browser, and
must not be able to write to it.

The read side is public data — anyone can curl it — so browsers get the same
access. Writes are a different matter: they authenticate with an X-Api-Key
header, and cross-origin writes would add attack surface for a capability the
site doesn't need.
"""
import common  # noqa: F401

client, main = common.fresh_client()

SITE = "https://shelfprotocol.com"
HOSTILE = "https://not-shelfprotocol.example"


def cors_headers(resp):
    return {k.lower(): v for k, v in resp.headers.items() if k.lower().startswith("access-control")}


# --- reads are allowed cross-origin ---
r = client.get("/v1/stats", headers={"Origin": SITE})
assert r.status_code == 200, r.text
h = cors_headers(r)
assert h.get("access-control-allow-origin") == "*", h
print("PASS: GET /v1/stats is readable cross-origin")

for path in ("/v1/search", "/v1/products", "/"):
    r = client.get(path, headers={"Origin": SITE})
    assert r.status_code == 200, (path, r.status_code)
    assert cors_headers(r).get("access-control-allow-origin") == "*", path
print("PASS: the agent-facing read endpoints all carry CORS headers")


# --- the preflight advertises reads only ---
r = client.options(
    "/v1/search",
    headers={
        "Origin": SITE,
        "Access-Control-Request-Method": "GET",
    },
)
assert r.status_code in (200, 204), r.status_code
allowed = cors_headers(r).get("access-control-allow-methods", "")
assert "GET" in allowed, allowed
assert "POST" not in allowed, f"writes must not be advertised cross-origin: {allowed}"
assert "PUT" not in allowed, f"writes must not be advertised cross-origin: {allowed}"
assert "DELETE" not in allowed, allowed
print("PASS: preflight advertises GET only — no POST/PUT/DELETE")


# --- a write preflight is refused ---
r = client.options(
    "/v1/merchants",
    headers={
        "Origin": HOSTILE,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-api-key",
    },
)
allowed = cors_headers(r).get("access-control-allow-methods", "")
assert "POST" not in allowed, f"cross-origin POST must never be permitted: {allowed}"
print("PASS: a cross-origin write preflight is not granted POST")


# --- credentials must never be allowed ---
# With allow_credentials, browsers reject a "*" origin anyway, and if cookie auth
# is ever added this is what would let a third-party page ride a visitor session.
for path in ("/v1/stats", "/v1/search"):
    r = client.get(path, headers={"Origin": HOSTILE})
    h = cors_headers(r)
    assert h.get("access-control-allow-credentials") != "true", (path, h)
print("PASS: credentials are never allowed cross-origin")


# --- writes still work same-origin (CORS must not have broken the API) ---
r = client.post("/v1/merchants", json={
    "shelf_version": "0.1",
    "merchant": {"name": "Cors Co", "domain": "corsco.example", "categories": ["food"]},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 25},
    "checkout": {"protocol": "manual"},
})
assert r.status_code == 200, r.text
assert client.get("/v1/merchants/corsco.example").status_code == 200
print("PASS: same-origin writes still work")

print("\nAll CORS tests passed.")
