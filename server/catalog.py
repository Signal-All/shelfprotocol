"""
Fetch and validate merchant catalog feeds (shelf-catalog.json).

The feed URL is merchant-controlled data, so the fetch is treated as hostile:
HTTPS only, publicly routable hosts only, no redirects, 5s timeout, 1MB and
1000-item caps. Set OPENSHELF_CATALOG_FETCH_GUARD=off to relax the scheme/IP
checks for local demos (size and time caps always apply).
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from urllib.parse import urlparse

import requests

GUARD_ENABLED = os.environ.get("OPENSHELF_CATALOG_FETCH_GUARD", "on").lower() not in ("off", "0", "false")
MAX_BYTES = 1_000_000
MAX_ITEMS = 1000
TIMEOUT_S = 5.0


class CatalogError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _assert_url_safe(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise CatalogError("feed_url must be https")
    if parsed.port not in (None, 443):
        raise CatalogError("feed_url must use port 443")
    host = parsed.hostname
    if not host:
        raise CatalogError("feed_url has no host")
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise CatalogError(f"cannot resolve {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # is_global excludes private, loopback, link-local, reserved, multicast.
        if not ip.is_global:
            raise CatalogError(f"{host} resolves to a non-public address")


def fetch(url: str) -> list[dict]:
    """Fetch, size-cap, parse, and validate a feed. Returns cleaned items."""
    if GUARD_ENABLED:
        _assert_url_safe(url)
    try:
        r = requests.get(url, timeout=TIMEOUT_S, allow_redirects=False, stream=True)
    except requests.RequestException as exc:
        raise CatalogError(f"fetch failed: {exc.__class__.__name__}")
    if r.status_code != 200:
        raise CatalogError(f"feed returned HTTP {r.status_code} (redirects are not followed)")
    body = b""
    for chunk in r.iter_content(65536):
        body += chunk
        if len(body) > MAX_BYTES:
            raise CatalogError(f"feed exceeds {MAX_BYTES} byte cap")
    try:
        doc = json.loads(body)
    except ValueError:
        raise CatalogError("feed is not valid JSON")
    return validate(doc)


def validate(doc) -> list[dict]:
    if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
        raise CatalogError('feed must be a JSON object with an "items" array')
    items = doc["items"]
    if len(items) > MAX_ITEMS:
        raise CatalogError(f"feed exceeds {MAX_ITEMS} item cap")
    cleaned = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not it.get("sku") or not it.get("name"):
            raise CatalogError(f"item {i}: sku and name are required")
        price = it.get("price_usd", 0)
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
            raise CatalogError(f"item {i}: price_usd must be a non-negative number")
        cats = it.get("categories", [])
        if not isinstance(cats, list):
            raise CatalogError(f"item {i}: categories must be a list")
        cleaned.append({
            "sku": str(it["sku"])[:64],
            "name": str(it["name"])[:200],
            "description": str(it.get("description", ""))[:1000],
            "categories": [str(c)[:64] for c in cats][:10],
            "price_usd": float(price),
            "url": str(it.get("url", ""))[:500],
            "in_stock": bool(it.get("in_stock", True)),
        })
    return cleaned
