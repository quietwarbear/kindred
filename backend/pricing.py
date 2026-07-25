"""Canonical Kindred subscription catalog and billing-provider mappings.

Application code, public pricing responses, Stripe setup, and RevenueCat
entitlements must derive plan identifiers and amounts from this module.
"""

import os
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


SUBSCRIPTION_TIERS = {
    "seedling": {
        "id": "seedling",
        "name": "Seedling",
        "emoji": "seedling",
        "tagline": "Perfect for small circles just getting started.",
        "max_members": 10,
        "features": [
            "Full event planning suite",
            "Community feed & posts",
            "Timeline / memory archive",
            "1 subyard",
        ],
        "limits": {"max_subyards": 1, "travel_coordination": False, "shared_funds": False, "analytics": False, "custom_branding": False, "multi_admin": False},
    },
    "sapling": {
        "id": "sapling",
        "name": "Sapling",
        "emoji": "sapling",
        "tagline": "Growing communities that need more room.",
        "max_members": 25,
        "features": [
            "All Seedling features",
            "Unlimited subyards",
            "Event templates",
            "RSVP & attendee management",
            "Basic notifications",
        ],
        "limits": {"max_subyards": 999, "travel_coordination": False, "shared_funds": False, "analytics": False, "custom_branding": False, "multi_admin": False},
    },
    "oak": {
        "id": "oak",
        "name": "Oak",
        "emoji": "oak",
        "tagline": "Full coordination tools for mid-size communities.",
        "max_members": 50,
        "features": [
            "All Sapling features",
            "Travel coordination",
            "Shared event funds",
            "Priority support",
            "Expanded event templates",
        ],
        "limits": {"max_subyards": 999, "travel_coordination": True, "shared_funds": True, "analytics": False, "custom_branding": False, "multi_admin": False},
    },
    "redwood": {
        "id": "redwood",
        "name": "Redwood",
        "emoji": "redwood",
        "tagline": "Advanced tools for large, active communities.",
        "max_members": 100,
        "features": [
            "All Oak features",
            "Advanced analytics & engagement tracking",
            "Custom branding (logo, color)",
            "Multi-admin controls",
        ],
        "limits": {"max_subyards": 999, "travel_coordination": True, "shared_funds": True, "analytics": True, "custom_branding": True, "multi_admin": True},
    },
    "elder-grove": {
        "id": "elder-grove",
        "name": "Elder Grove",
        "emoji": "elder-grove",
        "tagline": "Fully customized for enterprise-scale communities.",
        "max_members": 9999,
        "features": [
            "Fully customized community experience",
            "Dedicated account manager",
            "Enterprise-grade privacy & security",
            "Optional partner integrations",
        ],
        "limits": {"max_subyards": 999, "travel_coordination": True, "shared_funds": True, "analytics": True, "custom_branding": True, "multi_admin": True},
    },
}

TIER_ORDER = ["seedling", "sapling", "oak", "redwood", "elder-grove"]
BILLING_INTERVALS = ("monthly", "annual")
BILLING_ENVIRONMENT = os.environ.get("BILLING_ENVIRONMENT", "production").strip().lower()

# The only canonical monetary values. Seedling has one explicit non-recurring
# free option; it does not have a fabricated monthly or annual subscription.
# Elder Grove is custom-priced and therefore has no self-serve billing option.
PRICING_MATRIX = {
    "seedling": {
        "free": {
            "amount": 0.00,
            "currency": "usd",
            "recurring": False,
            "label": "Free",
        },
    },
    "sapling": {
        "monthly": {"amount": 9.99, "currency": "usd", "recurring": True, "period": "month"},
        "annual": {"amount": 89.99, "currency": "usd", "recurring": True, "period": "year"},
    },
    "oak": {
        "monthly": {"amount": 19.99, "currency": "usd", "recurring": True, "period": "month"},
        "annual": {"amount": 179.99, "currency": "usd", "recurring": True, "period": "year"},
    },
    "redwood": {
        "monthly": {"amount": 39.99, "currency": "usd", "recurring": True, "period": "month"},
        "annual": {"amount": 359.99, "currency": "usd", "recurring": True, "period": "year"},
    },
    "elder-grove": {},
}

PAID_TIER_IDS = tuple(tier_id for tier_id in TIER_ORDER if set(PRICING_MATRIX[tier_id]) == set(BILLING_INTERVALS))

