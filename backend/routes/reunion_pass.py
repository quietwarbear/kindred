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

from db import payments_collection, subscriptions_collection
from dependencies import ensure_minimum_role, get_current_user, now_iso
from reunion_pass_ledger import (
    CHIP_IN_PACKAGE_ID,
    MIN_CHIP_IN_CENTS,
    activate_reunion_pass,
    active_pass_for,
    capped_contribution,
    contributed_cents,
    remaining_cents,
)
from pricing import (
    REUNION_PASS,
    REUNION_PASS_PLAN_ID,
    reunion_pass_expires_at,
    reunion_pass_price_cents,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class ReunionPassCheckoutRequest(BaseModel):
    origin_url: str = Field(default="", max_length=300)
    ga_client_id: str = Field(default="", max_length=120)


class ChipInRequest(BaseModel):
    amount_cents: int = Field(ge=MIN_CHIP_IN_CENTS, le=1000000)
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


@router.get("/reunion-pass/status")
async def reunion_pass_status(current_user: dict[str, Any] = Depends(get_current_user)):
    """What the whole family sees: the price, what is in, what is left.

    Readable by any member, not just the host — the point of chip-in is that
    the family can see the goal they are funding.
    """
    community_id = current_user.get("community_id") or ""
    price = reunion_pass_price_cents()
    if not community_id:
        return {"price_cents": price, "contributed_cents": 0, "remaining_cents": price,
                "active": False, "expires_at": None}

    active = await active_pass_for(subscriptions_collection, community_id, REUNION_PASS_PLAN_ID)
    contributed = await contributed_cents(payments_collection, community_id)
    return {
        "price_cents": price,
        "contributed_cents": contributed,
        "remaining_cents": max(price - contributed, 0),
        "active": bool(active),
        "expires_at": (active or {}).get("expires_at"),
        "can_buy": current_user.get("role") == "host",
    }


@router.post("/reunion-pass/chip-in")
async def chip_in_to_reunion_pass(
    payload: ChipInRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Any member can put money toward the family's pass.

    Deliberately NOT host-gated. Reunions run on committees and budgets, and
    the organizer is rarely the one who should absorb the cost. The host still
    HOLDS the pass — this only changes who can pay for it.
    """
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
            detail="Join a family before chipping in.",
        )

    if await active_pass_for(subscriptions_collection, community_id, REUNION_PASS_PLAN_ID):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This family already holds a Reunion Pass.",
        )

    remaining = remaining_cents(
        reunion_pass_price_cents(), await contributed_cents(payments_collection, community_id)
    )
    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This pass is already fully funded.",
        )

    # Capped at what is left rather than accepting the overage and owing a
    # refund or a quiet transfer to another fund. Nobody is charged for more
    # than the family still needs.
    amount_cents = capped_contribution(payload.amount_cents, remaining)

    origin = (payload.origin_url or "").rstrip("/") or os.environ.get("APP_URL", "")
    metadata = {
        "kind": "reunion_pass_chip_in",
        "community_id": community_id,
        "user_id": current_user["id"],
        "user_email": current_user.get("email", ""),
        "package_id": CHIP_IN_PACKAGE_ID,
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
                        "unit_amount": amount_cents,
                        "product_data": {
                            "name": f"Toward the {REUNION_PASS['name']}",
                            "description": "A contribution to your family's Reunion Pass.",
                        },
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{origin}/subscription?chip_in=thanks&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/subscription?chip_in=cancelled",
            metadata=metadata,
        )
    except Exception:
        logger.exception("Chip-in checkout failed for community=%s", community_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not start checkout. Please try again.",
        )

    await payments_collection.insert_one(
        {
            "community_id": community_id,
            "user_id": current_user["id"],
            "user_email": current_user.get("email", ""),
            "package_id": CHIP_IN_PACKAGE_ID,
            "contribution_label": f"Toward the {REUNION_PASS['name']}",
            "amount": amount_cents / 100,
            "amount_cents": amount_cents,
            "currency": REUNION_PASS["currency"],
            "session_id": session.id,
            "status": "pending",
            "payment_status": "unpaid",
            "metadata": metadata,
            "created_at": now_iso(),
        }
    )

    return {"url": session.url, "session_id": session.id, "amount_cents": amount_cents}
