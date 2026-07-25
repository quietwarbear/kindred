"""Finance routes: travel plans, budget plans, payments, funds overview."""

import os
import uuid
from typing import Any, Literal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status

import logging
from datetime import datetime, timezone

from db import budget_plans_collection, payments_collection, subscriptions_collection, travel_plans_collection, users_collection
from dependencies import (
    CONTRIBUTION_PACKAGES,
    SUBSCRIPTION_TIERS,
    ensure_minimum_role,
    get_current_user,
    now_iso,
    require_feature,
)
from models import BudgetCreateRequest, PaymentCheckoutRequest, TravelPlanCreateRequest
from pricing import (
    BILLING_ENVIRONMENT,
    billing_amount,
    resolve_stripe_price,
    stripe_api_key_matches_environment,
)
from subscription_lifecycle import PAID_ACCESS_STATUSES, should_apply_provider_event

router = APIRouter(prefix="/api")


def _configure_stripe() -> None:
    api_key = os.environ.get("STRIPE_API_KEY", "")
    if not stripe_api_key_matches_environment(api_key):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe billing credentials do not match the configured billing environment.",
        )
    stripe.api_key = api_key


def _stripe_event_identity(event: dict) -> tuple[str, int]:
    event_id = event.get("id")
    event_created = event.get("created")
    if not isinstance(event_id, str) or not event_id or not isinstance(event_created, int):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stripe lifecycle event is missing its id or timestamp.",
        )
    return event_id, event_created


async def _apply_stripe_subscription_event(
    query: dict,
    event: dict,
    values: dict,
) -> tuple[bool, dict]:
    """Apply a signed Stripe event once and reject stale state transitions."""
    event_id, event_created = _stripe_event_identity(event)
    current = await subscriptions_collection.find_one(query, {"_id": 0})
    if not current:
        return False, {}
    if current.get("stripe_event_id") == event_id:
        return False, current
    if not should_apply_provider_event(current.get("stripe_event_created"), event_created):
        return False, current

    guarded_query = {
        **query,
        "stripe_event_id": {"$ne": event_id},
        "$or": [
            {"stripe_event_created": {"$exists": False}},
            {"stripe_event_created": {"$lte": event_created}},
        ],
    }
    result = await subscriptions_collection.update_one(
        guarded_query,
        {
            "$set": {
                **values,
                "stripe_event_id": event_id,
                "stripe_event_created": event_created,
                "updated_at": now_iso(),
            }
        },
    )
    return bool(result.matched_count), current


@router.get("/travel-plans")
async def list_travel_plans(
    event_id: str = "",
    current_user: dict[str, Any] = Depends(get_current_user),
):
    query = {"community_id": current_user["community_id"]}
    if event_id:
        query["event_id"] = event_id
    plans = await travel_plans_collection.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"travel_plans": plans}


@router.post("/travel-plans")
async def create_travel_plan(payload: TravelPlanCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    await require_feature(current_user, "travel_coordination")
    plan_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "event_id": payload.event_id,
        "title": (payload.title or "").strip() or "Travel Plan",
        "travel_type": payload.travel_type,
        "details": (payload.details or "").strip(),
        "coordinator_name": (payload.coordinator_name or current_user["full_name"]).strip(),
        "amount_estimate": float(payload.amount_estimate),
        "payment_status": payload.payment_status,
        "seats_available": payload.seats_available,
        "traveler_name": (payload.traveler_name or current_user["full_name"]).strip(),
        "mode": payload.mode,
        "origin": (payload.origin or "").strip(),
        "departure_at": payload.departure_at,
        "arrival_at": payload.arrival_at,
        "notes": (payload.notes or "").strip(),
        "estimated_cost": float(payload.estimated_cost),
        "travelers": [current_user["full_name"]],
        "created_by": current_user["id"],
        "created_at": now_iso(),
    }
    await travel_plans_collection.insert_one(plan_doc.copy())
    return plan_doc


