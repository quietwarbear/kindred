"""The money side of the Reunion Pass: what a family has put in, and granting
the pass once they reach the price.

Collections are passed in rather than imported. These are the rules that
decide whether a family gets what they paid for, so they must be testable
without a Mongo driver present — and it keeps the finance webhook from having
to import a route module to do arithmetic.
"""

from typing import Any, Optional

# Contributions toward a pass are ordinary one-time payments tagged with this
# package id, so they live in payments_collection beside the three standing
# contribution packages rather than needing a collection of their own.
CHIP_IN_PACKAGE_ID = "reunion-pass-chip-in"

# A floor, so a contribution is not eaten by the card fee. Low enough that a
# cousin with little to give can still take part — money spent on the reunion
# is the strongest activation signal there is.
MIN_CHIP_IN_CENTS = 500


async def active_pass_for(subscriptions, community_id: str, plan_id: str) -> Optional[dict]:
    return await subscriptions.find_one(
        {"community_id": community_id, "plan_id": plan_id, "status": "active"},
        {"_id": 0, "expires_at": 1, "activated_at": 1, "funded_by": 1},
    )


async def contributed_cents(payments, community_id: str) -> int:
    """What the family has already put toward a pass, in cents.

    Only paid contributions count. A started-and-abandoned checkout must never
    move a family closer to a pass they have not funded.
    """
    rows = await payments.aggregate([
        {"$match": {
            "community_id": community_id,
            "package_id": CHIP_IN_PACKAGE_ID,
            "payment_status": "paid",
        }},
        {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}}},
    ]).to_list(1)
    return int(rows[0]["total"]) if rows else 0


async def activate_reunion_pass(
    subscriptions,
    community_id: str,
    *,
    plan_id: str,
    expires_at: str,
    amount: float,
    currency: str,
    now: str,
    funded_by: str,
    user_id: str = "",
) -> bool:
    """Grant the pass to a community. True when THIS call granted it.

    Idempotent by construction: the upsert filter is the active pass itself,
    so a Stripe retry, a duplicate webhook, or two contributions landing at
    once all match the same row and write nothing the second time.
    """
    result = await subscriptions.update_one(
        {"community_id": community_id, "plan_id": plan_id, "status": "active"},
        {
            "$setOnInsert": {
                "community_id": community_id,
                "user_id": user_id,
                "plan_id": plan_id,
                "provider": "stripe",
                "status": "active",
                "funded_by": funded_by,
                "auto_renews": False,
                "amount": amount,
                "currency": currency,
                "activated_at": now,
                "current_period_end": expires_at,
                "expires_at": expires_at,
            }
        },
        upsert=True,
    )
    return bool(result.upserted_id)


def remaining_cents(price_cents: int, contributed: int) -> int:
    return max(price_cents - contributed, 0)


def capped_contribution(requested_cents: int, remaining: int) -> int:
    """Never charge anyone for more than the family still needs.

    Capping rather than accepting the overage avoids owing a refund or quietly
    moving the difference into another fund.
    """
    return min(requested_cents, remaining)
