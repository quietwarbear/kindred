"""Finance routes: travel plans, budget plans, payments, funds overview."""

import os
import uuid
from typing import Any, Literal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status

from db import budget_plans_collection, payments_collection, travel_plans_collection
from dependencies import (
    CONTRIBUTION_PACKAGES,
    build_stripe_checkout,
    ensure_minimum_role,
    get_current_user,
    now_iso,
)
from models import BudgetCreateRequest, PaymentCheckoutRequest, TravelPlanCreateRequest

router = APIRouter(prefix="/api")


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

    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
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

    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
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


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events. Requires STRIPE_WEBHOOK_SECRET environment variable."""
    stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    request_body = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(request_body, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request body")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    session_id = None
    payment_status = None
    event_type = event.get("type")

    if event_type == "checkout.session.completed":
        checkout_session = event.get("data", {}).get("object", {})
        session_id = checkout_session.get("id")
        payment_status = checkout_session.get("payment_status")
        if payment_status == "paid":
            payment_status = "paid"
        else:
            payment_status = "unpaid"

    if session_id:
        update_payload = {"status": event_type or "webhook-received", "payment_status": payment_status or "unpaid"}
        if payment_status == "paid":
            update_payload["completed_at"] = now_iso()
        await payments_collection.update_one({"session_id": session_id}, {"$set": update_payload})

    return {"received": True, "session_id": session_id, "payment_status": payment_status, "event_type": event_type}
