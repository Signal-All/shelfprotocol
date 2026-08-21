"""
Shelf Protocol SDK — the one line of code a developer adds to an agent.

    from shelfprotocol import lookup, search, can_buy

    profile = lookup("acme-coffee.example")
    ok, reason = can_buy(profile, amount_usd=40)

This is intentionally tiny. The whole point is that adopting Shelf Protocol costs a
developer almost nothing — drop it in once, every agent they build inherits it.
"""

from __future__ import annotations

import os
from typing import Optional

import requests

BASE_URL = os.environ.get("SHELF_URL", "https://api.shelfprotocol.com")
TIMEOUT = float(os.environ.get("SHELF_TIMEOUT", "5"))


def lookup(domain: str, base_url: str = None) -> Optional[dict]:
    """Return a merchant's agent profile, or None if it isn't in the registry."""
    base = base_url or BASE_URL
    try:
        r = requests.get(f"{base}/v1/merchants/{domain}", timeout=TIMEOUT)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def search(q: str = None, category: str = None, protocol: str = None,
           verified: bool = None, base_url: str = None) -> list[dict]:
    """Find candidate merchants for a user's request."""
    base = base_url or BASE_URL
    params = {k: v for k, v in {
        "q": q, "category": category, "protocol": protocol, "verified": verified
    }.items() if v is not None}
    try:
        r = requests.get(f"{base}/v1/search", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("results", [])
    except requests.RequestException:
        return []


def catalog(domain: str, q: str = None, base_url: str = None) -> list[dict]:
    """Return a merchant's cached catalog items, optionally filtered by q."""
    base = base_url or BASE_URL
    params = {"q": q} if q else {}
    try:
        r = requests.get(f"{base}/v1/merchants/{domain}/catalog", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("items", [])
    except requests.RequestException:
        return []


def products(q: str = None, category: str = None, verified: bool = None,
             in_stock: bool = None, base_url: str = None) -> list[dict]:
    """Search products across all merchants. Verified merchants rank first."""
    base = base_url or BASE_URL
    params = {k: v for k, v in {
        "q": q, "category": category, "verified": verified, "in_stock": in_stock
    }.items() if v is not None}
    try:
        r = requests.get(f"{base}/v1/products", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("results", [])
    except requests.RequestException:
        return []


def can_buy(profile: dict, amount_usd: float, require_verified: bool = True) -> tuple[bool, str]:
    """
    Decide whether an agent may autonomously purchase from this merchant.
    Returns (allowed, human_readable_reason).

    This encodes the safety contract: the *merchant* declares its limits in
    shelf.json, and the agent honors them. That's what makes autonomous buying
    safe enough to actually happen.
    """
    if not profile:
        return False, "Merchant not in Shelf Protocol registry — unknown/unverified."

    policy = profile.get("agent_policy", {})
    trust = profile.get("trust", {})

    if not policy.get("agents_allowed", False):
        return False, "Merchant does not allow agent purchases."

    if require_verified and not trust.get("verified_domain", False):
        return False, "Merchant domain is not verified — refusing autonomous purchase."

    ceiling = policy.get("max_autonomous_order_usd", 0) or 0
    if amount_usd > ceiling:
        return False, (
            f"${amount_usd:.2f} exceeds merchant's autonomous ceiling of "
            f"${ceiling:.2f} — escalate to human confirmation."
        )

    return True, f"OK: ${amount_usd:.2f} is within the ${ceiling:.2f} autonomous limit."
