"""Organizer-approved continuity from a reunion guest to one family member."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from db import (
    client,
    communities_collection,
    events_collection,
    family_access_requests_collection,
    guest_family_claims_collection,
    notification_events_collection,
    users_collection,
)
from dependencies import ensure_minimum_role, get_current_user, now_iso
from family_space_activation import ACTIVE, community_lifecycle_state
from guest_family_access import (
    find_relationship_invite,
    is_expired,
    safe_organizer_projection,
    safe_status_projection,
)

router = APIRouter(prefix="/api")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")


class FamilyAccessSubmission(BaseModel):
    idempotency_key: str = Field(min_length=16, max_length=128)


class FamilyAccessDecision(BaseModel):
    request_reference: str = Field(min_length=16, max_length=100)
    decision: Literal["approved", "declined"]
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=16, max_length=128)


class FamilyAccessCancellation(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=16, max_length=128)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_operation_key(value: str) -> str:
    if not _IDEMPOTENCY_KEY.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_idempotency_key", "message": "This request cannot be safely retried."},
        )
    return _digest(value)


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})


async def _active_community(community_id: str, *, session=None) -> dict[str, Any] | None:
    community = await communities_collection.find_one(
        {"id": community_id}, {"_id": 0, "id": 1, "name": 1, "lifecycle_state": 1}, session=session
    )
    return community if community_lifecycle_state(community or {}) == ACTIVE else None


async def _expire_if_needed(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("status") == "pending" and is_expired(request.get("expires_at")):
        updated = await family_access_requests_collection.find_one_and_update(
            {"id": request["id"], "status": "pending", "revision": request.get("revision", 0)},
            {"$set": {"status": "expired", "updated_at": now_iso()}, "$inc": {"revision": 1}},
            return_document=True,
        )
        return updated or request
    return request


async def _request_for_user(user_id: str) -> dict[str, Any] | None:
    request = await family_access_requests_collection.find_one(
        {"applicant_user_id": user_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    return await _expire_if_needed(request) if request else None


def _notification(
    *, community_id: str, event_type: str, title: str, description: str,
    audience_scope: str, recipient_user_ids: list[str], related_id: str = "",
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()), "community_id": community_id, "actor_name": "Kindred",
        "event_type": event_type, "title": title, "description": description,
        "related_id": related_id, "audience_scope": audience_scope,
        "recipient_user_ids": recipient_user_ids, "read_by_user_ids": [], "created_at": now_iso(),
    }


@router.post("/family-access/requests")
async def submit_family_access_request(
    payload: FamilyAccessSubmission,
    current_user: dict[str, Any] = Depends(get_current_user),
    continuity_claim: str | None = Header(default=None, alias="X-Kindred-Guest-Claim"),
):
    operation_hash = _validate_operation_key(payload.idempotency_key)
    secret = str(continuity_claim or "").strip()
    if not secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A private guest continuity claim is required.")
    claim_digest = _digest(secret)

    existing = await _request_for_user(current_user["id"])
    if existing:
        if existing.get("submission_operation_hash") != operation_hash:
            # One authenticated identity still converges to its canonical request.
            return safe_status_projection(existing)
        return safe_status_projection(existing)

    claim = await guest_family_claims_collection.find_one({"secret_digest": claim_digest}, {"_id": 0})
    unavailable = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This guest continuity claim is not available.")
    if not claim or claim.get("status") not in {"unclaimed", "claimed"} or is_expired(claim.get("expires_at")):
        raise unavailable
    if claim.get("claimed_by_user_id") and claim.get("claimed_by_user_id") != current_user["id"]:
        raise unavailable

    event = await events_collection.find_one(
        {"id": claim.get("event_id"), "community_id": claim.get("community_id"), "event_template": "reunion"},
        {"_id": 0, "id": 1, "community_id": 1, "event_invites": 1, "hidden_from_user_ids": 1},
    )
    community = await _active_community(str(claim.get("community_id") or ""))
    if (
        not event or not community
        or current_user["id"] in (event.get("hidden_from_user_ids") or [])
        or not find_relationship_invite(event, str(claim.get("relationship_fingerprint") or ""))
    ):
        raise unavailable

    target_community_id = community["id"]
    memberships = {str(value) for value in (current_user.get("community_ids") or []) if value}
    if current_user.get("community_id"):
        memberships.add(str(current_user["community_id"]))
    request_status = (
        "conflict"
        if memberships and (
            memberships != {target_community_id}
            or current_user.get("community_id") != target_community_id
        )
        else "approved"
        if current_user.get("community_id") == target_community_id
        else "pending"
    )
    timestamp = now_iso()
    request_doc = {
        "id": str(uuid.uuid4()), "public_reference": uuid.uuid4().hex,
        "community_id": target_community_id, "event_id": event["id"],
        "relationship_fingerprint": claim["relationship_fingerprint"],
        "applicant_user_id": current_user["id"],
        "applicant_name": str(current_user.get("full_name") or "Family guest")[:80],
        "status": request_status, "revision": 0,
        "submission_operation_hash": operation_hash,
        "created_at": timestamp, "updated_at": timestamp,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    }
    try:
        async def transaction(session):
            claimed = await guest_family_claims_collection.update_one(
                {"secret_digest": claim_digest, "$or": [{"status": "unclaimed"}, {"claimed_by_user_id": current_user["id"]}]},
                {"$set": {"status": "claimed", "claimed_by_user_id": current_user["id"], "claimed_at": timestamp}},
                session=session,
            )
            if claimed.matched_count != 1:
                raise unavailable
            await family_access_requests_collection.insert_one(request_doc.copy(), session=session)
            if request_status == "pending":
                organizers = await users_collection.find(
                    {"community_id": target_community_id, "role": {"$in": ["host", "organizer"]}},
                    {"_id": 0, "id": 1}, session=session,
                ).to_list(500)
                await notification_events_collection.insert_one(
                    _notification(
                        community_id=target_community_id, event_type="family-access-request",
                        title=f"{request_doc['applicant_name']} requested family access",
                        description="Review this guest-to-member request in the organizer command center.",
                        audience_scope="organizer", recipient_user_ids=[item["id"] for item in organizers],
                    ), session=session,
                )
        async with await client.start_session() as session:
            await session.with_transaction(transaction)
    except DuplicateKeyError:
        existing = await _request_for_user(current_user["id"])
        if not existing:
            raise _conflict("request_concurrency_conflict", "Refresh before trying again.")
        return safe_status_projection(existing)
    return safe_status_projection(request_doc, community.get("name", ""))


@router.get("/family-access/status")
async def own_family_access_status(current_user: dict[str, Any] = Depends(get_current_user)):
    request = await _request_for_user(current_user["id"])
    if not request:
        return {"status": "none", "revision": 0, "next_action_codes": ["return_to_reunion"]}
    community = await _active_community(request["community_id"])
    return safe_status_projection(request, (community or {}).get("name", ""))


@router.post("/family-access/cancel")
async def cancel_own_family_access_request(
    payload: FamilyAccessCancellation,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    operation_hash = _validate_operation_key(payload.idempotency_key)
    request = await _request_for_user(current_user["id"])
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family access request not found.")
    if request.get("status") == "cancelled" and request.get("cancel_operation_hash") == operation_hash:
        return safe_status_projection(request)
    if request.get("status") != "pending" or request.get("revision") != payload.expected_revision:
        raise _conflict("request_state_changed", "This request changed. Refresh before trying again.")
    updated = await family_access_requests_collection.find_one_and_update(
        {"id": request["id"], "applicant_user_id": current_user["id"], "status": "pending", "revision": payload.expected_revision},
        {"$set": {"status": "cancelled", "cancel_operation_hash": operation_hash, "updated_at": now_iso()}, "$inc": {"revision": 1}},
        return_document=True,
    )
    if not updated:
        raise _conflict("request_state_changed", "This request changed. Refresh before trying again.")
    return safe_status_projection(updated)


@router.get("/family-access/organizer/requests")
async def organizer_family_access_requests(current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    if not await _active_community(current_user["community_id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family space not found.")
    requests = await family_access_requests_collection.find(
        {"community_id": current_user["community_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"requests": [safe_organizer_projection(await _expire_if_needed(item)) for item in requests]}


@router.post("/family-access/organizer/decision")
async def decide_family_access_request(
    payload: FamilyAccessDecision,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    operation_hash = _validate_operation_key(payload.idempotency_key)
    decision_hash = _digest(json.dumps({"decision": payload.decision}, sort_keys=True))
    if not await _active_community(current_user["community_id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family space not found.")

    async def transaction(session):
        request = await family_access_requests_collection.find_one(
            {"public_reference": payload.request_reference, "community_id": current_user["community_id"]},
            {"_id": 0}, session=session,
        )
        if not request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family access request not found.")
        if request.get("decision_operation_hash") == operation_hash:
            if request.get("decision_payload_hash") != decision_hash:
                raise _conflict("idempotency_mismatch", "This retry does not match the original decision.")
            return request
        if request.get("status") != "pending" or request.get("revision") != payload.expected_revision:
            raise _conflict("request_state_changed", "This request changed. Refresh before trying again.")
        if is_expired(request.get("expires_at")):
            next_status = "expired"
        else:
            user = await users_collection.find_one({"id": request["applicant_user_id"]}, {"_id": 0}, session=session)
            if not user:
                next_status = "conflict"
            else:
                memberships = {str(value) for value in (user.get("community_ids") or []) if value}
                if user.get("community_id"):
                    memberships.add(str(user["community_id"]))
                cross_community = bool(memberships and memberships != {current_user["community_id"]})
                next_status = "conflict" if cross_community else payload.decision
                if next_status == "approved":
                    role = user.get("role") if user.get("role") in {"host", "organizer"} else "member"
                    result = await users_collection.update_one(
                        {"id": user["id"], "$or": [{"community_id": ""}, {"community_id": current_user["community_id"]}]},
                        {"$set": {"community_id": current_user["community_id"], "role": role, "onboarding_completed": True},
                         "$addToSet": {"community_ids": current_user["community_id"]}},
                        session=session,
                    )
                    if result.matched_count != 1:
                        next_status = "conflict"
        updated = await family_access_requests_collection.find_one_and_update(
            {"id": request["id"], "status": "pending", "revision": payload.expected_revision},
            {"$set": {"status": next_status, "decision_operation_hash": operation_hash,
                      "decision_payload_hash": decision_hash, "decided_by_user_id": current_user["id"],
                      "decided_at": now_iso(), "updated_at": now_iso()}, "$inc": {"revision": 1}},
            return_document=True, session=session,
        )
        if not updated:
            raise _conflict("request_state_changed", "This request changed. Refresh before trying again.")
        await notification_events_collection.insert_one(
            _notification(
                community_id=current_user["community_id"], event_type="family-access-status",
                title="Your family access request was updated",
                description=f"The request is now {next_status}.", audience_scope="user",
                recipient_user_ids=[request["applicant_user_id"]],
            ), session=session,
        )
        return updated

    async with await client.start_session() as session:
        request = await session.with_transaction(transaction)
    community = await _active_community(current_user["community_id"])
    return safe_status_projection(request, (community or {}).get("name", ""))
