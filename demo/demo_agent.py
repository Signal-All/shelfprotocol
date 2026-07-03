"""
Demo: a shopping agent that uses OpenShelf before it buys.

This simulates exactly the moment OpenShelf monetizes: a user tells an agent to
buy something, and the agent's FIRST move is to query OpenShelf to (a) find
merchants and (b) check whether it's allowed to buy autonomously.

Run (with the server running on :8080):
    OPENSHELF_URL=http://localhost:8080 python demo/demo_agent.py
"""

import os
import sys

# make the sdk importable when run from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from openshelf import search, lookup, can_buy  # noqa: E402

BASE = os.environ.get("OPENSHELF_URL", "http://localhost:8080")


def banner(text):
    print("\n" + "=" * 64)
    print(text)
    print("=" * 64)


def shop(user_request: str, budget_usd: float):
    banner(f'USER: "{user_request}"  (budget ${budget_usd:.2f})')

    # 1. Agent's first call: find candidate merchants via OpenShelf.
    print("[agent] querying OpenShelf for coffee merchants...")
    candidates = search(category="coffee", base_url=BASE)
    print(f"[agent] OpenShelf returned {len(candidates)} candidate merchant(s).")

    # 2. Agent ranks by trust + policy, picks the best it's allowed to use.
    for c in candidates:
        m = c["merchant"]
        profile = lookup(m["domain"], base_url=BASE)
        ok, reason = can_buy(profile, amount_usd=budget_usd, require_verified=True)
        verified = "verified" if profile.get("trust", {}).get("verified_domain") else "UNVERIFIED"
        protocol = profile.get("checkout", {}).get("protocol", "manual")
        print(f"\n  - {m['name']:<22} [{verified}, {protocol}]")
        print(f"      decision: {'BUY' if ok else 'SKIP'} — {reason}")
        if ok:
            print(f"\n[agent] ✅ Proceeding to checkout with {m['name']} via {protocol}.")
            print(f"[agent]    endpoint: {profile['checkout']['endpoint']}")
            return m["domain"]

    print("\n[agent] ❌ No merchant met the safety bar. Escalating to human.")
    return None


if __name__ == "__main__":
    # Case 1: small order — should auto-buy from a verified, AP2 merchant.
    shop("Order me a bag of coffee", budget_usd=40)

    # Case 2: order above every merchant's autonomous ceiling — agent must escalate.
    shop("Stock the office with $400 of coffee", budget_usd=400)

    banner("Why this is the business")
    print(
        "Every BUY decision above started with a call to OpenShelf.\n"
        "Merchants list themselves to be found; agents can't safely buy without\n"
        "the lookup. That call is the toll booth — and it grows with every new\n"
        "agent a developer ships, with zero sales effort."
    )