# Defaults are the current live Stripe Price IDs. Operators may rotate them
# through environment variables, but checkout verifies the remote amount,
# currency, interval, and metadata against this catalog before use.
BILLING_PROVIDER_MATRIX: dict[str, dict[str, dict[str, dict[str, str]]]] = {
    "sapling": {
        "monthly": {
            "stripe": {"price_id": os.environ.get("STRIPE_PRICE_SAPLING_MONTHLY", "price_1TCNAdAk1UyEdCJUIlI3clyU")},
            "revenuecat": {"product_id": "com.kindred.sapling.monthly", "entitlement_id": "sapling"},
        },
        "annual": {
            "stripe": {"price_id": os.environ.get("STRIPE_PRICE_SAPLING_ANNUAL", "price_1TCMNIAk1UyEdCJUHIFvOqex")},
            "revenuecat": {"product_id": "com.kindred.sapling.annual", "entitlement_id": "sapling"},
        },
    },
    "oak": {
        "monthly": {
            "stripe": {"price_id": os.environ.get("STRIPE_PRICE_OAK_MONTHLY", "price_1TCN7VAk1UyEdCJU3LdlXY14")},
            "revenuecat": {"product_id": "com.kindred.oak.monthly", "entitlement_id": "oak"},
        },
        "annual": {
            "stripe": {"price_id": os.environ.get("STRIPE_PRICE_OAK_ANNUAL", "price_1TCMQRAk1UyEdCJU8yS5hdLe")},
            "revenuecat": {"product_id": "com.kindred.oak.annual", "entitlement_id": "oak"},
        },
    },
    "redwood": {
        "monthly": {
            "stripe": {"price_id": os.environ.get("STRIPE_PRICE_REDWOOD_MONTHLY", "price_1TCN3XAk1UyEdCJUuhFERcuD")},
            "revenuecat": {"product_id": "com.kindred.redwood.monthly", "entitlement_id": "redwood"},
        },
        "annual": {
            "stripe": {"price_id": os.environ.get("STRIPE_PRICE_REDWOOD_ANNUAL", "price_1TCMVYAk1UyEdCJUJqhBRIFc")},
            "revenuecat": {"product_id": "com.kindred.redwood.annual", "entitlement_id": "redwood"},
        },
    },
}

REVENUECAT_ENTITLEMENT_TO_TIER = {
    "seedling": "seedling",
    "sapling": "sapling",
    "oak": "oak",
    "redwood": "redwood",
    "elder_grove": "elder-grove",
    "premium": "oak",  # Legacy entitlement retained for existing customers.
}

def get_billing_option(tier_id: str, billing_interval: str) -> dict:
    """Return one canonical plan/interval option or fail closed."""
    option = PRICING_MATRIX.get(tier_id, {}).get(billing_interval)
    if not option:
        raise ValueError(f"Unsupported billing option: {tier_id}/{billing_interval}.")
    return option


def billing_amount(tier_id: str, billing_interval: str) -> float:
    return float(get_billing_option(tier_id, billing_interval)["amount"])


def price_cents(tier_id: str, billing_interval: str) -> int:
    """Return one canonical paid amount in cents."""
    option = get_billing_option(tier_id, billing_interval)
    if not option["recurring"] or billing_interval not in BILLING_INTERVALS:
        raise ValueError("Only paid recurring options have provider prices.")
    return int(Decimal(str(option["amount"])) * 100)


def stripe_price_expectation(tier_id: str, billing_interval: str) -> dict:
    """Return the remote Stripe fields checkout must verify before use."""
    return {
        "active": True,
        "livemode": BILLING_ENVIRONMENT == "production",
        "currency": "usd",
        "unit_amount": price_cents(tier_id, billing_interval),
        "interval": "month" if billing_interval == "monthly" else "year",
        "tier": tier_id,
        "cycle": billing_interval,
    }


def stripe_api_key_matches_environment(api_key: str) -> bool:
    expected_prefixes = (
        ("sk_live_", "rk_live_")
        if BILLING_ENVIRONMENT == "production"
        else ("sk_test_", "rk_test_")
    )
    return bool(api_key and api_key.startswith(expected_prefixes))


