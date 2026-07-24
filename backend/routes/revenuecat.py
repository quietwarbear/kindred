"""RevenueCat billing integration routes for mobile app store purchases."""

import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from db import subscriptions_collection, users_collection
from dependencies import get_current_user, now_iso
from pricing import (
    REVENUECAT_ENTITLEMENT_TO_TIER,
    REVENUECAT_PRODUCT_IDS,
    SUBSCRIPTION_TIERS,
)
from subscription_lifecycle import (
    resolve_revenuecat_subscriber,
    resolve_revenuecat_webhook_purchase,
    should_apply_provider_event,
)

router = APIRouter(prefix="/api")

REVENUECAT_API_KEY = os.environ.get("REVENUECAT_API_KEY", "")
REVENUECAT_WEBHOOK_SECRET = os.environ.get("REVENUECAT_WEBHOOK_SECRET", "")

ENTITLEMENT_TO_TIER = REVENUECAT_ENTITLEMENT_TO_TIER


def _resolve_paid_purchase(subscriber: dict) -> Optional[tuple[str, str, str, str, str]]:
    return resolve_revenuecat_subscriber(subscriber)


def _resolve_webhook_purchase(event: dict) -> tuple[str, str, str, str]:
    try:
        return resolve_revenuecat_webhook_purchase(event)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _revenuecat_event_identity(event: dict) -> tuple[str, int]:
    event_id = event.get("id")
    event_timestamp_ms = event.get("event_timestamp_ms")
    if not isinstance(event_id, str) or not event_id or not isinstance(event_timestamp_ms, int):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RevenueCat lifecycle event is missing its id or timestamp.",
        )
    return event_id, event_timestamp_ms


async def _apply_revenuecat_event(
    app_user_id: str,
    event: dict,
    values: dict,
    *,
    upsert: bool = False,
) -> bool:
    """Apply one event only when it is not older than stored provider state."""
    event_id, event_timestamp_ms = _revenuecat_event_identity(event)
    current = await subscriptions_collection.find_one({"user_id": app_user_id}, {"_id": 0})
    if current and current.get("revenuecat_event_id") == event_id:
        return False
    if current and not should_apply_provider_event(
        current.get("revenuecat_event_timestamp_ms"),
        event_timestamp_ms,
    ):
        return False
    if not current and not upsert:
        return False

    query = {
        "user_id": app_user_id,
        "revenuecat_event_id": {"$ne": event_id},
        "$or": [
            {"revenuecat_event_timestamp_ms": {"$exists": False}},
            {"revenuecat_event_timestamp_ms": {"$lte": event_timestamp_ms}},
        ],
    }
    event_values = {
        **values,
        "revenuecat_event_id": event_id,
        "revenuecat_event_timestamp_ms": event_timestamp_ms,
        "updated_at": now_iso(),
    }
    result = await subscriptions_collection.update_one(
        query,
        {"$set": event_values},
        upsert=upsert and current is None,
    )
    return bool(result.matched_count or result.upserted_id)


