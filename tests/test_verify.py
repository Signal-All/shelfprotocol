"""DNS-TXT verification: stubbed-DNS positive/negative paths + demo-mode skip."""
import os

os.environ["OPENSHELF_DNS_CHECK"] = "on"
import common  # noqa: E402

client, main = common.fresh_client()

body = {
    "merchant": {"name": "T", "domain": "shop.example", "categories": ["x"]},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 50},
}
r = client.post("/v1/merchants", json=body)
assert r.status_code == 200, r.text
key = r.json()["api_key"]
token = r.json()["verification_token"]


class FakeRdata:
    def __init__(self, s):
        self.strings = [s.encode()]


class FakeResolver:
    answers = []

    def resolve(self, qname, rtype):
        assert qname == "_openshelf.shop.example", qname
        assert rtype == "TXT"
        return self.answers


main.dns.resolver.Resolver = FakeResolver
main.DNS_CHECK_ENABLED = True

FakeResolver.answers = [FakeRdata("openshelf-verify=WRONG")]
r = client.post("/v1/merchants/shop.example/verify", headers={"X-Api-Key": key})
assert r.status_code == 422, (r.status_code, r.text)
assert "do not contain the expected" in r.text
print("PASS: wrong token -> 422")

FakeResolver.answers = [FakeRdata("unrelated=1"), FakeRdata(token)]
r = client.post("/v1/merchants/shop.example/verify", headers={"X-Api-Key": key})
assert r.status_code == 200, (r.status_code, r.text)
prof = client.get("/v1/merchants/shop.example").json()
assert prof["trust"]["verified_domain"] is True
assert "verified_at" in main.db.get("shop.example")["_meta"]
print("PASS: matching token -> verified_domain true, verified_at stamped")

main.DNS_CHECK_ENABLED = False
body["merchant"]["domain"] = "demo.example"
key2 = client.post("/v1/merchants", json=body).json()["api_key"]


def boom(*a, **k):
    raise AssertionError("DNS must not be queried when check is off")


FakeResolver.resolve = boom
r = client.post("/v1/merchants/demo.example/verify", headers={"X-Api-Key": key2})
assert r.status_code == 200, (r.status_code, r.text)
print("PASS: DNS check off skips DNS, still requires api_key")

r = client.post("/v1/merchants/demo.example/verify", headers={"X-Api-Key": "osk_nope"})
assert r.status_code == 401
print("PASS: demo mode still 401s on bad api_key")

print("\nAll verify-flow tests passed.")
