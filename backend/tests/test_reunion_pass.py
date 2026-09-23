"""The Reunion Pass is a one-time payment that grants a dated entitlement.

These cover the parts that decide whether a family gets what they paid for:
the pass is not a subscription tier, it lifts the member cap, it expires, and
a lapsed pass stops conferring access.
"""

import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pricing
from subscription_lifecycle import subscription_has_paid_access


def _pass(status="active", expires_at=None):
    return {
        "plan_id": pricing.REUNION_PASS_PLAN_ID,
        "provider": "stripe",
        "status": status,
        "current_period_end": expires_at or pricing.reunion_pass_expires_at(),
    }


# --- the catalog ----------------------------------------------------------

def test_the_pass_is_not_a_subscription_tier():
    """It must stay out of SUBSCRIPTION_TIERS: every entry there needs a
    pricing-matrix row and a full provider matrix, which a one-time SKU with
    no store products cannot honestly supply."""
    assert pricing.REUNION_PASS_PLAN_ID not in pricing.SUBSCRIPTION_TIERS
    assert pricing.REUNION_PASS_PLAN_ID not in pricing.TIER_ORDER


def test_the_pass_does_not_auto_renew():
    assert pricing.REUNION_PASS["auto_renews"] is False


def test_price_is_149_dollars_in_cents():
    assert pricing.reunion_pass_price_cents() == 14900


def test_it_grants_a_tier_that_actually_exists():
    assert pricing.REUNION_PASS["grants_tier"] in pricing.SUBSCRIPTION_TIERS


def test_the_catalog_invariants_still_hold_with_the_pass_defined():
    """Adding the pass must not disturb the tier ladder's own guards."""
    pricing.validate_catalog()


# --- the window -----------------------------------------------------------

def test_a_pass_lasts_twelve_months():
    bought = datetime(2026, 7, 1, tzinfo=timezone.utc)
    expires = datetime.fromisoformat(pricing.reunion_pass_expires_at(bought))
    assert (expires - bought).days == 365


def test_the_window_is_measured_from_purchase_not_from_now():
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert pricing.reunion_pass_expires_at(old).startswith("2020-12-31")


# --- identification -------------------------------------------------------

def test_a_pass_is_recognised_as_a_pass():
    assert pricing.is_reunion_pass(_pass()) is True


@pytest.mark.parametrize("sub", [None, {}, {"plan_id": "oak"}, {"plan_id": "seedling"}])
def test_a_subscription_is_not_a_pass(sub):
    assert pricing.is_reunion_pass(sub) is False


# --- access ---------------------------------------------------------------

def test_an_active_pass_confers_paid_access():
    assert subscription_has_paid_access(_pass()) is True


def test_an_expired_pass_confers_nothing():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert subscription_has_paid_access(_pass(expires_at=past)) is False


def test_a_pending_pass_confers_nothing():
    """A checkout that was started and never paid must not grant access."""
    assert subscription_has_paid_access(_pass(status="pending")) is False
