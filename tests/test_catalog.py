"""Catalog feeds: SSRF guards, validation, endpoints, product search."""
import common  # noqa: F401

from server import catalog as cat  # noqa: E402

client, main = common.fresh_client()

for bad_url, why in [
    ("http://feeds.example.com/cat.json", "plain http"),
    ("https://feeds.example.com:8443/cat.json", "non-443 port"),
    ("https://localhost/cat.json", "loopback"),
    ("https://127.0.0.1/cat.json", "loopback IP"),
    ("https://10.0.0.5/cat.json", "private IP"),
    ("https://169.254.169.254/latest/meta-data", "cloud metadata (link-local)"),
]:
    try:
        cat._assert_url_safe(bad_url)
        raise AssertionError(f"guard let through: {why} ({bad_url})")
    except cat.CatalogError:
        pass
print("PASS: SSRF guard rejects http, odd ports, loopback, private, link-local")

# DNS-rebinding: _assert_url_safe validates one resolution; the actual fetch
# must be pinned to that exact IP, not re-resolve (a rebinding DNS server
# could answer public on the first lookup and private on the second).
_rebind_host = "rebinding.example.test"
_answers = iter([
    [(2, 1, 6, "", ("93.184.216.34", 443))],   # first lookup: public IP (passes the guard)
    [(2, 1, 6, "", ("10.1.2.3", 443))],        # second lookup: private IP (would fail if not pinned)
])
_orig_real = cat._real_getaddrinfo
cat._real_getaddrinfo = lambda host, *a, **kw: next(_answers) if host == _rebind_host else _orig_real(host, *a, **kw)
try:
    cat._assert_url_safe(f"https://{_rebind_host}/cat.json")
    resolved = __import__("socket").getaddrinfo(_rebind_host, 443)
    assert resolved[0][4][0] == "93.184.216.34", (
        f"DNS rebinding bypass: connect would resolve to {resolved[0][4][0]}, "
        f"not the pinned, validated IP"
    )
finally:
    cat._real_getaddrinfo = _orig_real
    cat._clear_pin()
print("PASS: fetch is pinned to the validated IP — a second, differing DNS answer can't rebind it")

good = {"items": [{"sku": "A1", "name": "Thing", "price_usd": 9.5}]}
items = cat.validate(good)
assert items[0]["in_stock"] is True and items[0]["price_usd"] == 9.5
for bad, why in [
    ({"items": "nope"}, "items not a list"),
    ({"items": [{"name": "no sku"}]}, "missing sku"),
    ({"items": [{"sku": "A", "name": "N", "price_usd": -1}]}, "negative price"),
    ({"items": [{"sku": "A", "name": "N", "price_usd": True}]}, "bool price"),
    ({"items": [{"sku": str(i), "name": "N"} for i in range(1001)]}, "over item cap"),
]:
    try:
        cat.validate(bad)
        raise AssertionError(f"validator let through: {why}")
    except cat.CatalogError:
        pass
print("PASS: validator enforces schema, price sanity, item cap")

reg = {
    "merchant": {"name": "Cat Co", "domain": "catco.example", "categories": ["coffee"]},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 100},
    "catalog": {"feed_url": "https://catco.example/.well-known/shelf-catalog.json"},
}
key = client.post("/v1/merchants", json=reg).json()["api_key"]

FEED = {"items": [
    {"sku": "ESP-1", "name": "Espresso Blend", "categories": ["coffee"], "price_usd": 18.5},
    {"sku": "DEC-1", "name": "Decaf Blend", "categories": ["coffee"], "price_usd": 19.0, "in_stock": False},
]}
main.catalog.fetch = lambda url: cat.validate(FEED)

r = client.post("/v1/merchants/catco.example/catalog/refresh", headers={"X-Api-Key": "osk_wrong"})
assert r.status_code == 401, r.text
r = client.post("/v1/merchants/catco.example/catalog/refresh", headers={"X-Api-Key": key})
assert r.status_code == 200 and r.json()["items_indexed"] == 2, r.text
print("PASS: refresh requires api_key, indexes items, 401s otherwise")

prof = client.get("/v1/merchants/catco.example").json()
assert prof["catalog"]["item_count"] == 2 and prof["catalog"]["updated_at"]
print("PASS: merchant record catalog metadata updated")

r = client.get("/v1/merchants/catco.example/catalog", params={"q": "decaf"}).json()
assert r["count"] == 1 and r["items"][0]["sku"] == "DEC-1", r
assert client.get("/v1/merchants/ghost.example/catalog").status_code == 404
print("PASS: per-merchant catalog serves cached items with q filter")

r = client.get("/v1/products", params={"q": "espresso", "verified": True}).json()
assert r["count"] == 0, r
client.post("/v1/merchants/catco.example/verify", headers={"X-Api-Key": key})
r = client.get("/v1/products", params={"q": "espresso", "verified": True}).json()
assert r["count"] == 1 and r["results"][0]["merchant_verified"] is True, r
r = client.get("/v1/products", params={"in_stock": True, "q": "blend"}).json()
assert {p["sku"] for p in r["results"]} == {"ESP-1"}, r
print("PASS: /v1/products respects verified and in_stock filters")

FEED["items"] = [{"sku": "NEW-1", "name": "New Roast", "price_usd": 20.0}]
client.post("/v1/merchants/catco.example/catalog/refresh", headers={"X-Api-Key": key})
r = client.get("/v1/merchants/catco.example/catalog").json()
assert r["count"] == 1 and r["items"][0]["sku"] == "NEW-1", r
print("PASS: refresh replaces the cached catalog")


def boom(url):
    raise cat.CatalogError("feed exceeds 1000000 byte cap")


main.catalog.fetch = boom
r = client.post("/v1/merchants/catco.example/catalog/refresh", headers={"X-Api-Key": key})
assert r.status_code == 422 and "byte cap" in r.json()["detail"]["reason"], r.text
print("PASS: feed errors return 422 with reason and advice")

assert client.get("/v1/stats").json()["products_indexed"] == 1
print("PASS: stats reports products_indexed")

print("\nAll catalog tests passed.")
