"""One-time setup script: create Stripe Products and recurring Prices for Kindred subscription tiers.

Run this ONCE to initialize your Stripe catalog, then copy the printed
environment variables into your Railway / .env configuration.

Usage:
    STRIPE_API_KEY=sk_live_... python setup_stripe_subscriptions.py
"""

import os
import sys

import stripe
from pricing import (
    BILLING_ENVIRONMENT,
    PAID_TIER_IDS,
    SUBSCRIPTION_TIERS,
    price_cents,
    stripe_api_key_matches_environment,
)

stripe.api_key = os.environ.get("STRIPE_API_KEY", "")

if not stripe_api_key_matches_environment(stripe.api_key):
    print(f"ERROR: STRIPE_API_KEY does not match BILLING_ENVIRONMENT={BILLING_ENVIRONMENT}.")
    sys.exit(1)

TIERS = [
    {
        "id": tier_id,
        "name": f"Kindred {SUBSCRIPTION_TIERS[tier_id]['name']}",
        "description": (
            f"{SUBSCRIPTION_TIERS[tier_id]['tagline']} "
            f"Up to {SUBSCRIPTION_TIERS[tier_id]['max_members']} members."
        ),
        "monthly_cents": price_cents(tier_id, "monthly"),
        "annual_cents": price_cents(tier_id, "annual"),
    }
    for tier_id in PAID_TIER_IDS
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
