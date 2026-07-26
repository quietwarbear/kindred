"""Subscription catalog plus legacy Stripe subscription management.

New web purchases are owned by RevenueCat Billing and start in the RevenueCat
Web SDK. Direct Stripe subscription creation is deliberately unavailable.
Stripe remains here only for already-created legacy subscriptions and one-time
add-on payments.
"""

import os
from datetime import datetime, timezone
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status

from db import subscriptions_collection, subyards_collection, users_collection
from dependencies import (
    SUBSCRIPTION_TIERS,
    TIER_ORDER,
    ensure_minimum_role,
    get_community_tier,
    get_current_user,
    now_iso,
)
from models import SubscriptionCheckoutRequest
from pricing import (
    plan_payload,
    stripe_api_key_matches_environment,
)
from subscription_lifecycle import PAID_ACCESS_STATUSES

router = APIRouter(prefix="/api")

# Owner/admin emails that always receive top-tier ("redwood") access
ADMIN_EMAILS = {
    "hodari@ubuntu-village.org",
    "shy@ubuntu-village.org",
    "quiet927@gmail.com",
}


def _is_admin_email(email: str | None) -> bool:
    """Return True if the email belongs to an admin/owner."""
    if not email:
        return False
    email = email.lower().strip()
    return email in ADMIN_EMAILS or email.endswith("@ubuntu-village.org")


def _configure_stripe() -> None:
    api_key = os.environ.get("STRIPE_API_KEY", "")
    if not stripe_api_key_matches_environment(api_key):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe billing credentials do not match the configured billing environment.",
        )
    stripe.api_key = api_key


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@router.get("/subscriptions/plans")
async def list_subscription_plans():
    return {"plans": [plan_payload(tier_id) for tier_id in TIER_ORDER]}


@router.get("/subscriptions/current")
async def get_current_subscription(current_user: dict[str, Any] = Depends(get_current_user)):
    # Admin/owner override — always top tier
    if _is_admin_email(current_user.get("email")):
        top_tier = SUBSCRIPTION_TIERS["redwood"]
        member_count = await users_collection.count_documents({"community_id": current_user["community_id"]})
        subyard_count = await subyards_collection.count_documents({"community_id": current_user["community_id"]})
        return {
            "subscription": {
                "id": "admin-override",
                "community_id": current_user["community_id"],
                "plan_id": "redwood",
                "plan_name": "Redwood",
                "status": "active",
                "provider": "admin_override",
            },
            "tier": plan_payload(top_tier["id"]),
            "usage": {"member_count": member_count, "subyard_count": subyard_count},
        }

    sub = await subscriptions_collection.find_one(
        {"community_id": current_user["community_id"], "status": {"$in": ["active", "past_due", "canceling"]}},
        {"_id": 0},
    )
    tier = get_community_tier(sub)
    member_count = await users_collection.count_documents({"community_id": current_user["community_id"]})
    subyard_count = await subyards_collection.count_documents({"community_id": current_user["community_id"]})
    return {
        "subscription": sub,
        "tier": plan_payload(tier["id"]),
        "usage": {"member_count": member_count, "subyard_count": subyard_count},
    }


# ---------------------------------------------------------------------------
# Checkout — legacy direct Stripe creation is permanently fail-closed
# ---------------------------------------------------------------------------

@router.post("/subscriptions/checkout")
async def create_subscription_checkout(
    payload: SubscriptionCheckoutRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "host")
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Direct Stripe subscription checkout is retired. "
            "Use the verified RevenueCat Billing purchase flow."
        ),
    )


# ---------------------------------------------------------------------------
# Checkout status polling (frontend polls after redirect back)
# ---------------------------------------------------------------------------

