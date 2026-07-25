"""Fast, offline regression checks for commercial-readiness invariants."""

import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from pricing import (  # noqa: E402
    BILLING_INTERVALS,
    BILLING_ENVIRONMENT,
    BILLING_PROVIDER_MATRIX,
    PAID_TIER_IDS,
    PRICING_MATRIX,
    REVENUECAT_ENTITLEMENT_TO_TIER,
    REVENUECAT_PRODUCT_IDS,
    STRIPE_PRICE_IDS,
    TIER_ORDER,
    annual_savings,
    price_cents,
    resolve_revenuecat_product,
    resolve_stripe_price,
    stripe_price_expectation,
    stripe_api_key_matches_environment,
    validate_catalog,
)
from subscription_lifecycle import (  # noqa: E402
    resolve_revenuecat_subscriber,
    resolve_revenuecat_webhook_purchase,
    should_apply_provider_event,
    subscription_has_paid_access,
)


def read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def test_canonical_pricing_matches_live_schedule_and_provider_mappings():
    assert TIER_ORDER == ["seedling", "sapling", "oak", "redwood", "elder-grove"]
    assert {
        tier_id: {interval: option["amount"] for interval, option in intervals.items()}
        for tier_id, intervals in PRICING_MATRIX.items()
    } == {
        "seedling": {"free": 0.0},
        "sapling": {"monthly": 9.99, "annual": 89.99},
        "oak": {"monthly": 19.99, "annual": 179.99},
        "redwood": {"monthly": 39.99, "annual": 359.99},
        "elder-grove": {},
    }
    assert set(PRICING_MATRIX["seedling"]) == {"free"}
    assert not PRICING_MATRIX["seedling"]["free"]["recurring"]
    assert set(STRIPE_PRICE_IDS) == set(PAID_TIER_IDS)
    assert set(REVENUECAT_PRODUCT_IDS) == set(PAID_TIER_IDS)
    assert price_cents("sapling", "monthly") == 999
    assert price_cents("redwood", "annual") == 35999
    assert annual_savings("sapling") == {
        "amount": 29.89,
        "percent": 24.9,
        "comparison": "12_monthly_payments",
    }

    for tier_id in PAID_TIER_IDS:
        assert set(BILLING_PROVIDER_MATRIX[tier_id]) == set(BILLING_INTERVALS)
        for interval in BILLING_INTERVALS:
            provider = BILLING_PROVIDER_MATRIX[tier_id][interval]
            assert resolve_stripe_price(provider["stripe"]["price_id"]) == (tier_id, interval)
            assert resolve_revenuecat_product(provider["revenuecat"]["product_id"]) == (
                tier_id,
                interval,
                tier_id,
            )


def test_catalog_rejects_missing_or_contradictory_provider_intervals():
    missing = deepcopy(BILLING_PROVIDER_MATRIX)
    del missing["oak"]["annual"]
    with pytest.raises(RuntimeError, match="map every billing interval"):
        validate_catalog(provider_matrix=missing)

    crossed_entitlement = deepcopy(BILLING_PROVIDER_MATRIX)
    crossed_entitlement["sapling"]["annual"]["revenuecat"]["entitlement_id"] = "oak"
    with pytest.raises(RuntimeError, match="wrong native entitlement"):
        validate_catalog(provider_matrix=crossed_entitlement)

    duplicate_identifier = deepcopy(BILLING_PROVIDER_MATRIX)
    duplicate_identifier["redwood"]["annual"]["stripe"]["price_id"] = (
        duplicate_identifier["redwood"]["monthly"]["stripe"]["price_id"]
    )
    with pytest.raises(RuntimeError, match="must be unique"):
        validate_catalog(provider_matrix=duplicate_identifier)


def test_remote_stripe_expectations_detect_swapped_or_contradictory_prices():
    monthly = stripe_price_expectation("oak", "monthly")
    annual = stripe_price_expectation("oak", "annual")
    assert monthly == {
        "active": True,
        "livemode": True,
        "currency": "usd",
        "unit_amount": 1999,
        "interval": "month",
        "tier": "oak",
        "cycle": "monthly",
    }
    assert annual["unit_amount"] == 17999
    assert annual["interval"] == "year"
    assert annual["cycle"] == "annual"
    assert monthly != annual
    assert BILLING_ENVIRONMENT == "production"
    assert stripe_api_key_matches_environment("sk_live_example")
    assert not stripe_api_key_matches_environment("sk_test_example")


def test_revenuecat_product_entitlement_and_interval_resolution_fails_closed():
    expiration_ms = 2_000_000_000_000
    event = {
        "product_id": "com.kindred.oak.annual",
        "entitlement_ids": ["oak"],
        "expiration_at_ms": expiration_ms,
    }
    assert resolve_revenuecat_webhook_purchase(event)[:3] == ("oak", "annual", "oak")

    with pytest.raises(ValueError, match="entitlement"):
        resolve_revenuecat_webhook_purchase({**event, "entitlement_ids": ["sapling"]})
    with pytest.raises(ValueError, match="Unknown RevenueCat product"):
        resolve_revenuecat_webhook_purchase({**event, "product_id": "com.kindred.unknown"})


