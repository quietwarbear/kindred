"""Private family gathering proposals, interest pulses, and draft conversion."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from db import (
    client,
    communities_collection,
    events_collection,
    gathering_proposal_conversions_collection,
    gathering_proposal_responses_collection,
    gathering_proposals_collection,
    notification_events_collection,
    users_collection,
)
from dependencies import ensure_minimum_role, get_current_user, now_iso
from family_space_activation import ACTIVE, community_lifecycle_state
from gathering_proposals import (
    DECLINE_REASONS,
    GATHERING_TYPES,
    INTEREST_RESPONSES,
    ProposalValidationError,
    clean_private_text,
    conversion_preview_value,
    digest_payload,
    member_projection,
    new_draft_document,
)

router = APIRouter(prefix="/api/gathering-proposals")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_PUBLIC_REFERENCE = re.compile(r"^[a-f0-9]{32}$")
_ACTIVE_ROLES = {"member", "organizer", "host"}
_INACTIVE_ACCOUNT_STATES = ["suspended", "removed", "deleted"]


class ProposalSubmission(BaseModel):
    working_title: str = Field(min_length=1, max_length=120)
    gathering_type: Literal["family_reunion", "holiday", "milestone", "day_trip", "virtual", "other"]
    broad_date_window: str = Field(default="", max_length=80)
    location_suggestion: str = Field(default="", max_length=120)
    organizer_note: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(min_length=16, max_length=128)


class RevisionOperation(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=16, max_length=128)


class DeclineOperation(RevisionOperation):
    reason: Literal["not_a_fit", "needs_more_detail", "timing_not_workable", "duplicate", "other"]


class InterestOperation(BaseModel):
    response: Literal["interested", "maybe", "not_available"]
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=16, max_length=128)


class ConversionSelection(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    start_at: str = Field(min_length=1, max_length=80)
    end_at: str = Field(min_length=1, max_length=80)
    timezone: str = Field(min_length=1, max_length=100)
    location: str = Field(default="", max_length=160)
    gathering_format: Literal["in-person", "online", "hybrid"] = "in-person"
    max_attendees: int = Field(default=50, ge=1, le=10000)
    organizer_reference: str = Field(min_length=1, max_length=100)


class ConversionOperation(ConversionSelection):
    expected_revision: int = Field(ge=0)
    preview_digest: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=16, max_length=128)


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})


def _unprocessable(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": code, "message": message})


def _operation_hash(value: str, *, community_id: str, actor_id: str, subject: str) -> str:
    if not _IDEMPOTENCY_KEY.fullmatch(value):
        raise _unprocessable("invalid_idempotency_key", "This operation cannot be safely retried.")
    return hashlib.sha256(f"{community_id}\n{actor_id}\n{subject}\n{value}".encode()).hexdigest()


def _payload_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validated_submission(payload: ProposalSubmission) -> dict[str, Any]:
    try:
        return {
            "working_title": clean_private_text(payload.working_title, maximum=120, required=True),
            "gathering_type": payload.gathering_type,
            "broad_date_window": clean_private_text(payload.broad_date_window, maximum=80),
            "location_suggestion": clean_private_text(payload.location_suggestion, maximum=120),
            "organizer_note": clean_private_text(payload.organizer_note, maximum=1000),
        }
    except ProposalValidationError as exc:
        raise _unprocessable(exc.code, "The private proposal text could not be accepted.") from None


async def _active_actor(user: dict[str, Any], *, session=None) -> tuple[dict[str, Any], dict[str, Any]]:
    community_id = str(user.get("community_id") or "")
    if not community_id or user.get("role") not in _ACTIVE_ROLES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family proposal not found.")
    community = await communities_collection.find_one(
        {"id": community_id}, {"_id": 0, "id": 1, "lifecycle_state": 1}, session=session
    )
    actor = await users_collection.find_one(
        {
            "id": user.get("id"),
            "community_id": community_id,
            "role": {"$in": sorted(_ACTIVE_ROLES)},
            "account_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
            "membership_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
        },
        {"_id": 0, "id": 1, "community_id": 1, "role": 1, "full_name": 1},
        session=session,
    )
    if not actor or community_lifecycle_state(community or {}) != ACTIVE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family proposal not found.")
    return actor, community


async def _eligible_users(community_id: str, *, session=None) -> list[dict[str, Any]]:
    return await users_collection.find(
        {
            "community_id": community_id,
            "role": {"$in": sorted(_ACTIVE_ROLES)},
            "account_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
            "membership_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
        },
        {"_id": 0, "id": 1, "role": 1, "full_name": 1},
        session=session,
    ).to_list(2000)


async def _proposal_by_reference(reference: str, community_id: str, *, session=None) -> dict[str, Any] | None:
    if not _PUBLIC_REFERENCE.fullmatch(reference):
        return None
    return await gathering_proposals_collection.find_one(
        {"public_reference": reference, "community_id": community_id}, {"_id": 0}, session=session
    )


async def _responses(proposal_id: str, *, session=None) -> list[dict[str, Any]]:
    return await gathering_proposal_responses_collection.find(
        {"proposal_id": proposal_id}, {"_id": 0}, session=session
    ).to_list(2000)


async def _project(proposal: dict[str, Any], user: dict[str, Any], *, organizer: bool = False) -> dict[str, Any]:
    responses, eligible = await asyncio.gather(
        _responses(proposal["id"]),
        _eligible_users(proposal["community_id"]),
    )
    return member_projection(
        proposal,
        viewer_id=user["id"],
        responses=responses,
        eligible_user_ids={item["id"] for item in eligible},
        organizer=organizer,
    )


def _notification(
    *, notification_id: str, community_id: str, event_type: str, title: str,
    description: str, recipients: list[str], related_id: str, audience_scope: str = "user",
) -> dict[str, Any]:
    return {
        "id": notification_id,
        "community_id": community_id,
        "actor_name": "Kindred",
        "event_type": event_type,
        "title": title,
        "description": description,
        "related_id": related_id,
        "audience_scope": audience_scope,
        "recipient_user_ids": recipients,
        "read_by_user_ids": [],
        "created_at": now_iso(),
    }


async def _insert_notification(value: dict[str, Any]) -> None:
    await notification_events_collection.update_one(
        {"id": value["id"]}, {"$setOnInsert": value}, upsert=True
    )


async def _notify_submission(proposal: dict[str, Any]) -> None:
    organizers = await users_collection.find(
        {
            "community_id": proposal["community_id"],
            "role": {"$in": ["host", "organizer"]},
            "account_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
            "membership_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
        },
        {"_id": 0, "id": 1},
    ).to_list(500)
    await _insert_notification(_notification(
        notification_id=f"gathering-proposal-submitted:{proposal['id']}",
        community_id=proposal["community_id"], event_type="gathering-proposal-submitted",
        title="A private gathering proposal needs review",
        description="Open the organizer proposal review in Kindred.",
        recipients=[item["id"] for item in organizers], related_id="", audience_scope="organizer",
    ))


async def _remove_pulse_notifications(proposal: dict[str, Any]) -> None:
    await notification_events_collection.delete_many({
        "id": f"gathering-proposal-published:{proposal['id']}",
        "community_id": proposal["community_id"],
    })


@router.post("")
async def submit_proposal(payload: ProposalSubmission, current_user: dict[str, Any] = Depends(get_current_user)):
    actor, _ = await _active_actor(current_user)
    content = _validated_submission(payload)
    operation_hash = _operation_hash(
        payload.idempotency_key, community_id=actor["community_id"], actor_id=actor["id"], subject="submit"
    )
    payload_hash = _payload_hash(content)
    existing = await gathering_proposals_collection.find_one({"submission_operation_hash": operation_hash}, {"_id": 0})
    if existing:
        if existing.get("submission_payload_hash") != payload_hash:
            raise _conflict("idempotency_payload_conflict", "This retry does not match the original proposal.")
        await _notify_submission(existing)
        return await _project(existing, actor)
    timestamp = now_iso()
    proposal = {
        "id": str(uuid.uuid4()),
        "public_reference": uuid.uuid4().hex,
        "community_id": actor["community_id"],
        "proposer_user_id": actor["id"],
        "proposer_display_name": actor.get("full_name", "Family member"),
        **content,
        "state": "submitted",
        "revision": 0,
        "submission_operation_hash": operation_hash,
        "submission_payload_hash": payload_hash,
        "operations": [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    try:
        await gathering_proposals_collection.insert_one(proposal.copy())
    except DuplicateKeyError:
        existing = await gathering_proposals_collection.find_one({"submission_operation_hash": operation_hash}, {"_id": 0})
        if not existing or existing.get("submission_payload_hash") != payload_hash:
            raise _conflict("proposal_submission_conflict", "The proposal changed. Refresh before trying again.")
        await _notify_submission(existing)
        return await _project(existing, actor)
    await _notify_submission(proposal)
    return await _project(proposal, actor)


@router.get("")
async def list_member_proposals(current_user: dict[str, Any] = Depends(get_current_user)):
    actor, _ = await _active_actor(current_user)
    proposals = await gathering_proposals_collection.find(
        {
            "community_id": actor["community_id"],
            "$or": [{"state": "published"}, {"proposer_user_id": actor["id"]}],
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return {"proposals": [await _project(item, actor) for item in proposals]}


@router.get("/organizer/review")
async def organizer_review(current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    actor, _ = await _active_actor(current_user)
    if actor.get("role") not in {"host", "organizer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organizer access required.")
    proposals = await gathering_proposals_collection.find(
        {"community_id": actor["community_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    organizers = await users_collection.find(
        {
            "community_id": actor["community_id"],
            "role": {"$in": ["host", "organizer"]},
            "account_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
            "membership_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
        },
        {"_id": 0, "id": 1, "full_name": 1, "role": 1},
    ).sort("full_name", 1).to_list(500)
    return {
        "proposals": [await _project(item, actor, organizer=True) for item in proposals],
        "eligible_organizers": [
            {"organizer_reference": item["id"], "display_name": item.get("full_name", "Organizer"), "role": item["role"]}
            for item in organizers
        ],
    }


@router.get("/{proposal_reference}")
async def proposal_detail(proposal_reference: str, current_user: dict[str, Any] = Depends(get_current_user)):
    actor, _ = await _active_actor(current_user)
    proposal = await _proposal_by_reference(proposal_reference, actor["community_id"])
    if not proposal or (proposal.get("state") != "published" and proposal.get("proposer_user_id") != actor["id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family proposal not found.")
    return await _project(proposal, actor)


def _prior_operation(proposal: dict[str, Any], operation_hash: str, payload_hash: str) -> bool:
    prior = next((item for item in proposal.get("operations") or [] if item.get("operation_hash") == operation_hash), None)
    if prior and prior.get("payload_hash") != payload_hash:
        raise _conflict("idempotency_payload_conflict", "This operation key was already used differently.")
    return bool(prior)


async def _transition(
    proposal: dict[str, Any], actor: dict[str, Any], *, target: str,
    allowed: set[str], expected_revision: int, idempotency_key: str,
    action: str, moderation_reason: str = "",
) -> dict[str, Any]:
    operation_hash = _operation_hash(
        idempotency_key, community_id=proposal["community_id"], actor_id=actor["id"], subject=proposal["id"]
    )
    payload_hash = _payload_hash({"action": action, "target": target, "reason": moderation_reason})
    if _prior_operation(proposal, operation_hash, payload_hash):
        return proposal
    if proposal.get("state") == target:
        return proposal
    if proposal.get("state") not in allowed or int(proposal.get("revision", 0) or 0) != expected_revision:
        raise _conflict("proposal_state_changed", "This proposal changed. Refresh before trying again.")
    operation = {
        "operation_hash": operation_hash,
        "payload_hash": payload_hash,
        "action": action,
        "resulting_revision": expected_revision + 1,
        "at": now_iso(),
    }
    set_fields = {"state": target, "updated_at": now_iso()}
    if moderation_reason:
        set_fields["moderation_reason"] = moderation_reason
    updated = await gathering_proposals_collection.find_one_and_update(
        {
            "id": proposal["id"], "community_id": proposal["community_id"],
            "state": {"$in": sorted(allowed)}, "revision": expected_revision,
        },
        {"$set": set_fields, "$inc": {"revision": 1}, "$push": {"operations": {"$each": [operation], "$slice": -100}}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if updated:
        return updated
    concurrent = await gathering_proposals_collection.find_one({"id": proposal["id"]}, {"_id": 0})
    if concurrent and _prior_operation(concurrent, operation_hash, payload_hash):
        return concurrent
    raise _conflict("proposal_state_changed", "This proposal changed. Refresh before trying again.")


async def _organizer_proposal(reference: str, user: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure_minimum_role(user, "organizer")
    actor, _ = await _active_actor(user)
    if actor.get("role") not in {"host", "organizer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organizer access required.")
    proposal = await _proposal_by_reference(reference, actor["community_id"])
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family proposal not found.")
    return actor, proposal


@router.post("/{proposal_reference}/withdraw")
async def withdraw_proposal(
    proposal_reference: str, payload: RevisionOperation, current_user: dict[str, Any] = Depends(get_current_user)
):
    actor, _ = await _active_actor(current_user)
    proposal = await _proposal_by_reference(proposal_reference, actor["community_id"])
    if not proposal or proposal.get("proposer_user_id") != actor["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family proposal not found.")
    updated = await _transition(
        proposal, actor, target="withdrawn", allowed={"submitted"}, expected_revision=payload.expected_revision,
        idempotency_key=payload.idempotency_key, action="withdraw",
    )
    await _remove_pulse_notifications(updated)
    return await _project(updated, actor)


@router.post("/{proposal_reference}/publish")
async def publish_proposal(
    proposal_reference: str, payload: RevisionOperation, current_user: dict[str, Any] = Depends(get_current_user)
):
    actor, proposal = await _organizer_proposal(proposal_reference, current_user)
    updated = await _transition(
        proposal, actor, target="published", allowed={"submitted"}, expected_revision=payload.expected_revision,
        idempotency_key=payload.idempotency_key, action="publish",
    )
    eligible = await _eligible_users(updated["community_id"])
    await _insert_notification(_notification(
        notification_id=f"gathering-proposal-published:{updated['id']}",
        community_id=updated["community_id"], event_type="gathering-proposal-published",
        title="A private family interest pulse is ready",
        description="Share one private interest response in Kindred.",
        recipients=[item["id"] for item in eligible], related_id="",
    ))
    return await _project(updated, actor, organizer=True)


@router.post("/{proposal_reference}/decline")
async def decline_proposal(
    proposal_reference: str, payload: DeclineOperation, current_user: dict[str, Any] = Depends(get_current_user)
):
    actor, proposal = await _organizer_proposal(proposal_reference, current_user)
    if payload.reason not in DECLINE_REASONS:
        raise _unprocessable("invalid_decline_reason", "Choose a supported decline reason.")
    updated = await _transition(
        proposal, actor, target="declined", allowed={"submitted", "published"},
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        action="decline", moderation_reason=payload.reason,
    )
    await _remove_pulse_notifications(updated)
    proposer = updated.get("proposer_user_id")
    if proposer:
        await _insert_notification(_notification(
            notification_id=f"gathering-proposal-declined:{updated['id']}",
            community_id=updated["community_id"], event_type="gathering-proposal-declined",
            title="Your gathering proposal was reviewed",
            description="Open Kindred to see its current status.", recipients=[proposer],
            related_id="",
        ))
    return await _project(updated, actor, organizer=True)


@router.post("/{proposal_reference}/close")
async def close_proposal(
    proposal_reference: str, payload: RevisionOperation, current_user: dict[str, Any] = Depends(get_current_user)
):
    actor, proposal = await _organizer_proposal(proposal_reference, current_user)
    updated = await _transition(
        proposal, actor, target="expired", allowed={"published"}, expected_revision=payload.expected_revision,
        idempotency_key=payload.idempotency_key, action="close", moderation_reason="closed_by_organizer",
    )
    await _remove_pulse_notifications(updated)
    return await _project(updated, actor, organizer=True)


@router.put("/{proposal_reference}/interest")
async def record_interest(
    proposal_reference: str, payload: InterestOperation, current_user: dict[str, Any] = Depends(get_current_user)
):
    actor, _ = await _active_actor(current_user)
    proposal = await _proposal_by_reference(proposal_reference, actor["community_id"])
    if not proposal or proposal.get("state") != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family proposal not found.")
    operation_hash = _operation_hash(
        payload.idempotency_key, community_id=proposal["community_id"], actor_id=actor["id"], subject=proposal["id"]
    )
    payload_hash = _payload_hash({"response": payload.response})

    async def transaction(session):
        fresh_actor, _ = await _active_actor(actor, session=session)
        fresh = await gathering_proposals_collection.find_one(
            {"id": proposal["id"], "community_id": proposal["community_id"], "state": "published"},
            {"_id": 0, "id": 1}, session=session,
        )
        if not fresh:
            raise _conflict("proposal_state_changed", "This interest pulse is no longer accepting responses.")
        existing = await gathering_proposal_responses_collection.find_one(
            {"proposal_id": proposal["id"], "user_id": fresh_actor["id"]}, {"_id": 0}, session=session
        )
        prior = next((item for item in (existing or {}).get("operations", []) if item.get("operation_hash") == operation_hash), None)
        if prior:
            if prior.get("payload_hash") != payload_hash:
                raise _conflict("idempotency_payload_conflict", "This response retry does not match the original response.")
            return existing
        current_revision = int((existing or {}).get("revision", 0) or 0)
        if current_revision != payload.expected_revision:
            raise _conflict("interest_revision_conflict", "Your interest response changed. Refresh before trying again.")
        operation = {"operation_hash": operation_hash, "payload_hash": payload_hash, "resulting_revision": current_revision + 1}
        if not existing:
            response = {
                "id": str(uuid.uuid4()), "proposal_id": proposal["id"],
                "community_id": proposal["community_id"], "user_id": fresh_actor["id"],
                "response": payload.response, "revision": 1, "operations": [operation],
                "created_at": now_iso(), "updated_at": now_iso(),
            }
            await gathering_proposal_responses_collection.insert_one(response.copy(), session=session)
            return response
        updated = await gathering_proposal_responses_collection.find_one_and_update(
            {"id": existing["id"], "revision": current_revision},
            {"$set": {"response": payload.response, "updated_at": now_iso()}, "$inc": {"revision": 1}, "$push": {"operations": {"$each": [operation], "$slice": -50}}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER, session=session,
        )
        if not updated:
            raise _conflict("interest_revision_conflict", "Your interest response changed. Refresh before trying again.")
        return updated

    try:
        async with await client.start_session() as session:
            await session.with_transaction(transaction)
    except DuplicateKeyError:
        existing = await gathering_proposal_responses_collection.find_one(
            {"proposal_id": proposal["id"], "user_id": actor["id"]}, {"_id": 0}
        )
        prior = next((item for item in (existing or {}).get("operations", []) if item.get("operation_hash") == operation_hash), None)
        if not prior or prior.get("payload_hash") != payload_hash:
            raise _conflict("interest_concurrency_conflict", "Your interest response changed. Refresh before trying again.")
    fresh_proposal = await gathering_proposals_collection.find_one({"id": proposal["id"]}, {"_id": 0})
    return await _project(fresh_proposal or proposal, actor)


async def _conversion_preview(
    proposal: dict[str, Any], selection: ConversionSelection, *, session=None
) -> tuple[dict[str, Any], dict[str, Any]]:
    organizer = await users_collection.find_one(
        {
            "id": selection.organizer_reference,
            "community_id": proposal["community_id"],
            "role": {"$in": ["host", "organizer"]},
            "account_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
            "membership_status": {"$nin": _INACTIVE_ACCOUNT_STATES},
        },
        {"_id": 0, "id": 1, "full_name": 1, "role": 1}, session=session,
    )
    if not organizer:
        raise _unprocessable("invalid_conversion_organizer", "Choose an active family organizer.")
    try:
        preview = conversion_preview_value(
            title=selection.title, start_at=selection.start_at, end_at=selection.end_at,
            timezone_name=selection.timezone, location=selection.location,
            gathering_format=selection.gathering_format, max_attendees=selection.max_attendees,
            organizer_display_name=organizer.get("full_name", "Organizer"),
        )
    except ProposalValidationError as exc:
        raise _unprocessable(exc.code, "The private reunion draft details are not valid.") from None
    return preview, organizer


@router.post("/{proposal_reference}/conversion-preview")
async def conversion_preview(
    proposal_reference: str, payload: ConversionSelection, current_user: dict[str, Any] = Depends(get_current_user)
):
    actor, proposal = await _organizer_proposal(proposal_reference, current_user)
    if proposal.get("state") != "published":
        raise _conflict("proposal_not_convertible", "This proposal is not available for conversion.")
    preview, _ = await _conversion_preview(proposal, payload)
    preview["proposal_state"] = proposal["state"]
    preview["proposal_revision"] = proposal["revision"]
    return preview


def _conversion_response(conversion: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "draft_created",
        "proposal_state": "converted",
        "next_action": "continue_planning",
        "planning_path": f"/reunion/command/{conversion['created_event_id']}",
    }


def _assert_conversion_payload(conversion: dict[str, Any], preview_digest: str) -> None:
    if conversion.get("payload_hash") != preview_digest:
        raise _conflict(
            "proposal_already_converted",
            "This proposal already created a different canonical draft.",
        )


async def _recover_conversion(proposal_id: str) -> dict[str, Any] | None:
    # A competing transaction can commit between the proposal read and the
    # conversion lookup. Retry only bounded local reads so both callers can
    # recover the same canonical draft.
    for _ in range(10):
        existing = await gathering_proposal_conversions_collection.find_one(
            {"proposal_id": proposal_id}, {"_id": 0}
        )
        if existing:
            return existing
        await asyncio.sleep(0.01)
    return None


async def _finish_conversion(conversion: dict[str, Any]) -> None:
    await notification_events_collection.delete_many({
        "id": f"gathering-proposal-published:{conversion['proposal_id']}",
        "community_id": conversion["community_id"],
    })
    proposer = conversion.get("proposer_user_id")
    if proposer:
        await _insert_notification(_notification(
            notification_id=f"gathering-proposal-converted:{conversion['proposal_id']}",
            community_id=conversion["community_id"], event_type="gathering-proposal-converted",
            title="Your gathering proposal moved into planning",
            description="An organizer created a private draft in Kindred.", recipients=[proposer],
            related_id="",
        ))


@router.post("/{proposal_reference}/convert")
async def convert_proposal(
    proposal_reference: str, payload: ConversionOperation, current_user: dict[str, Any] = Depends(get_current_user)
):
    actor, proposal = await _organizer_proposal(proposal_reference, current_user)
    existing = await gathering_proposal_conversions_collection.find_one({"proposal_id": proposal["id"]}, {"_id": 0})
    if existing:
        _assert_conversion_payload(existing, payload.preview_digest)
        await _finish_conversion(existing)
        return _conversion_response(existing)
    if proposal.get("state") == "converted":
        existing = await _recover_conversion(proposal["id"])
        if existing:
            _assert_conversion_payload(existing, payload.preview_digest)
            await _finish_conversion(existing)
            return _conversion_response(existing)
    if proposal.get("state") != "published" or proposal.get("revision") != payload.expected_revision:
        raise _conflict("proposal_state_changed", "This proposal changed. Refresh before converting it.")
    selection = ConversionSelection(**payload.model_dump(exclude={"expected_revision", "preview_digest", "idempotency_key"}))
    preview, organizer = await _conversion_preview(proposal, selection)
    if preview["preview_digest"] != payload.preview_digest:
        raise _conflict("conversion_preview_changed", "The exact conversion preview changed. Review it again.")
    operation_hash = _operation_hash(
        payload.idempotency_key, community_id=proposal["community_id"], actor_id=actor["id"], subject=proposal["id"]
    )
    timestamp = now_iso()
    event_doc = new_draft_document(
        community_id=proposal["community_id"], organizer=organizer, proposal_id=proposal["id"],
        preview=preview, timestamp=timestamp,
    )
    conversion = {
        "id": str(uuid.uuid4()), "proposal_id": proposal["id"],
        "proposal_reference": proposal["public_reference"], "community_id": proposal["community_id"],
        "created_event_id": event_doc["id"], "converted_by_user_id": actor["id"],
        "selected_organizer_user_id": organizer["id"], "proposer_user_id": proposal.get("proposer_user_id"),
        "operation_hash": operation_hash, "payload_hash": digest_payload(preview["proposal"]),
        "created_at": timestamp,
    }

    async def transaction(session):
        fresh_actor, community = await _active_actor(actor, session=session)
        if fresh_actor.get("role") not in {"host", "organizer"} or community_lifecycle_state(community) != ACTIVE:
            raise _conflict("conversion_authorization_changed", "Organizer authorization changed. Refresh before trying again.")
        fresh = await gathering_proposals_collection.find_one(
            {
                "id": proposal["id"], "community_id": proposal["community_id"],
                "state": "published", "revision": payload.expected_revision,
            }, {"_id": 0}, session=session,
        )
        if not fresh:
            raise _conflict("proposal_state_changed", "This proposal changed. Refresh before converting it.")
        fresh_preview, fresh_organizer = await _conversion_preview(fresh, selection, session=session)
        if fresh_preview["preview_digest"] != payload.preview_digest or fresh_organizer["id"] != organizer["id"]:
            raise _conflict("conversion_preview_changed", "The exact conversion preview changed. Review it again.")
        await gathering_proposal_conversions_collection.insert_one(conversion.copy(), session=session)
        await events_collection.insert_one(event_doc.copy(), session=session)
        result = await gathering_proposals_collection.update_one(
            {"id": fresh["id"], "state": "published", "revision": payload.expected_revision},
            {"$set": {"state": "converted", "updated_at": timestamp}, "$inc": {"revision": 1}},
            session=session,
        )
        if result.modified_count != 1:
            raise _conflict("proposal_state_changed", "This proposal changed. Refresh before converting it.")

    try:
        async with await client.start_session() as session:
            await session.with_transaction(transaction)
    except HTTPException as exc:
        existing = await _recover_conversion(proposal["id"])
        if exc.status_code != status.HTTP_409_CONFLICT or not existing:
            raise
        _assert_conversion_payload(existing, payload.preview_digest)
        conversion = existing
    except DuplicateKeyError:
        existing = await _recover_conversion(proposal["id"])
        if not existing:
            raise _conflict("proposal_conversion_conflict", "The proposal conversion changed. Refresh before trying again.")
        _assert_conversion_payload(existing, payload.preview_digest)
        conversion = existing
    await _finish_conversion(conversion)
    return _conversion_response(conversion)