@router.post("/revenuecat/webhook")
async def revenuecat_webhook(request: Request):
    """Handle RevenueCat webhook events for mobile purchases."""
    if not REVENUECAT_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RevenueCat webhook verification is not configured.",
        )
    authorization = request.headers.get("authorization", "")
    if authorization != f"Bearer {REVENUECAT_WEBHOOK_SECRET}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid RevenueCat webhook authorization.")
    body = await request.json()
    event = body.get("event", {})
    event_type = event.get("type", "")
    app_user_id = event.get("app_user_id", "")

    if not app_user_id:
        return {"status": "ignored", "reason": "no app_user_id"}

    user_doc = await users_collection.find_one({"id": app_user_id}, {"_id": 0})
    if not user_doc:
        return {"status": "ignored", "reason": "user not found"}

    effective_events = {
        "INITIAL_PURCHASE",
        "RENEWAL",
        "UNCANCELLATION",
        "SUBSCRIPTION_EXTENDED",
        "REFUND_REVERSED",
    }
    if event_type in effective_events:
        active_tier, billing_interval, entitlement_id, expires_at = _resolve_webhook_purchase(event)
        applied = await _apply_revenuecat_event(
            app_user_id,
            event,
            {
                "user_id": app_user_id,
                "community_id": user_doc["community_id"],
                "plan_id": active_tier,
                "plan_name": SUBSCRIPTION_TIERS[active_tier]["name"],
                "status": "active",
                "provider": "revenuecat",
                "billing_cycle": billing_interval,
                "store": event.get("store", "unknown"),
                "current_period_end": expires_at,
                "revenuecat_product_id": event.get("product_id", ""),
                "revenuecat_entitlement_id": entitlement_id,
            },
            upsert=True,
        )
        if not applied:
            return {"status": "ignored", "reason": "stale event"}
    elif event_type in {"CANCELLATION", "SUBSCRIPTION_PAUSED", "BILLING_ISSUE", "EXPIRATION"}:
        _, _, _, expires_at = _resolve_webhook_purchase(event)
        current = await subscriptions_collection.find_one({"user_id": app_user_id}, {"_id": 0})
        if not current or current.get("revenuecat_product_id") != event.get("product_id"):
            return {"status": "ignored", "reason": "event does not match the active product"}

        if event_type == "EXPIRATION":
            values = {"status": "canceled", "current_period_end": expires_at}
        elif event_type == "BILLING_ISSUE":
            grace_at_ms = event.get("grace_period_expiration_at_ms")
            grace_at = (
                datetime.fromtimestamp(grace_at_ms / 1000, tz=timezone.utc).isoformat()
                if isinstance(grace_at_ms, (int, float))
                else expires_at
            )
            values = {"status": "past_due", "grace_period_expires_at": grace_at}
        else:
            values = {"status": "canceling", "current_period_end": expires_at}

        applied = await _apply_revenuecat_event(app_user_id, event, values)
        if not applied:
            return {"status": "ignored", "reason": "stale event"}

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
    try:
        purchase = _resolve_paid_purchase(subscriber)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    active_tier = purchase[0] if purchase else "seedling"
    billing_interval = purchase[1] if purchase else None
    entitlement_id = purchase[2] if purchase else None
    product_id = purchase[3] if purchase else None
    expires_at = purchase[4] if purchase else ""
    purchase_status = "active" if purchase else "free"

    subscription_values = {
        "user_id": app_user_id,
        "community_id": current_user["community_id"],
        "plan_id": active_tier,
        "plan_name": SUBSCRIPTION_TIERS[active_tier]["name"],
        "status": purchase_status,
        "provider": "revenuecat",
        "current_period_end": expires_at,
        "updated_at": now_iso(),
    }
    if purchase:
        subscription_values.update(
            {
                "billing_cycle": billing_interval,
                "revenuecat_product_id": product_id,
                "revenuecat_entitlement_id": entitlement_id,
            }
        )
    update_document = {"$set": subscription_values}
    if not purchase:
        update_document["$unset"] = {
            "billing_cycle": "",
            "revenuecat_product_id": "",
            "revenuecat_entitlement_id": "",
        }
    await subscriptions_collection.update_one(
        {"user_id": app_user_id},
        update_document,
        upsert=True,
    )

    return {
        "tier": active_tier,
        "status": purchase_status,
        "billing_interval": billing_interval,
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
    try:
        purchase = _resolve_paid_purchase(subscriber)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    active_tier = purchase[0] if purchase else "seedling"
    billing_interval = purchase[1] if purchase else None
    entitlement_id = purchase[2] if purchase else None
    product_id = purchase[3] if purchase else None
    expires_at = purchase[4] if purchase else ""

    if purchase:
        await subscriptions_collection.update_one(
            {"user_id": app_user_id},
            {
                "$set": {
                    "user_id": app_user_id,
                    "community_id": current_user["community_id"],
                    "plan_id": active_tier,
                    "plan_name": SUBSCRIPTION_TIERS[active_tier]["name"],
                    "status": "active",
                    "provider": "revenuecat",
                    "billing_cycle": billing_interval,
                    "current_period_end": expires_at,
                    "revenuecat_product_id": product_id,
                    "revenuecat_entitlement_id": entitlement_id,
                    "updated_at": now_iso(),
                }
            },
            upsert=True,
        )
    else:
        await subscriptions_collection.update_one(
            {"user_id": app_user_id},
            {
                "$set": {
                    "user_id": app_user_id,
                    "community_id": current_user["community_id"],
                    "plan_id": "seedling",
                    "plan_name": SUBSCRIPTION_TIERS["seedling"]["name"],
                    "status": "free",
                    "provider": "revenuecat",
                    "current_period_end": "",
                    "updated_at": now_iso(),
                },
                "$unset": {
                    "billing_cycle": "",
                    "revenuecat_product_id": "",
                    "revenuecat_entitlement_id": "",
                },
            },
            upsert=True,
        )

    return {
        "restored": bool(purchase),
        "tier": active_tier,
        "status": "active" if purchase else "free",
        "billing_interval": billing_interval,
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
        "product_mapping": REVENUECAT_PRODUCT_IDS,
        "webhook_url": "/api/revenuecat/webhook",
    }
