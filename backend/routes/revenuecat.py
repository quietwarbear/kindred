"""RevenueCat billing integration routes for mobile app store purchases."""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from db import subscriptions_collection, users_collection
from dependencies import get_current_user, now_iso

router = APIRouter(prefix="/api")

REVENUECAT_API_KEY = os.environ.get("REVENUECAT_API_KEY", "")
REVENUECAT_WEBHOOK_SECRET = os.environ.get("REVENUECAT_WEBHOOK_SECRET", "")

# Map RevenueCat entitlement IDs to our internal tier names
ENTITLEMENT_TO_TIER = {
    "seedling": "seedling",
    "sapling": "sapling",
    "oak": "oak",
    "redwood": "redwood",
    "elder_grove": "elder_grove",
    "premium": "oak",
}


@router.post("/revenuecat/webhook")
async def revenuecat_webhook(request: Request):
    """Handle RevenueCat webhook events for mobile purchases."""
    body = await request.json()
    event = body.get("event", {})
    event_type = event.get("type", "")
    app_user_id = event.get("app_user_id", "")

    if not app_user_id:
        return {"status": "ignored", "reason": "no app_user_id"}

    user_doc = await users_collection.find_one({"id": app_user_id}, {"_id": 0})
    if not user_doc:
        return {"status": "ignored", "reason": "user not found"}

    entitlements = event.get("subscriber", {}).get("entitlements", {})
    active_tier = "seedling"
    expires_at = ""
    for ent_id, ent_data in entitlements.items():
        if ent_data.get("expires_date"):
            mapped_tier = ENTITLEMENT_TO_TIER.get(ent_id, "seedling")
            active_tier = mapped_tier
            expires_at = ent_data["expires_date"]
            break

    if event_type in ("INITIAL_PURCHASE", "RENEWAL", "PRODUCT_CHANGE"):
        await subscriptions_collection.update_one(
            {"user_id": app_user_id},
            {
                "$set": {
                    "user_id": app_user_id,
                    "tier": active_tier,
                    "status": "active",
                    "provider": "revenuecat",
                    "store": event.get("store", "unknown"),
                    "current_period_end": expires_at,
                    "revenuecat_product_id": event.get("product_id", ""),
                    "updated_at": now_iso(),
                }
            },
            upsert=True,
        )
    elif event_type in ("CANCELLATION", "EXPIRATION"):
        await subscriptions_collection.update_one(
            {"user_id": app_user_id},
            {"$set": {"status": "canceled", "updated_at": now_iso()}},
        )
    elif event_type == "BILLING_ISSUE":
        await subscriptions_collection.update_one(
            {"user_id": app_user_id},
            {"$set": {"status": "past_due", "updated_at": now_iso()}},
        )

    return {"status": "ok"}


