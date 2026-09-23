"""Reunion Pass — one payment, twelve months, no member cap.

The pass is bought by the host and can be funded by the family (Phase 3). It
is not a subscription: mode is "payment", nothing auto-renews, and the
entitlement it writes carries a fixed end date.

Only a host can buy one. That is not a permissions detail, it is the product:
the pass covers a Circle, not a person, and entitlement resolves against the
buyer's ACTIVE community. A member who wants their own gathering starts their
own Circle — the data model supports belonging to several.
"""

import logging
import os
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from db import subscriptions_collection
from dependencies import ensure_minimum_role, get_current_user, now_iso
from pricing import (
    REUNION_PASS,
    REUNION_PASS_PLAN_ID,
    reunion_pass_price_cents,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class ReunionPassCheckoutRequest(BaseModel):
    origin_url: str = Field(default="", max_length=300)
    ga_client_id: str = Field(default="", max_length=120)


@router.post("/reunion-pass/checkout")
async def create_reunion_pass_checkout(
    payload: ReunionPassCheckoutRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "host")

    stripe_key = os.environ.get("STRIPE_API_KEY", "")
    if not stripe_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payments are not configured.",
        )
    stripe.api_key = stripe_key

    community_id = current_user.get("community_id") or ""
    if not community_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start a gathering before buying a Reunion Pass.",
        )

    existing = await subscriptions_collection.find_one(
        {"community_id": community_id, "plan_id": REUNION_PASS_PLAN_ID, "status": "active"},
        {"_id": 0, "expires_at": 1},
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This family already holds a Reunion Pass.",
        )

    origin = (payload.origin_url or "").rstrip("/") or os.environ.get("APP_URL", "")
    metadata = {
        "kind": "reunion_pass",
        "community_id": community_id,
        "user_id": current_user["id"],
        "user_email": current_user.get("email", ""),
        "ga_client_id": payload.ga_client_id or current_user.get("ga_client_id") or "",
    }

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": REUNION_PASS["currency"],
                        "unit_amount": reunion_pass_price_cents(),
                        "product_data": {
                            "name": REUNION_PASS["name"],
                            "description": REUNION_PASS["tagline"],
                        },
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{origin}/subscription?pass=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/subscription?pass=cancelled",
            metadata=metadata,
        )
    except Exception:
        logger.exception("Reunion Pass checkout could not be created for %s", community_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not start checkout. Please try again.",
        )

    # Pending row, so a completed session has something to match against and a
    # duplicate purchase is visible before the webhook lands.
    await subscriptions_collection.insert_one(
        {
            "community_id": community_id,
            "user_id": current_user["id"],
            "plan_id": REUNION_PASS_PLAN_ID,
            "provider": "stripe",
            "status": "pending",
            "session_id": session.id,
            "amount": REUNION_PASS["amount"],
            "currency": REUNION_PASS["currency"],
            "auto_renews": False,
            "created_at": now_iso(),
        }
    )

    return {"url": session.url, "session_id": session.id}
