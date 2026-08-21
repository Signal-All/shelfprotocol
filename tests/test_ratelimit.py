"""Rate limiting: read/write limits, 429 shape, off-switch, window reset."""
import importlib
import os

os.environ["SHELF_RATE_LIMIT"] = "on"
os.environ["SHELF_RATE_LIMIT_READS_PER_MIN"] = "5"
os.environ["SHELF_RATE_LIMIT_WRITES_PER_MIN"] = "3"
import common  # noqa: E402

client, main = common.fresh_client()
from server import ratelimit  # noqa: E402

codes = [client.get("/v1/search?q=coffee").status_code for _ in range(6)]
assert codes == [200] * 5 + [429], codes
r = client.get("/v1/search")
assert "retry-after" in {k.lower() for k in r.headers}, r.headers
body = r.json()["detail"]
assert body["error"] == "rate_limited" and body["limit_per_min"] == 5, body
print("PASS: reads capped at 5/min, 429 carries Retry-After + structured detail")

reg = {"merchant": {"name": "T", "domain": "rl-test.example", "categories": ["x"]},
       "agent_policy": {"agents_allowed": True}}
w_codes = []
for i in range(4):
    reg["merchant"]["domain"] = f"rl-{i}.example"
    w_codes.append(client.post("/v1/merchants", json=reg).status_code)
assert w_codes == [200, 200, 200, 429], w_codes
print("PASS: writes capped independently at 3/min")

r = client.get("/")
assert r.status_code == 200
assert r.json()["rate_limits"] == {"reads_per_min": 5, "writes_per_min": 3}
print("PASS: / is exempt and advertises the limits")

main.limiter._counts.clear()
main.limiter._current_window = 0
assert client.get("/v1/search").status_code == 200
print("PASS: fresh window admits requests again")

os.environ["SHELF_RATE_LIMIT"] = "off"
importlib.reload(ratelimit)
assert ratelimit.ENABLED is False
codes = [client.get("/v1/search").status_code for _ in range(10)]
assert all(c == 200 for c in codes), codes
print("PASS: SHELF_RATE_LIMIT=off disables limiting entirely")

print("\nAll rate-limit tests passed.")
