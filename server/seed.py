"""
Seed the registry with sample merchants so the demo has something to find.
Run after the server is importable:  python -m server.seed
"""

from .db import DB

SAMPLE_MERCHANTS = [
    {
        "shelf_version": "0.1",
        "merchant": {
            "name": "Acme Coffee Co.",
            "domain": "acme-coffee.example",
            "description": "Specialty roasted coffee beans shipped fresh, plus subscriptions.",
            "categories": ["food.beverages.coffee", "subscriptions"],
            "support_email": "support@acme-coffee.example",
            "country": "US",
        },
        "agent_policy": {
            "agents_allowed": True,
            "max_autonomous_order_usd": 250,
            "requires_human_confirmation_above_usd": 100,
            "returns_window_days": 30,
            "rate_limit_per_min": 60,
        },
        "checkout": {"protocol": "AP2", "endpoint": "https://acme-coffee.example/agent/checkout",
                     "accepts": ["card", "agent_wallet"], "currencies": ["USD"]},
        "catalog": {"feed_url": "https://acme-coffee.example/.well-known/shelf-catalog.json",
                    "item_count": 42, "updated_at": "2026-06-23T00:00:00Z"},
        "trust": {"verified_domain": True, "verification_method": "dns-txt", "reputation_optin": True},
        "_meta": {"lookups": 0},
    },
    {
        "shelf_version": "0.1",
        "merchant": {
            "name": "BeanByte Roasters",
            "domain": "beanbyte.example",
            "description": "Single-origin coffee for developers. API-first ordering.",
            "categories": ["food.beverages.coffee"],
            "support_email": "hi@beanbyte.example",
            "country": "US",
        },
        "agent_policy": {
            "agents_allowed": True,
            "max_autonomous_order_usd": 75,
            "requires_human_confirmation_above_usd": 75,
            "returns_window_days": 14,
            "rate_limit_per_min": 120,
        },
        "checkout": {"protocol": "AP2", "endpoint": "https://beanbyte.example/buy",
                     "accepts": ["agent_wallet"], "currencies": ["USD"]},
        "catalog": {"feed_url": "", "item_count": 8, "updated_at": "2026-06-20T00:00:00Z"},
        "trust": {"verified_domain": True, "verification_method": "dns-txt", "reputation_optin": True},
        "_meta": {"lookups": 0},
    },
    {
        "shelf_version": "0.1",
        "merchant": {
            "name": "GreyMarket Mugs",
            "domain": "greymarket-mugs.example",
            "description": "Cheap mugs. Unverified domain, manual checkout only.",
            "categories": ["home.kitchen.drinkware"],
            "support_email": "",
            "country": "US",
        },
        "agent_policy": {
            "agents_allowed": True,
            "max_autonomous_order_usd": 0,
            "requires_human_confirmation_above_usd": 0,
            "returns_window_days": 0,
            "rate_limit_per_min": 30,
        },
        "checkout": {"protocol": "manual", "endpoint": "", "accepts": ["card"], "currencies": ["USD"]},
        "catalog": {"feed_url": "", "item_count": 100, "updated_at": "2026-01-01T00:00:00Z"},
        "trust": {"verified_domain": False, "verification_method": "dns-txt", "reputation_optin": False},
        "_meta": {"lookups": 0},
    },
]


def run():
    db = DB()
    for m in SAMPLE_MERCHANTS:
        db.upsert(m["merchant"]["domain"], m)
    print(f"Seeded {len(SAMPLE_MERCHANTS)} merchants. Total indexed: {db.count()}")


if __name__ == "__main__":
    run()
