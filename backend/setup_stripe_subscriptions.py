"""One-time setup script: create Stripe Products and recurring Prices for Kindred subscription tiers.

Run this ONCE to initialize your Stripe catalog, then copy the printed
environment variables into your Railway / .env configuration.

Usage:
    STRIPE_API_KEY=sk_live_... python setup_stripe_subscriptions.py
"""

import os
import sys

import stripe

stripe.api_key = os.environ.get("STRIPE_API_KEY", "")

if not stripe.api_key:
    print("ERROR: Set STRIPE_API_KEY environment variable first.")
    sys.exit(1)

TIERS = [
    {
        "id": "sapling",
        "name": "Kindred Sapling",
        "description": "Growing communities — up to 25 members. Unlimited subyards, event templates, RSVP management.",
        "monthly_cents": 999,
        "annual_cents": 8999,
    },
    {
        "id": "oak",
        "name": "Kindred Oak",
        "description": "Mid-size communities — up to 50 members. Travel coordination, shared funds, priority support.",
        "monthly_cents": 1999,
        "annual_cents": 17999,
    },
    {
        "id": "redwood",
        "name": "Kindred Redwood",
        "description": "Large communities — up to 100 members. Analytics, custom branding, multi-admin controls.",
        "monthly_cents": 3999,
        "annual_cents": 35999,
    },
]


def main():
    env_lines = []
    print("\n=== Creating Stripe Products & Recurring Prices for Kindred ===\n")

    for tier in TIERS:
        # Create product
        product = stripe.Product.create(
            name=tier["name"],
            description=tier["description"],
            metadata={"kindred_tier": tier["id"]},
        )
        print(f"  Created product: {product.id} — {tier['name']}")

        # Monthly recurring price
        monthly_price = stripe.Price.create(
            product=product.id,
            unit_amount=tier["monthly_cents"],
            currency="usd",
            recurring={"interval": "month"},
            metadata={"kindred_tier": tier["id"], "billing_cycle": "monthly"},
        )
        env_key_monthly = f"STRIPE_PRICE_{tier['id'].upper()}_MONTHLY"
        env_lines.append(f"{env_key_monthly}={monthly_price.id}")
        print(f"    Monthly price: {monthly_price.id} (${tier['monthly_cents']/100:.2f}/mo)")

        # Annual recurring price
        annual_price = stripe.Price.create(
            product=product.id,
            unit_amount=tier["annual_cents"],
            currency="usd",
            recurring={"interval": "year"},
            metadata={"kindred_tier": tier["id"], "billing_cycle": "annual"},
        )
        env_key_annual = f"STRIPE_PRICE_{tier['id'].upper()}_ANNUAL"
        env_lines.append(f"{env_key_annual}={annual_price.id}")
        print(f"    Annual price:  {annual_price.id} (${tier['annual_cents']/100:.2f}/yr)")

    print("\n=== Add these environment variables to Railway / .env ===\n")
    for line in env_lines:
        print(f"  {line}")
    print()


if __name__ == "__main__":
    main()
