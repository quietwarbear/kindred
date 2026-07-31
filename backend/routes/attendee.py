"""Authenticated, attendee-safe reunion hub routes."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from attendee_hub import build_attendee_hub
from db import events_collection, memories_collection
from dependencies import get_current_user, get_event_for_user, now_iso
from models import AttendeeMemoryRequest
from rsvp_integrity import RSVPWriteConflict, compare_and_swap_event

router = APIRouter(prefix="/api")


async def _attendee_reunion(
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


async def _has_attendee_memory(
    event: dict[str, Any],
    current_user: dict[str, Any],
) -> bool:
    memory = await memories_collection.find_one(
        {
            "community_id": current_user["community_id"],
            "event_id": event["id"],
            "created_by": current_user["id"],
            "source": "reunion_attendee_prompt",
        },
        {"_id": 0, "id": 1},
    )
    return bool(memory)


async def _hub(
    event: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    return build_attendee_hub(
        event,
        current_user,
        has_memory=await _has_attendee_memory(event, current_user),
    )


@router.get("/events/{event_id}/attendee-hub")
async def attendee_hub(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _attendee_reunion(event_id, current_user)
    return await _hub(event, current_user)


@router.post("/events/{event_id}/attendee-hub/itinerary-reviewed")
async def review_attendee_itinerary(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await _attendee_reunion(event_id, current_user)

    def mutate(event: dict[str, Any]) -> dict[str, Any]:
        reviewers = list(dict.fromkeys(event.get("attendee_hub_reviewed_by") or []))
        if current_user["id"] not in reviewers:
            reviewers.append(current_user["id"])
        return {"attendee_hub_reviewed_by": reviewers}

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
            detail={"code": "attendee_write_conflict", "message": str(exc)},
        ) from exc
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reunion not found.",
        )
    return await _hub(event, current_user)


@router.post("/events/{event_id}/attendee-hub/memory")
async def create_attendee_memory(
    event_id: str,
    payload: AttendeeMemoryRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _attendee_reunion(event_id, current_user)
    story = payload.story.strip()
    if not story:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A story is required.",
        )
    existing = await memories_collection.find_one(
        {
            "community_id": current_user["community_id"],
            "event_id": event_id,
            "created_by": current_user["id"],
            "source": "reunion_attendee_prompt",
        },
        {"_id": 0},
    )
    if existing:
        return await _hub(event, current_user)

    # This path deliberately bypasses AI tagging and every external provider.
    # It uses the existing community memory schema and visibility boundary.
    operation_source = (
        f"{current_user['community_id']}:{event_id}:{current_user['id']}:"
        "reunion_attendee_prompt"
    )
    operation_hash = hashlib.sha256(operation_source.encode("utf-8")).hexdigest()
    memory = {
        "_id": f"attendee-memory:{operation_hash}",
        "id": operation_hash[:32],
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_by_name": current_user.get("full_name", ""),
        "title": f"A story from {event.get('title', 'our reunion')}"[:160],
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
        "created_at": now_iso(),
    }
    await memories_collection.update_one(
        {"_id": memory["_id"]},
        {"$setOnInsert": memory},
        upsert=True,
    )
    return build_attendee_hub(event, current_user, has_memory=True)
