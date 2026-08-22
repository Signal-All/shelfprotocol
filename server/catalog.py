"""
Fetch and validate merchant catalog feeds (shelf-catalog.json).

The feed URL is merchant-controlled data, so the fetch is treated as hostile:
HTTPS only, publicly routable hosts only, no redirects, 5s timeout, 1MB and
1000-item caps. Set SHELF_CATALOG_FETCH_GUARD=off to relax the scheme/IP
checks for local demos (size and time caps always apply).
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import threading
from urllib.parse import urlparse

import requests

GUARD_ENABLED = os.environ.get("SHELF_CATALOG_FETCH_GUARD", "on").lower() not in ("off", "0", "false")
MAX_BYTES = 1_000_000
MAX_ITEMS = 1000
TIMEOUT_S = 5.0
USER_AGENT = "ShelfProtocolBot/0.1 (+https://shelfprotocol.com)"

# --- DNS-rebinding guard --------------------------------------------------
# _assert_url_safe() resolves the host and checks every IP is public, but a
# plain requests.get() right after it re-resolves DNS independently when it
# opens the connection. A malicious authoritative DNS server for the fed URL's
# host can answer the first lookup with a public IP (passing the guard) and
# the second, moments later, with a private/internal one (TOCTOU bypass).
# We close that window by pinning the exact IP that was validated: patch
# socket.getaddrinfo (which requests/urllib3 calls under the hood via
# socket.create_connection) to return only the pinned IP for that host,
# scoped per-thread so concurrent fetches on other threads are unaffected.
_real_getaddrinfo = socket.getaddrinfo
_pin_local = threading.local()


def _pinned_getaddrinfo(host, *args, **kwargs):
    pin = getattr(_pin_local, "pin", None)
    if pin and pin[0] == host:
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (pin[1], 443))]
    return _real_getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _pinned_getaddrinfo


class CatalogError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _assert_url_safe(url: str):
    """Validate url is safe to fetch, and pin DNS resolution (this thread
    only) to the exact IP just validated, so the connection requests.get()
    opens right after this call can't be rebound to a different address."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise CatalogError("feed_url must be https")
    if parsed.port not in (None, 443):
        raise CatalogError("feed_url must use port 443")
    host = parsed.hostname
    if not host:
        raise CatalogError("feed_url has no host")
    try:
        infos = _real_getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise CatalogError(f"cannot resolve {host}")
    safe_ip = None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # is_global excludes private, loopback, link-local, reserved, multicast.
        if not ip.is_global:
            raise CatalogError(f"{host} resolves to a non-public address")
        safe_ip = safe_ip or info[4][0]
    _pin_local.pin = (host, safe_ip)


def _clear_pin():
    _pin_local.pin = None


def _fetch_pinned(url: str) -> requests.Response:
    """requests.get with the DNS-rebinding guard's error wrapped as CatalogError.
    Caller is responsible for pinning (_assert_url_safe) before and clearing
    (_clear_pin) after, in a finally block."""
    try:
        return requests.get(url, timeout=TIMEOUT_S, allow_redirects=False, stream=True,
                             headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        raise CatalogError(f"fetch failed: {exc.__class__.__name__}")


def fetch(url: str) -> list[dict]:
    """Fetch, size-cap, parse, and validate a feed. Returns cleaned items."""
    if GUARD_ENABLED:
        _assert_url_safe(url)
    try:
        r = _fetch_pinned(url)
    finally:
        if GUARD_ENABLED:
            _clear_pin()
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
    seen_skus: set[str] = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not it.get("sku") or not it.get("name"):
            raise CatalogError(f"item {i}: sku and name are required")
        price = it.get("price_usd", 0)
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
            raise CatalogError(f"item {i}: price_usd must be a non-negative number")
        cats = it.get("categories", [])
        if not isinstance(cats, list):
            raise CatalogError(f"item {i}: categories must be a list")
        sku = str(it["sku"])[:64]
        # Every item needs a unique sku — the products table's primary key is
        # (domain, sku), so a duplicate here would otherwise reach the DB as
        # a bulk insert and fail partway through, after any prior DELETE on
        # a refresh already committed. Reject up front instead of risking a
        # partial write.
        if sku in seen_skus:
            raise CatalogError(f"item {i}: duplicate sku {sku!r} — every item needs a unique sku")
        seen_skus.add(sku)
        cleaned.append({
            "sku": sku,
            "name": str(it["name"])[:200],
            "description": str(it.get("description", ""))[:1000],
            "categories": [str(c)[:64] for c in cats][:10],
            "price_usd": float(price),
            "url": str(it.get("url", ""))[:500],
            "in_stock": bool(it.get("in_stock", True)),
        })
    return cleaned
