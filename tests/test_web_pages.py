"""The merchant and registry pages render third-party data in a browser.

Store names, descriptions, product titles and product URLs all arrive from a
merchant's own feed. That makes every one of them attacker-controlled: a store
that puts a <script> tag in a product title, or a javascript: URL in a product
link, must not be able to run code in the page we show to a different merchant.

These tests enforce the two rules that keep that true — text goes in via
textContent, and links are scheme-checked — and unit-test the URL guard in a
real JS engine against hostile input.
"""
import html.parser
import json
import os
import re
import shutil
import subprocess
import sys

import common  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every page under web/ is covered by the structural checks — Ratchet Rule 13 binds
# the whole directory, not just the two pages that happen to fetch merchant data
# today. A future page that renders a store name is exactly the one that would be
# written without remembering the rule.
PAGES = {
    "landing": os.path.join(ROOT, "web", "index.html"),
    "merchant": os.path.join(ROOT, "web", "m", "index.html"),
    "registry": os.path.join(ROOT, "web", "registry", "index.html"),
    "developers": os.path.join(ROOT, "web", "developers", "index.html"),
}
# Only these two read the registry at runtime.
API_PAGES = {k: PAGES[k] for k in ("merchant", "registry")}


class Balanced(html.parser.HTMLParser):
    VOID = {"meta", "br", "link", "img", "hr", "input", "source", "area"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.bad = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            self.bad.append(tag)


for name, path in PAGES.items():
    assert os.path.exists(path), f"{name} page missing at {path}"
    src = open(path, encoding="utf-8").read()
    p = Balanced()
    p.feed(src)
    assert not p.stack, f"{name}: unclosed tags {p.stack}"
    assert not p.bad, f"{name}: mismatched tags {p.bad}"
print("PASS: both pages exist and their markup is balanced")


# --- no HTML-injection sinks anywhere in either page ---
SINKS = ["innerHTML", "outerHTML", "document.write", "insertAdjacentHTML", "eval("]
for name, path in PAGES.items():
    src = open(path, encoding="utf-8").read()
    for sink in SINKS:
        assert sink not in src, (
            f"{name}: uses {sink!r} — merchant-supplied text must only reach the DOM "
            f"via textContent, or a store can inject script into this page"
        )
print("PASS: neither page contains an HTML-injection sink (innerHTML, document.write, eval, …)")


# --- the merchant page must route every merchant-supplied link through the guard ---
merchant_src = open(PAGES["merchant"], encoding="utf-8").read()
assert "safeHref(" in merchant_src, "merchant page must have a URL scheme guard"
hrefs = []
for name, path in PAGES.items():
    hrefs += re.findall(r"\.href\s*=\s*([^;\n]+)", open(path, encoding="utf-8").read())
for h in hrefs:
    h = h.strip()
    ok = (
        h.startswith('"') or h.startswith("'")          # a literal we wrote
        or h.startswith("href")                          # the safeHref result
        or "encodeURIComponent" in h                     # encoded into a literal
        or h.startswith("API")
    )
    assert ok, f"a page assigns an unguarded href: {h!r}"
print("PASS: every href across all pages is a literal, encoded, or passes the scheme guard")


# --- the data-fetching pages must talk to the real registry in production ---
for name, path in API_PAGES.items():
    src = open(path, encoding="utf-8").read()
    assert "https://api.shelfprotocol.com" in src, f"{name}: production API base missing"
    assert "http://localhost:8080" in src, f"{name}: local dev fallback missing"
print("PASS: both pages point at the production registry, with a localhost fallback")


# --- unit-test the URL guard in a real JS engine ---
if not shutil.which("node"):
    print("SKIP: node not installed, can't exercise safeHref directly")
else:
    m = re.search(r"function safeHref\(url\) \{.*?\n  \}", merchant_src, re.S)
    assert m, "could not extract safeHref from the merchant page"
    harness = (
        "global.location = { href: 'https://shelfprotocol.com/m/' };\n"
        + m.group(0)
        + "\nconst cases = " + json.dumps([
            ["https://example.com/p/1", True],
            ["http://example.com/p/1", True],
            ["javascript:alert(document.cookie)", False],
            ["JaVaScRiPt:alert(1)", False],
            ["  javascript:alert(1)", False],
            ["data:text/html,<script>alert(1)</script>", False],
            ["vbscript:msgbox(1)", False],
            ["file:///etc/passwd", False],
            ["", False],
            [None, False],
            ["/relative/path", True],
        ]) + ";\n"
        "let bad = [];\n"
        "for (const [input, shouldPass] of cases) {\n"
        "  const out = safeHref(input);\n"
        "  const passed = out !== null;\n"
        "  if (passed !== shouldPass) bad.push([input, out, shouldPass]);\n"
        "}\n"
        "console.log(JSON.stringify(bad));\n"
    )
    res = subprocess.run([shutil.which("node"), "-e", harness],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    failures = json.loads(res.stdout.strip())
    assert not failures, f"safeHref mishandled: {failures}"
    print("PASS: safeHref accepts http/https, rejects javascript:, data:, vbscript:, file:")


# --- the domain parser must not accept junk ---
if shutil.which("node"):
    m = re.search(r"function getDomain\(\) \{.*?\n  \}", merchant_src, re.S)
    assert m, "could not extract getDomain from the merchant page"
    harness = (
        "global.location = { search: '' };\n"
        "global.URLSearchParams = URLSearchParams;\n"
        + m.group(0).replace("location.search", "SEARCH")
        + "\nconst cases = " + json.dumps([
            ["?d=example.com", "example.com"],
            ["?d=EXAMPLE.COM", "example.com"],
            ["?d=https://example.com/products", "example.com"],
            ["?domain=example.co.uk", "example.co.uk"],
            ["?d=<script>alert(1)</script>", ""],
            ["?d=javascript:alert(1)", ""],
            ["?d=notadomain", ""],
            ["?d=", ""],
            ["", ""],
        ]) + ";\n"
        "let bad = [];\n"
        "for (const [search, expected] of cases) {\n"
        "  global.SEARCH = search;\n"
        "  const out = getDomain();\n"
        "  if (out !== expected) bad.push([search, out, expected]);\n"
        "}\n"
        "console.log(JSON.stringify(bad));\n"
    )
    res = subprocess.run([shutil.which("node"), "-e", harness],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    failures = json.loads(res.stdout.strip())
    assert not failures, f"getDomain mishandled: {failures}"
    print("PASS: getDomain normalizes real domains and rejects script/junk input")

# --- the landing page's store-address box is a user-input surface too ---
if shutil.which("node"):
    landing_src = open(PAGES["landing"], encoding="utf-8").read()
    m = re.search(r'var d = \(input\.value.*?\n    \}', landing_src, re.S)
    assert m, "could not extract the landing page's domain handling"
    # The extracted block ends with a bare `return;` on the reject path, so give
    # that path an explicit value and fall through to ACCEPT.
    body = (m.group(0)
            .replace("input.value", "INPUT")
            .replace("err.textContent =", "ERR =")
            .replace("return;", "return 'REJECT';"))
    harness = (
        "let INPUT, ERR;\nfunction attempt(v){ INPUT = v; ERR = null;\n"
        + body
        + "\n return 'ACCEPT'; }\n"
        "const cases = " + json.dumps([
            ["yourstore.com", "ACCEPT"],
            ["https://www.yourstore.com/products/x", "ACCEPT"],
            ["  GFUEL.COM  ", "ACCEPT"],
            ["<script>alert(1)</script>", "REJECT"],
            ["javascript:alert(1)", "REJECT"],
            ["../../etc/passwd", "REJECT"],
            ["notadomain", "REJECT"],
            ["", "REJECT"],
        ]) + ";\n"
        "let bad=[];\nfor (const [v,exp] of cases){ const got = attempt(v); if (got!==exp) bad.push([v,got,exp]); }\n"
        "console.log(JSON.stringify(bad));\n"
    )
    res = subprocess.run([shutil.which("node"), "-e", harness],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    failures = json.loads(res.stdout.strip())
    assert not failures, f"landing page domain box mishandled: {failures}"
    print("PASS: the landing page's store-address box accepts real domains and rejects junk")


# --- the API must keep returning the shape the pages read ---
# If an endpoint's response shape changes, these pages break silently in a
# browser and nothing else in the suite would notice.
client, main = common.fresh_client()
client.post("/v1/merchants", json={
    "shelf_version": "0.1",
    "merchant": {"name": "Shape Co", "domain": "shapeco.example", "categories": ["food"]},
    "agent_policy": {"agents_allowed": True, "max_autonomous_order_usd": 40},
    "checkout": {"protocol": "manual"},
})
main.db.set_catalog("shapeco.example", [
    {"sku": "S1", "name": "Thing", "description": "", "categories": ["food"],
     "price_usd": 9.5, "url": "https://shapeco.example/s1", "in_stock": True},
])

prof = client.get("/v1/merchants/shapeco.example").json()
for path in [("merchant", "name"), ("trust", "verified_domain"),
             ("agent_policy", "agents_allowed"), ("agent_policy", "max_autonomous_order_usd"),
             ("checkout", "protocol")]:
    cur = prof
    for k in path:
        assert isinstance(cur, dict) and k in cur, f"/m/ reads {'.'.join(path)}, missing from lookup"
        cur = cur[k]

cat = client.get("/v1/merchants/shapeco.example/catalog").json()
assert "items" in cat and cat["items"], cat
for k in ("name", "price_usd", "in_stock", "url"):
    assert k in cat["items"][0], f"/m/ reads item.{k}, missing from catalog"

srch = client.get("/v1/search?limit=100").json()
assert "results" in srch, srch
r0 = srch["results"][0]
for path in [("merchant", "domain"), ("merchant", "name"),
             ("trust", "verified_domain"), ("agent_policy", "max_autonomous_order_usd")]:
    cur = r0
    for k in path:
        assert isinstance(cur, dict) and k in cur, f"/registry/ reads {'.'.join(path)}, missing from search"
        cur = cur[k]

stats = client.get("/v1/stats").json()
for k in ("merchants_indexed", "verified_merchants", "products_indexed", "total_agent_lookups"):
    assert k in stats, f"/registry/ reads stats.{k}, missing"
print("PASS: the API still returns every field the two pages read")

print("\nAll web page tests passed.")