def test_revenuecat_subscriber_rejects_multiple_or_unmapped_active_products():
    future = "2035-01-01T00:00:00Z"
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    subscriber = {
        "subscriptions": {
            "com.kindred.sapling.monthly": {"expires_date": future},
        },
        "entitlements": {"sapling": {"expires_date": future}},
    }
    assert resolve_revenuecat_subscriber(subscriber, now)[:4] == (
        "sapling",
        "monthly",
        "sapling",
        "com.kindred.sapling.monthly",
    )
    contradictory = deepcopy(subscriber)
    contradictory["subscriptions"]["com.kindred.unknown"] = {"expires_date": future}
    with pytest.raises(ValueError, match="contradictory"):
        resolve_revenuecat_subscriber(contradictory, now)
    with pytest.raises(ValueError, match="unmapped"):
        resolve_revenuecat_subscriber(
            {
                "subscriptions": {"com.kindred.unknown": {"expires_date": future}},
                "entitlements": {"unknown": {"expires_date": future}},
            },
            now,
        )


def test_lifecycle_access_and_event_ordering_preserve_then_expire_access():
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert subscription_has_paid_access({"status": "active"}, now)
    assert subscription_has_paid_access(
        {
            "status": "active",
            "provider": "stripe",
            "current_period_end": "2030-02-01T00:00:00+00:00",
        },
        now,
    )
    assert not subscription_has_paid_access({"status": "active", "provider": "revenuecat"}, now)
    assert subscription_has_paid_access(
        {"status": "canceling", "current_period_end": "2030-02-01T00:00:00+00:00"},
        now,
    )
    assert not subscription_has_paid_access(
        {"status": "canceling", "current_period_end": "2029-12-01T00:00:00+00:00"},
        now,
    )
    assert subscription_has_paid_access(
        {"status": "past_due", "grace_period_expires_at": "2030-01-02T00:00:00+00:00"},
        now,
    )
    assert not subscription_has_paid_access({"status": "canceled"}, now)
    assert should_apply_provider_event(None, 100)
    assert should_apply_provider_event(100, 101)
    assert not should_apply_provider_event(101, 100)


def test_native_prices_and_savings_are_storekit_localized():
    revenuecat = read("frontend/src/lib/revenuecat.js")
    subscription_page = read("frontend/src/components/SubscriptionPage.jsx")
    assert "product.priceString" in revenuecat
    assert "product.currencyCode" in revenuecat
    assert "getLocalizedRevenueCatPricing" in subscription_page
    assert "localizedBillingOption" in subscription_page
    assert "formatLocalizedPrice" in subscription_page


def test_checkout_interval_and_authenticated_toggle_are_explicit():
    models = read("backend/models.py")
    subscriptions = read("backend/routes/subscriptions.py")
    subscription_page = read("frontend/src/components/SubscriptionPage.jsx")
    assert 'billing_cycle: Literal["monthly", "annual"]' in models
    assert '"billing_cycle": "annual",\n                "provider": "admin_override"' not in subscriptions
    assert 'aria-label="Billing interval"' in subscription_page
    assert 'role="group"' in subscription_page
    assert 'aria-pressed={billingCycle === "monthly"}' in subscription_page
    assert 'aria-pressed={billingCycle === "annual"}' in subscription_page


def test_public_prices_are_loaded_from_backend_instead_of_duplicated():
    landing = read("frontend/src/components/LandingPage.jsx")
    pricing_page = read("frontend/src/components/PricingPage.jsx")
    hook = read("frontend/src/hooks/usePublicPlans.js")
    obsolete_literals = ("$49", "$79", "$129", "start at $19")

    assert all(value not in landing for value in obsolete_literals)
    assert 'apiRequest("/subscriptions/plans")' in hook
    assert "<PublicPlanCards" in landing
    assert "<PublicPlanCards" in pricing_page


def test_marketing_routes_are_public_and_consumer_strategy_link_is_removed():
    app = read("frontend/src/App.js")
    landing = read("frontend/src/components/LandingPage.jsx")
    assert 'element={<PricingPage />} path="/pricing"' in app
    assert 'element={<PrivacyPolicyPage />} path="/privacy"' in app
    assert 'element={<SupportPage />} path="/support"' in app
    assert 'to="/pricing"' in landing
    assert "Explore the strategy deck" not in landing
    assert 'to="/subscription"' not in landing


def test_privacy_policy_and_data_map_name_active_vendor_paths():
    policy = read("frontend/src/components/PrivacyPolicyPage.jsx")
    data_map = read("docs/PRIVACY_DATA_MAP.md")
    combined = f"{policy}\n{data_map}".lower()
    for vendor in (
        "google analytics",
        "google tag manager",
        "posthog",
        "stripe",
        "revenuecat",
        "resend",
        "mongodb",
        "litellm",
        "openai",
        "whisper",
        "gemini",
    ):
        assert vendor in combined
    assert "we do not collect data" not in combined
    assert "collects no data" not in combined


def test_canonical_public_identity_replaces_legacy_marketing_domain():
    identity = read("frontend/src/config/publicIdentity.js")
    store_listing = read("frontend/STORE_LISTINGS.md")
    checklist = read("frontend/SUBMISSION_CHECKLIST.md")
    assert "https://www.heykindred.org" in identity
    assert "kindred.ubuntumarket.com" not in store_listing
    assert "kindred.ubuntumarket.com" not in checklist


def test_unsupported_trial_claim_is_not_rendered():
    subscription_page = read("frontend/src/components/SubscriptionPage.jsx").lower()
    assert "14-day trial" not in subscription_page
    assert "trial period" not in subscription_page
    assert "equivalent" not in subscription_page
    assert "save ~" not in subscription_page
    assert "approximately 25%" not in subscription_page
