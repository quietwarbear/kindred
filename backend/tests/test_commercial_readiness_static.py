"""Fast, offline regression checks for commercial-readiness invariants."""

import json
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
    LEGACY_STRIPE_SUBSCRIPTION_PRICE_IDS,
    PAID_TIER_IDS,
    PRICING_MATRIX,
    REVENUECAT_ENTITLEMENT_TO_TIER,
    REVENUECAT_PRODUCT_IDS,
    REVENUECAT_PRODUCT_IDS_BY_PLATFORM,
    TIER_ORDER,
    annual_savings,
    price_cents,
    revenuecat_billing_mapping,
    resolve_revenuecat_product,
    resolve_legacy_stripe_subscription_price,
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
    assert set(REVENUECAT_PRODUCT_IDS) == set(PAID_TIER_IDS)
    assert set(REVENUECAT_PRODUCT_IDS_BY_PLATFORM) == {"web", "app_store", "play_store"}
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
            assert set(provider) == {"revenuecat"}
            assert provider["revenuecat"]["entitlement_id"] == f"{tier_id}_access"
            for product_id in provider["revenuecat"]["products"].values():
                assert resolve_revenuecat_product(product_id) == (
                    tier_id,
                    interval,
                    f"{tier_id}_access",
                )


def test_catalog_rejects_missing_or_contradictory_provider_intervals():
    missing = deepcopy(BILLING_PROVIDER_MATRIX)
    del missing["oak"]["annual"]
    with pytest.raises(RuntimeError, match="map every billing interval"):
        validate_catalog(provider_matrix=missing)

    crossed_entitlement = deepcopy(BILLING_PROVIDER_MATRIX)
    crossed_entitlement["sapling"]["annual"]["revenuecat"]["entitlement_id"] = "oak_access"
    with pytest.raises(RuntimeError, match="wrong entitlement"):
        validate_catalog(provider_matrix=crossed_entitlement)

    duplicate_identifier = deepcopy(BILLING_PROVIDER_MATRIX)
    duplicate_identifier["redwood"]["annual"]["revenuecat"]["products"]["web"] = (
        duplicate_identifier["redwood"]["monthly"]["revenuecat"]["products"]["web"]
    )
    with pytest.raises(RuntimeError, match="unique"):
        validate_catalog(provider_matrix=duplicate_identifier)


def test_revenuecat_billing_expectations_cover_every_paid_plan_interval():
    mapping = revenuecat_billing_mapping()
    expected_web_products = {
        "sapling": {
            "monthly": "sapling_monthly_web_v2",
            "annual": "sapling_annual_web_v2",
        },
        "oak": {
            "monthly": "oak_monthly_web_v2",
            "annual": "oak_annual_web_v2",
        },
        "redwood": {
            "monthly": "redwood_monthly_web_v2",
            "annual": "redwood_annual_web_v2",
        },
    }
    assert set(mapping) == set(PAID_TIER_IDS)
    for tier_id in PAID_TIER_IDS:
        assert set(mapping[tier_id]) == set(BILLING_INTERVALS)
        for interval in BILLING_INTERVALS:
            expected = mapping[tier_id][interval]
            assert expected["product_id"] == expected_web_products[tier_id][interval]
            assert expected["offering_id"] == f"{tier_id}_access"
            assert expected["entitlement_id"] == f"{tier_id}_access"
            assert expected["package_id"] == (
                "$rc_monthly" if interval == "monthly" else "$rc_annual"
            )
            assert expected["amount_micros"] == price_cents(tier_id, interval) * 10_000
            assert expected["currency"] == "USD"
            assert expected["period"] == ("P1M" if interval == "monthly" else "P1Y")

    assert all(
        expected["product_id"].endswith("_web_v2")
        for intervals in mapping.values()
        for expected in intervals.values()
    )