@router.get("/subscriptions/checkout/status/{session_id}")
async def get_subscription_checkout_status(
    session_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    sub_doc = await subscriptions_collection.find_one(
        {"session_id": session_id, "community_id": current_user["community_id"]}, {"_id": 0}
    )
    if not sub_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription session not found.")

    _configure_stripe()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.InvalidRequestError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkout session not found.")

    # For subscription mode, check if subscription is active
    payment_status = "unpaid"
    stripe_subscription_id = session.subscription or ""

    if session.payment_status == "paid" or session.status == "complete":
        payment_status = "paid"

    update_payload: dict[str, Any] = {"payment_status": payment_status}

    if stripe_subscription_id and not sub_doc.get("stripe_subscription_id"):
        update_payload["stripe_subscription_id"] = stripe_subscription_id

    if payment_status == "paid" and sub_doc.get("status") != "active":
        stored_cycle = sub_doc.get("billing_cycle")
        if stored_cycle not in ("monthly", "annual"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The paid checkout is missing a valid billing interval.",
            )
        if not stripe_subscription_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe did not return a subscription for the completed checkout.",
            )
        # Retrieve the Stripe subscription to get period end. Activation fails
        # closed when provider state cannot be verified.
        try:
            stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
            period_end = datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc)
            update_payload["current_period_end"] = period_end.isoformat()
            update_payload["expires_at"] = period_end.isoformat()
        except (AttributeError, TypeError, ValueError, stripe.error.StripeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify the paid subscription period with Stripe.",
            ) from exc

        update_payload["status"] = "active"
        update_payload["activated_at"] = now_iso()

        # Supersede any other active subs for this community
        await subscriptions_collection.update_many(
            {
                "community_id": current_user["community_id"],
                "status": {"$in": list(PAID_ACCESS_STATUSES)},
                "session_id": {"$ne": session_id},
            },
            {"$set": {"status": "superseded"}},
        )

        # Send welcome email
        try:
            from email_service import send_subscription_welcome
            await send_subscription_welcome(
                email=sub_doc.get("user_email", current_user.get("email", "")),
                plan_name=sub_doc.get("plan_name", ""),
                billing_cycle=stored_cycle,
                amount=sub_doc.get("amount", 0),
            )
        except Exception:
            pass  # Don't fail checkout over email

    await subscriptions_collection.update_one({"session_id": session_id}, {"$set": update_payload})
    updated = await subscriptions_collection.find_one({"session_id": session_id}, {"_id": 0})
    return {
        "status": session.status,
        "payment_status": payment_status,
        "subscription": updated,
    }


# ---------------------------------------------------------------------------
# Cancel subscription (graceful — at end of period)
# ---------------------------------------------------------------------------

@router.post("/subscriptions/cancel")
async def cancel_subscription(current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "host")
    sub = await subscriptions_collection.find_one(
        {"community_id": current_user["community_id"], "status": {"$in": ["active", "past_due"]}}, {"_id": 0}
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active subscription to cancel.")

    if sub.get("provider") == "revenuecat":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Manage this subscription through the RevenueCat customer portal.",
        )
    if sub.get("provider") != "stripe":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The subscription provider cannot be managed by this legacy endpoint.",
        )

    # Existing legacy Stripe subscribers retain provider-backed cancellation.
    stripe_sub_id = sub.get("stripe_subscription_id", "")
    if not stripe_sub_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The legacy Stripe subscription is missing its provider identifier.",
        )
    _configure_stripe()
    try:
        stripe.Subscription.modify(stripe_sub_id, cancel_at_period_end=True)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe cancellation error: {str(e)}")

    access_until = sub.get("current_period_end") or sub.get("expires_at") or "the end of your billing period"

    await subscriptions_collection.update_one(
        {"id": sub["id"]},
        {"$set": {"status": "canceling", "cancel_at_period_end": True, "cancelled_at": now_iso()}},
    )

    # Send cancellation email
    try:
        from email_service import send_subscription_cancelled
        await send_subscription_cancelled(
            email=sub.get("user_email", current_user.get("email", "")),
            plan_name=sub.get("plan_name", ""),
            access_until=access_until if isinstance(access_until, str) else str(access_until),
        )
    except Exception:
        pass

    return {
        "status": "canceling",
        "message": f"Your {sub['plan_name']} plan will cancel at the end of your billing period. You'll retain full access until {access_until}.",
    }


# ---------------------------------------------------------------------------
# Reactivate (undo pending cancellation)
# ---------------------------------------------------------------------------

@router.post("/subscriptions/reactivate")
async def reactivate_subscription(current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "host")
    sub = await subscriptions_collection.find_one(
        {"community_id": current_user["community_id"], "status": "canceling"}, {"_id": 0}
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending cancellation to reactivate.")

    if sub.get("provider") != "stripe":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reactivate this subscription through the RevenueCat customer portal.",
        )
    stripe_sub_id = sub.get("stripe_subscription_id", "")
    if not stripe_sub_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The legacy Stripe subscription is missing its provider identifier.",
        )
    _configure_stripe()
    try:
        stripe.Subscription.modify(stripe_sub_id, cancel_at_period_end=False)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe error: {str(e)}")

    await subscriptions_collection.update_one(
        {"id": sub["id"]},
        {"$set": {"status": "active", "cancel_at_period_end": False, "cancelled_at": None}},
    )

    return {"status": "active", "message": f"Your {sub['plan_name']} plan has been reactivated!"}


# ---------------------------------------------------------------------------
# Customer portal (Stripe-hosted page for managing payment methods, invoices)
# ---------------------------------------------------------------------------