@router.post("/travel-plans/{plan_id}/assign-self")
async def assign_self_to_travel(plan_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    plan_doc = await travel_plans_collection.find_one({"id": plan_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not plan_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Travel plan not found.")
    travelers = plan_doc.get("travelers", [])
    if current_user["full_name"] in travelers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already assigned to this travel plan.")
    travelers.append(current_user["full_name"])
    await travel_plans_collection.update_one({"id": plan_id}, {"$set": {"travelers": travelers}})
    plan_doc["travelers"] = travelers
    return plan_doc


@router.put("/travel-plans/{plan_id}")
async def update_travel_plan(plan_id: str, payload: TravelPlanCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    plan_doc = await travel_plans_collection.find_one({"id": plan_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not plan_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Travel plan not found.")
    updates = {
        "title": (payload.title or plan_doc.get("title", "")).strip(),
        "travel_type": payload.travel_type or plan_doc.get("travel_type", "driving"),
        "details": (payload.details or "").strip(),
        "coordinator_name": (payload.coordinator_name or plan_doc.get("coordinator_name", "")).strip(),
        "amount_estimate": float(payload.amount_estimate),
        "payment_status": payload.payment_status,
        "seats_available": payload.seats_available,
        "mode": payload.mode or plan_doc.get("mode", "driving"),
        "origin": (payload.origin or "").strip(),
        "departure_at": payload.departure_at or plan_doc.get("departure_at", ""),
        "arrival_at": payload.arrival_at or plan_doc.get("arrival_at", ""),
        "notes": (payload.notes or "").strip(),
        "estimated_cost": float(payload.estimated_cost),
    }
    await travel_plans_collection.update_one({"id": plan_id}, {"$set": updates})
    plan_doc.update(updates)
    return plan_doc


@router.delete("/travel-plans/{plan_id}")
async def delete_travel_plan(plan_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    result = await travel_plans_collection.delete_one({"id": plan_id, "community_id": current_user["community_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Travel plan not found.")
    return {"ok": True}


@router.get("/budget-plans")
async def list_budget_plans(current_user: dict[str, Any] = Depends(get_current_user)):
    budgets = await budget_plans_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"budgets": budgets}


@router.post("/budget-plans")
async def create_budget_plan(payload: BudgetCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    await require_feature(current_user, "shared_funds")
    budget_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "title": payload.title.strip(),
        "target_amount": float(payload.target_amount),
        "current_amount": float(payload.current_amount),
        "suggested_contribution": float(payload.suggested_contribution),
        "budget_type": payload.budget_type,
        "event_id": payload.event_id,
        "notes": (payload.notes or "").strip(),
        "line_items": payload.line_items,
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "created_at": now_iso(),
    }
    await budget_plans_collection.insert_one(budget_doc.copy())
    return budget_doc


@router.put("/budget-plans/{budget_id}")
async def update_budget_plan(budget_id: str, payload: BudgetCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    doc = await budget_plans_collection.find_one({"id": budget_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget plan not found.")
    updates = {
        "title": payload.title.strip() or doc["title"],
        "target_amount": float(payload.target_amount),
        "current_amount": float(payload.current_amount),
        "suggested_contribution": float(payload.suggested_contribution),
        "budget_type": payload.budget_type or doc.get("budget_type", "event"),
        "notes": (payload.notes or "").strip(),
        "line_items": payload.line_items if payload.line_items else doc.get("line_items", []),
    }
    await budget_plans_collection.update_one({"id": budget_id}, {"$set": updates})
    doc.update(updates)
    return doc


@router.delete("/budget-plans/{budget_id}")
async def delete_budget_plan(budget_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    result = await budget_plans_collection.delete_one({"id": budget_id, "community_id": current_user["community_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget plan not found.")
    return {"ok": True}


@router.get("/payments/summary")
async def payment_summary(current_user: dict[str, Any] = Depends(get_current_user)):
    transactions = await payments_collection.find(
        {"community_id": current_user["community_id"]},
        {"_id": 0, "id": 1, "session_id": 1, "package_id": 1, "contribution_label": 1, "amount": 1, "currency": 1, "status": 1, "payment_status": 1, "user_email": 1, "created_at": 1, "completed_at": 1},
    ).sort("created_at", -1).to_list(200)
    paid_agg = await payments_collection.aggregate([
        {"$match": {"community_id": current_user["community_id"], "payment_status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    return {"transactions": transactions, "total_paid": round(paid_agg[0]["total"], 2) if paid_agg else 0.0, "packages": list(CONTRIBUTION_PACKAGES.values())}


@router.get("/funds-travel/overview")
async def funds_travel_overview(current_user: dict[str, Any] = Depends(get_current_user)):
    payment_summary_payload = await payment_summary(current_user)
    budgets = await budget_plans_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    travel_plans = await travel_plans_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    pending_travel_total = round(sum(item.get("amount_estimate", 0) for item in travel_plans), 2)
    return {**payment_summary_payload, "budgets": budgets, "travel_plans": travel_plans, "pending_travel_total": pending_travel_total}


@router.post("/payments/checkout/session")
async def create_checkout_session(
    payload: PaymentCheckoutRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    package = CONTRIBUTION_PACKAGES.get(payload.package_id)
    if not package:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contribution package.")

    _configure_stripe()
    metadata = {
        "community_id": current_user["community_id"],
        "user_id": current_user["id"],
        "user_email": current_user["email"],
        "package_id": package["id"],
        "contribution_label": package["label"],
    }

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": int(float(package["amount"]) * 100),
                        "product_data": {
                            "name": package["label"],
                            "description": package["description"],
                        },
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{payload.origin_url.rstrip('/')}/funds-travel?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{payload.origin_url.rstrip('/')}/funds-travel",
            metadata=metadata,
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe error: {str(e)}")

    transaction_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "user_id": current_user["id"],
        "user_email": current_user["email"],
        "package_id": package["id"],
        "contribution_label": package["label"],
        "amount": float(package["amount"]),
        "currency": "usd",
        "metadata": metadata,
        "session_id": session.id,
        "payment_id": "",
        "status": "initiated",
        "payment_status": "unpaid",
        "created_at": now_iso(),
        "completed_at": None,
    }
    await payments_collection.insert_one(transaction_doc.copy())
    return {"url": session.url, "session_id": session.id}


@router.get("/payments/checkout/status/{session_id}")
async def get_checkout_status(session_id: str, request: Request, current_user: dict[str, Any] = Depends(get_current_user)):
    transaction_doc = await payments_collection.find_one({"session_id": session_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not transaction_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment session not found.")

    _configure_stripe()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkout session not found.")

    # Map Stripe payment_status to our payment_status
    payment_status = "unpaid"
    if session.payment_status == "paid":
        payment_status = "paid"

    update_payload = {
        "status": session.status,
        "payment_status": payment_status,
        "amount": transaction_doc.get("amount", 0),
        "currency": transaction_doc.get("currency", "usd"),
    }
    if payment_status == "paid" and not transaction_doc.get("completed_at"):
        update_payload["completed_at"] = now_iso()
    await payments_collection.update_one({"session_id": session_id}, {"$set": update_payload})
    updated_transaction = await payments_collection.find_one({"session_id": session_id}, {"_id": 0})
    return {
        "status": session.status,
        "payment_status": payment_status,
        "amount_total": session.amount_total and session.amount_total / 100 or 0,
        "currency": session.currency,
        "metadata": session.metadata,
        "transaction": updated_transaction,
    }


logger = logging.getLogger(__name__)


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for both one-time payments and recurring subscriptions.

    Supported events:
      - checkout.session.completed  (one-time payments & initial subscription activation)
      - invoice.paid                (subscription renewal successful)
      - invoice.payment_failed      (subscription renewal failed)
      - customer.subscription.updated (plan change, status change)
      - customer.subscription.deleted (subscription fully cancelled)
    """
    _configure_stripe()
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook verification is not configured.",
        )

    request_body = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(request_body, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request body")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})
    logger.info("Stripe webhook received: %s", event_type)

    # -----------------------------------------------------------------------
    # checkout.session.completed — handles BOTH one-time payments AND the
    # initial subscription activation (first checkout for a new subscriber).
    # -----------------------------------------------------------------------
    if event_type == "checkout.session.completed":
        session_id = data_object.get("id")
        payment_status = "paid" if data_object.get("payment_status") == "paid" else "unpaid"
        mode = data_object.get("mode")  # "payment" or "subscription"
        metadata = data_object.get("metadata", {})

        # --- One-time payments (contribution / add-on) ---
        if mode == "payment":
            update_payload = {
                "status": "checkout.session.completed",
                "payment_status": payment_status,
            }
            if payment_status == "paid":
                update_payload["completed_at"] = now_iso()
            await payments_collection.update_one({"session_id": session_id}, {"$set": update_payload})

        # --- Subscription checkout ---
        elif mode == "subscription":
            stripe_subscription_id = data_object.get("subscription", "")
            sub_doc = await subscriptions_collection.find_one({"session_id": session_id}, {"_id": 0})
            if not sub_doc:
                return {"received": True, "event_type": event_type, "status": "ignored", "reason": "unknown session"}
            expected_metadata = {
                "community_id": sub_doc.get("community_id", ""),
                "user_id": sub_doc.get("user_id", ""),
                "plan_id": sub_doc.get("plan_id", ""),
                "billing_cycle": sub_doc.get("billing_cycle", ""),
            }
            if any(metadata.get(key) != value for key, value in expected_metadata.items()):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Stripe checkout metadata does not match the pending subscription.",
                )
            update_payload = {
                "payment_status": payment_status,
                "stripe_subscription_id": stripe_subscription_id,
            }

            if payment_status == "paid":
                if not stripe_subscription_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Paid Stripe checkout is missing its subscription.",
                    )
                try:
                    stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
                    price_id = stripe_sub["items"]["data"][0]["price"]["id"]
                    resolved_plan, resolved_cycle = resolve_stripe_price(price_id)
                    period_end = datetime.fromtimestamp(
                        stripe_sub.current_period_end,
                        tz=timezone.utc,
                    ).isoformat()
                except (KeyError, IndexError, TypeError, ValueError, AttributeError, stripe.error.StripeError) as exc:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Unable to verify the Stripe subscription created by checkout.",
                    ) from exc
                expected_livemode = BILLING_ENVIRONMENT == "production"
                if bool(stripe_sub.livemode) != expected_livemode:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe subscription environment does not match billing configuration.",
                    )
                if (resolved_plan, resolved_cycle) != (
                    sub_doc.get("plan_id"),
                    sub_doc.get("billing_cycle"),
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe subscription product does not match the pending plan and interval.",
                    )
                update_payload.update(
                    {
                        "status": "active",
                        "activated_at": now_iso(),
                        "current_period_end": period_end,
                        "expires_at": period_end,
                        "stripe_price_id": price_id,
                    }
                )

            applied, _ = await _apply_stripe_subscription_event(
                {"session_id": session_id},
                event,
                update_payload,
            )
            if applied and payment_status == "paid":
                community_id = sub_doc.get("community_id", "")
                if community_id:
                    await subscriptions_collection.update_many(
                        {
                            "community_id": community_id,
                            "status": {"$in": list(PAID_ACCESS_STATUSES)},
                            "session_id": {"$ne": session_id},
                        },
                        {"$set": {"status": "superseded"}},
                    )

                try:
                    from email_service import send_subscription_welcome
                    await send_subscription_welcome(
                        email=sub_doc.get("user_email", ""),
                        plan_name=sub_doc.get("plan_name", ""),
                        billing_cycle=sub_doc.get("billing_cycle", ""),
                        amount=sub_doc.get("amount", 0),
                    )
                except Exception as exc:
                    logger.warning("Welcome email failed: %s", exc)

        return {"received": True, "event_type": event_type, "mode": mode}

    # -----------------------------------------------------------------------
    # invoice.paid — a subscription renewal was charged successfully.
    # Fires for EVERY successful invoice, including the first one.  For the
    # first invoice the checkout.session.completed handler above already
    # activates the subscription, so we focus on subsequent renewals here.
    # -----------------------------------------------------------------------
    if event_type == "invoice.paid":
        stripe_subscription_id = data_object.get("subscription", "")
        billing_reason = data_object.get("billing_reason", "")  # "subscription_cycle", "subscription_create", …

        if stripe_subscription_id:
            sub_doc = await subscriptions_collection.find_one(
                {"stripe_subscription_id": stripe_subscription_id}, {"_id": 0}
            )

            if sub_doc:
                try:
                    stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
                    price_id = stripe_sub["items"]["data"][0]["price"]["id"]
                    plan_id, billing_cycle = resolve_stripe_price(price_id)
                    period_end = datetime.fromtimestamp(
                        stripe_sub.current_period_end,
                        tz=timezone.utc,
                    ).isoformat()
                except (KeyError, IndexError, TypeError, ValueError, AttributeError, stripe.error.StripeError) as exc:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Unable to verify the renewed Stripe subscription.",
                    ) from exc
                if bool(stripe_sub.livemode) != (BILLING_ENVIRONMENT == "production"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe renewal environment does not match billing configuration.",
                    )

                cancel_at_period_end = bool(stripe_sub.cancel_at_period_end)
                update_values = {
                    "status": "canceling" if cancel_at_period_end else "active",
                    "payment_status": "paid",
                    "current_period_end": period_end,
                    "expires_at": period_end,
                    "cancel_at_period_end": cancel_at_period_end,
                    "stripe_price_id": price_id,
                    "plan_id": plan_id,
                    "plan_name": SUBSCRIPTION_TIERS[plan_id]["name"],
                    "billing_cycle": billing_cycle,
                    "amount": billing_amount(plan_id, billing_cycle),
                }
                applied, previous = await _apply_stripe_subscription_event(
                    {"stripe_subscription_id": stripe_subscription_id},
                    event,
                    update_values,
                )

                # Send renewal email only for actual renewals (not the first invoice)
                if applied and billing_reason == "subscription_cycle":
                    try:
                        from email_service import send_subscription_renewed
                        await send_subscription_renewed(
                            email=previous.get("user_email", ""),
                            plan_name=update_values["plan_name"],
                            amount=float(data_object.get("amount_paid", 0)) / 100,
                            next_renewal=period_end[:10] if period_end else "—",
                        )
                    except Exception as exc:
                        logger.warning("Renewal email failed: %s", exc)

        return {"received": True, "event_type": event_type}

    # -----------------------------------------------------------------------
    # invoice.payment_failed — a subscription renewal charge failed.
    # Stripe will automatically retry according to Smart Retries settings.
    # -----------------------------------------------------------------------
    if event_type == "invoice.payment_failed":
        stripe_subscription_id = data_object.get("subscription", "")

        if stripe_subscription_id:
            sub_doc = await subscriptions_collection.find_one(
                {"stripe_subscription_id": stripe_subscription_id}, {"_id": 0}
            )

            if sub_doc:
                applied, previous = await _apply_stripe_subscription_event(
                    {"stripe_subscription_id": stripe_subscription_id},
                    event,
                    {"status": "past_due", "payment_status": "failed"},
                )

                try:
                    if not applied:
                        return {"received": True, "event_type": event_type, "status": "ignored"}
                    from email_service import send_payment_failed
                    await send_payment_failed(
                        email=previous.get("user_email", ""),
                        plan_name=previous.get("plan_name", ""),
                    )
                except Exception as exc:
                    logger.warning("Payment failed email error: %s", exc)

        return {"received": True, "event_type": event_type}

    # -----------------------------------------------------------------------
    # customer.subscription.updated — plan change, payment method update,
    # cancel_at_period_end toggled, etc.
    # -----------------------------------------------------------------------
    if event_type == "customer.subscription.updated":
        stripe_subscription_id = data_object.get("id", "")
        cancel_at_period_end = data_object.get("cancel_at_period_end", False)
        stripe_status = data_object.get("status", "")  # active, past_due, canceled, …

        if stripe_subscription_id:
            sub_doc = await subscriptions_collection.find_one(
                {"stripe_subscription_id": stripe_subscription_id}, {"_id": 0}
            )

            if sub_doc:
                status_map = {
                    "active": "active",
                    "past_due": "past_due",
                    "canceled": "canceled",
                    "unpaid": "past_due",
                    "incomplete": "pending",
                    "incomplete_expired": "canceled",
                    "paused": "past_due",
                    "trialing": "pending",
                }
                if stripe_status not in status_map:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe returned an unsupported subscription status.",
                    )
                new_status = status_map[stripe_status]
                if cancel_at_period_end and stripe_status == "active":
                    new_status = "canceling"
                update_payload = {
                    "status": new_status,
                    "cancel_at_period_end": cancel_at_period_end,
                }
                if bool(data_object.get("livemode")) != (BILLING_ENVIRONMENT == "production"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe subscription environment does not match billing configuration.",
                    )

                # Update period end
                period_end_ts = data_object.get("current_period_end")
                if period_end_ts:
                    period_end = datetime.fromtimestamp(period_end_ts, tz=timezone.utc).isoformat()
                    update_payload["current_period_end"] = period_end
                    update_payload["expires_at"] = period_end

                # Check for plan changes (items array)
                items = data_object.get("items", {}).get("data", [])
                if not items:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe subscription update is missing its Price.",
                    )
                new_price_id = items[0].get("price", {}).get("id", "")
                try:
                    new_tier, new_cycle = resolve_stripe_price(new_price_id)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe subscription uses an unmapped Price.",
                    ) from exc
                update_payload.update({
                    "stripe_price_id": new_price_id,
                    "plan_id": new_tier,
                    "plan_name": SUBSCRIPTION_TIERS[new_tier]["name"],
                    "billing_cycle": new_cycle,
                    "amount": billing_amount(new_tier, new_cycle),
                })

                applied, previous = await _apply_stripe_subscription_event(
                    {"stripe_subscription_id": stripe_subscription_id},
                    event,
                    update_payload,
                )
                if applied and (
                    previous.get("plan_id") != new_tier
                    or previous.get("billing_cycle") != new_cycle
                ):
                    try:
                        from email_service import send_subscription_upgraded
                        await send_subscription_upgraded(
                            email=previous.get("user_email", ""),
                            old_plan=previous.get("plan_name", ""),
                            new_plan=update_payload["plan_name"],
                            amount=update_payload["amount"],
                            billing_cycle=new_cycle,
                        )
                    except Exception as exc:
                        logger.warning("Upgrade email failed: %s", exc)

        return {"received": True, "event_type": event_type}

    # -----------------------------------------------------------------------
    # customer.subscription.deleted — subscription is fully cancelled
    # (period ended after cancel_at_period_end, or immediate cancellation).
    # -----------------------------------------------------------------------
    if event_type == "customer.subscription.deleted":
        stripe_subscription_id = data_object.get("id", "")

        if stripe_subscription_id:
            sub_doc = await subscriptions_collection.find_one(
                {"stripe_subscription_id": stripe_subscription_id}, {"_id": 0}
            )

            if sub_doc:
                if bool(data_object.get("livemode")) != (BILLING_ENVIRONMENT == "production"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe cancellation environment does not match billing configuration.",
                    )
                applied, previous = await _apply_stripe_subscription_event(
                    {"stripe_subscription_id": stripe_subscription_id},
                    event,
                    {
                        "status": "canceled",
                        "payment_status": "canceled",
                        "cancel_at_period_end": False,
                        "cancelled_at": sub_doc.get("cancelled_at") or now_iso(),
                    },
                )

                # Send final cancellation email if we haven't already
                # (the "canceling" email was sent when user clicked cancel;
                #  this one confirms the subscription is now truly ended)
                if applied and previous.get("status") != "canceled":
                    try:
                        from email_service import send_subscription_cancelled
                        await send_subscription_cancelled(
                            email=previous.get("user_email", ""),
                            plan_name=previous.get("plan_name", ""),
                            access_until="now",
                        )
                    except Exception as exc:
                        logger.warning("Cancellation email failed: %s", exc)

        return {"received": True, "event_type": event_type}

    # -----------------------------------------------------------------------
    # Unhandled event type — acknowledge receipt so Stripe doesn't retry.
    # -----------------------------------------------------------------------
    logger.info("Unhandled Stripe event type: %s", event_type)
    return {"received": True, "event_type": event_type}