def test_direct_stripe_subscription_prices_are_legacy_only():
    assert set(LEGACY_STRIPE_SUBSCRIPTION_PRICE_IDS) == set(PAID_TIER_IDS)
    for tier_id in PAID_TIER_IDS:
        for interval in BILLING_INTERVALS:
            price_id = LEGACY_STRIPE_SUBSCRIPTION_PRICE_IDS[tier_id][interval]
            assert resolve_legacy_stripe_subscription_price(price_id) == (tier_id, interval)

    subscriptions = read("backend/routes/subscriptions.py")
    assert "Direct Stripe subscription checkout is retired" in subscriptions
    direct_checkout = subscriptions.split(
        '@router.post("/subscriptions/checkout")',
        1,
    )[1].split(
        '@router.get("/subscriptions/checkout/status/{session_id}")',
        1,
    )[0]
    assert "stripe.checkout.Session.create(" not in direct_checkout
    assert "setup-stripe-products" not in subscriptions
    assert BILLING_ENVIRONMENT == "production"
    assert stripe_api_key_matches_environment("sk_live_example")
    assert not stripe_api_key_matches_environment("sk_test_example")


def test_revenuecat_product_entitlement_and_interval_resolution_fails_closed():
    expiration_ms = 2_000_000_000_000
    event = {
        "product_id": "com.kindred.oak.annual",
        "entitlement_ids": ["oak_access"],
        "expiration_at_ms": expiration_ms,
    }
    assert resolve_revenuecat_webhook_purchase(event)[:3] == (
        "oak",
        "annual",
        "oak_access",
    )

    with pytest.raises(ValueError, match="entitlement"):
        resolve_revenuecat_webhook_purchase({**event, "entitlement_ids": ["sapling_access"]})
    with pytest.raises(ValueError, match="Unknown RevenueCat product"):
        resolve_revenuecat_webhook_purchase({**event, "product_id": "com.kindred.unknown"})


def test_revenuecat_subscriber_rejects_multiple_or_unmapped_active_products():
    future = "2035-01-01T00:00:00Z"
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    subscriber = {
        "subscriptions": {
            "com.kindred.sapling.monthly": {"expires_date": future},
        },
        "entitlements": {"sapling_access": {"expires_date": future}},
    }
    assert resolve_revenuecat_subscriber(subscriber, now)[:4] == (
        "sapling",
        "monthly",
        "sapling_access",
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
    assert 'offerings?.all?.[`${planId}_access`]' in revenuecat
    assert "expectedOfferingId" in revenuecat


def test_local_storekit_fixture_matches_the_canonical_matrix():
    storekit = json.loads(read("frontend/ios/App/app64a12dfad0.storekit"))
    subscriptions = [
        subscription
        for group in storekit["subscriptionGroups"]
        for subscription in group["subscriptions"]
    ]
    actual = {
        subscription["productID"]: (
            subscription["displayPrice"],
            subscription["recurringSubscriptionPeriod"],
        )
        for subscription in subscriptions
    }
    assert actual == {
        "com.kindred.sapling.monthly": ("9.99", "P1M"),
        "com.kindred.sapling.annual": ("89.99", "P1Y"),
        "com.kindred.oak.monthly": ("19.99", "P1M"),
        "com.kindred.oak.annual": ("179.99", "P1Y"),
        "com.kindred.redwood.monthly": ("39.99", "P1M"),
        "com.kindred.redwood.annual": ("359.99", "P1Y"),
    }


def test_web_subscription_uses_revenuecat_billing_and_fails_closed_on_drift():
    web = read("frontend/src/lib/revenuecatWeb.js")
    subscription_page = read("frontend/src/components/SubscriptionPage.jsx")
    subscriptions = read("backend/routes/subscriptions.py")

    assert '@revenuecat/purchases-js' in web
    for invariant in (
        "offering",
        "package",
        "product",
        "billing interval",
        "currency",
        "amount",
        "free trial",
        "introductory price",
    ):
        assert invariant in web
    assert "makeRevenueCatWebPurchase" in subscription_page
    assert 'apiRequest("/subscriptions/checkout"' not in subscription_page
    assert "Direct Stripe subscription checkout is retired" in subscriptions


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
