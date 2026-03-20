"""Subscription routes — Stripe recurring billing."""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status

from db import subscriptions_collection, subyards_collection, users_collection
from dependencies import (
    STRIPE_PRICE_IDS,
    SUBSCRIPTION_TIERS,
    TIER_ORDER,
    ensure_minimum_role,
    get_community_tier,
    get_current_user,
    now_iso,
)
from models import SubscriptionCheckoutRequest

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Stripe Customer management
# ---------------------------------------------------------------------------

async def _get_or_create_stripe_customer(user: dict[str, Any]) -> str:
    """Retrieve existing Stripe Customer ID or create a new one."""
    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")

    # Check if the user already has a Stripe customer ID stored
    sub_doc = await subscriptions_collection.find_one(
        {"community_id": user["community_id"], "stripe_customer_id": {"$exists": True, "$ne": ""}},
        {"stripe_customer_id": 1, "_id": 0},
    )
    if sub_doc and sub_doc.get("stripe_customer_id"):
        return sub_doc["stripe_customer_id"]

    # Also check the user doc itself
    user_doc = await users_collection.find_one({"id": user["id"]}, {"_id": 0})
    if user_doc and user_doc.get("stripe_customer_id"):
        return user_doc["stripe_customer_id"]

    # Create a new Stripe Customer
    customer = stripe.Customer.create(
        email=user.get("email", ""),
        name=user.get("full_name", ""),
        metadata={
            "kindred_user_id": user["id"],
            "kindred_community_id": user["community_id"],
        },
    )

    # Store customer ID on the user doc for future reference
    await users_collection.update_one(
        {"id": user["id"]},
        {"$set": {"stripe_customer_id": customer.id}},
    )

    return customer.id


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@router.get("/subscriptions/plans")
async def list_subscription_plans():
    plans = []
    for tier_id in TIER_ORDER:
        tier = SUBSCRIPTION_TIERS[tier_id]
        plans.append({
            "id": tier["id"],
            "name": tier["name"],
            "emoji": tier["emoji"],
            "tagline": tier["tagline"],
            "max_members": tier["max_members"],
            "monthly_price": tier["monthly_price"],
            "annual_price": tier["annual_price"],
            "features": tier["features"],
            "limits": tier["limits"],
        })
    return {"plans": plans}


@router.get("/subscriptions/current")
async def get_current_subscription(current_user: dict[str, Any] = Depends(get_current_user)):
    sub = await subscriptions_collection.find_one(
        {"community_id": current_user["community_id"], "status": {"$in": ["active", "past_due", "canceling"]}},
        {"_id": 0},
    )
    tier = get_community_tier(sub)
    member_count = await users_collection.count_documents({"community_id": current_user["community_id"]})
    subyard_count = await subyards_collection.count_documents({"community_id": current_user["community_id"]})
    return {
        "subscription": sub,
        "tier": {
            "id": tier["id"],
            "name": tier["name"],
            "emoji": tier["emoji"],
            "max_members": tier["max_members"],
            "monthly_price": tier["monthly_price"],
            "annual_price": tier["annual_price"],
            "features": tier["features"],
            "limits": tier["limits"],
        },
        "usage": {"member_count": member_count, "subyard_count": subyard_count},
    }


# ---------------------------------------------------------------------------
# Checkout — creates a Stripe Subscription via Checkout Session
# ---------------------------------------------------------------------------

