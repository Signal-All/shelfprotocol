"""Delisting: removal is unconditional, atomic, and survives the next importer run.

The point of these tests is the promise made in the README — that a merchant who
asks to be removed stays removed. A delete that the importer undoes on its next
pass is not a removal, so the suppression half is tested as hard as the delete.
"""
import common  # noqa: F401

from server import importer  # noqa: E402

client, main = common.fresh_client()
db = main.db

SHELF = {
    "shelf_version": "0.1",
    "merchant": {"name": "Delist Co", "domain": "delistco.example",
                 "categories": ["food.beverages.coffee"]},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 50},
    "checkout": {"protocol": "manual"},
    "catalog": {"feed_url": "https://delistco.example/shelf-catalog.json"},
}

# --- a listed merchant can be delisted, record and products both gone ---
r = client.post("/v1/merchants", json=SHELF)
assert r.status_code == 200, r.text
assert db.get("delistco.example") is not None
db.set_catalog("delistco.example", [
    {"sku": "A1", "name": "Beans", "description": "", "categories": ["coffee"],
     "price_usd": 12.0, "url": "https://delistco.example/a1", "in_stock": True},
])
assert db.get_catalog("delistco.example"), "catalog should be populated before delisting"

existed = db.delist("delistco.example", "asked by email")
assert existed is True
assert db.get("delistco.example") is None, "merchant record must be gone"
assert db.get_catalog("delistco.example") == [], "cached products must be gone too"
assert client.get("/v1/merchants/delistco.example").status_code == 404
print("PASS: delist removes the merchant record and its cached products")

# --- and it is remembered ---
assert db.is_delisted("delistco.example") is True
assert db.is_delisted("someoneelse.example") is False
print("PASS: delisting is recorded, and doesn't leak to other domains")

# --- case/whitespace can't be used to slip past the suppression list ---
assert db.is_delisted("  DelistCo.Example  ") is True
print("PASS: suppression lookup normalizes case and whitespace")


# --- the importer must refuse a delisted domain, without touching the network ---
calls = []
importer._robots_allows = lambda d: (calls.append(d), True)[1]
importer._fetch_json = lambda url: (_ for _ in ()).throw(
    AssertionError("importer fetched a delisted domain's feed")
)

result = importer.import_domain(db, "delistco.example")
assert "delisted" in result, result
assert calls == [], "delisted domains must be rejected before any outbound request"
assert db.get("delistco.example") is None
print("PASS: importer skips a delisted domain and makes no network call doing it")


# --- delisting a domain that was never listed still suppresses it ---
existed = db.delist("neverlisted.example")
assert existed is False
assert db.is_delisted("neverlisted.example") is True
result = importer.import_domain(db, "neverlisted.example")
assert "delisted" in result, result
print("PASS: pre-emptive delisting works for a domain that was never indexed")


# --- registering voluntarily clears the suppression (opting back in) ---
r = client.post("/v1/merchants", json=SHELF)
assert r.status_code == 200, r.text
assert db.is_delisted("delistco.example") is False, (
    "a domain that registers itself has opted back in; suppression must not persist"
)
assert db.get("delistco.example") is not None
print("PASS: voluntary re-registration clears the suppression entry")


# --- suppression blocks the bulk importer, not the owner ---
db.delist("delistco.example")
assert db.get("delistco.example") is None
r = client.post("/v1/merchants", json=SHELF)
assert r.status_code == 200, "the owner must always be able to opt back in"
print("PASS: delisting never locks a real owner out of their own domain")

# --- the opt-back-in must be atomic: one lock acquisition, not two ---
# A delist landing between the write and the un-suppress would leave the domain
# deleted but no longer suppressed — re-importable, which is the exact outcome
# this feature exists to prevent.
import inspect
src = inspect.getsource(main.register_merchant)
assert "clear_suppression=True" in src, (
    "register_merchant must clear suppression inside the upsert's lock"
)
assert "db.relist(" not in src, (
    "register_merchant must not call relist separately — that reintroduces the window"
)
db.delist("atomic.example")
rec = dict(SHELF)
rec["merchant"] = {**SHELF["merchant"], "domain": "atomic.example"}
r = client.post("/v1/merchants", json=rec)
assert r.status_code == 200, r.text
assert db.is_delisted("atomic.example") is False
assert db.get("atomic.example") is not None
print("PASS: opt-back-in clears suppression atomically, not as a second write")

print("\nAll delist tests passed.")