def annual_savings(tier_id: str) -> dict:
    """Compare the annual charge with twelve canonical monthly charges."""
    monthly_total = Decimal(str(billing_amount(tier_id, "monthly"))) * 12
    annual_total = Decimal(str(billing_amount(tier_id, "annual")))
    saved = (monthly_total - annual_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    percent = ((saved / monthly_total) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return {
        "amount": float(saved),
        "percent": float(percent),
        "comparison": "12_monthly_payments",
    }


def public_billing_options(tier_id: str) -> dict:
    options = deepcopy(PRICING_MATRIX[tier_id])
    if "annual" in options:
        options["annual"]["savings"] = annual_savings(tier_id)
    return options


def plan_payload(tier_id: str) -> dict:
    tier = SUBSCRIPTION_TIERS[tier_id]
    return {
        **tier,
        "billing_options": public_billing_options(tier_id),
        "custom_pricing": tier_id == "elder-grove",
    }


def provider_mapping(provider: str) -> dict[str, dict[str, str]]:
    """Return plan/interval identifiers for one provider."""
    field = "price_id" if provider == "stripe" else "product_id"
    if provider not in ("stripe", "revenuecat"):
        raise ValueError("Unknown billing provider.")
    return {
        tier_id: {
            interval: BILLING_PROVIDER_MATRIX[tier_id][interval][provider][field]
            for interval in BILLING_INTERVALS
        }
        for tier_id in PAID_TIER_IDS
    }


STRIPE_PRICE_IDS = provider_mapping("stripe")
REVENUECAT_PRODUCT_IDS = provider_mapping("revenuecat")


def resolve_revenuecat_product(product_id: str) -> tuple[str, str, str]:
    """Resolve a native product to canonical plan, interval, and entitlement."""
    for tier_id in PAID_TIER_IDS:
        for interval in BILLING_INTERVALS:
            config = BILLING_PROVIDER_MATRIX[tier_id][interval]["revenuecat"]
            if config["product_id"] == product_id:
                return tier_id, interval, config["entitlement_id"]
    raise ValueError("Unknown RevenueCat product.")


def resolve_stripe_price(price_id: str) -> tuple[str, str]:
    """Resolve a Stripe Price ID to one canonical plan and interval."""
    for tier_id in PAID_TIER_IDS:
        for interval in BILLING_INTERVALS:
            if BILLING_PROVIDER_MATRIX[tier_id][interval]["stripe"]["price_id"] == price_id:
                return tier_id, interval
    raise ValueError("Unknown Stripe Price.")


def validate_catalog(
    pricing_matrix: Optional[dict] = None,
    provider_matrix: Optional[dict] = None,
) -> None:
    """Fail if provider mappings drift from plan definitions.

    Optional matrices make the drift checks directly testable without mutating
    the process-wide canonical catalog.
    """
    pricing_matrix = PRICING_MATRIX if pricing_matrix is None else pricing_matrix
    provider_matrix = BILLING_PROVIDER_MATRIX if provider_matrix is None else provider_matrix
    if list(SUBSCRIPTION_TIERS) != TIER_ORDER:
        raise RuntimeError("Pricing tier order must match the canonical catalog.")
    if BILLING_ENVIRONMENT not in {"production", "test"}:
        raise RuntimeError("BILLING_ENVIRONMENT must be 'production' or 'test'.")
    if set(pricing_matrix) != set(TIER_ORDER):
        raise RuntimeError("Every tier must have an explicit pricing-matrix entry.")
    if set(pricing_matrix["seedling"]) != {"free"} or pricing_matrix["seedling"]["free"]["amount"] != 0:
        raise RuntimeError("Seedling must have one explicit free option and no recurring intervals.")
    if pricing_matrix["elder-grove"]:
        raise RuntimeError("Custom-priced Elder Grove cannot expose self-serve billing intervals.")
    if set(provider_matrix) != set(PAID_TIER_IDS):
        raise RuntimeError("Every paid tier must have a provider matrix.")
    if any(mapped not in SUBSCRIPTION_TIERS for mapped in REVENUECAT_ENTITLEMENT_TO_TIER.values()):
        raise RuntimeError("RevenueCat contains an unknown canonical tier.")
    identifiers = {"stripe": set(), "revenuecat": set()}
    for tier_id in PAID_TIER_IDS:
        if set(pricing_matrix[tier_id]) != set(BILLING_INTERVALS):
            raise RuntimeError(f"{tier_id} must define monthly and annual pricing.")
        if set(provider_matrix[tier_id]) != set(BILLING_INTERVALS):
            raise RuntimeError(f"{tier_id} must map every billing interval.")
        for interval in BILLING_INTERVALS:
            provider_entry = provider_matrix[tier_id][interval]
            if set(provider_entry) != {"stripe", "revenuecat"}:
                raise RuntimeError(f"{tier_id}/{interval} must map Stripe and RevenueCat.")
            stripe_id = provider_entry["stripe"].get("price_id", "")
            revenuecat = provider_entry["revenuecat"]
            revenuecat_id = revenuecat.get("product_id", "")
            if not stripe_id or not revenuecat_id:
                raise RuntimeError(f"{tier_id}/{interval} has an empty provider identifier.")
            if revenuecat.get("entitlement_id") != tier_id:
                raise RuntimeError(f"{tier_id}/{interval} resolves to the wrong native entitlement.")
            identifiers["stripe"].add(stripe_id)
            identifiers["revenuecat"].add(revenuecat_id)
    expected_count = len(PAID_TIER_IDS) * len(BILLING_INTERVALS)
    if any(len(values) != expected_count for values in identifiers.values()):
        raise RuntimeError("Provider identifiers must be unique for every plan/interval.")


validate_catalog()
