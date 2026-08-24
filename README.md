# Shelf Protocol

**robots.txt for commerce.** The open directory AI agents query before they buy.

Merchants publish a tiny `shelf.json` describing what they sell and what agents
are allowed to do. Agents make one lookup before transacting. Shelf Protocol is the
index in the middle — the handshake layer between agents and the commercial web.

```
agent  ──lookup──▶  Shelf Protocol Registry  ◀──publish──  merchant
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
| `sdk/shelfprotocol/` | The one-line lookup client a developer drops into an agent, plus the MCP server and the LangChain/CrewAI tool adapters. Pip-installable (`pyproject.toml` at repo root). |
| `demo/demo_agent.py` | A shopping agent that uses Shelf Protocol to decide what it's allowed to buy. |
| `web/index.html` | Developer landing page. |
| `tests/` | Test suites (`cd tests && for t in test_*.py; do python3 $t; done`). |

## Run it locally (90 seconds)

```bash
cd shelfprotocol
pip install -r server/requirements.txt

# 1. start the registry
python -m uvicorn server.main:app --port 8080
#    interactive API docs at http://localhost:8080/docs

# 2. in another terminal, seed sample merchants
python -m server.seed

# 3. run the demo agent against it
SHELF_URL=http://localhost:8080 python demo/demo_agent.py
```

You'll watch an agent query Shelf Protocol, get back verified merchants, and either
buy autonomously (within the merchant's declared limit) or escalate to a human.

> **Note:** SQLite stores its file next to `server/db.py` by default. If you run
> on a network/mounted drive that errors with `disk I/O error`, set a local
> path: `export SHELF_DB=/tmp/shelf.sqlite`.

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
export SHELF_API_KEY=osk_...   # the api_key from the registration response

curl -X POST http://localhost:8080/v1/merchants/acme-coffee.example/verify \
  -H "X-Api-Key: $SHELF_API_KEY"
```

To change your listing later (limits, checkout endpoint, feed URL — anything
except the domain itself), send the same body to `PUT /v1/merchants/<domain>`
with your `X-Api-Key` header. Verification status survives updates.

`PUT` is a full replace of the merchant-declared fields, not a partial patch —
first `GET /v1/merchants/<domain>` to see your current listing, edit the
field(s) you want to change, then `PUT` the whole thing back. This matters
most if you're editing a listing you didn't originally register yourself (see
Seeding & claiming below) — you won't know its current `checkout`/`catalog`
values otherwise, and a `PUT` that omits them clears them.

The registry looks up `_shelfprotocol.<domain>` in DNS and confirms the TXT record
carries your verification token. On success it flips `trust.verified_domain` to
`true`, which is required before `can_buy()` will allow an agent to purchase
autonomously (see below).

> **Local demo:** `.example` domains can never resolve in real DNS. Start the
> server with `SHELF_DNS_CHECK=off` to skip the TXT lookup (the api_key
> check still applies).

## Rate limits

The registry rate-limits per client IP on `/v1/*`: **120 reads/min** (lookup,
search, stats) and **10 writes/min** (register, verify). Exceeding a limit
returns `429` with a `Retry-After` header. Tune with
`SHELF_RATE_LIMIT_READS_PER_MIN` / `SHELF_RATE_LIMIT_WRITES_PER_MIN`,
or disable for local demos and tests with `SHELF_RATE_LIMIT=off`.

## Seeding & claiming (solving the empty registry)

The registry can pre-index stores from their public product feeds:

```bash
python -m server.importer domains.txt   # one store domain per line
```

Imported listings are **unclaimed**: discoverable in search, but inert —
`verified_domain: false` and a $0 autonomous ceiling, so `can_buy()` refuses
them. A merchant takes ownership of its listing with:

```bash
curl -X POST http://localhost:8080/v1/merchants/acme-coffee.example/claim
```

That returns an api_key and a DNS record; the claim completes when the
`/verify` DNS check passes. Until then the listing can't be edited, so a
claimant who doesn't control the domain's DNS can never control its listing.

## Catalog feeds (products, not just merchants)