@router.post("/subscriptions/portal")
async def create_customer_portal(
    body: dict,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Create a portal only for an existing legacy Stripe subscriber."""
    ensure_minimum_role(current_user, "host")
    sub = await subscriptions_collection.find_one(
        {
            "community_id": current_user["community_id"],
            "provider": "stripe",
            "stripe_customer_id": {"$exists": True, "$ne": ""},
        },
        {"_id": 0, "stripe_customer_id": 1},
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RevenueCat subscriptions must be managed through the RevenueCat customer portal.",
        )
    customer_id = sub["stripe_customer_id"]
    _configure_stripe()
    origin_url = body.get("origin_url", os.environ.get("APP_URL", "https://www.heykindred.org"))

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{origin_url}/subscription",
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Portal error: {str(e)}")

    return {"url": portal_session.url}


# ---------------------------------------------------------------------------
# Feature gating
# ---------------------------------------------------------------------------

@router.get("/subscriptions/feature-check/{feature_key}")
async def check_feature_access(feature_key: str, current_user: dict[str, Any] = Depends(get_current_user)):
    # Admin/owner override — all features unlocked
    if _is_admin_email(current_user.get("email")):
        top_tier = SUBSCRIPTION_TIERS["redwood"]
        return {"feature_key": feature_key, "allowed": True, "tier_id": top_tier["id"], "tier_name": top_tier["name"]}

    sub = await subscriptions_collection.find_one(
        {
            "community_id": current_user["community_id"],
            "status": {"$in": list(PAID_ACCESS_STATUSES)},
        },
        {"_id": 0},
    )
    tier = get_community_tier(sub)
    limits = tier.get("limits", {})
    allowed = limits.get(feature_key, False)
    return {"feature_key": feature_key, "allowed": allowed, "tier_id": tier["id"], "tier_name": tier["name"]}


# ---------------------------------------------------------------------------
# Add-ons (unchanged — still one-time payments)
# ---------------------------------------------------------------------------

ADDONS_CATALOG = [
    {
        "id": "storage-10gb",
        "name": "Extra Media Storage",
        "description": "10 GB additional storage for photos, voice notes, and files.",
        "price_cents": 1000,
        "price_display": "$10.00",
        "billing": "one-time",
        "category": "storage",
    },
    {
        "id": "storage-25gb",
        "name": "Premium Media Storage",
        "description": "25 GB additional storage with priority upload speeds.",
        "price_cents": 2500,
        "price_display": "$25.00",
        "billing": "one-time",
        "category": "storage",
    },
    {
        "id": "templates-premium",
        "name": "Premium Event Templates",
        "description": "12 curated event templates for weddings, reunions, graduations, and more.",
        "price_cents": 999,
        "price_display": "$9.99",
        "billing": "one-time",
        "category": "templates",
    },
    {
        "id": "sms-100",
        "name": "SMS Reminder Pack (100)",
        "description": "100 SMS text reminders for events and RSVPs.",
        "price_cents": 999,
        "price_display": "$9.99",
        "billing": "one-time",
        "category": "sms",
    },
    {
        "id": "sms-500",
        "name": "SMS Reminder Pack (500)",
        "description": "500 SMS text reminders with analytics.",
        "price_cents": 3999,
        "price_display": "$39.99",
        "billing": "one-time",
        "category": "sms",
    },
]


@router.get("/addons/catalog")
async def list_addons():
    """Return available add-on products."""
    return {"addons": ADDONS_CATALOG}


@router.post("/addons/checkout")
async def addon_checkout(
    body: dict,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Create a Stripe checkout session for an add-on purchase."""
    addon_id = body.get("addon_id", "")
    origin_url = body.get("origin_url", "")
    addon = next((a for a in ADDONS_CATALOG if a["id"] == addon_id), None)
    if not addon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Add-on not found.")

    _configure_stripe()
    metadata = {
        "type": "addon",
        "user_id": current_user["id"],
        "community_id": current_user["community_id"],
        "addon_id": addon_id,
        "addon_name": addon["name"],
    }

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": addon["price_cents"],
                        "product_data": {
                            "name": addon["name"],
                            "description": addon["description"],
                        },
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{origin_url}?addon_success={addon_id}",
            cancel_url=f"{origin_url}?addon_cancel=1",
            metadata=metadata,
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe error: {str(e)}")

    return {"checkout_url": session.url, "session_id": session.id}


@router.get("/addons/purchased")
async def list_purchased_addons(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return add-ons purchased by this community."""
    from db import payments_collection
    purchases = await payments_collection.find(
        {"community_id": current_user["community_id"], "metadata.type": "addon"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"purchases": purchases}
