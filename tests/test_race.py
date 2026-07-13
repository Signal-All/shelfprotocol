"""Lost-update protection: updates racing verify must never drop verified_domain."""
import threading

import common  # noqa: F401

client, main = common.fresh_client()

body = {
    "merchant": {"name": "Race Co", "domain": "raceco.example", "categories": ["x"]},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 50},
}
key = client.post("/v1/merchants", json=body).json()["api_key"]

errors = []


def updater(i):
    b = dict(body, agent_policy={"agents_allowed": True, "max_autonomous_order_usd": 50 + i})
    r = client.put("/v1/merchants/raceco.example", json=b, headers={"X-Api-Key": key})
    if r.status_code != 200:
        errors.append(r.text)


def verifier():
    r = client.post("/v1/merchants/raceco.example/verify", headers={"X-Api-Key": key})
    if r.status_code != 200:
        errors.append(r.text)


threads = [threading.Thread(target=updater, args=(i,)) for i in range(50)]
threads.insert(25, threading.Thread(target=verifier))
for t in threads:
    t.start()
for t in threads:
    t.join()
assert not errors, errors[:3]

prof = client.get("/v1/merchants/raceco.example").json()
assert prof["trust"]["verified_domain"] is True, "lost update: verification was clobbered"
meta = main.db.get("raceco.example")["_meta"]
assert meta.get("verified_at"), "verified_at missing"
assert meta.get("api_key_hash"), "api_key_hash lost"
print("PASS: 50 concurrent updates + 1 verify — verified_domain and _meta survive")

before = main.db.get("raceco.example")["_meta"].get("lookups", 0)


def looker():
    client.get("/v1/merchants/raceco.example")


def upd():
    client.put("/v1/merchants/raceco.example", json=body, headers={"X-Api-Key": key})


threads = [threading.Thread(target=looker) for _ in range(30)] + [threading.Thread(target=upd) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
after = main.db.get("raceco.example")["_meta"]["lookups"]
assert after >= before + 30, (before, after)
print(f"PASS: lookup counter intact under concurrent updates ({before} -> {after})")

print("\nAll race tests passed.")
