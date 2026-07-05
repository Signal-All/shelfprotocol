# OpenShelf

**robots.txt for commerce.** The open directory AI agents query before they buy.

Merchants publish a tiny `shelf.json` describing what they sell and what agents
are allowed to do. Agents make one lookup before transacting. OpenShelf is the
index in the middle — the handshake layer between agents and the commercial web.

```
agent  ──lookup──▶  OpenShelf Registry  ◀──publish──  merchant
        "can I buy here, and how?"        "here's my shelf.json"
```

## Why it self-adopts (no sales motion)

- **Merchants publish** to avoid being invisible to AI shoppers. FOMO, not a sales call.
- **Developers add one lookup** because it's cheaper and safer than scraping. One line, spreads by copy-paste.
- **The index compounds**: more merchants → agents prefer it → more developers depend on it → more merchants join.

## What's in this repo

| Path | What it is |
|------|------------|
| `spec/SPEC.md` | The open standard. The `shelf.json` format + verification. |
| `spec/shelf.json.example` | A sample merchant file. |
| `server/` | The registry API (FastAPI + SQLite). Register, lookup, search, verify, stats. |
| `sdk/openshelf.py` | The one-line lookup client a developer drops into an agent. |
| `demo/demo_agent.py` | A shopping agent that uses OpenShelf to decide what it's allowed to buy. |
| `web/index.html` | Developer landing page. |

## Run it locally (90 seconds)

```bash
cd openshelf
pip install -r server/requirements.txt

# 1. start the registry
python -m uvicorn server.main:app --port 8080
#    interactive API docs at http://localhost:8080/docs

# 2. in another terminal, seed sample merchants
python -m server.seed

# 3. run the demo agent against it
OPENSHELF_URL=http://localhost:8080 python demo/demo_agent.py
```

You'll watch an agent query OpenShelf, get back verified merchants, and either
buy autonomously (within the merchant's declared limit) or escalate to a human.

> **Note:** SQLite stores its file next to `server/db.py` by default. If you run
> on a network/mounted drive that errors with `disk I/O error`, set a local
> path: `export OPENSHELF_DB=/tmp/openshelf.sqlite`.

## Register a merchant

`POST /v1/merchants` with a `shelf.json` body (see `spec/shelf.json.example` for the full schema):

```bash
curl -X POST http://localhost:8080/v1/merchants \
  -H "Content-Type: application/json" \
  -d '{
    "merchant": {
      "name": "Acme Coffee Co.",
      "domain": "acme-coffee.example",
      "categories": ["food.beverages.coffee"]
    },
    "agent_policy": {
      "agents_allowed": true,
      "max_autonomous_order_usd": 250
    },
    "checkout": {
      "protocol": "AP2",
      "endpoint": "https://acme-coffee.example/agent/checkout"
    },
    "catalog": {
      "feed_url": "https://acme-coffee.example/.well-known/shelf-catalog.json"
    }
  }'
```

The response includes an `api_key` (save it — shown only once) and a `verification_dns_record` to add to your DNS. Once the TXT record is live, confirm ownership with:

```bash
export OPENSHELF_API_KEY=osk_...   # the api_key from the registration response

curl -X POST http://localhost:8080/v1/merchants/acme-coffee.example/verify \
  -H "X-Api-Key: $OPENSHELF_API_KEY"
```

To change your listing later (limits, checkout endpoint, feed URL — anything
except the domain itself), send the same body to `PUT /v1/merchants/<domain>`
with your `X-Api-Key` header. Verification status survives updates.

The registry looks up `_openshelf.<domain>` in DNS and confirms the TXT record
carries your verification token. On success it flips `trust.verified_domain` to
`true`, which is required before `can_buy()` will allow an agent to purchase
autonomously (see below).

> **Local demo:** `.example` domains can never resolve in real DNS. Start the
> server with `OPENSHELF_DNS_CHECK=off` to skip the TXT lookup (the api_key
> check still applies).

## Rate limits

The registry rate-limits per client IP on `/v1/*`: **120 reads/min** (lookup,
search, stats) and **10 writes/min** (register, verify). Exceeding a limit
returns `429` with a `Retry-After` header. Tune with
`OPENSHELF_RATE_LIMIT_READS_PER_MIN` / `OPENSHELF_RATE_LIMIT_WRITES_PER_MIN`,
or disable for local demos and tests with `OPENSHELF_RATE_LIMIT=off`.

## Catalog feeds (products, not just merchants)

Publishing a catalog is two steps: declare a `catalog.feed_url` when you
register (as in the example above), and host a `shelf-catalog.json` file at
that URL (copy `spec/shelf-catalog.json.example` as a starting point). Then
ask the registry to crawl it:

```bash
curl -X POST http://localhost:8080/v1/merchants/acme-coffee.example/catalog/refresh \
  -H "X-Api-Key: $OPENSHELF_API_KEY"
```

The fetch is guarded (HTTPS to a public host only, no redirects, 5s timeout,
1MB / 1000-item caps; `OPENSHELF_CATALOG_FETCH_GUARD=off` relaxes the
scheme/IP checks for local demos). Agents then query the cache:

```python
from openshelf import catalog, products

catalog("acme-coffee.example", q="decaf")   # one merchant's items
products(q="espresso", verified=True)       # across all merchants, verified first
```

## The one line developers add

```python
from openshelf import lookup, can_buy

profile = lookup("acme-coffee.example")
ok, why = can_buy(profile, amount_usd=40)   # honors the merchant's declared limits
```

## How it makes money

1. **Free tier** — registration and lookups are free. This is how you get scale.
2. **Verified listings** — merchants pay for a verified badge that lets agents
   buy from them autonomously (higher conversion). This is the first revenue.
3. **Metered API** — charge per lookup/search above a free threshold, the way
   Stripe/Twilio/AWS meter usage. Grows automatically with agent traffic.
4. **Enterprise** — priority placement, richer data fields, private catalogs,
   reputation data feeds for big retailers and payment networks.

No step requires a sales team. Revenue scales with the number of agents in the
world, which is the bet.

## The roadmap that turns this into a moat

- **v0 (this repo):** the spec + registry + SDK + demo. Prove the loop.
- **v1:** hosted API. (Real DNS-TXT verification, rate limiting, product-catalog feeds: done.)
- **v2:** a *reputation* layer — log transaction outcomes, score merchants. Once
  agents check reputation before buying, the data itself becomes the moat.
- **v3:** become the default lookup baked into agent frameworks (LangChain,
  CrewAI, AutoGen). One integration seeds thousands of silent adoptions.

## Honest risk

If Google, Anthropic, or Shopify ships their own version and bakes it into their
platform, the window narrows. Speed and openness (so it feels like a neutral
standard, not a vendor product) are the defenses. Move fast; publish the spec
publicly; get into a framework template early.
