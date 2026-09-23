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
import reunion_pass_ledger as ledger
from subscription_lifecycle import subscription_has_paid_access


async def _activate(subs):
    return await ledger.activate_reunion_pass(
        subs,
        "c1",
        plan_id=pricing.REUNION_PASS_PLAN_ID,
        expires_at=pricing.reunion_pass_expires_at(),
        amount=pricing.REUNION_PASS["amount"],
        currency=pricing.REUNION_PASS["currency"],
        now="2026-09-23T00:00:00+00:00",
        funded_by="chip_in",
    )


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


# --- chip-in --------------------------------------------------------------

class _FakePayments:
    """Stands in for payments_collection so the balance maths can be tested
    without a Mongo driver."""

    def __init__(self, total_cents=0):
        self._total = total_cents
        self.pipelines = []

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        total = self._total
        outer = self

        class _Cursor:
            async def to_list(self, _n):
                return [{"_id": None, "total": total}] if outer._total else []

        return _Cursor()


@pytest.mark.asyncio
async def test_only_paid_contributions_count():
    """A started-and-abandoned checkout must never move a family closer to a
    pass they have not funded."""
    fake = _FakePayments(5000)
    assert await ledger.contributed_cents(fake, "c1") == 5000

    match = fake.pipelines[0][0]["$match"]
    assert match["payment_status"] == "paid"
    assert match["package_id"] == ledger.CHIP_IN_PACKAGE_ID
    assert match["community_id"] == "c1"


@pytest.mark.asyncio
async def test_a_family_with_no_contributions_is_at_zero():
    assert await ledger.contributed_cents(_FakePayments(0), "c1") == 0


def test_the_chip_in_floor_is_above_a_trivial_amount():
    """Below a floor, Stripe's fee eats the contribution."""
    assert ledger.MIN_CHIP_IN_CENTS >= 100
    assert ledger.MIN_CHIP_IN_CENTS < pricing.reunion_pass_price_cents()


class _FakeSubs:
    def __init__(self, already_active=False):
        self.already_active = already_active
        self.calls = []

    async def update_one(self, flt, update, upsert=False):
        self.calls.append((flt, update, upsert))

        class _Res:
            upserted_id = None if self.already_active else "new-id"

        return _Res()


@pytest.mark.asyncio
async def test_activation_is_idempotent():
    """Two contributions landing at once, or a Stripe retry, must not grant
    two passes."""
    assert await _activate(_FakeSubs(already_active=False)) is True
    assert await _activate(_FakeSubs(already_active=True)) is False


@pytest.mark.asyncio
async def test_activation_upserts_against_the_active_pass_itself():
    """The filter IS the idempotency guard — it must match on the community,
    the pass, and an active status, or a retry writes a second row."""
    subs = _FakeSubs()
    await _activate(subs)

    flt, update, upsert = subs.calls[0]
    assert flt == {
        "community_id": "c1",
        "plan_id": pricing.REUNION_PASS_PLAN_ID,
        "status": "active",
    }
    assert upsert is True
    assert "$setOnInsert" in update
    assert update["$setOnInsert"]["auto_renews"] is False
    assert update["$setOnInsert"]["funded_by"] == "chip_in"


# --- capping --------------------------------------------------------------

def test_nobody_is_charged_more_than_the_family_still_needs():
    assert ledger.capped_contribution(20000, 3000) == 3000


def test_a_contribution_under_the_remainder_is_charged_in_full():
    assert ledger.capped_contribution(2500, 14900) == 2500


def test_remaining_never_goes_negative():
    """An overfunded family must read as zero left, not a negative goal."""
    assert ledger.remaining_cents(14900, 20000) == 0
    assert ledger.remaining_cents(14900, 14900) == 0
    assert ledger.remaining_cents(14900, 900) == 14000
