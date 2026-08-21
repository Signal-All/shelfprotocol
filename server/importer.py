"""
Seed the registry with unclaimed listings from public Shopify product feeds.

Usage:
    python -m server.importer domains.txt [--limit N]

domains.txt: one store domain per line (comments with #). For each domain the
importer checks robots.txt, fetches the public /products.json feed (same SSRF
guard and size caps as the catalog crawler), and creates a conservative
UNCLAIMED listing: discoverable, agents_allowed, but max_autonomous_order_usd
0 and verified_domain false — no agent can spend anything until the merchant
claims the listing (POST /claim) and proves ownership via DNS (POST /verify).
Existing records are never touched.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.robotparser

import requests

from . import catalog
from .db import DB

FEED_PATH = "/products.json?limit=250"
MAX_CATEGORIES = 5


def _robots_allows(domain: str) -> bool:
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = requests.get(f"https://{domain}/robots.txt", timeout=catalog.TIMEOUT_S,
                         headers={"User-Agent": catalog.USER_AGENT})
        if r.status_code >= 400:
            return True  # no robots.txt — crawling public endpoints is allowed
        rp.parse(r.text.splitlines())
    except requests.RequestException:
        return False  # unreachable host — skip rather than guess
    return rp.can_fetch(catalog.USER_AGENT, f"https://{domain}/products.json")


def _fetch_json(url: str):
    if catalog.GUARD_ENABLED:
        catalog._assert_url_safe(url)
    try:
        r = requests.get(url, timeout=catalog.TIMEOUT_S, allow_redirects=False, stream=True,
                         headers={"User-Agent": catalog.USER_AGENT})
    finally:
        if catalog.GUARD_ENABLED:
            catalog._clear_pin()
    if r.status_code != 200:
        raise catalog.CatalogError(f"HTTP {r.status_code}")
    body = b""
    for chunk in r.iter_content(65536):
        body += chunk
        if len(body) > catalog.MAX_BYTES:
            raise catalog.CatalogError("feed exceeds byte cap")
    return json.loads(body)


def _to_items(domain: str, products: list[dict]) -> list[dict]:
    items = []
    for p in products[:catalog.MAX_ITEMS]:
        variants = p.get("variants") or [{}]
        v = variants[0]
        sku = v.get("sku") or str(p.get("id", ""))
        if not sku or not p.get("title"):
            continue
        try:
            price = float(v.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        items.append({
            "sku": sku,
            "name": p["title"],
            "description": (p.get("body_html") or "")[:1000],
            "categories": [c for c in [p.get("product_type", "")] + (p.get("tags") or [])[:MAX_CATEGORIES] if c],
            "price_usd": max(price, 0.0),
            "url": f"https://{domain}/products/{p.get('handle', '')}",
            "in_stock": any(bool(x.get("available", True)) for x in variants),
        })
    return catalog.validate({"items": items})


def _store_name(domain: str, products: list[dict]) -> str:
    vendors = [p.get("vendor") for p in products if p.get("vendor")]
    if vendors:
        return max(set(vendors), key=vendors.count)
    return domain.split(".")[0].replace("-", " ").title()


def import_domain(db: DB, domain: str) -> str:
    domain = domain.lower().strip()
    if db.get(domain):
        return "skipped (already indexed)"
    if not _robots_allows(domain):
        return "skipped (robots.txt or unreachable)"
    feed_url = f"https://{domain}{FEED_PATH}"
    try:
        doc = _fetch_json(feed_url)
    except (catalog.CatalogError, ValueError) as exc:
        return f"skipped ({exc})"
    products = doc.get("products") or []
    if not products:
        return "skipped (no products)"
    try:
        items = _to_items(domain, products)
    except catalog.CatalogError as exc:
        return f"skipped (invalid items: {exc.reason})"

    record = {
        "shelf_version": "0.1",
        "merchant": {
            "name": _store_name(domain, products),
            "domain": domain,
            "description": "Imported from the store's public product feed. Unclaimed listing.",
            "categories": sorted({c for it in items for c in it["categories"]})[:10],
            "support_email": "",
            "country": "US",
        },
        "agent_policy": {
            "agents_allowed": True,
            "max_autonomous_order_usd": 0,
            "requires_human_confirmation_above_usd": 0,
            "returns_window_days": 0,
            "rate_limit_per_min": 60,
        },
        "checkout": {"protocol": "manual", "endpoint": "", "accepts": [], "currencies": ["USD"]},
        "catalog": {
            "feed_url": f"https://{domain}/products.json",
            "item_count": len(items),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "trust": {"verified_domain": False, "verification_method": "dns-txt", "reputation_optin": False},
        "_meta": {"claimed": False, "imported_at": time.time(),
                  "source": "shopify-products-json", "lookups": 0},
    }
    db.upsert(domain, record)
    db.set_catalog(domain, items)
    return f"imported ({len(items)} items)"


def run(path: str, limit: int = 0):
    db = DB()
    with open(path) as f:
        domains = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if limit:
        domains = domains[:limit]
    for d in domains:
        print(f"{d}: {import_domain(db, d)}")
    print(f"\nDone. Total indexed: {db.count()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m server.importer domains.txt [--limit N]")
    n = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    run(sys.argv[1], n)
