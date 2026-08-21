"""
Shelf Protocol Registry API
=======================
The hosted index for the Shelf Protocol standard. Merchants register their
`shelf.json`; agents look merchants up by domain or search by category/product.

Run:
    pip install fastapi uvicorn
    uvicorn server.main:app --reload --port 8080

Then open http://localhost:8080/docs for the interactive API.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from typing import Optional

import dns.exception
import dns.resolver
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import catalog, ratelimit
from .db import DB

# Set SHELF_DNS_CHECK=off to skip the DNS TXT lookup in /verify — for local
# demos with reserved TLDs (.example) that can never resolve. Defaults to on.
DNS_CHECK_ENABLED = os.environ.get("SHELF_DNS_CHECK", "on").lower() not in ("off", "0", "false")
DNS_LOOKUP_TIMEOUT_S = 5.0

app = FastAPI(
    title="Shelf Protocol Registry",
    version="0.1.0",
    description="robots.txt for commerce — the directory agents query before they buy.",
)

db = DB()

limiter = ratelimit.RateLimiter()


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if ratelimit.ENABLED and request.url.path.startswith("/v1/"):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            kind, limit = "write", ratelimit.WRITES_PER_MIN
        else:
            kind, limit = "read", ratelimit.READS_PER_MIN
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check(client_ip, kind, limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "detail": {
                        "error": "rate_limited",
                        "limit_per_min": limit,
                        "retry_after_seconds": retry_after,
                    }
                },
            )
    return await call_next(request)


# ---------- Schemas (mirror the shelf.json spec) ----------

class Merchant(BaseModel):
    name: str
    domain: str
    description: str = ""
    categories: list[str] = []
    support_email: str = ""
    country: str = "US"


class AgentPolicy(BaseModel):
    agents_allowed: bool = True
    max_autonomous_order_usd: float = 0
    requires_human_confirmation_above_usd: float = 0
    returns_window_days: int = 0
    rate_limit_per_min: int = 60


class Checkout(BaseModel):
    protocol: str = "manual"          # AP2 | UCP | manual
    endpoint: str = ""
    accepts: list[str] = []
    currencies: list[str] = ["USD"]


class Catalog(BaseModel):
    feed_url: str = ""
    item_count: int = 0
    updated_at: str = ""


class ShelfDoc(BaseModel):
    shelf_version: str = "0.1"
    merchant: Merchant
    agent_policy: AgentPolicy = Field(default_factory=AgentPolicy)
    checkout: Checkout = Field(default_factory=Checkout)
    catalog: Catalog = Field(default_factory=Catalog)


class RegisterResponse(BaseModel):
    domain: str
    status: str
    verification_token: str
    verification_dns_record: str
    api_key: str
    message: str


# ---------- Endpoints ----------

@app.get("/", tags=["meta"])
def root():
    return {
        "service": "Shelf Protocol Registry",
        "version": "0.1.0",
        "spec": "robots.txt for commerce",
        "merchants_indexed": db.count(),
        "rate_limits": (
            {"reads_per_min": ratelimit.READS_PER_MIN, "writes_per_min": ratelimit.WRITES_PER_MIN}
            if ratelimit.ENABLED else "disabled"
        ),
        "endpoints": {
            "register": "POST /v1/merchants",
            "claim": "POST /v1/merchants/{domain}/claim (take ownership of an imported listing)",
            "update": "PUT /v1/merchants/{domain} (X-Api-Key)",
            "lookup": "GET /v1/merchants/{domain}",
            "search": "GET /v1/search?q=&category=&protocol=&verified=",
            "verify": "POST /v1/merchants/{domain}/verify (checks the _shelfprotocol DNS TXT record)",
            "catalog_refresh": "POST /v1/merchants/{domain}/catalog/refresh (crawls your shelf-catalog.json)",
            "catalog": "GET /v1/merchants/{domain}/catalog?q=",
            "products": "GET /v1/products?q=&category=&verified=&in_stock=",
            "stats": "GET /v1/stats",
        },
    }


@app.post("/v1/merchants", response_model=RegisterResponse, tags=["merchant"])
def register_merchant(doc: ShelfDoc):
    """A merchant publishes its shelf.json to the registry. Free, no approval gate."""
    domain = doc.merchant.domain.lower().strip()
    if not domain or "." not in domain:
        raise HTTPException(400, "merchant.domain must be a valid domain")

    existing = db.get(domain)
    if existing:
        if not existing.get("_meta", {}).get("claimed", True):
            raise HTTPException(
                409,
                "domain is already indexed but unclaimed — POST /v1/merchants/{domain}/claim to take ownership",
            )
        raise HTTPException(
            409,
            "domain already registered — use PUT /v1/merchants/{domain} with your X-Api-Key to update your listing",
        )

    token = "shelfprotocol-verify=" + secrets.token_urlsafe(16)
    api_key = "osk_" + secrets.token_urlsafe(24)
    record = doc.model_dump()
    record["trust"] = {
        "verified_domain": False,
        "verification_method": "dns-txt",
        "reputation_optin": True,
    }
    record["_meta"] = {
        "registered_at": time.time(),
        "verification_token": token,
        "api_key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
        "lookups": 0,
        "claimed": True,
    }
    db.upsert(domain, record)

    return RegisterResponse(
        domain=domain,
        status="indexed",
        verification_token=token,
        verification_dns_record=f'_shelfprotocol.{domain}  TXT  "{token}"',
        api_key=api_key,
        message="Indexed. Add the DNS TXT record then POST /verify to get verified_domain:true.",
    )


@app.post("/v1/merchants/{domain}/claim", response_model=RegisterResponse, tags=["merchant"])
def claim_merchant(domain: str):
    """
    Start claiming an imported (unclaimed) listing. Issues credentials; the
    claim completes only when /verify proves domain ownership via DNS TXT.
    Calling claim again before verifying rotates the pending credentials —
    only the real domain owner can ever finish, so rotation is harmless.
    """
    domain = domain.lower().strip()
    record = db.get(domain)
    if not record:
        raise HTTPException(404, "domain not indexed — register it with POST /v1/merchants")
    if record.get("_meta", {}).get("claimed", True):
        raise HTTPException(409, "listing already claimed — its owner manages it with their api_key")

    token = "shelfprotocol-verify=" + secrets.token_urlsafe(16)
    api_key = "osk_" + secrets.token_urlsafe(24)

    def apply(current: dict) -> dict:
        meta = current.setdefault("_meta", {})
        meta["verification_token"] = token
        meta["api_key_hash"] = hashlib.sha256(api_key.encode()).hexdigest()
        meta["claim_requested_at"] = time.time()
        return current

    db.transform(domain, apply)
    return RegisterResponse(
        domain=domain,
        status="claim_pending",
        verification_token=token,
        verification_dns_record=f'_shelfprotocol.{domain}  TXT  "{token}"',
        api_key=api_key,
        message="Add the DNS TXT record then POST /verify to complete the claim and get verified_domain:true.",
    )


@app.put("/v1/merchants/{domain}", tags=["merchant"])
def update_merchant(
    domain: str,
    doc: ShelfDoc,
    x_api_key: str = Header(..., description="api_key returned at registration"),
):
    """
    Update your listing. Replaces the merchant-declared parts (merchant,
    agent_policy, checkout, catalog.feed_url); registry-owned state (trust,
    verification, lookup counters) is preserved. The domain itself is immutable.
    """
    domain = domain.lower().strip()
    record = db.get(domain)
    if not record:
        raise HTTPException(404, "merchant not registered")
    stored_hash = record.get("_meta", {}).get("api_key_hash", "")
    if hashlib.sha256(x_api_key.encode()).hexdigest() != stored_hash:
        raise HTTPException(401, "invalid api_key")
    if not record.get("_meta", {}).get("claimed", True):
        raise HTTPException(403, "claim is pending — complete DNS verification (POST /verify) before editing the listing")
    body_domain = doc.merchant.domain.lower().strip()
    if body_domain and body_domain != domain:
        raise HTTPException(400, "merchant.domain is immutable — register the new domain instead")

    def apply(current: dict) -> dict:
        updated = doc.model_dump()
        updated["merchant"]["domain"] = domain
        updated["trust"] = current["trust"]
        updated["_meta"] = current["_meta"]
        # item_count/updated_at are registry-owned: set by /catalog/refresh, not the merchant.
        old_catalog = current.get("catalog", {})
        updated["catalog"]["item_count"] = old_catalog.get("item_count", 0)
        updated["catalog"]["updated_at"] = old_catalog.get("updated_at", "")
        return updated

    updated = db.transform(domain, apply)
    return {"domain": domain, "status": "updated", "verified_domain": updated["trust"]["verified_domain"]}


def _public(record: dict) -> dict:
    """Strip registry-internal state (credential hash, tokens, counters) from
    a record before returning it to agents; surface only the claimed flag."""
    view = {k: v for k, v in record.items() if k != "_meta"}
    view["claimed"] = bool(record.get("_meta", {}).get("claimed", True))
    return view


@app.get("/v1/merchants/{domain}", tags=["agent"])
def lookup_merchant(domain: str):
    """THE call an agent makes before transacting. Returns the merchant's agent profile."""
    domain = domain.lower().strip()
    record = db.get(domain)
    if not record:
        raise HTTPException(
            status_code=404,
            detail={
                "domain": domain,
                "status": "unknown",
                "advice": "Merchant not in Shelf Protocol. Treat as unverified.",
            },
        )
    db.bump_lookup(domain)
    return _public(record)


