"""PUT /v1/merchants/{domain}: auth, state preservation, immutability, rate bucket."""
import os

os.environ["OPENSHELF_RATE_LIMIT"] = "on"
os.environ["OPENSHELF_RATE_LIMIT_WRITES_PER_MIN"] = "6"
os.environ["OPENSHELF_RATE_LIMIT_READS_PER_MIN"] = "100"
import common  # noqa: E402

client, main = common.fresh_client()

body = {
    "merchant": {"name": "Upd Co", "domain": "updco.example", "categories": ["coffee"]},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 50},
    "checkout": {"protocol": "AP2", "endpoint": "https://updco.example/checkout"},
    "catalog": {"feed_url": "https://updco.example/.well-known/shelf-catalog.json"},
}
key = client.post("/v1/merchants", json=body).json()["api_key"]              # write 1
client.post("/v1/merchants/updco.example/verify", headers={"X-Api-Key": key})  # write 2


def fake_crawl(current):
    current["catalog"]["item_count"] = 7
    current["catalog"]["updated_at"] = "2026-07-04T00:00:00Z"
    current["_meta"]["lookups"] = 3
    return current


main.db.transform("updco.example", fake_crawl)

new_body = dict(body, agent_policy={"agents_allowed": True, "max_autonomous_order_usd": 200})
r = client.put("/v1/merchants/updco.example", json=new_body, headers={"X-Api-Key": "osk_wrong"})  # write 3
assert r.status_code == 401, r.text
assert client.put("/v1/merchants/ghost.example", json=new_body, headers={"X-Api-Key": key}).status_code == 404  # write 4
print("PASS: 401 on bad key, 404 on unknown domain")

r = client.put("/v1/merchants/updco.example", json=new_body, headers={"X-Api-Key": key})  # write 5
assert r.status_code == 200 and r.json()["verified_domain"] is True, r.text
prof = client.get("/v1/merchants/updco.example").json()
assert prof["agent_policy"]["max_autonomous_order_usd"] == 200
assert prof["trust"]["verified_domain"] is True
assert prof["catalog"]["item_count"] == 7 and prof["catalog"]["updated_at"] == "2026-07-04T00:00:00Z"
meta = main.db.get("updco.example")["_meta"]
assert meta["lookups"] >= 3 and meta["api_key_hash"]
print("PASS: fields updated; trust, catalog counters, and _meta preserved")

assert client.put("/v1/merchants/updco.example", json=new_body, headers={"X-Api-Key": key}).status_code == 200  # write 6
print("PASS: api_key still valid after update")

bad = dict(new_body)
bad["merchant"] = dict(new_body["merchant"], domain="hijack.example")
r = client.put("/v1/merchants/updco.example", json=bad, headers={"X-Api-Key": key})  # write 7
assert r.status_code == 429, (r.status_code, r.text)
print("PASS: PUT is counted in the write rate bucket (7th write -> 429)")

main.limiter._counts.clear()
main.limiter._current_window = 0
r = client.put("/v1/merchants/updco.example", json=bad, headers={"X-Api-Key": key})
assert r.status_code == 400 and "immutable" in r.text, (r.status_code, r.text)
print("PASS: domain change rejected as immutable")

r = client.post("/v1/merchants", json=body)
assert r.status_code == 409 and "PUT /v1/merchants/{domain}" in r.text, r.text
print("PASS: 409 message references PUT endpoint")

print("\nAll update-endpoint tests passed.")
