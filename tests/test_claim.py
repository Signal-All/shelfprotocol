"""Unclaimed listings: import, claim lifecycle, 403 gates, _meta stripping."""
import common  # noqa: F401

from server import importer  # noqa: E402

client, main = common.fresh_client()

SHOPIFY_FEED = {"products": [
    {"id": 111, "title": "Pour Over Kit", "handle": "pour-over", "vendor": "Brew Bros",
     "product_type": "coffee-gear", "tags": ["gear"], "body_html": "<p>Nice kit</p>",
     "variants": [{"sku": "BB-PO-1", "price": "39.00", "available": True}]},
    {"id": 222, "title": "Filter Papers", "handle": "filters", "vendor": "Brew Bros",
     "product_type": "coffee-gear", "tags": [],
     "variants": [{"sku": "", "price": "6.50", "available": False}]},
]}
importer._robots_allows = lambda domain: True
importer._fetch_json = lambda url: SHOPIFY_FEED

status = importer.import_domain(main.db, "brewbros.example")
assert status == "imported (2 items)", status
assert importer.import_domain(main.db, "brewbros.example") == "skipped (already indexed)"
print("PASS: importer creates listing from Shopify feed, never clobbers existing")

prof = client.get("/v1/merchants/brewbros.example").json()
assert prof["claimed"] is False
assert prof["merchant"]["name"] == "Brew Bros"
assert prof["trust"]["verified_domain"] is False
assert prof["agent_policy"]["max_autonomous_order_usd"] == 0
assert "_meta" not in prof, "public lookup must not leak _meta"
print("PASS: imported listing is unclaimed, inert, and public view has no _meta")

from shelfprotocol import can_buy  # noqa: E402

ok, why = can_buy(prof, amount_usd=5)
assert not ok, why
print("PASS: can_buy refuses the unclaimed listing")

r = client.get("/v1/products", params={"q": "pour over"}).json()
assert r["count"] == 1 and r["results"][0]["domain"] == "brewbros.example"
print("PASS: imported products are searchable")

r = client.post("/v1/merchants/brewbros.example/claim")
assert r.status_code == 200 and r.json()["status"] == "claim_pending", r.text
key = r.json()["api_key"]

upd = {"merchant": {"name": "Brew Bros Official", "domain": "brewbros.example", "categories": ["coffee-gear"]},
       "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 100}}
r = client.put("/v1/merchants/brewbros.example", json=upd, headers={"X-Api-Key": key})
assert r.status_code == 403 and "claim is pending" in r.text, (r.status_code, r.text)
r = client.post("/v1/merchants/brewbros.example/catalog/refresh", headers={"X-Api-Key": key})
assert r.status_code == 403, (r.status_code, r.text)
print("PASS: claim-pending credentials cannot edit listing or catalog (403)")

key2 = client.post("/v1/merchants/brewbros.example/claim").json()["api_key"]
assert client.put("/v1/merchants/brewbros.example", json=upd, headers={"X-Api-Key": key}).status_code == 401
print("PASS: re-claim rotates pending credentials (old key now 401)")

r = client.post("/v1/merchants/brewbros.example/verify", headers={"X-Api-Key": key2})
assert r.status_code == 200 and r.json()["claimed"] is True, r.text
r = client.put("/v1/merchants/brewbros.example", json=upd, headers={"X-Api-Key": key2})
assert r.status_code == 200, r.text
prof = client.get("/v1/merchants/brewbros.example").json()
assert prof["claimed"] is True and prof["merchant"]["name"] == "Brew Bros Official"
assert prof["trust"]["verified_domain"] is True
print("PASS: verify completes claim; owner can now edit; verification retained")

assert client.post("/v1/merchants/brewbros.example/claim").status_code == 409
print("PASS: claimed listings cannot be re-claimed")

importer.import_domain(main.db, "other.example")
reg = {"merchant": {"name": "X", "domain": "other.example", "categories": ["x"]}, "agent_policy": {"agents_allowed": True}}
r = client.post("/v1/merchants", json=reg)
assert r.status_code == 409 and "/claim" in r.text, r.text
reg["merchant"]["domain"] = "brewbros.example"
r = client.post("/v1/merchants", json=reg)
assert r.status_code == 409 and "PUT /v1/merchants" in r.text, r.text
print("PASS: 409 messages route to claim vs update correctly")

reg["merchant"]["domain"] = "fresh.example"
key3 = client.post("/v1/merchants", json=reg).json()["api_key"]
upd["merchant"]["domain"] = "fresh.example"
assert client.put("/v1/merchants/fresh.example", json=upd, headers={"X-Api-Key": key3}).status_code == 200
print("PASS: self-registered listings remain editable pre-verification (claimed at birth)")

r = client.get("/v1/search", params={"q": "brew"}).json()
assert r["count"] >= 1 and all("_meta" not in m for m in r["results"])
assert all("claimed" in m for m in r["results"])
print("PASS: search results strip _meta and surface claimed flag")

# Real-world data quality: a merchant feed with two products sharing the
# same sku (messy inventory data, not a malformed feed) must never create a
# merchant record with catalog metadata that doesn't match reality — a live
# production import once did exactly this and left a ghost listing claiming
# items that were never actually written.
DUPLICATE_SKU_FEED = {"products": [
    {"id": 1, "title": "Mug", "handle": "mug", "vendor": "Messy Co",
     "product_type": "kitchen", "tags": [], "variants": [{"sku": "SAME", "price": "10.00", "available": True}]},
    {"id": 2, "title": "Plate", "handle": "plate", "vendor": "Messy Co",
     "product_type": "kitchen", "tags": [], "variants": [{"sku": "SAME", "price": "8.00", "available": True}]},
]}
importer._fetch_json = lambda url: DUPLICATE_SKU_FEED
status = importer.import_domain(main.db, "messyco.example")
assert status.startswith("skipped"), status
assert main.db.get("messyco.example") is None, "duplicate-sku import must not create a merchant record"
print("PASS: importer skips cleanly on duplicate skus, never leaves a ghost merchant record")

print("\nAll claim-flow tests passed.")
