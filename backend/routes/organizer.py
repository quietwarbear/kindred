"""Organizer-only reunion command-center routes."""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from db import (
    budget_plans_collection,
    communities_collection,
    events_collection,
    invites_collection,
    notification_events_collection,
    travel_plans_collection,
    users_collection,
)
from dependencies import (
    ensure_minimum_role,
    get_current_user,
    get_event_for_user,
    normalize_email,
    now_iso,
)
from event_privacy import serialize_event_for_guest
from models import (
    PlanningTeamAssignmentRequest,
    PlanningTeamInvitationRequest,
    ReminderPreflightRequest,
)
from organizer_command_center import (
    build_command_center,
    canonical_response_summary,
)
from organizer_reminders import reminder_preflight, validate_idempotency_key

router = APIRouter(prefix="/api")

MEANINGFUL_EVENT_TYPES = {
    "event-create",
    "event-invite",
    "reminder-send",
    "rsvp-update",
}


async def _organizer_reunion(
    event_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    # Platform administration is intentionally irrelevant here. Only the
    # canonical role in the user's active community grants organizer access.
    ensure_minimum_role(current_user, "organizer")
    event = await get_event_for_user(event_id, current_user)
    if event.get("event_template") != "reunion":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reunion not found.",
        )
    return event


async def _command_center_context(
    event: dict[str, Any],
    current_user: dict[str, Any],
) -> dict[str, Any]:
    community_id = current_user["community_id"]
    event_id = event["id"]
    members = await users_collection.find(
        {"community_id": community_id},
        {
            "_id": 0,
            "id": 1,
            "email": 1,
            "email_normalized": 1,
            "role": 1,
        },
    ).to_list(500)
    member_ids_by_email = {
        normalize_email(
            member.get("email_normalized") or member.get("email", "")
        ): member["id"]
        for member in members
        if member.get("id")
        and normalize_email(member.get("email_normalized") or member.get("email", ""))
    }
    organizer_ids = {
        member["id"]
        for member in members
        if member.get("role") in {"host", "organizer"}
    }
    assigned_ids = set(event.get("planning_team_member_ids") or [])
    assigned_count = len(assigned_ids & organizer_ids)
    pending_count = await invites_collection.count_documents(
        {
            "community_id": community_id,
            "planning_event_id": event_id,
            "role": "organizer",
            "status": "pending",
        }
    )
    travel_plans = await travel_plans_collection.find(
        {"community_id": community_id, "event_id": event_id},
        {"_id": 0, "id": 1},
    ).to_list(200)
    budgets = await budget_plans_collection.find(
        {"community_id": community_id, "event_id": event_id},
        {
            "_id": 0,
            "event_id": 1,
            "target_amount": 1,
            "current_amount": 1,
        },
    ).to_list(200)
    changes = (
        await notification_events_collection.find(
            {
                "community_id": community_id,
                "related_id": event_id,
                "event_type": {"$in": sorted(MEANINGFUL_EVENT_TYPES)},
            },
            {"_id": 0, "event_type": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .to_list(8)
    )
    recent_changes = [
        {
            "kind": str(change.get("event_type") or "planning-change"),
            "at": str(change.get("created_at") or ""),
        }
        for change in changes
    ]
    recent_changes.extend(
        {
            "kind": kind,
            "at": str(item.get(timestamp_key) or ""),
        }
        for kind, items, timestamp_key in (
            ("overall-rsvp", event.get("rsvp_records", []), "updated_at"),
            ("activity-rsvp", event.get("activity_rsvps", []), "updated_at"),
            ("itinerary-update", event.get("agenda", []), "updated_at"),
        )
        for item in items
        if item.get(timestamp_key)
    )
    recent_changes.sort(key=lambda item: item["at"], reverse=True)
    return {
        "member_ids_by_email": member_ids_by_email,
        "travel_plans": travel_plans,
        "budgets": budgets,
        "planning_team_assigned": assigned_count,
        "planning_team_pending": pending_count,
        "recent_changes": recent_changes[:8],
    }


@router.get("/events/{event_id}/command-center")
async def command_center(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_reunion(event_id, current_user)
    context = await _command_center_context(event, current_user)
    responses = canonical_response_summary(
        event,
        member_ids_by_email=context["member_ids_by_email"],
    )
    preflight = reminder_preflight(invitation_count=responses["missing"])
    return build_command_center(
        event,
        **context,
        reminder_preflight=preflight,
    )


@router.get("/events/{event_id}/guest-preview")
async def guest_preview(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_reunion(event_id, current_user)
    preview = serialize_event_for_guest(
        event,
        {
            "id": "organizer-preview-only",
            "invitee_name": "Invited guest",
            "rsvp_status": "pending",
        },
    )
    community = await communities_collection.find_one(
        {"id": current_user["community_id"]},
        {"_id": 0, "name": 1},
    )
    preview["community_name"] = (community or {}).get("name", "")
    preview["invited_by_name"] = event.get("created_by_name", "")
    return preview


@router.get("/events/{event_id}/planning-team")
async def planning_team(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_reunion(event_id, current_user)
    community_id = current_user["community_id"]
    assigned_ids = list(dict.fromkeys(event.get("planning_team_member_ids") or []))
    assigned = await users_collection.find(
        {
            "id": {"$in": assigned_ids},
            "community_id": community_id,
            "role": {"$in": ["host", "organizer"]},
        },
        {"_id": 0, "id": 1, "full_name": 1, "role": 1},
    ).to_list(200)
    pending = await invites_collection.find(
        {
            "community_id": community_id,
            "planning_event_id": event["id"],
            "role": "organizer",
            "status": "pending",
        },
        {"_id": 0, "id": 1, "email": 1, "created_at": 1},
    ).to_list(200)
    return {
        "assigned": assigned,
        "pending_invitations": pending,
    }


def _planning_invite_key(community_id: str, event_id: str, email: str) -> str:
    source = f"{community_id}\n{event_id}\n{email}".encode()
    return hashlib.sha256(source).hexdigest()


@router.post("/events/{event_id}/planning-team/invitations")
async def invite_planning_team_member(
    event_id: str,
    payload: PlanningTeamInvitationRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_reunion(event_id, current_user)
    try:
        idempotency_key = validate_idempotency_key(payload.idempotency_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    email = normalize_email(str(payload.email))
    existing_member = await users_collection.find_one(
        {
            "community_id": current_user["community_id"],
            "$or": [
                {"email_normalized": email},
                {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
            ],
        },
        {"_id": 0, "id": 1, "role": 1},
    )
    if existing_member:
        if existing_member.get("role") not in {"host", "organizer"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This member is not an organizer. Kindred will not "
                    "automatically elevate their community permissions."
                ),
            )
        await events_collection.update_one(
            {
                "id": event["id"],
                "community_id": current_user["community_id"],
            },
            {"$addToSet": {"planning_team_member_ids": existing_member["id"]}},
        )
        return {"status": "assigned", "assigned": 1, "pending_invitations": 0}

    active_key = _planning_invite_key(
        current_user["community_id"],
        event["id"],
        email,
    )
    existing = await invites_collection.find_one(
        {
            "$or": [
                {"planning_team_idempotency_key": idempotency_key},
                {"active_planning_invite_key": active_key},
            ]
        },
        {"_id": 0, "id": 1, "status": 1},
    )
    if existing:
        return {
            "status": existing.get("status", "pending"),
            "assigned": 0,
            "pending_invitations": 1 if existing.get("status") == "pending" else 0,
        }
    invite_doc = {
        "id": str(uuid.uuid4()),
        "code": uuid.uuid4().hex[:8].upper(),
        "email": email,
        "email_normalized": email,
        "role": "organizer",
        "status": "pending",
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_at": now_iso(),
        "planning_event_id": event["id"],
        "planning_team_idempotency_key": idempotency_key,
        "active_planning_invite_key": active_key,
    }
    try:
        await invites_collection.insert_one(invite_doc.copy())
    except DuplicateKeyError:
        existing = await invites_collection.find_one(
            {"active_planning_invite_key": active_key},
            {"_id": 0, "status": 1},
        )
        return {
            "status": (existing or {}).get("status", "pending"),
            "assigned": 0,
            "pending_invitations": 1,
        }
    return {"status": "pending", "assigned": 0, "pending_invitations": 1}


@router.post("/events/{event_id}/planning-team/assignments")
async def assign_planning_team_member(
    event_id: str,
    payload: PlanningTeamAssignmentRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_reunion(event_id, current_user)
    try:
        validate_idempotency_key(payload.idempotency_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    member = await users_collection.find_one(
        {
            "id": payload.member_id,
            "community_id": current_user["community_id"],
            "role": {"$in": ["host", "organizer"]},
        },
        {"_id": 0, "id": 1},
    )
    if not member:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an existing organizer can be assigned to the planning team.",
        )
    await events_collection.update_one(
        {
            "id": event["id"],
            "community_id": current_user["community_id"],
        },
        {"$addToSet": {"planning_team_member_ids": member["id"]}},
    )
    return {"status": "assigned"}


@router.delete("/events/{event_id}/planning-team/assignments/{member_id}")
async def revoke_planning_team_assignment(
    event_id: str,
    member_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_reunion(event_id, current_user)
    await events_collection.update_one(
        {
            "id": event["id"],
            "community_id": current_user["community_id"],
        },
        {"$pull": {"planning_team_member_ids": member_id}},
    )
    return {"status": "revoked"}


@router.delete("/events/{event_id}/planning-team/invitations/{invitation_id}")
async def revoke_planning_team_invitation(
    event_id: str,
    invitation_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await _organizer_reunion(event_id, current_user)
    result = await invites_collection.update_one(
        {
            "id": invitation_id,
            "community_id": current_user["community_id"],
            "planning_event_id": event_id,
            "status": "pending",
        },
        {
            "$set": {"status": "revoked", "revoked_at": now_iso()},
            "$unset": {"active_planning_invite_key": ""},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning-team invitation not found.",
        )
    return {"status": "revoked"}


@router.post("/events/{event_id}/reminders/preflight")
async def organizer_reminder_preflight(
    event_id: str,
    payload: ReminderPreflightRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_reunion(event_id, current_user)
    try:
        validate_idempotency_key(payload.idempotency_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    context = await _command_center_context(event, current_user)
    responses = canonical_response_summary(
        event,
        member_ids_by_email=context["member_ids_by_email"],
    )
    return reminder_preflight(invitation_count=responses["missing"])
