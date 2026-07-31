"""Private post-reunion recap and next-gathering continuity routes."""

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
    memories_collection,
    next_gathering_operations_collection,
    notification_events_collection,
    reunion_recaps_collection,
    users_collection,
)
from dependencies import ensure_minimum_role, get_current_user, get_event_for_user, now_iso
from family_space_activation import ACTIVE, community_lifecycle_state
from itinerary import parse_local_datetime, valid_timezone
from reunion_recap import (
    build_recap_projection,
    carry_forward_catalog,
    preview_digest,
    recap_state,
    reunion_completion,
)

router = APIRouter(prefix="/api")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_MESSAGE_LIMIT = 2000


class RecapMessageRequest(BaseModel):
    message: str = ""
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=16, max_length=128)


class RecapTransitionRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=16, max_length=128)


class NextGatheringSelection(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    start_at: str = Field(min_length=1, max_length=80)
    end_at: str = Field(min_length=1, max_length=80)
    timezone: str = Field(min_length=1, max_length=100)
    itinerary_selection_references: list[str] = Field(default_factory=list, max_length=100)
    contribution_selection_references: list[str] = Field(default_factory=list, max_length=100)
    carry_gathering_format: bool = False
    carry_capacity: bool = False


class NextGatheringCreateRequest(NextGatheringSelection):
    preview_digest: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=16, max_length=128)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _operation_hash(value: str, event: dict[str, Any], user: dict[str, Any]) -> str:
    if not _IDEMPOTENCY_KEY.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_idempotency_key", "message": "This operation cannot be safely retried."},
        )
    return _digest(f"{event['community_id']}\n{event['id']}\n{user['id']}\n{value}")


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})


def _validated_message(value: str) -> str:
    message = value.strip()
    if len(message) > _MESSAGE_LIMIT or any(
        ord(character) < 32 and character not in {"\n", "\r", "\t"}
        for character in message
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_recap_message", "message": "Use up to 2,000 standard text characters."},
        )
    return message