@router.post("/revenuecat/validate")
async def validate_mobile_receipt(
    body: dict,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Validate a mobile purchase receipt and update subscription status.
    Called from mobile app after a purchase is made via RevenueCat SDK.
    """
    import httpx

    if not REVENUECAT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RevenueCat integration not configured.",
        )

    app_user_id = current_user["id"]
    url = f"https://api.revenuecat.com/v1/subscribers/{app_user_id}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {REVENUECAT_API_KEY}"})

    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to validate receipt with RevenueCat.")

    subscriber = resp.json().get("subscriber", {})
    entitlements = subscriber.get("entitlements", {})

    active_tier = "seedling"
    expires_at = ""
    for ent_id, ent_data in entitlements.items():
        if ent_data.get("expires_date"):
            mapped = ENTITLEMENT_TO_TIER.get(ent_id, "seedling")
            active_tier = mapped
            expires_at = ent_data["expires_date"]
            break

    await subscriptions_collection.update_one(
        {"user_id": app_user_id},
        {
            "$set": {
                "user_id": app_user_id,
                "tier": active_tier,
                "status": "active" if entitlements else "free",
                "provider": "revenuecat",
                "current_period_end": expires_at,
                "updated_at": now_iso(),
            }
        },
        upsert=True,
    )

    return {
        "tier": active_tier,
        "status": "active" if entitlements else "free",
        "expires_at": expires_at,
        "entitlements": list(entitlements.keys()),
    }


@router.get("/revenuecat/status")
async def revenuecat_status(current_user: dict[str, Any] = Depends(get_current_user)):
    """Check if RevenueCat integration is configured."""
    return {
        "configured": bool(REVENUECAT_API_KEY),
        "webhook_configured": bool(REVENUECAT_WEBHOOK_SECRET),
    }


BUNDLE_ID = "com.ubuntumarket.kindred"


@router.get("/revenuecat/offerings")
async def revenuecat_offerings(current_user: dict[str, Any] = Depends(get_current_user)):
    """Fetch current product offerings from RevenueCat for display in mobile app."""
    import httpx

    if not REVENUECAT_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RevenueCat not configured.")

    app_user_id = current_user["id"]
    url = f"https://api.revenuecat.com/v1/subscribers/{app_user_id}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={
            "Authorization": f"Bearer {REVENUECAT_API_KEY}",
            "X-Platform": "ios",
        })

    if resp.status_code == 404:
        # Create subscriber on first fetch
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={
                "Authorization": f"Bearer {REVENUECAT_API_KEY}",
                "X-Platform": "ios",
            })

    if resp.status_code != 200:
        return {"offerings": [], "subscriber": {}, "error": "Unable to fetch from RevenueCat."}

    data = resp.json()
    subscriber = data.get("subscriber", {})
    return {
        "subscriber": {
            "entitlements": subscriber.get("entitlements", {}),
            "subscriptions": subscriber.get("subscriptions", {}),
            "non_subscriptions": subscriber.get("non_subscriptions", {}),
            "first_seen": subscriber.get("first_seen", ""),
        },
        "bundle_id": BUNDLE_ID,
    }


@router.post("/revenuecat/restore")
async def restore_purchases(current_user: dict[str, Any] = Depends(get_current_user)):
    """Restore purchases for a user (called after app reinstall)."""
    import httpx

    if not REVENUECAT_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RevenueCat not configured.")

    app_user_id = current_user["id"]
    url = f"https://api.revenuecat.com/v1/subscribers/{app_user_id}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {REVENUECAT_API_KEY}"})

    if resp.status_code != 200:
        return {"restored": False, "error": "Unable to fetch subscriber data."}

    subscriber = resp.json().get("subscriber", {})
    entitlements = subscriber.get("entitlements", {})

    active_tier = "seedling"
    expires_at = ""
    for ent_id, ent_data in entitlements.items():
        if ent_data.get("expires_date"):
            mapped = ENTITLEMENT_TO_TIER.get(ent_id, "seedling")
            active_tier = mapped
            expires_at = ent_data["expires_date"]
            break

    if entitlements:
        await subscriptions_collection.update_one(
            {"user_id": app_user_id},
            {
                "$set": {
                    "user_id": app_user_id,
                    "tier": active_tier,
                    "status": "active",
                    "provider": "revenuecat",
                    "current_period_end": expires_at,
                    "updated_at": now_iso(),
                }
            },
            upsert=True,
        )

    return {
        "restored": bool(entitlements),
        "tier": active_tier,
        "status": "active" if entitlements else "free",
        "entitlements": list(entitlements.keys()),
    }


@router.get("/revenuecat/config")
async def revenuecat_config():
    """Return mobile SDK configuration for the Kindred app."""
    return {
        "bundle_id": BUNDLE_ID,
        "platform": "ios",
        "entitlement_ids": list(ENTITLEMENT_TO_TIER.keys()),
        "tier_mapping": ENTITLEMENT_TO_TIER,
        "webhook_url": "/api/revenuecat/webhook",
    }