def _dns_txt_has_token(domain: str, token: str) -> tuple[bool, str]:
    """Return whether `_shelfprotocol.<domain>` publishes a TXT record equal to token."""
    qname = f"_shelfprotocol.{domain}"
    resolver = dns.resolver.Resolver()
    resolver.lifetime = DNS_LOOKUP_TIMEOUT_S
    try:
        answers = resolver.resolve(qname, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False, f"no TXT record found at {qname}"
    except dns.resolver.NoNameservers:
        return False, f"no nameserver could answer for {qname}"
    except dns.exception.DNSException as exc:
        return False, f"DNS lookup for {qname} failed: {exc.__class__.__name__}"

    found = [b"".join(rdata.strings).decode("utf-8", "replace") for rdata in answers]
    if token in found:
        return True, "token matched"
    return False, f"TXT record(s) at {qname} do not contain the expected verification token"


@app.post("/v1/merchants/{domain}/verify", tags=["merchant"])
def verify_merchant(domain: str, x_api_key: str = Header(..., description="api_key returned at registration")):
    """
    Confirm domain ownership. Requires the api_key issued at registration, then
    checks that `_shelfprotocol.<domain>` publishes a TXT record with the
    verification token. Set SHELF_DNS_CHECK=off to skip the DNS lookup for
    local demos (.example domains can never resolve).
    """
    domain = domain.lower().strip()
    record = db.get(domain)
    if not record:
        raise HTTPException(404, "merchant not registered")
    stored_hash = record.get("_meta", {}).get("api_key_hash", "")
    if hashlib.sha256(x_api_key.encode()).hexdigest() != stored_hash:
        raise HTTPException(401, "invalid api_key")

    if DNS_CHECK_ENABLED:
        token = record.get("_meta", {}).get("verification_token", "")
        if not token:
            raise HTTPException(409, "no verification token on file — re-register to get one")
        ok, why = _dns_txt_has_token(domain, token)
        if not ok:
            raise HTTPException(
                422,
                {
                    "domain": domain,
                    "verified_domain": False,
                    "reason": why,
                    "expected_record": f'_shelfprotocol.{domain}  TXT  "{token}"',
                    "advice": "Add the TXT record, wait for DNS propagation, then retry.",
                },
            )

    def apply(current: dict) -> dict:
        current["trust"]["verified_domain"] = True
        meta = current.setdefault("_meta", {})
        meta["verified_at"] = time.time()
        meta["claimed"] = True
        return current

    db.transform(domain, apply)
    return {"domain": domain, "verified_domain": True, "claimed": True, "method": "dns-txt"}


@app.post("/v1/merchants/{domain}/catalog/refresh", tags=["merchant"])
def refresh_catalog(domain: str, x_api_key: str = Header(..., description="api_key returned at registration")):
    """
    Crawl and cache the merchant's shelf-catalog.json from catalog.feed_url.
    The fetch is guarded: HTTPS to a public host only, no redirects, 5s/1MB caps.
    """
    domain = domain.lower().strip()
    record = db.get(domain)
    if not record:
        raise HTTPException(404, "merchant not registered")
    stored_hash = record.get("_meta", {}).get("api_key_hash", "")
    if hashlib.sha256(x_api_key.encode()).hexdigest() != stored_hash:
        raise HTTPException(401, "invalid api_key")
    if not record.get("_meta", {}).get("claimed", True):
        raise HTTPException(403, "claim is pending — complete DNS verification (POST /verify) before managing the catalog")
    feed_url = record.get("catalog", {}).get("feed_url", "")
    if not feed_url:
        raise HTTPException(400, "no catalog.feed_url in your shelf.json — update your listing first")

    try:
        items = catalog.fetch(feed_url)
    except catalog.CatalogError as exc:
        raise HTTPException(
            422,
            {"domain": domain, "feed_url": feed_url, "reason": exc.reason,
             "advice": "Fix the feed and retry. See spec/shelf-catalog.json.example."},
        )

    db.set_catalog(domain, items)

    def apply(current: dict) -> dict:
        current.setdefault("catalog", {})["item_count"] = len(items)
        current["catalog"]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return current

    db.transform(domain, apply)
    return {"domain": domain, "items_indexed": len(items)}


@app.get("/v1/merchants/{domain}/catalog", tags=["agent"])
def get_catalog(
    domain: str,
    q: Optional[str] = Query(None, description="free-text match on name/description/categories"),
    limit: int = 100,
):
    """Serve a merchant's cached catalog items."""
    domain = domain.lower().strip()
    if not db.get(domain):
        raise HTTPException(404, "merchant not registered")
    items = db.get_catalog(domain, q=q, limit=limit)
    return {"domain": domain, "count": len(items), "items": items}


@app.get("/v1/products", tags=["agent"])
def search_products(
    q: Optional[str] = Query(None, description="free-text match on name/description/categories"),
    category: Optional[str] = None,
    verified: Optional[bool] = Query(None, description="only products from verified merchants"),
    in_stock: Optional[bool] = Query(None, description="only in-stock products"),
    limit: int = 20,
):
    """Search cached products across all merchants. Verified merchants rank first."""
    results = db.search_products(
        q=q, category=category, verified=verified, in_stock=in_stock, limit=limit
    )
    return {"count": len(results), "results": results}


@app.get("/v1/search", tags=["agent"])
def search(
    q: Optional[str] = Query(None, description="free-text match on name/description/categories"),
    category: Optional[str] = None,
    protocol: Optional[str] = Query(None, description="AP2 | UCP | manual"),
    verified: Optional[bool] = Query(None, description="only verified merchants"),
    max_order_usd: Optional[float] = Query(None, description="merchant allows autonomous orders >= this"),
    limit: int = 20,
):
    """Agents call this to find candidate merchants for a user's request."""
    results = db.search(
        q=q, category=category, protocol=protocol,
        verified=verified, max_order_usd=max_order_usd, limit=limit,
    )
    return {"count": len(results), "results": [_public(r) for r in results]}


@app.get("/v1/stats", tags=["meta"])
def stats():
    return db.stats()