async def _active_reunion(event_id: str, user: dict[str, Any]) -> dict[str, Any]:
    event = await get_event_for_user(event_id, user)
    community = await communities_collection.find_one(
        {"id": user["community_id"]}, {"_id": 0, "lifecycle_state": 1}
    )
    if (
        event.get("event_template") != "reunion"
        or community_lifecycle_state(community or {}) != ACTIVE
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reunion recap not found.")
    return event


def _require_ready(event: dict[str, Any]) -> None:
    completion = reunion_completion(event)
    if completion["state"] == "legacy_conflict":
        raise _conflict("reunion_completion_legacy_conflict", "This reunion has ambiguous completion data and remains unchanged.")
    if completion["state"] != "ready":
        raise _conflict("reunion_not_complete", "The reunion has not reached its validated final end.")


async def _memories(event: dict[str, Any], user: dict[str, Any]) -> list[dict[str, Any]]:
    return await memories_collection.find(
        {
            "community_id": event["community_id"],
            "event_id": event["id"],
            "created_by": user["id"],
        },
        {"_id": 0, "capsule_status": 1, "created_by": 1, "created_at": 1, "updated_at": 1},
    ).to_list(100)


async def _published_memory_count(event: dict[str, Any]) -> int:
    return await memories_collection.count_documents({
        "community_id": event["community_id"],
        "event_id": event["id"],
        "capsule_status": "published",
    })


async def _recap(event: dict[str, Any]) -> dict[str, Any] | None:
    return await reunion_recaps_collection.find_one(
        {"event_id": event["id"], "community_id": event["community_id"]}, {"_id": 0}
    )


async def _has_next_gathering(event: dict[str, Any]) -> bool:
    return bool(await next_gathering_operations_collection.find_one(
        {"source_event_id": event["id"], "community_id": event["community_id"]}, {"_id": 0, "id": 1}
    ))


async def _projection(
    event: dict[str, Any], recap: dict[str, Any] | None, user: dict[str, Any], *, organizer_preview: bool
) -> dict[str, Any]:
    memories, next_gathering_started, published_count = await asyncio.gather(
        _memories(event, user),
        _has_next_gathering(event),
        _published_memory_count(event),
    )
    return build_recap_projection(
        event,
        recap,
        memories,
        user,
        organizer_preview=organizer_preview,
        next_gathering_started=next_gathering_started,
        published_memory_count=published_count,
    )


@router.get("/events/{event_id}/recap")
async def reunion_recap(event_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    event = await _active_reunion(event_id, current_user)
    recap = await _recap(event)
    if recap_state(event, recap) != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reunion recap not found.")
    return await _projection(event, recap, current_user, organizer_preview=False)


@router.get("/events/{event_id}/recap/organizer")
async def organizer_recap_preview(event_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event = await _active_reunion(event_id, current_user)
    completion = reunion_completion(event)
    projection = await _projection(event, await _recap(event), current_user, organizer_preview=True)
    projection["completion"] = completion
    projection["carry_forward_catalog"] = carry_forward_catalog(event)
    return projection


async def _ensure_recap_record(event: dict[str, Any]) -> None:
    identity = {"event_id": event["id"], "community_id": event["community_id"]}
    try:
        await reunion_recaps_collection.update_one(
            identity,
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "event_id": event["id"],
                "community_id": event["community_id"],
                "state": "ready",
                "message": "",
                "revision": 0,
                "operations": [],
                "created_at": now_iso(),
            }},
            upsert=True,
        )
    except DuplicateKeyError:
        # Two first mutations can both observe no recap before one upsert wins.
        # Accept only that expected race; an unrelated duplicate must still fail.
        if not await reunion_recaps_collection.find_one(identity, {"_id": 1}):
            raise


def _prior_operation(recap: dict[str, Any], operation_hash: str, payload_hash: str) -> bool:
    prior = next(
        (item for item in recap.get("operations") or [] if item.get("operation_hash") == operation_hash),
        None,
    )
    if prior and prior.get("payload_hash") != payload_hash:
        raise _conflict("idempotency_payload_conflict", "This operation key was already used for different recap content.")
    return bool(prior)


async def _recap_mutation(
    event: dict[str, Any],
    user: dict[str, Any],
    *,
    action: Literal["edit", "publish", "unpublish"],
    expected_revision: int,
    idempotency_key: str,
    message: str | None = None,
) -> dict[str, Any]:
    _require_ready(event)
    operation_hash = _operation_hash(idempotency_key, event, user)
    normalized_message = _validated_message(message) if message is not None else None
    payload_hash = _digest(json.dumps({"action": action, "message": normalized_message}, sort_keys=True))
    await _ensure_recap_record(event)
    current = await _recap(event)
    if not current:
        raise _conflict("recap_write_conflict", "The recap changed. Refresh before trying again.")
    if _prior_operation(current, operation_hash, payload_hash):
        current["_mutation_applied"] = False
        return current
    desired_state = {"edit": current.get("state", "ready"), "publish": "published", "unpublish": "unpublished"}[action]
    if action in {"publish", "unpublish"} and current.get("state") == desired_state:
        current["_mutation_applied"] = False
        return current
    if action == "edit" and current.get("message", "") == normalized_message:
        current["_mutation_applied"] = False
        return current
    if int(current.get("revision", 0) or 0) != expected_revision:
        raise _conflict("recap_revision_conflict", "The recap changed. Refresh before trying again.")

    set_fields: dict[str, Any] = {
        "state": desired_state,
        "updated_at": now_iso(),
        "updated_by_user_id": user["id"],
    }
    if action == "publish":
        set_fields.update({
            "publish_operation_hash": operation_hash,
            "unpublish_operation_hash": "",
        })
    elif action == "unpublish":
        set_fields.update({
            "publish_operation_hash": "",
            "unpublish_operation_hash": operation_hash,
        })
    if normalized_message is not None:
        set_fields.update({
            "message": normalized_message,
            "author_user_id": user["id"],
            "author_tombstone": False,
        })
    operation = {
        "operation_hash": operation_hash,
        "payload_hash": payload_hash,
        "action": action,
        "resulting_revision": expected_revision + 1,
        "at": now_iso(),
    }
    updated = await reunion_recaps_collection.find_one_and_update(
        {
            "event_id": event["id"],
            "community_id": event["community_id"],
            "revision": expected_revision,
        },
        {
            "$set": set_fields,
            "$inc": {"revision": 1},
            "$push": {"operations": {"$each": [operation], "$slice": -100}},
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        concurrent = await _recap(event)
        if concurrent and _prior_operation(concurrent, operation_hash, payload_hash):
            concurrent["_mutation_applied"] = False
            return concurrent
        raise _conflict("recap_revision_conflict", "The recap changed. Refresh before trying again.")
    updated["_mutation_applied"] = True
    return updated


async def _publish_notification(event: dict[str, Any], operation_hash: str) -> None:
    hidden_ids = set(event.get("hidden_from_user_ids") or [])
    users = await users_collection.find(
        {"community_id": event["community_id"], "id": {"$nin": list(hidden_ids)}},
        {"_id": 0, "id": 1},
    ).to_list(2000)
    recipients = [item["id"] for item in users if item.get("id")]
    notification_id = f"reunion-recap:{operation_hash[:32]}"
    await notification_events_collection.update_one(
        {"id": notification_id},
        {"$setOnInsert": {
            "id": notification_id,
            "community_id": event["community_id"],
            "actor_name": "Kindred",
            "event_type": "reunion-recap-published",
            "title": "The private reunion recap is ready",
            "description": "Review the reunion and continue preserving family memories in Kindred.",
            "related_id": event["id"],
            "audience_scope": "user",
            "recipient_user_ids": recipients,
            "read_by_user_ids": [],
            "created_at": now_iso(),
        }},
        upsert=True,
    )


@router.put("/events/{event_id}/recap/message")
async def edit_recap_message(
    event_id: str, payload: RecapMessageRequest, current_user: dict[str, Any] = Depends(get_current_user)
):
    ensure_minimum_role(current_user, "organizer")
    event = await _active_reunion(event_id, current_user)
    recap = await _recap_mutation(
        event,
        current_user,
        action="edit",
        expected_revision=payload.expected_revision,
        idempotency_key=payload.idempotency_key,
        message=payload.message,
    )
    return await _projection(event, recap, current_user, organizer_preview=True)


@router.post("/events/{event_id}/recap/publish")
async def publish_recap(
    event_id: str, payload: RecapTransitionRequest, current_user: dict[str, Any] = Depends(get_current_user)
):
    ensure_minimum_role(current_user, "organizer")
    event = await _active_reunion(event_id, current_user)
    recap = await _recap_mutation(
        event,
        current_user,
        action="publish",
        expected_revision=payload.expected_revision,
        idempotency_key=payload.idempotency_key,
    )
    operation_hash = _operation_hash(payload.idempotency_key, event, current_user)
    recap.pop("_mutation_applied", None)
    if recap.get("state") == "published" and recap.get("publish_operation_hash") == operation_hash:
        # Idempotent even after a crash between the recap CAS and notification insert.
        await _publish_notification(event, operation_hash)
    return await _projection(event, recap, current_user, organizer_preview=True)


@router.post("/events/{event_id}/recap/unpublish")
async def unpublish_recap(
    event_id: str, payload: RecapTransitionRequest, current_user: dict[str, Any] = Depends(get_current_user)
):
    ensure_minimum_role(current_user, "organizer")
    event = await _active_reunion(event_id, current_user)
    recap = await _recap_mutation(
        event,
        current_user,
        action="unpublish",
        expected_revision=payload.expected_revision,
        idempotency_key=payload.idempotency_key,
    )
    operation_hash = _operation_hash(payload.idempotency_key, event, current_user)
    recap.pop("_mutation_applied", None)
    if recap.get("state") == "unpublished" and recap.get("unpublish_operation_hash") == operation_hash:
        await notification_events_collection.delete_many({
            "community_id": event["community_id"],
            "related_id": event["id"],
            "event_type": "reunion-recap-published",
        })
    return await _projection(event, recap, current_user, organizer_preview=True)


def _next_gathering_preview(event: dict[str, Any], payload: NextGatheringSelection) -> dict[str, Any]:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail={"code": "invalid_next_gathering_title", "message": "Choose a gathering title."})
    timezone_name = payload.timezone.strip()
    if not valid_timezone(timezone_name):
        raise HTTPException(status_code=422, detail={"code": "invalid_next_gathering_timezone", "message": "Choose a valid gathering timezone."})
    start = parse_local_datetime(payload.start_at, timezone_name)
    end = parse_local_datetime(payload.end_at, timezone_name)
    if not start or not end or end <= start:
        raise HTTPException(status_code=422, detail={"code": "invalid_next_gathering_boundary", "message": "Choose valid, unambiguous start and end times."})

    catalog = carry_forward_catalog(event)
    activities = {item["selection_reference"]: item for item in catalog["itinerary_templates"]}
    contributions = {item["selection_reference"]: item for item in catalog["contribution_categories"]}
    requested_activities = list(dict.fromkeys(payload.itinerary_selection_references))
    requested_contributions = list(dict.fromkeys(payload.contribution_selection_references))
    if any(reference not in activities for reference in requested_activities) or any(
        reference not in contributions for reference in requested_contributions
    ):
        raise HTTPException(status_code=422, detail={"code": "invalid_carry_forward_selection", "message": "One or more carry-forward choices are no longer available."})

    proposal = {
        "new_gathering": {
            "title": title,
            "start_at": payload.start_at,
            "end_at": payload.end_at,
            "timezone": timezone_name,
            "publication_state": "organizer_draft",
            "invitation_count": 0,
            "rsvp_response_count": 0,
        },
        "carried_forward": {
            "gathering_format": (
                event.get("gathering_format")
                if payload.carry_gathering_format
                and event.get("gathering_format") in {"in-person", "online", "hybrid"}
                else "in-person"
            ),
            "max_attendees": (
                int(event.get("max_attendees", 50) or 50)
                if payload.carry_capacity
                and isinstance(event.get("max_attendees", 50), int)
                and 1 <= int(event.get("max_attendees", 50) or 50) <= 10000
                else 50
            ),
            "itinerary_templates": [activities[reference] for reference in requested_activities],
            "contribution_categories": [contributions[reference] for reference in requested_contributions],
        },
        "guarantees": {
            "zero_invitations": True,
            "zero_responses": True,
            "zero_assignments": True,
            "new_structural_identifiers": True,
        },
    }
    return {"proposal": proposal, "preview_digest": preview_digest(proposal)}


@router.post("/events/{event_id}/next-gathering/preview")
async def next_gathering_preview(
    event_id: str, payload: NextGatheringSelection, current_user: dict[str, Any] = Depends(get_current_user)
):
    ensure_minimum_role(current_user, "organizer")
    event = await _active_reunion(event_id, current_user)
    _require_ready(event)
    return _next_gathering_preview(event, payload)


def _new_event_document(
    source: dict[str, Any], user: dict[str, Any], proposal: dict[str, Any], operation_hash: str
) -> dict[str, Any]:
    new_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kindred-next-gathering:{operation_hash}"))
    gathering = proposal["new_gathering"]
    carried = proposal["carried_forward"]
    timestamp = now_iso()
    agenda = [
        {
            "id": str(uuid.uuid4()),
            "title": item["title"],
            "description": "",
            "start_at": "",
            "end_at": "",
            "timezone": gathering["timezone"],
            "attendance_requested": item["attendance_requested"],
            "visibility": "draft",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        for item in carried["itinerary_templates"]
    ]
    potluck = [
        {"id": str(uuid.uuid4()), "item_name": item["label"], "assigned_to": "", "assigned_to_id": ""}
        for item in carried["contribution_categories"]
        if item["kind"] == "potluck"
    ]
    volunteer = [
        {"id": str(uuid.uuid4()), "title": item["label"], "needed_count": 1, "assigned_members": [], "assigned_member_ids": []}
        for item in carried["contribution_categories"]
        if item["kind"] == "volunteer"
    ]
    return {
        "id": new_id,
        "community_id": source["community_id"],
        "created_by": user["id"],
        "created_by_name": user.get("full_name", "Organizer"),
        "title": gathering["title"],
        "description": "",
        "start_at": gathering["start_at"],
        "end_at": gathering["end_at"],
        "timezone": gathering["timezone"],
        "location": "",
        "event_template": "reunion",
        "gathering_format": carried["gathering_format"],
        "max_attendees": carried["max_attendees"],
        "publication_state": "organizer_draft",
        "hidden_from_user_ids": [],
        "event_invites": [],
        "rsvp_records": [],
        "activity_rsvps": [],
        "agenda": agenda,
        "potluck_items": potluck,
        "volunteer_slots": volunteer,
        "planning_checklist": [],
        "event_role_assignments": [],
        "assigned_roles": [],
        "rsvp_revision": 0,
        "created_at": timestamp,
        "client_request_id": "",
    }


def _creation_response(operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "draft_created",
        "next_action": "continue_planning",
        "planning_path": f"/reunion/command/{operation['created_event_id']}",
    }


@router.post("/events/{event_id}/next-gathering")
async def create_next_gathering(
    event_id: str, payload: NextGatheringCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)
):
    ensure_minimum_role(current_user, "organizer")
    event = await _active_reunion(event_id, current_user)
    _require_ready(event)
    operation_hash = _operation_hash(payload.idempotency_key, event, current_user)
    selection = NextGatheringSelection(**payload.model_dump(exclude={"preview_digest", "idempotency_key"}))
    preview = _next_gathering_preview(event, selection)
    if preview["preview_digest"] != payload.preview_digest:
        raise _conflict("next_gathering_preview_changed", "The carry-forward preview changed. Review it again before creating the draft.")
    payload_hash = preview_digest(preview["proposal"])
    existing = await next_gathering_operations_collection.find_one({"operation_hash": operation_hash}, {"_id": 0})
    if existing:
        if existing.get("payload_hash") != payload_hash:
            raise _conflict("idempotency_payload_conflict", "This operation key was already used for a different draft.")
        return _creation_response(existing)

    event_doc = _new_event_document(event, current_user, preview["proposal"], operation_hash)
    operation = {
        "id": str(uuid.uuid4()),
        "operation_hash": operation_hash,
        "payload_hash": payload_hash,
        "community_id": event["community_id"],
        "source_event_id": event["id"],
        "created_event_id": event_doc["id"],
        "created_by_user_id": current_user["id"],
        "created_at": now_iso(),
    }

    async def transaction(session):
        source = await events_collection.find_one(
            {
                "id": event["id"],
                "community_id": event["community_id"],
                "event_template": "reunion",
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            {"_id": 0},
            session=session,
        )
        if not source or reunion_completion(source)["state"] != "ready":
            raise _conflict("reunion_completion_changed", "The reunion completion state changed. Refresh before trying again.")
        actor = await users_collection.find_one(
            {
                "id": current_user["id"],
                "community_id": event["community_id"],
                "role": {"$in": ["host", "organizer"]},
            },
            {"_id": 0, "id": 1},
            session=session,
        )
        community = await communities_collection.find_one(
            {"id": event["community_id"], "lifecycle_state": ACTIVE},
            {"_id": 0, "id": 1},
            session=session,
        )
        if not actor or not community:
            raise _conflict("next_gathering_authorization_changed", "The family-space authorization changed. Refresh before trying again.")
        fresh_preview = _next_gathering_preview(source, selection)
        if fresh_preview["preview_digest"] != payload.preview_digest:
            raise _conflict("next_gathering_preview_changed", "The carry-forward preview changed. Review it again before creating the draft.")
        await next_gathering_operations_collection.insert_one(operation.copy(), session=session)
        await events_collection.insert_one(event_doc.copy(), session=session)

    try:
        async with await client.start_session() as session:
            await session.with_transaction(transaction)
    except DuplicateKeyError:
        existing = await next_gathering_operations_collection.find_one({"operation_hash": operation_hash}, {"_id": 0})
        if not existing or existing.get("payload_hash") != payload_hash:
            raise _conflict("next_gathering_creation_conflict", "The draft creation changed. Refresh before trying again.")
        return _creation_response(existing)
    return _creation_response(operation)