Publishing a catalog is two steps: declare a `catalog.feed_url` when you
register (as in the example above), and host a `shelf-catalog.json` file at
that URL (copy `spec/shelf-catalog.json.example` as a starting point). Then
ask the registry to crawl it:

```bash
curl -X POST http://localhost:8080/v1/merchants/acme-coffee.example/catalog/refresh \
  -H "X-Api-Key: $SHELF_API_KEY"
```

The fetch is guarded (HTTPS to a public host only, no redirects, 5s timeout,
1MB / 1000-item caps; `SHELF_CATALOG_FETCH_GUARD=off` relaxes the
scheme/IP checks for local demos). Every item also needs a unique `sku` and
a `name`, a non-negative `price_usd`, and a `categories` list if present —
if any item fails validation (including two items sharing a `sku`, a real
data-quality issue Shopify feeds sometimes have), the whole refresh is
rejected with `422` and a `reason` explaining exactly what's wrong and
which item, rather than silently dropping or guessing at bad data. Agents
then query the cache:

```python
from shelfprotocol import catalog, products

catalog("acme-coffee.example", q="decaf")   # one merchant's items
products(q="espresso", verified=True)       # across all merchants, verified first
```

## The one line developers add

```bash
pip install shelfprotocol
```

```python
from shelfprotocol import lookup, can_buy

profile = lookup("acme-coffee.example")
ok, why = can_buy(profile, amount_usd=40)   # honors the merchant's declared limits
```

Defaults to the hosted registry at `api.shelfprotocol.com`; point at a
self-hosted one with `SHELF_URL`.

## Use it from any MCP client

```bash
pip install "shelfprotocol[mcp]"
```

```json
{
  "mcpServers": {
    "shelfprotocol": { "command": "shelfprotocol-mcp" }
  }
}
```

Exposes `lookup`, `search`, `can_buy`, `catalog`, and `products` as tools —
add this to Claude Desktop, Claude Code, or any other MCP client and it can
check the registry before buying anything, without writing any code.

The MCP tool's `can_buy(domain, amount_usd)` is stricter than the raw SDK's
`can_buy(profile, amount_usd, require_verified=True)`: it has no
`require_verified` argument at all, so a manipulated prompt can never talk
an agent into skipping domain verification through this tool. Code you write
yourself can still opt out deliberately with the SDK function directly.

## Use it from LangChain or CrewAI

```bash
pip install "shelfprotocol[langchain]"     # or: "shelfprotocol[crewai]"
```

```python
from langchain.agents import create_agent
from shelfprotocol.langchain_tools import get_tools

agent = create_agent(model, tools=get_tools())
```

```python
from crewai import Agent
from shelfprotocol.crewai_tools import get_tools

buyer = Agent(role="Purchasing agent", goal="...", tools=get_tools())
```

Both give the agent the same five tools as the MCP server — `shelf_lookup`,
`shelf_search`, `shelf_can_buy`, `shelf_catalog`, `shelf_products` — so it can
find merchants, read their catalogs, and check a purchase against the
merchant's declared limits before spending anything.

Names carry a `shelf_` prefix because framework tool lists are flat and
unnamespaced, and a bare `search` or `products` will collide with the web-search
tool most agent stacks already carry. Pass `get_tools(prefix="")` for the bare
names if you know yours won't clash.

`shelf_can_buy` is hardened the same way the MCP tool is: no `require_verified`
argument exists on it, so a manipulated prompt cannot talk the agent into
skipping domain verification. Deliberate opt-out stays available in code you
write yourself, via the SDK's `can_buy()` directly.

> **Note:** `crewai` pins `mcp~=1.28`, which contradicts the `[mcp]` extra's
> `mcp>=2.0`, so `pip install "shelfprotocol[mcp,crewai]"` fails to resolve.
> That's intentional — the alternative is pip quietly backtracking `crewai` to
> a years-old release that these adapters were never tested against. Either
> extra alone installs fine, and you don't need both: the CrewAI adapter and
> the MCP server are two routes to the same tools.

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
