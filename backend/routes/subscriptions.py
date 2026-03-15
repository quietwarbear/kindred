"""Subscription routes."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest
from fastapi import APIRouter, Depends, HTTPException, Request, status

from db import subscriptions_collection, subyards_collection, users_collection
from dependencies import (
    SUBSCRIPTION_TIERS,
    TIER_ORDER,
    build_stripe_checkout,
    ensure_minimum_role,
    get_community_tier,
    get_current_user,
    now_iso,
)
from models import SubscriptionCheckoutRequest

router = APIRouter(prefix="/api")


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
        {"community_id": current_user["community_id"], "status": "active"}, {"_id": 0}
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

    amount = tier["annual_price"] if payload.billing_cycle == "annual" else tier["monthly_price"]
    stripe_checkout = build_stripe_checkout(request)
    checkout_request = CheckoutSessionRequest(
        amount=float(amount),
        currency="usd",
        success_url=f"{payload.origin_url.rstrip('/')}/subscription?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{payload.origin_url.rstrip('/')}/subscription",
        metadata={
            "type": "subscription",
            "community_id": current_user["community_id"],
            "user_id": current_user["id"],
            "user_email": current_user["email"],
            "plan_id": tier["id"],
            "plan_name": tier["name"],
            "billing_cycle": payload.billing_cycle,
        },
    )
    session = await stripe_checkout.create_checkout_session(checkout_request)

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
        "session_id": session.session_id,
        "status": "pending",
        "payment_status": "unpaid",
        "created_at": now_iso(),
        "activated_at": None,
        "expires_at": None,
        "cancelled_at": None,
    }
    await subscriptions_collection.insert_one(sub_doc.copy())
    return {"url": session.url, "session_id": session.session_id}


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

    stripe_checkout = build_stripe_checkout(request)
    checkout_status = await stripe_checkout.get_checkout_status(session_id)

    update_payload = {
        "payment_status": checkout_status.payment_status,
    }

    if checkout_status.payment_status == "paid" and sub_doc.get("status") != "active":
        now = datetime.now(timezone.utc)
        if sub_doc.get("billing_cycle") == "annual":
            expires = now + timedelta(days=365)
        else:
            expires = now + timedelta(days=30)

        update_payload["status"] = "active"
        update_payload["activated_at"] = now.isoformat()
        update_payload["expires_at"] = expires.isoformat()

        await subscriptions_collection.update_many(
            {"community_id": current_user["community_id"], "status": "active", "session_id": {"$ne": session_id}},
            {"$set": {"status": "superseded"}},
        )

    await subscriptions_collection.update_one({"session_id": session_id}, {"$set": update_payload})
    updated = await subscriptions_collection.find_one({"session_id": session_id}, {"_id": 0})
    return {
        "status": checkout_status.status,
        "payment_status": checkout_status.payment_status,
        "subscription": updated,
    }


@router.post("/subscriptions/cancel")
async def cancel_subscription(current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "host")
    sub = await subscriptions_collection.find_one(
        {"community_id": current_user["community_id"], "status": "active"}, {"_id": 0}
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active subscription to cancel.")
    await subscriptions_collection.update_one(
        {"id": sub["id"]},
        {"$set": {"status": "cancelled", "cancelled_at": now_iso()}},
    )
    return {"status": "cancelled", "message": f"Your {sub['plan_name']} plan has been cancelled. You'll retain access until {sub.get('expires_at', 'the end of your billing period')}."}


@router.get("/subscriptions/feature-check/{feature_key}")
async def check_feature_access(feature_key: str, current_user: dict[str, Any] = Depends(get_current_user)):
    sub = await subscriptions_collection.find_one(
        {"community_id": current_user["community_id"], "status": "active"}, {"_id": 0}
    )
    tier = get_community_tier(sub)
    limits = tier.get("limits", {})
    allowed = limits.get(feature_key, False)
    return {"feature_key": feature_key, "allowed": allowed, "tier_id": tier["id"], "tier_name": tier["name"]}


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

    stripe_checkout = build_stripe_checkout(request)
    checkout_request = CheckoutSessionRequest(
        amount=float(addon["price_cents"] / 100),
        currency="usd",
        success_url=f"{origin_url}?addon_success={addon_id}",
        cancel_url=f"{origin_url}?addon_cancel=1",
        metadata={
            "type": "addon",
            "user_id": current_user["id"],
            "community_id": current_user["community_id"],
            "addon_id": addon_id,
            "addon_name": addon["name"],
        },
    )
    session = await stripe_checkout.create_checkout_session(checkout_request)
    return {"checkout_url": session.url, "session_id": session.session_id}


@router.get("/addons/purchased")
async def list_purchased_addons(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return add-ons purchased by this community."""
    from db import payments_collection
    purchases = await payments_collection.find(
        {"community_id": current_user["community_id"], "metadata.type": "addon"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"purchases": purchases}
