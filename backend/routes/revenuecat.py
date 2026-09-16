"""RevenueCat billing integration routes for mobile app store purchases."""

import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from db import subscriptions_collection, users_collection
from dependencies import get_current_user, now_iso
from pricing import (
    REVENUECAT_ENTITLEMENT_TO_TIER,
    SUBSCRIPTION_TIERS,
    revenuecat_billing_mapping,
    revenuecat_product_mapping,
)
from subscription_lifecycle import (
    resolve_revenuecat_webhook_purchase,
    should_apply_provider_event,
)

router = APIRouter(prefix="/api")

REVENUECAT_WEBHOOK_SECRET = os.environ.get("REVENUECAT_WEBHOOK_SECRET", "")

ENTITLEMENT_TO_TIER = REVENUECAT_ENTITLEMENT_TO_TIER


def _resolve_webhook_purchase(event: dict) -> tuple[str, str, str, str]:
    try:
        return resolve_revenuecat_webhook_purchase(event)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


def _revenuecat_event_identity(event: dict) -> tuple[str, int]:
    event_id = event.get("id")
    event_timestamp_ms = event.get("event_timestamp_ms")
    if (
        not isinstance(event_id, str)
        or not event_id
        or not isinstance(event_timestamp_ms, int)
    ):
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
    current = await subscriptions_collection.find_one(
        {"user_id": app_user_id}, {"_id": 0}
    )
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid RevenueCat webhook authorization.",
        )
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
        active_tier, billing_interval, entitlement_id, expires_at = (
            _resolve_webhook_purchase(event)
        )
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
    elif event_type in {
        "CANCELLATION",
        "SUBSCRIPTION_PAUSED",
        "BILLING_ISSUE",
        "EXPIRATION",
    }:
        _, _, _, expires_at = _resolve_webhook_purchase(event)
        current = await subscriptions_collection.find_one(
            {"user_id": app_user_id}, {"_id": 0}
        )
        if not current or current.get("revenuecat_product_id") != event.get(
            "product_id"
        ):
            return {
                "status": "ignored",
                "reason": "event does not match the active product",
            }

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


BUNDLE_ID = "com.ubuntumarket.kindred"


# The SDK asks by client platform; the catalog is keyed by store.
_PLATFORM_STORE = {"ios": "app_store", "android": "play_store", "web": "web"}


@router.get("/revenuecat/config")
async def revenuecat_config(platform: str = "ios"):
    """Return SDK configuration for the Kindred app.

    The platform decides which store's product identifiers come back. This used
    to be hardcoded to iOS, which left an Android client holding App Store
    identifiers — they match nothing in the Play offering, so every purchase
    fails to resolve. Defaults to ios so older clients are unaffected.
    """
    store = _PLATFORM_STORE.get((platform or "").strip().lower())
    if not store:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown platform '{platform}' — expected ios, android or web",
        )
    return {
        "bundle_id": BUNDLE_ID,
        "platform": platform,
        "entitlement_ids": list(ENTITLEMENT_TO_TIER.keys()),
        "tier_mapping": ENTITLEMENT_TO_TIER,
        "product_mapping": revenuecat_product_mapping(store),
        "webhook_url": "/api/revenuecat/webhook",
    }


@router.get("/revenuecat/web-catalog")
async def revenuecat_web_catalog(
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Return the canonical RevenueCat Billing (web) catalog.

    The web SDK validates the live offering / package / product it fetches from
    RevenueCat against this catalog (product + offering + package + entitlement
    ids, amount, currency, interval) and refuses to purchase on any mismatch.

    Catalog data only — no gateway is contacted and no charge is created here.
    Web purchases stay inert until the deployment configures the RevenueCat
    Billing public key on the client; this endpoint never enables a charge.
    """
    return {"catalog": revenuecat_billing_mapping()}
