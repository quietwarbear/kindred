"""Authenticated, attendee-safe private reunion memory capsule routes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import client, events_collection, memories_collection
from dependencies import get_current_user, get_event_for_user, now_iso
from models import (
    ReunionMemoryContributionRequest,
    ReunionMemoryOperationRequest,
)
from reunion_memory_capsule import build_reunion_memory_capsule
from rsvp_integrity import RSVPWriteConflict, compare_and_swap_event

router = APIRouter(prefix="/api")


class CapsuleConflict(RuntimeError):
    pass


class CapsuleNotFound(RuntimeError):
    pass


def contribution_identity(
    event_id: str, user_id: str, community_id: str
) -> tuple[str, str]:
    source = f"{community_id}:{event_id}:{user_id}:reunion_attendee_prompt"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"attendee-memory:{digest}", digest[:32]


def _operation_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_digest(story: str, contribution_status: str) -> str:
    canonical = json.dumps(
        {"status": contribution_status, "story": story},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _authorized_reunion(
    event_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    event = await get_event_for_user(event_id, current_user)
    if event.get("event_template") != "reunion":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reunion not found.",
        )
    return event


async def _capsule_memories(
    event_id: str,
    current_user: dict[str, Any],
) -> list[dict[str, Any]]:
    return (
        await memories_collection.find(
            {
                "community_id": current_user["community_id"],
                "event_id": event_id,
                "$or": [
                    {"capsule_status": {"$ne": "draft"}},
                    {"created_by": current_user["id"]},
                ],
            },
            {"_id": 0},
        )
        .sort("created_at", 1)
        .to_list(500)
    )


async def capsule_projection(
    event: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    return build_reunion_memory_capsule(
        event,
        await _capsule_memories(event["id"], current_user),
        current_user,
    )


async def save_capsule_contribution(
    event_id: str,
    payload: ReunionMemoryContributionRequest,
    current_user: dict[str, Any],
    *,
    expected_memory_id: str | None = None,
    prompt_retry: bool = False,
) -> dict[str, Any]:
    """Persist one contribution inside an event-authorization transaction."""
    story = payload.story.strip()
    operation_hash = _operation_hash(payload.idempotency_key)
    payload_hash = _payload_digest(story, payload.status)
    mongo_id, memory_id = contribution_identity(
        event_id,
        current_user["id"],
        current_user["community_id"],
    )
    if expected_memory_id and expected_memory_id != memory_id:
        raise CapsuleNotFound()

    async def transaction(session):
        event = await events_collection.find_one(
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
                "event_template": "reunion",
            },
            {"_id": 0},
            session=session,
        )
        if not event:
            raise CapsuleNotFound()
        existing = await memories_collection.find_one(
            {"_id": mongo_id},
            session=session,
        )
        if existing:
            if (
                existing.get("community_id") != current_user["community_id"]
                or existing.get("event_id") != event_id
                or existing.get("created_by") != current_user["id"]
            ):
                raise CapsuleNotFound()
            previous_operation = existing.get("capsule_operation_hash", "")
            if previous_operation == operation_hash:
                if existing.get("capsule_payload_hash") != payload_hash:
                    raise CapsuleConflict()
                return existing
            if expected_memory_id is None:
                if prompt_retry:
                    return existing
                raise CapsuleConflict()
            revision = int(existing.get("capsule_revision", 0) or 0)
            query: dict[str, Any] = {
                "_id": mongo_id,
                "created_by": current_user["id"],
                "event_id": event_id,
            }
            query["capsule_revision"] = (
                revision if "capsule_revision" in existing else {"$exists": False}
            )
            result = await memories_collection.update_one(
                query,
                {
                    "$set": {
                        "description": story,
                        "capsule_status": payload.status,
                        "capsule_operation_hash": operation_hash,
                        "capsule_payload_hash": payload_hash,
                        "updated_at": now_iso(),
                    },
                    "$inc": {"capsule_revision": 1},
                },
                session=session,
            )
            if result.matched_count != 1:
                raise CapsuleConflict()
            return await memories_collection.find_one(
                {"_id": mongo_id},
                session=session,
            )
        if expected_memory_id is not None:
            raise CapsuleNotFound()
        created_at = now_iso()
        memory = {
            "_id": mongo_id,
            "id": memory_id,
            "community_id": current_user["community_id"],
            "created_by": current_user["id"],
            "created_by_name": current_user.get("full_name", ""),
            "title": "A reunion story",
            "description": story,
            "event_id": event_id,
            "event_title": event.get("title", ""),
            "category": "story",
            "image_data_url": "",
            "voice_note_data_url": "",
            "tags": [],
            "ai_summary": "",
            "sentiment": "neutral",
            "mood": "warm",
            "comments": [],
            "source": "reunion_attendee_prompt",
            "capsule_status": payload.status,
            "capsule_operation_hash": operation_hash,
            "capsule_payload_hash": payload_hash,
            "capsule_revision": 1,
            "created_at": created_at,
            "updated_at": created_at,
        }
        await memories_collection.insert_one(memory, session=session)
        return memory

    async with await client.start_session() as session:
        return await session.with_transaction(transaction)


def _translate_capsule_error(error: Exception) -> HTTPException:
    if isinstance(error, CapsuleNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reunion contribution not found.",
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "memory_contribution_conflict",
            "message": "This contribution changed. Refresh before trying again.",
        },
    )


@router.get("/events/{event_id}/memory-capsule")
async def reunion_memory_capsule(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _authorized_reunion(event_id, current_user)
    return await capsule_projection(event, current_user)


@router.post("/events/{event_id}/memory-capsule/contribution")
async def create_reunion_memory_contribution(
    event_id: str,
    payload: ReunionMemoryContributionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    try:
        await save_capsule_contribution(event_id, payload, current_user)
    except (CapsuleConflict, CapsuleNotFound) as exc:
        raise _translate_capsule_error(exc) from exc
    event = await _authorized_reunion(event_id, current_user)
    return await capsule_projection(event, current_user)


@router.put("/events/{event_id}/memory-capsule/contribution/{memory_id}")
async def update_reunion_memory_contribution(
    event_id: str,
    memory_id: str,
    payload: ReunionMemoryContributionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    try:
        await save_capsule_contribution(
            event_id,
            payload,
            current_user,
            expected_memory_id=memory_id,
        )
    except (CapsuleConflict, CapsuleNotFound) as exc:
        raise _translate_capsule_error(exc) from exc
    event = await _authorized_reunion(event_id, current_user)
    return await capsule_projection(event, current_user)


@router.delete("/events/{event_id}/memory-capsule/contribution/{memory_id}")
async def withdraw_reunion_memory_contribution(
    event_id: str,
    memory_id: str,
    payload: ReunionMemoryOperationRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    operation_hash = _operation_hash(payload.idempotency_key)
    mongo_id, own_memory_id = contribution_identity(
        event_id,
        current_user["id"],
        current_user["community_id"],
    )
    if memory_id != own_memory_id:
        raise _translate_capsule_error(CapsuleNotFound())

    async def transaction(session):
        event = await events_collection.find_one(
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
                "event_template": "reunion",
            },
            {"_id": 0, "id": 1, "memory_capsule_withdrawal_hashes": 1},
            session=session,
        )
        if not event:
            raise CapsuleNotFound()
        if operation_hash in (event.get("memory_capsule_withdrawal_hashes") or []):
            return
        memory = await memories_collection.find_one(
            {
                "_id": mongo_id,
                "event_id": event_id,
                "created_by": current_user["id"],
            },
            {"_id": 1},
            session=session,
        )
        if not memory:
            raise CapsuleNotFound()
        await memories_collection.delete_one(
            {"_id": mongo_id, "created_by": current_user["id"]},
            session=session,
        )
        await events_collection.update_one(
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
                "event_template": "reunion",
            },
            {"$addToSet": {"memory_capsule_withdrawal_hashes": operation_hash}},
            session=session,
        )

    try:
        async with await client.start_session() as session:
            await session.with_transaction(transaction)
    except (CapsuleConflict, CapsuleNotFound) as exc:
        raise _translate_capsule_error(exc) from exc
    event = await _authorized_reunion(event_id, current_user)
    return await capsule_projection(event, current_user)


@router.post("/events/{event_id}/memory-capsule/reviewed")
async def review_reunion_memory_capsule(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await _authorized_reunion(event_id, current_user)

    def mutate(event: dict[str, Any]) -> dict[str, Any]:
        reviewers = list(dict.fromkeys(event.get("memory_capsule_reviewed_by") or []))
        if current_user["id"] not in reviewers:
            reviewers.append(current_user["id"])
        return {"memory_capsule_reviewed_by": reviewers}

    try:
        event = await compare_and_swap_event(
            events_collection,
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
                "event_template": "reunion",
            },
            mutate,
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "memory_capsule_write_conflict",
                "message": "The capsule changed. Refresh before trying again.",
            },
        ) from exc
    if not event:
        raise _translate_capsule_error(CapsuleNotFound())
    return await capsule_projection(event, current_user)