@router.post("/subscriptions/checkout")
async def create_subscription_checkout(
    payload: SubscriptionCheckoutRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "host")
    tier = SUBSCRIPTION_TIERS.get(payload.plan_id)
    if not tier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subscription plan.")
    if tier["monthly_price"] == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact sales for Elder Grove pricing.")

    # Look up the recurring Stripe Price ID for this tier + cycle
    price_ids = STRIPE_PRICE_IDS.get(payload.plan_id, {})
    price_id = price_ids.get(payload.billing_cycle, "")
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe price not configured for {payload.plan_id}/{payload.billing_cycle}. Run setup_stripe_subscriptions.py first.",
        )

    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")

    # Get or create Stripe Customer
    customer_id = await _get_or_create_stripe_customer(current_user)

    metadata = {
        "type": "subscription",
        "community_id": current_user["community_id"],
        "user_id": current_user["id"],
        "user_email": current_user["email"],
        "plan_id": tier["id"],
        "plan_name": tier["name"],
        "billing_cycle": payload.billing_cycle,
    }

    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{payload.origin_url.rstrip('/')}/subscription?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{payload.origin_url.rstrip('/')}/subscription",
            metadata=metadata,
            subscription_data={"metadata": metadata},
            allow_promotion_codes=True,
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe error: {str(e)}")

    # Store a pending subscription record
    amount = tier["annual_price"] if payload.billing_cycle == "annual" else tier["monthly_price"]
    sub_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "user_id": current_user["id"],
        "user_email": current_user["email"],
        "plan_id": tier["id"],
        "plan_name": tier["name"],
        "billing_cycle": payload.billing_cycle,
        "amount": float(amount),
        "currency": "usd",
        "session_id": session.id,
        "stripe_customer_id": customer_id,
        "stripe_subscription_id": "",
        "stripe_price_id": price_id,
        "status": "pending",
        "payment_status": "unpaid",
        "provider": "stripe",
        "cancel_at_period_end": False,
        "created_at": now_iso(),
        "activated_at": None,
        "expires_at": None,
        "cancelled_at": None,
        "current_period_end": None,
    }
    await subscriptions_collection.insert_one(sub_doc.copy())
    return {"url": session.url, "session_id": session.id}


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

    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
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
        # Retrieve the Stripe subscription to get period end
        try:
            stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
            period_end = datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc)
            update_payload["current_period_end"] = period_end.isoformat()
            update_payload["expires_at"] = period_end.isoformat()
        except Exception:
            # Fallback
            now = datetime.now(timezone.utc)
            period_end = now + (timedelta(days=365) if sub_doc.get("billing_cycle") == "annual" else timedelta(days=30))
            update_payload["current_period_end"] = period_end.isoformat()
            update_payload["expires_at"] = period_end.isoformat()

        update_payload["status"] = "active"
        update_payload["activated_at"] = now_iso()

        # Supersede any other active subs for this community
        await subscriptions_collection.update_many(
            {"community_id": current_user["community_id"], "status": "active", "session_id": {"$ne": session_id}},
            {"$set": {"status": "superseded"}},
        )

        # Send welcome email
        try:
            from email_service import send_subscription_welcome
            await send_subscription_welcome(
                email=sub_doc.get("user_email", current_user.get("email", "")),
                plan_name=sub_doc.get("plan_name", ""),
                billing_cycle=sub_doc.get("billing_cycle", "monthly"),
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

    # Cancel on Stripe (at period end — user keeps access until then)
    stripe_sub_id = sub.get("stripe_subscription_id", "")
    if stripe_sub_id and sub.get("provider") == "stripe":
        stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
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

    stripe_sub_id = sub.get("stripe_subscription_id", "")
    if stripe_sub_id and sub.get("provider") == "stripe":
        stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
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
    """Create a Stripe Customer Portal session for managing payment methods and invoices."""
    ensure_minimum_role(current_user, "host")
    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")

    customer_id = await _get_or_create_stripe_customer(current_user)
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
    sub = await subscriptions_collection.find_one(
        {"community_id": current_user["community_id"], "status": {"$in": ["active", "canceling"]}}, {"_id": 0}
    )
    tier = get_community_tier(sub)
    limits = tier.get("limits", {})
    allowed = limits.get(feature_key, False)
    return {"feature_key": feature_key, "allowed": allowed, "tier_id": tier["id"], "tier_name": tier["name"]}


# ---------------------------------------------------------------------------
# Admin: one-time Stripe product/price setup (REMOVE after initial run)
# ---------------------------------------------------------------------------

SETUP_TIERS = [
    {"id": "sapling", "name": "Kindred Sapling", "desc": "Growing communities — up to 25 members.", "monthly_cents": 999, "annual_cents": 8999},
    {"id": "oak", "name": "Kindred Oak", "desc": "Mid-size communities — up to 50 members.", "monthly_cents": 1999, "annual_cents": 17999},
    {"id": "redwood", "name": "Kindred Redwood", "desc": "Large communities — up to 100 members.", "monthly_cents": 3999, "annual_cents": 35999},
]


@router.post("/subscriptions/admin/setup-stripe-products")
async def setup_stripe_products(current_user: dict[str, Any] = Depends(get_current_user)):
    """One-time admin endpoint: create Stripe Products and recurring Prices.

    Returns the env vars to set in Railway. REMOVE this endpoint after use.
    """
    ensure_minimum_role(current_user, "host")
    # Extra safety: only the platform admin can run this
    admin_email = os.environ.get("PLATFORM_ADMIN_EMAIL", "")
    if current_user.get("email") != admin_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only platform admin can run setup.")

    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
    if not stripe.api_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="STRIPE_API_KEY not set.")

    env_vars = {}
    created = []

    for tier in SETUP_TIERS:
        product = stripe.Product.create(
            name=tier["name"],
            description=tier["desc"],
            metadata={"kindred_tier": tier["id"]},
        )

        monthly_price = stripe.Price.create(
            product=product.id,
            unit_amount=tier["monthly_cents"],
            currency="usd",
            recurring={"interval": "month"},
            metadata={"kindred_tier": tier["id"], "billing_cycle": "monthly"},
        )

        annual_price = stripe.Price.create(
            product=product.id,
            unit_amount=tier["annual_cents"],
            currency="usd",
            recurring={"interval": "year"},
            metadata={"kindred_tier": tier["id"], "billing_cycle": "annual"},
        )

        env_vars[f"STRIPE_PRICE_{tier['id'].upper()}_MONTHLY"] = monthly_price.id
        env_vars[f"STRIPE_PRICE_{tier['id'].upper()}_ANNUAL"] = annual_price.id
        created.append({
            "tier": tier["id"],
            "product_id": product.id,
            "monthly_price_id": monthly_price.id,
            "annual_price_id": annual_price.id,
        })

    return {"status": "success", "env_vars": env_vars, "created": created}


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

    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
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
