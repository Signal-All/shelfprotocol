# OpenShelf Spec v0.1 — "robots.txt for commerce"

OpenShelf is an **open standard** that lets any merchant describe itself to AI
agents, and lets any agent reliably discover what a merchant sells, what it
costs, and what the agent is allowed to do — without scraping a website.

There are two parts:

1. **`shelf.json`** — a file a merchant hosts at `https://<domain>/.well-known/shelf.json`.
   This is the source of truth, owned by the merchant. (Analogous to `robots.txt`.)
2. **The OpenShelf Registry** — a hosted index that crawls/accepts `shelf.json`
   files, verifies them, and serves fast lookups + search to agents. Agents that
   don't want to fetch each domain individually just query the registry.

An agent's first call before transacting with a merchant is:

```
GET https://api.openshelf.dev/v1/merchants/{domain}
```

If the merchant is listed, the agent gets a clean, structured, machine-readable
profile. If not, the agent treats the merchant as "unknown / unverified."

---

## The `shelf.json` format

```json
{
  "shelf_version": "0.1",
  "merchant": {
    "name": "Acme Coffee Co.",
    "domain": "acme-coffee.example",
    "description": "Specialty roasted coffee beans shipped fresh.",
    "categories": ["food.beverages.coffee", "subscriptions"],
    "support_email": "support@acme-coffee.example",
    "country": "US"
  },
  "agent_policy": {
    "agents_allowed": true,
    "max_autonomous_order_usd": 250,
    "requires_human_confirmation_above_usd": 100,
    "returns_window_days": 30,
    "rate_limit_per_min": 60
  },
  "checkout": {
    "protocol": "AP2",
    "endpoint": "https://acme-coffee.example/agent/checkout",
    "accepts": ["card", "agent_wallet"],
    "currencies": ["USD"]
  },
  "catalog": {
    "feed_url": "https://acme-coffee.example/.well-known/shelf-catalog.json",
    "item_count": 42,
    "updated_at": "2026-06-23T00:00:00Z"
  },
  "trust": {
    "verified_domain": false,
    "verification_method": "dns-txt",
    "reputation_optin": true
  }
}
```

### Field notes

- **`agent_policy`** is the part agents care about most. It tells an agent the
  ceiling it can spend autonomously and when it must stop and ask a human. This
  is the single biggest unlock — it removes the #1 blocker (trust/safety) by
  letting the *merchant* declare the rules of engagement.
- **`checkout.protocol`** names the commerce protocol the merchant speaks
  (AP2, UCP, or `manual`). Agents skip merchants whose protocol they can't use.
- **`catalog.feed_url`** points to an optional product feed (same idea, larger
  file) so agents can match a user's request to real SKUs.
- **`trust.verified_domain`** is set by the Registry after a DNS-TXT or
  file-based ownership check. Agents can require `verified_domain: true` for
  higher-value purchases.

---

## Domain verification (how merchants prove ownership)

To get `verified_domain: true`, a merchant adds a DNS TXT record:

```
_openshelf.<domain>  TXT  "openshelf-verify=<token>"
```

The Registry checks this asynchronously. Verified merchants rank higher in
search and are eligible for autonomous (no-human) purchases.

### Unclaimed listings and claiming

The Registry may index merchants from public data (e.g. a store's public
product feed) before the merchant ever registers. Such listings are marked
`"claimed": false` and are deliberately inert: `verified_domain` is false and
`max_autonomous_order_usd` is 0, so no agent can spend anything autonomously.

The merchant takes ownership with `POST /v1/merchants/{domain}/claim`, which
issues credentials, and the claim completes only when the DNS TXT check above
passes. Until then the listing cannot be edited — a claimant who cannot edit
DNS for the domain can never control its listing.

---

## Catalog feeds (how agents find actual products)

A merchant can go beyond its profile and publish its products in a
`shelf-catalog.json` feed hosted at the URL declared in `catalog.feed_url`
(conventionally `https://<domain>/.well-known/shelf-catalog.json`):

```json
{
  "catalog_version": "0.1",
  "domain": "acme-coffee.example",
  "updated_at": "2026-07-04T00:00:00Z",
  "items": [
    {
      "sku": "ACME-ESP-12OZ",
      "name": "Espresso Blend, 12oz whole bean",
      "description": "Dark roast espresso blend.",
      "categories": ["food.beverages.coffee"],
      "price_usd": 18.5,
      "url": "https://acme-coffee.example/products/espresso-blend",
      "in_stock": true
    }
  ]
}
```

`sku` and `name` are required per item; everything else is optional. Feeds are
capped at 1000 items and 1MB.

The Registry crawls and caches the feed when the merchant calls
`POST /v1/merchants/{domain}/catalog/refresh` (authenticated with the
registration api_key). The fetch enforces HTTPS to a publicly routable host,
follows no redirects, and validates every item. Agents then query the cache:
`GET /v1/merchants/{domain}/catalog` for one merchant, or `GET /v1/products?q=`
to search products across all merchants.

See `spec/shelf-catalog.json.example` for a complete feed.

---

## Why this self-adopts

- **Merchants publish** because being absent means being invisible to AI
  shoppers. Pure FOMO, no sales call needed.
- **Developers wire in one lookup** because it's cheaper and more reliable than
  scraping. One line of code, dropped into a framework template, spreads by
  copy-paste.
- **The registry compounds**: more merchants → agents prefer it → more
  developers depend on it → more merchants join to stay visible.

This document is intentionally permissive. Fork it, extend it, embed it. The
goal is for `shelf.json` to become as boring and universal as `robots.txt`.
