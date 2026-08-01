"""Authenticated, attendee-safe reunion hub routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from attendee_hub import build_attendee_hub
from db import events_collection, memories_collection, reunion_recaps_collection
from dependencies import get_current_user, get_event_for_user
from models import AttendeeMemoryRequest, ReunionMemoryContributionRequest
from routes.reunion_memories import (
    CapsuleConflict,
    CapsuleNotFound,
    contribution_identity,
    save_capsule_contribution,
)
from rsvp_integrity import RSVPWriteConflict, compare_and_swap_event
from reunion_recap import recap_state

router = APIRouter(prefix="/api")


async def _attendee_reunion(
    event_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    event = await get_event_for_user(event_id, current_user)
    if event.get("event_template") not in {"reunion", "holiday_meal"}:
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
        },
        {"_id": 0, "id": 1},
    )
    return bool(memory)


async def _hub(
    event: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    hub = build_attendee_hub(
        event,
        current_user,
        has_memory=await _has_attendee_memory(event, current_user),
    )
    recap = await reunion_recaps_collection.find_one(
        {"event_id": event["id"], "community_id": current_user["community_id"]},
        {"_id": 0, "state": 1},
    )
    hub["recap"]["state"] = recap_state(event, recap)
    return hub


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
                "event_template": {"$in": ["reunion", "holiday_meal"]},
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

    # The capsule store rechecks event visibility inside the same transaction
    # as the memory insert. It deliberately bypasses AI and every provider.
    _mongo_id, memory_id = contribution_identity(
        event_id,
        current_user["id"],
        current_user["community_id"],
    )
    try:
        await save_capsule_contribution(
            event_id,
            ReunionMemoryContributionRequest(
                story=story,
                status="published",
                idempotency_key=f"release4-attendee-prompt:{memory_id}",
            ),
            current_user,
            prompt_retry=True,
        )
    except CapsuleNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reunion not found.",
        ) from exc
    except CapsuleConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "memory_contribution_conflict",
                "message": "This contribution changed. Refresh before trying again.",
            },
        ) from exc
    return build_attendee_hub(event, current_user, has_memory=True)
