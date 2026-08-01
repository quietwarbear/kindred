"""Events and gatherings routes."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from courtyard_helpers import (
    build_planning_checklist,
    build_recurring_dates,
    build_role_suggestions,
)
from db import events_collection, users_collection
from event_privacy import serialize_event_for_user
from holiday_pilot import (
    HOLIDAY_PILOT_CONFIRMATION_CODES,
    build_holiday_pilot_readiness,
)
from dependencies import (
    build_invite_reminders_for_user,
    ensure_minimum_role,
    get_community_for_user,
    get_current_user,
    get_event_for_user,
    get_subyard_for_user,
    log_notification_event,
    normalize_email,
    now_iso,
    GATHERING_TEMPLATES,
    visible_event_query_for_user,
)
from ai_gathering import generate_gathering_plan
from itinerary import (
    ACTIVITY_RESPONSES,
    activity_summaries,
    canonical_activity_responses,
    local_day_key,
    normalize_activity,
    overlap_pairs,
    parse_local_datetime,
    replace_respondent_activity_responses,
    safe_roster_row_key,
    valid_timezone,
    validate_activity,
)
from rsvp_integrity import (
    RSVPWriteConflict,
    compare_and_swap_event,
    member_invite_aliases,
)
from models import (
    ActivityRSVPRequest,
    AgendaItemRequest,
    ChecklistItemRequest,
    ChecklistToggleRequest,
    EventCreateRequest,
    EventInviteCreateRequest,
    GatheringPlanRequest,
    HolidayPilotChecklistRequest,
    EventMeetingLinkRequest,
    EventPublic,
    EventRoleAssignmentRequest,
    EventUpdateRequest,
    PotluckClaimRequest,
    PotluckItemRequest,
    RSVPRequest,
    VolunteerSignupRequest,
    VolunteerSlotRequest,
)

router = APIRouter(prefix="/api")


def _holiday_setup_revision_filter(event: dict[str, Any]) -> dict[str, Any]:
    revision = int(event.get("holiday_setup_revision", 0) or 0)
    if revision == 0:
        return {"$in": [None, 0]}
    return revision


def _event_with_activity_summaries(event_doc: dict[str, Any]) -> dict[str, Any]:
    event_doc["activity_rsvp_summaries"] = activity_summaries(event_doc)
    if event_doc.get("event_template") == "holiday_meal":
        event_doc["holiday_pilot_readiness"] = build_holiday_pilot_readiness(event_doc)
    return event_doc


def _agenda_activity_from_payload(
    payload: AgendaItemRequest,
    *,
    activity_id: str,
    reunion_timezone: str,
    created_at: str,
) -> dict[str, Any]:
    activity = normalize_activity(
        payload.model_dump(),
        activity_id=activity_id,
    )
    activity["created_at"] = created_at
    activity["updated_at"] = created_at
    if activity.get("start_at") or activity.get("end_at"):
        errors = validate_activity(activity, reunion_timezone)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_itinerary_activity", "errors": errors},
            )
    return activity


def _event_invite_message(event_doc: dict[str, Any], rsvp_link: str) -> str:
    published = [
        item
        for item in event_doc.get("agenda", [])
        if item.get("visibility") == "published"
    ]
    date_label = event_doc.get("start_at", "")
    if event_doc.get("end_at"):
        date_label = f"{date_label} through {event_doc['end_at']}"
    activity_label = f" {len(published)} planned activities." if published else ""
    featured = next(
        (item for item in published if item.get("featured")),
        published[0] if published else None,
    )
    featured_label = f" First up: {featured.get('title')}." if featured else ""
    virtual_label = (
        f" Join online: {event_doc.get('zoom_link', '')}"
        if event_doc.get("gathering_format") in {"online", "hybrid"}
        and event_doc.get("zoom_link")
        else ""
    )
    return (
        f"You're invited to {event_doc['title']} · {date_label} · "
        f"{event_doc.get('location') or 'location to be announced'}."
        f"{activity_label}{featured_label}{virtual_label} "
        f"View the full schedule and tell us which activities you're joining: {rsvp_link}"
    )


@router.get("/gatherings/templates")
async def gathering_templates(current_user: dict[str, Any] = Depends(get_current_user)):
    _ = current_user
    return {"templates": GATHERING_TEMPLATES}


@router.post("/gatherings/{event_id}/send-reminders")
async def send_gathering_reminders(
    event_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    pending_invites = [
        invite
        for invite in event_doc.get("event_invites", [])
        if invite.get("rsvp_status", "pending") == "pending"
    ]
    delivery_status = (
        "email-ready" if os.environ.get("RESEND_API_KEY") else "connection-ready"
    )
    sent_at = now_iso()
    for invite in pending_invites:
        invite["reminder_sent_at"] = sent_at
        invite["reminder_delivery_status"] = delivery_status
    await events_collection.update_one(
        {"id": event_id},
        {"$set": {"event_invites": event_doc.get("event_invites", [])}},
    )
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="reminder-send",
        title=f"Reminder batch created for {event_doc['title']}",
        description=f"{len(pending_invites)} recurring invite reminder(s) prepared.",
        related_id=event_id,
        audience_scope=(
            "organizer" if event_doc.get("hidden_from_user_ids") else "event"
        ),
    )
    return {
        "sent_count": len(pending_invites),
        "delivery_status": delivery_status,
        "event": event_doc,
    }


@router.get("/gatherings/reminders")
async def gatherings_reminders(
    current_user: dict[str, Any] = Depends(get_current_user),
):
    events = (
        await events_collection.find(
            {
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
                "publication_state": {"$ne": "organizer_draft"},
            },
            {"_id": 0},
        )
        .sort("start_at", 1)
        .to_list(200)
    )
    return {"reminders": build_invite_reminders_for_user(current_user, events)}


@router.get("/events")
async def list_events(current_user: dict[str, Any] = Depends(get_current_user)):
    events = (
        await events_collection.find(
            visible_event_query_for_user(current_user),
            {"_id": 0},
        )
        .sort("start_at", 1)
        .to_list(200)
    )
    return [
        serialize_event_for_user(_event_with_activity_summaries(event), current_user)
        for event in events
    ]


@router.get("/events/{event_id}")
async def get_event(
    event_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    event_doc = await get_event_for_user(event_id, current_user)
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/publish-holiday-draft")
async def publish_holiday_draft(
    event_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    ensure_minimum_role(current_user, "organizer")
    event = await get_event_for_user(event_id, current_user)
    if (
        event.get("event_template") != "holiday_meal"
        or event.get("publication_state") != "organizer_draft"
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holiday meal draft not found.",
        )
    readiness = build_holiday_pilot_readiness(event)
    if not readiness.get("can_finish_setup"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "holiday_pilot_setup_incomplete",
                "next_action_code": readiness.get("next_action_code"),
            },
        )
    updated = await events_collection.update_one(
        {
            "id": event_id,
            "community_id": current_user["community_id"],
            "publication_state": "organizer_draft",
            "holiday_setup_revision": _holiday_setup_revision_filter(event),
        },
        {
            "$set": {"publication_state": "published", "published_at": now_iso()},
            "$inc": {"holiday_setup_revision": 1},
        },
    )
    if updated.modified_count != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "holiday_pilot_publish_conflict"},
        )
    event["publication_state"] = "published"
    return serialize_event_for_user(_event_with_activity_summaries(event), current_user)


@router.post("/events/{event_id}/holiday-pilot-checklist", response_model=EventPublic)
async def update_holiday_pilot_checklist(
    event_id: str,
    payload: HolidayPilotChecklistRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Persist one content-free organizer confirmation without provider activity."""
    ensure_minimum_role(current_user, "organizer")
    event = await get_event_for_user(event_id, current_user)
    if event.get("event_template") != "holiday_meal":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holiday meal not found.",
        )
    if payload.code not in HOLIDAY_PILOT_CONFIRMATION_CODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_holiday_pilot_confirmation"},
        )
    operator = "$addToSet" if payload.checked else "$pull"
    updated = await events_collection.update_one(
        {
            "id": event_id,
            "community_id": current_user["community_id"],
            "event_template": "holiday_meal",
            "holiday_setup_revision": _holiday_setup_revision_filter(event),
        },
        {
            operator: {"holiday_pilot_confirmations": payload.code},
            "$inc": {"holiday_setup_revision": 1},
        },
    )
    if updated.modified_count != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "holiday_pilot_checklist_conflict"},
        )
    confirmations = set(event.get("holiday_pilot_confirmations", []))
    if payload.checked:
        confirmations.add(payload.code)
    else:
        confirmations.discard(payload.code)
    event["holiday_pilot_confirmations"] = sorted(confirmations)
    return serialize_event_for_user(_event_with_activity_summaries(event), current_user)


@router.put("/events/{event_id}", response_model=EventPublic)
async def update_event(
    event_id: str,
    payload: EventUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    updates = {}
    if payload.title.strip():
        updates["title"] = payload.title.strip()
    if payload.description is not None and payload.description != "":
        updates["description"] = payload.description.strip()
    if payload.start_at:
        updates["start_at"] = payload.start_at
    if payload.end_at:
        updates["end_at"] = payload.end_at
    if payload.rsvp_deadline:
        updates["rsvp_deadline"] = payload.rsvp_deadline
    if payload.timezone:
        if not valid_timezone(payload.timezone):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Primary timezone is not valid.",
            )
        updates["timezone"] = payload.timezone
    if payload.location:
        updates["location"] = payload.location.strip()
    if payload.gathering_format:
        updates["gathering_format"] = payload.gathering_format
    if payload.max_attendees is not None:
        updates["max_attendees"] = payload.max_attendees
    if payload.zoom_link is not None and payload.zoom_link != "":
        updates["zoom_link"] = payload.zoom_link.strip()
    if payload.special_focus is not None and payload.special_focus != "":
        updates["special_focus"] = payload.special_focus.strip()
    if payload.map_url is not None and payload.map_url != "":
        updates["map_url"] = payload.map_url.strip()
    prospective_timezone = updates.get("timezone", event_doc.get("timezone", "UTC"))
    prospective_start = updates.get("start_at", event_doc.get("start_at", ""))
    prospective_end = updates.get("end_at", event_doc.get("end_at", ""))
    prospective_deadline = updates.get(
        "rsvp_deadline", event_doc.get("rsvp_deadline", "")
    )
    parsed_start = parse_local_datetime(prospective_start, prospective_timezone)
    parsed_end = parse_local_datetime(prospective_end, prospective_timezone)
    parsed_deadline = parse_local_datetime(prospective_deadline, prospective_timezone)
    if prospective_start and not parsed_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gathering start must be a valid, unambiguous local date and time.",
        )
    if prospective_end and not parsed_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gathering end must be a valid, unambiguous local date and time.",
        )
    if prospective_end and parsed_start and parsed_end and parsed_end < parsed_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gathering end must not be before its start.",
        )
    if prospective_deadline and not parsed_deadline:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="RSVP deadline must be a valid, unambiguous local date and time.",
        )
    if (
        prospective_deadline
        and parsed_deadline
        and parsed_start
        and parsed_deadline > parsed_start
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="RSVP deadline must not be after the gathering starts.",
        )
    if "timezone" in updates:
        inherited_errors = []
        for activity in event_doc.get("agenda", []):
            if activity.get("timezone"):
                continue
            if not any(
                activity.get(field) for field in ("start_at", "end_at", "rsvp_deadline")
            ):
                continue
            errors = validate_activity(activity, prospective_timezone)
            if errors:
                inherited_errors.append(
                    {
                        "activity_id": activity.get("id", ""),
                        "title": activity.get("title", ""),
                        "errors": errors,
                    }
                )
        if inherited_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "invalid_inherited_itinerary_timezone",
                    "message": (
                        "The timezone change would make one or more inherited "
                        "activity times invalid or ambiguous."
                    ),
                    "activities": inherited_errors,
                },
            )
    if updates:
        update_filter: dict[str, Any] = {
            "id": event_id,
            "community_id": current_user["community_id"],
        }
        update_document: dict[str, Any] = {"$set": updates}
        if event_doc.get("event_template") == "holiday_meal":
            update_filter["holiday_setup_revision"] = _holiday_setup_revision_filter(
                event_doc
            )
            update_document["$inc"] = {"holiday_setup_revision": 1}
        updated = await events_collection.update_one(update_filter, update_document)
        if (
            event_doc.get("event_template") == "holiday_meal"
            and updated.modified_count != 1
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "gathering_update_conflict"},
            )
        event_doc.update(updates)
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    ensure_minimum_role(current_user, "organizer")
    await get_event_for_user(event_id, current_user)
    await events_collection.delete_one({"id": event_id})
    return {"ok": True}


@router.post("/gatherings/ai-plan")
async def ai_plan_gathering(
    payload: GatheringPlanRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Turn a one-sentence ask into a structured, ready-to-create gathering plan (draft)."""
    ensure_minimum_role(current_user, "organizer")
    community = await get_community_for_user(current_user)
    recent = (
        await events_collection.find(
            {
                "community_id": current_user["community_id"],
                "publication_state": {"$ne": "organizer_draft"},
            },
            {"_id": 0, "title": 1},
        )
        .sort("start_at", -1)
        .to_list(5)
    )
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gpt-4o-mini")
    plan = await generate_gathering_plan(
        api_key,
        model,
        {
            "prompt": (payload.prompt or "").strip(),
            "community_name": community.get("name", ""),
            "community_type": community.get("community_type", "community"),
            "recent_gatherings": [e.get("title", "") for e in recent if e.get("title")],
        },
    )
    return {"plan": plan, "ai_enabled": bool(api_key)}


@router.post("/events", response_model=EventPublic)
async def create_event(
    payload: EventCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    client_request_id = payload.client_request_id.strip()
    if payload.event_template == "holiday_meal" and len(client_request_id) < 16:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "holiday_draft_idempotency_required",
                "message": "This private draft needs a retry-safe request ID.",
            },
        )
    if (
        payload.event_template == "holiday_meal"
        and payload.recurrence_frequency != "none"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "holiday_draft_must_be_one_time",
                "message": "Create one private holiday meal draft at a time.",
            },
        )
    if client_request_id:
        existing = await events_collection.find_one(
            {
                "community_id": current_user["community_id"],
                "created_by": current_user["id"],
                "client_request_id": client_request_id,
            },
            {"_id": 0},
        )
        if existing:
            return serialize_event_for_user(
                _event_with_activity_summaries(existing),
                current_user,
            )
    if not valid_timezone(payload.timezone):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Primary timezone is not valid.",
        )
    parsed_start = parse_local_datetime(payload.start_at, payload.timezone)
    parsed_end = parse_local_datetime(payload.end_at, payload.timezone)
    parsed_deadline = parse_local_datetime(payload.rsvp_deadline, payload.timezone)
    if not parsed_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gathering start must be a valid, unambiguous local date and time.",
        )
    if payload.end_at and not parsed_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gathering end must be a valid, unambiguous local date and time.",
        )
    if payload.end_at and parsed_start and parsed_end and parsed_end < parsed_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gathering end must not be before its start.",
        )
    if payload.rsvp_deadline and not parsed_deadline:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="RSVP deadline must be a valid, unambiguous local date and time.",
        )
    if (
        payload.rsvp_deadline
        and parsed_deadline
        and parsed_start
        and parsed_deadline > parsed_start
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="RSVP deadline must not be after the gathering starts.",
        )
    subyard_name = ""
    if payload.subyard_id:
        subyard_doc = await get_subyard_for_user(payload.subyard_id, current_user)
        subyard_name = subyard_doc["name"]

    assigned_roles = payload.assigned_roles or build_role_suggestions(
        payload.event_template
    )
    series_id = str(uuid.uuid4()) if payload.recurrence_frequency != "none" else ""
    created_at = now_iso()
    normalized_agenda = []
    for source in payload.agenda or []:
        if not isinstance(source, dict) or not source.get("title"):
            continue
        agenda_payload = AgendaItemRequest(**source)
        normalized_agenda.append(
            _agenda_activity_from_payload(
                agenda_payload,
                activity_id=str(uuid.uuid4()),
                reunion_timezone=payload.timezone,
                created_at=created_at,
            )
        )

    event_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "start_at": payload.start_at,
        "end_at": payload.end_at,
        "rsvp_deadline": payload.rsvp_deadline,
        "timezone": payload.timezone,
        "location": payload.location.strip(),
        "map_url": (payload.map_url or "").strip(),
        "event_template": payload.event_template,
        "publication_state": (
            "organizer_draft"
            if payload.event_template == "holiday_meal"
            else "published"
        ),
        "special_focus": (payload.special_focus or "").strip(),
        "gathering_format": payload.gathering_format,
        "max_attendees": payload.max_attendees,
        "subyard_id": payload.subyard_id,
        "subyard_name": subyard_name,
        "assigned_roles": assigned_roles,
        "planning_checklist": build_planning_checklist(
            payload.event_template, payload.gathering_format
        ),
        "travel_coordination_notes": (payload.travel_coordination_notes or "").strip(),
        "suggested_contribution": float(payload.suggested_contribution or 0.0),
        "recurrence_frequency": payload.recurrence_frequency,
        "series_id": series_id,
        "is_recurring_instance": False,
        "parent_event_id": "",
        "zoom_link": (payload.zoom_link or "").strip(),
        "hidden_from_user_ids": payload.hidden_from_member_ids or [],
        "event_invites": [],
        "event_role_assignments": (
            []
            if payload.event_template == "holiday_meal"
            else [
                {"id": str(uuid.uuid4()), "role_name": role, "assignees": []}
                for role in assigned_roles
            ]
        ),
        "agenda": normalized_agenda,
        "activity_rsvps": [],
        "activity_rsvp_summaries": {},
        "volunteer_slots": [
            {
                "id": str(uuid.uuid4()),
                "title": s.get("title", ""),
                "needed_count": int(s.get("needed_count", 1) or 1),
                "assigned_members": [],
            }
            for s in (payload.volunteer_slots or [])
            if isinstance(s, dict) and s.get("title")
        ],
        "potluck_items": [
            {"id": str(uuid.uuid4()), "item_name": str(p).strip(), "assigned_to": ""}
            for p in (payload.potluck_items or [])
            if str(p).strip()
        ],
        "rsvp_records": [],
        "created_at": created_at,
        "client_request_id": client_request_id,
        "holiday_pilot_confirmations": [],
        "holiday_setup_revision": 0,
        "rsvp_revision": 0,
    }
    event_doc["activity_rsvp_summaries"] = activity_summaries(event_doc)
    try:
        await events_collection.insert_one(event_doc.copy())
    except DuplicateKeyError:
        if not client_request_id:
            raise
        existing = await events_collection.find_one(
            {
                "community_id": current_user["community_id"],
                "created_by": current_user["id"],
                "client_request_id": client_request_id,
            },
            {"_id": 0},
        )
        if not existing:
            raise
        return serialize_event_for_user(
            _event_with_activity_summaries(existing),
            current_user,
        )

    recurring_dates = build_recurring_dates(
        payload.start_at, payload.recurrence_frequency
    )
    if recurring_dates:
        recurring_docs = []
        for index, next_start in enumerate(recurring_dates, start=1):
            recurring_docs.append(
                {
                    **event_doc,
                    "id": str(uuid.uuid4()),
                    "title": f"{event_doc['title']} · {payload.recurrence_frequency.title()} #{index + 1}",
                    "start_at": next_start,
                    "is_recurring_instance": True,
                    "parent_event_id": event_doc["id"],
                    "event_invites": [],
                    "event_role_assignments": [
                        {"id": str(uuid.uuid4()), "role_name": role, "assignees": []}
                        for role in assigned_roles
                    ],
                    "agenda": [],
                    "activity_rsvps": [],
                    "activity_rsvp_summaries": {},
                    "volunteer_slots": [],
                    "potluck_items": [],
                    "rsvp_records": [],
                    # The root organizer request owns the idempotency key.
                    # Recurring instances must not collide with that unique
                    # retry-safety record.
                    "client_request_id": "",
                    "planning_checklist": build_planning_checklist(
                        payload.event_template, payload.gathering_format
                    ),
                    "created_at": now_iso(),
                }
            )
        await events_collection.insert_many([item.copy() for item in recurring_docs])
    # Surprise gatherings stay silent — no community-wide notification or activity entry,
    # so the guest(s) of honor never get a hint.
    if payload.event_template != "holiday_meal" and not (
        payload.hidden_from_member_ids or []
    ):
        await log_notification_event(
            community_id=current_user["community_id"],
            actor_name=current_user["full_name"],
            event_type="event-create",
            title=f"New gathering: {event_doc['title']}",
            description=f"{current_user['full_name']} created a {payload.gathering_format} gathering at {event_doc['location']}.",
            related_id=event_doc["id"],
            audience_scope="community",
        )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/rsvp")
async def update_rsvp(
    event_id: str,
    payload: RSVPRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await get_event_for_user(event_id, current_user)

    def mutate(event_doc: dict[str, Any]) -> dict[str, Any]:
        aliases = member_invite_aliases(event_doc, current_user)
        next_records = [
            record
            for record in event_doc.get("rsvp_records", [])
            if record.get("user_id") not in aliases
        ]
        next_records.append(
            {
                "user_id": current_user["id"],
                "user_name": current_user["full_name"],
                "status": payload.status,
                "guests": max(0, payload.guests),
                "updated_at": now_iso(),
            }
        )
        event_invites = event_doc.get("event_invites", [])
        for invite in event_invites:
            if invite.get("member_id") == current_user["id"] or (
                invite.get("invite_source") == "member"
                and normalize_email(invite.get("email", ""))
                == normalize_email(current_user.get("email", ""))
            ):
                invite["member_id"] = current_user["id"]
                invite["rsvp_status"] = payload.status
        return {
            "rsvp_records": next_records,
            "event_invites": event_invites,
        }

    try:
        event_doc = await compare_and_swap_event(
            events_collection,
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            mutate,
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "rsvp_write_conflict", "message": str(exc)},
        ) from exc
    if not event_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found."
        )
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="rsvp-update",
        title=f"RSVP updated for {event_doc['title']}",
        description=f"{current_user['full_name']} responded: {payload.status}",
        related_id=event_id,
        audience_scope="organizer",
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/reveal", response_model=EventPublic)
async def reveal_event(
    event_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    """Lift the surprise: un-hide a gathering from its guest(s) of honor, and announce it."""
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    was_hidden = bool(event_doc.get("hidden_from_user_ids"))
    # Reveal this event and any recurring instances in its series.
    await events_collection.update_many(
        {
            "community_id": current_user["community_id"],
            "$or": [{"id": event_id}, {"parent_event_id": event_id}],
        },
        {"$set": {"hidden_from_user_ids": []}},
    )
    if was_hidden:
        await log_notification_event(
            community_id=current_user["community_id"],
            actor_name=current_user["full_name"],
            event_type="event-create",
            title=f"New gathering: {event_doc['title']}",
            description=f"{current_user['full_name']} revealed a gathering at {event_doc.get('location', '')}.",
            related_id=event_id,
            audience_scope="community",
        )
    event_doc["hidden_from_user_ids"] = []
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/meeting-link", response_model=EventPublic)
async def save_meeting_link(
    event_id: str,
    payload: EventMeetingLinkRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    event_doc["zoom_link"] = payload.zoom_link.strip()
    await events_collection.update_one(
        {"id": event_id}, {"$set": {"zoom_link": event_doc["zoom_link"]}}
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/invites", response_model=EventPublic)
async def create_event_invites(
    event_id: str,
    payload: EventInviteCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    if event_doc.get("publication_state") == "organizer_draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "organizer_draft_invitation_blocked",
                "message": "Finish the private organizer review before creating invitation credentials.",
            },
        )
    existing_invites = event_doc.get("event_invites", [])
    existing_emails = {invite.get("email", "").lower() for invite in existing_invites}
    invite_records = existing_invites[:]
    app_url = os.environ.get("APP_URL", "https://www.heykindred.org").rstrip("/")

    if payload.member_ids:
        members = await users_collection.find(
            {
                "community_id": current_user["community_id"],
                "id": {"$in": payload.member_ids},
            },
            {"_id": 0, "password_hash": 0},
        ).to_list(500)
        for member in members:
            email = member["email"].lower()
            if email in existing_emails:
                continue
            invite_id = str(uuid.uuid4())
            rsvp_link = f"{app_url}/rsvp#{invite_id}"
            invite_records.append(
                {
                    "id": invite_id,
                    "member_id": member["id"],
                    "invitee_name": member["full_name"],
                    "email": member["email"],
                    "invite_source": "member",
                    "status": "invited",
                    "rsvp_status": "pending",
                    "note": (payload.note or "").strip(),
                    "zoom_link": (
                        event_doc.get("zoom_link", "")
                        if event_doc.get("gathering_format") in {"online", "hybrid"}
                        else ""
                    ),
                    "share_message": _event_invite_message(event_doc, rsvp_link),
                    "delivery_status": "ready-for-email",
                    "created_at": now_iso(),
                }
            )
            existing_emails.add(email)

    for guest_email in payload.guest_emails:
        email = normalize_email(guest_email)
        if not email or email in existing_emails:
            continue
        invite_id = str(uuid.uuid4())
        rsvp_link = f"{app_url}/rsvp#{invite_id}"
        invite_records.append(
            {
                "id": invite_id,
                "invitee_name": email.split("@")[0],
                "email": email,
                "invite_source": "guest",
                "status": "invited",
                "rsvp_status": "pending",
                "note": (payload.note or "").strip(),
                "zoom_link": (
                    event_doc.get("zoom_link", "")
                    if event_doc.get("gathering_format") in {"online", "hybrid"}
                    else ""
                ),
                "share_message": _event_invite_message(event_doc, rsvp_link),
                "delivery_status": "ready-for-email",
                "created_at": now_iso(),
            }
        )
        existing_emails.add(email)

    event_doc["event_invites"] = invite_records
    event_doc["activity_rsvp_summaries"] = activity_summaries(event_doc)
    await events_collection.update_one(
        {"id": event_id},
        {
            "$set": {
                "event_invites": invite_records,
                "activity_rsvp_summaries": event_doc["activity_rsvp_summaries"],
            }
        },
    )
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="event-invite",
        title=f"Gathering invites prepared for {event_doc['title']}",
        description=f"{len(invite_records)} invite record(s) currently attached to this gathering.",
        related_id=event_id,
        audience_scope=(
            "organizer" if event_doc.get("hidden_from_user_ids") else "event"
        ),
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/role-assignments", response_model=EventPublic)
async def assign_event_roles(
    event_id: str,
    payload: EventRoleAssignmentRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    assignments = event_doc.get("event_role_assignments", [])
    normalized_role = payload.role_name.strip().lower()
    normalized_assignees = []
    for assignee in payload.assignees:
        clean = assignee.strip()
        if clean and clean not in normalized_assignees:
            normalized_assignees.append(clean)

    updated = False
    for assignment in assignments:
        if assignment.get("role_name", "").lower() == normalized_role:
            existing = assignment.get("assignees", [])
            for assignee in normalized_assignees:
                if assignee not in existing:
                    existing.append(assignee)
            assignment["assignees"] = existing
            updated = True
            break

    if not updated:
        assignments.append(
            {
                "id": str(uuid.uuid4()),
                "role_name": payload.role_name.strip(),
                "assignees": normalized_assignees,
            }
        )

    event_doc["event_role_assignments"] = assignments
    await events_collection.update_one(
        {"id": event_id}, {"$set": {"event_role_assignments": assignments}}
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/agenda", response_model=EventPublic)
async def add_agenda_item(
    event_id: str,
    payload: AgendaItemRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    agenda = event_doc.get("agenda", [])
    agenda.append(
        _agenda_activity_from_payload(
            payload,
            activity_id=str(uuid.uuid4()),
            reunion_timezone=event_doc.get("timezone", "UTC"),
            created_at=now_iso(),
        )
    )
    agenda.sort(
        key=lambda item: (
            item.get("start_at") or "9999",
            item.get("time_label", ""),
            item.get("title", ""),
        )
    )
    event_doc["agenda"] = agenda
    event_doc["activity_rsvp_summaries"] = activity_summaries(event_doc)
    await events_collection.update_one(
        {"id": event_id},
        {
            "$set": {
                "agenda": agenda,
                "activity_rsvp_summaries": event_doc["activity_rsvp_summaries"],
            }
        },
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.put("/events/{event_id}/agenda/{activity_id}", response_model=EventPublic)
async def update_agenda_activity(
    event_id: str,
    activity_id: str,
    payload: AgendaItemRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    agenda = event_doc.get("agenda", [])
    existing = next((item for item in agenda if item.get("id") == activity_id), None)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary activity not found.",
        )

    replacement = _agenda_activity_from_payload(
        payload,
        activity_id=activity_id,
        reunion_timezone=event_doc.get("timezone", "UTC"),
        created_at=existing.get("created_at") or now_iso(),
    )
    changed_schedule = any(
        existing.get(key) != replacement.get(key)
        for key in (
            "start_at",
            "end_at",
            "timezone",
            "venue_name",
            "venue_address",
            "venue_detail",
            "map_url",
            "virtual_link",
            "location_tba",
        )
    )
    history = list(existing.get("revision_history") or [])
    if changed_schedule:
        history.append(
            {
                "changed_at": now_iso(),
                "start_at": existing.get("start_at", ""),
                "end_at": existing.get("end_at", ""),
                "timezone": existing.get("timezone", ""),
                "venue_name": existing.get("venue_name", ""),
                "venue_address": existing.get("venue_address", ""),
                "venue_detail": existing.get("venue_detail", ""),
            }
        )
    replacement["revision_history"] = history[-20:]
    replacement["updated_at"] = now_iso()
    agenda = [replacement if item.get("id") == activity_id else item for item in agenda]
    agenda.sort(
        key=lambda item: (
            item.get("start_at") or "9999",
            item.get("time_label", ""),
            item.get("title", ""),
        )
    )
    event_doc["agenda"] = agenda
    await events_collection.update_one({"id": event_id}, {"$set": {"agenda": agenda}})
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post(
    "/events/{event_id}/agenda/{activity_id}/duplicate", response_model=EventPublic
)
async def duplicate_agenda_activity(
    event_id: str,
    activity_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    source = next(
        (item for item in event_doc.get("agenda", []) if item.get("id") == activity_id),
        None,
    )
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary activity not found.",
        )
    duplicate = normalize_activity(
        {
            **source,
            "title": f"{source.get('title', 'Activity')} copy",
            "visibility": "draft",
            "featured": False,
            "revision_history": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        },
        activity_id=str(uuid.uuid4()),
    )
    agenda = [*event_doc.get("agenda", []), duplicate]
    agenda.sort(
        key=lambda item: (item.get("start_at") or "9999", item.get("title", ""))
    )
    event_doc["agenda"] = agenda
    await events_collection.update_one({"id": event_id}, {"$set": {"agenda": agenda}})
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post(
    "/events/{event_id}/agenda/{activity_id}/publish", response_model=EventPublic
)
async def publish_agenda_activity(
    event_id: str,
    activity_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    agenda = event_doc.get("agenda", [])
    activity = next((item for item in agenda if item.get("id") == activity_id), None)
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary activity not found.",
        )
    errors = validate_activity(activity, event_doc.get("timezone", "UTC"))
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_itinerary_activity", "errors": errors},
        )
    activity["visibility"] = "published"
    activity["updated_at"] = now_iso()
    await events_collection.update_one({"id": event_id}, {"$set": {"agenda": agenda}})
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.delete("/events/{event_id}/agenda/{activity_id}", response_model=EventPublic)
async def delete_agenda_activity(
    event_id: str,
    activity_id: str,
    confirm_responses: bool = Query(False),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    activity = next(
        (item for item in event_doc.get("agenda", []) if item.get("id") == activity_id),
        None,
    )
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary activity not found.",
        )
    response_count = sum(
        1
        for item in event_doc.get("activity_rsvps", [])
        if item.get("activity_id") == activity_id
    )
    if response_count and not confirm_responses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "activity_has_responses",
                "response_count": response_count,
                "message": "Confirm before removing an activity with responses.",
            },
        )
    if response_count:
        activity["visibility"] = "archived"
        activity["archived_at"] = now_iso()
    else:
        event_doc["agenda"] = [
            item
            for item in event_doc.get("agenda", [])
            if item.get("id") != activity_id
        ]
    event_doc["activity_rsvp_summaries"] = activity_summaries(event_doc)
    await events_collection.update_one(
        {"id": event_id},
        {
            "$set": {
                "agenda": event_doc.get("agenda", []),
                "activity_rsvp_summaries": event_doc["activity_rsvp_summaries"],
            }
        },
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/activity-rsvp")
async def update_activity_rsvp(
    event_id: str,
    payload: ActivityRSVPRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await get_event_for_user(event_id, current_user)
    if payload.status not in ACTIVITY_RESPONSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid activity response.",
        )

    def mutate(event_doc: dict[str, Any]) -> dict[str, Any]:
        activity = next(
            (
                item
                for item in event_doc.get("agenda", [])
                if item.get("id") == payload.activity_id
                and item.get("visibility") == "published"
                and item.get("attendance_requested", True)
            ),
            None,
        )
        if not activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity RSVP is unavailable.",
            )
        deadline_value = activity.get("rsvp_deadline", "")
        deadline = parse_local_datetime(
            deadline_value,
            activity.get("timezone") or event_doc.get("timezone", "UTC"),
        )
        if deadline_value and (not deadline or datetime.now(timezone.utc) > deadline):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "activity_rsvp_closed",
                    "message": "This activity is not accepting RSVP changes.",
                },
            )
        replacement = {
            "activity_id": payload.activity_id,
            "respondent_id": current_user["id"],
            "respondent_type": "member",
            "display_name": current_user["full_name"],
            "status": payload.status,
            "party_size": max(1, payload.party_size),
            "updated_at": now_iso(),
            "via": "authenticated",
        }
        aliases = member_invite_aliases(event_doc, current_user)
        responses = replace_respondent_activity_responses(
            event_doc.get("activity_rsvps", []),
            current_user["id"],
            [replacement],
            aliases,
        )
        event_doc["activity_rsvps"] = responses
        summaries = activity_summaries(event_doc)
        return {
            "activity_rsvps": responses,
            "activity_rsvp_summaries": summaries,
        }

    try:
        event_doc = await compare_and_swap_event(
            events_collection,
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            mutate,
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "rsvp_write_conflict", "message": str(exc)},
        ) from exc
    if not event_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found."
        )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.get("/events/{event_id}/operations")
async def reunion_operations(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    agenda = [
        item
        for item in event_doc.get("agenda", [])
        if item.get("visibility") != "archived"
    ]
    responses = canonical_activity_responses(event_doc)
    overall = event_doc.get("rsvp_records", [])
    summaries = activity_summaries(event_doc)
    activity_days = {
        item.get("id", ""): local_day_key(
            item.get("start_at", ""),
            item.get("timezone") or event_doc.get("timezone", "UTC"),
        )
        for item in agenda
        if item.get("id") and item.get("start_at")
    }
    day_people: dict[str, dict[str, dict[str, Any]]] = {}
    for response in responses:
        day = activity_days.get(response.get("activity_id", ""))
        respondent_id = response.get("respondent_id", "")
        if not day or not respondent_id:
            continue
        existing_person = day_people.setdefault(day, {}).get(respondent_id, {})
        response_status = response.get("status", "no-response")
        combined_status = (
            "coming"
            if "coming" in {existing_person.get("status"), response_status}
            else (
                "maybe"
                if "maybe" in {existing_person.get("status"), response_status}
                else response_status
            )
        )
        day_people[day][respondent_id] = {
            "status": combined_status,
            "party_size": max(
                int(existing_person.get("party_size", 1)),
                int(response.get("party_size", 1) or 1),
            ),
        }
    day_summaries = {
        day: {
            "coming": sum(
                1 for person in people.values() if person["status"] == "coming"
            ),
            "maybe": sum(
                1 for person in people.values() if person["status"] == "maybe"
            ),
            "party_size": sum(
                person["party_size"]
                for person in people.values()
                if person["status"] == "coming"
            ),
        }
        for day, people in day_people.items()
    }
    rosters = {}
    for activity in agenda:
        activity_id = activity.get("id", "")
        rosters[activity_id] = [
            {
                "row_key": safe_roster_row_key(
                    activity_id,
                    response.get("respondent_id", ""),
                ),
                "display_name": response.get("display_name") or "Invited guest",
                "status": response.get("status", "no-response"),
                "party_size": max(1, int(response.get("party_size", 1) or 1)),
                "updated_at": response.get("updated_at", ""),
            }
            for response in responses
            if response.get("activity_id") == activity_id
        ]
    recent = sorted(
        [
            {
                "row_key": safe_roster_row_key(
                    item.get("activity_id", "overall"),
                    item.get("respondent_id") or item.get("user_id", ""),
                ),
                "display_name": item.get("display_name")
                or item.get("user_name")
                or "Invited guest",
                "status": item.get("status", ""),
                "updated_at": item.get("updated_at", ""),
            }
            for item in [*responses, *overall]
        ],
        key=lambda item: item.get("updated_at", ""),
        reverse=True,
    )[:10]
    return {
        "event_id": event_id,
        "timezone": event_doc.get("timezone", "UTC"),
        "total_invitees": len(event_doc.get("event_invites", [])),
        "unanswered_invitations": sum(
            1
            for invite in event_doc.get("event_invites", [])
            if invite.get("rsvp_status", "pending") == "pending"
        ),
        "overall": {
            response: sum(1 for item in overall if item.get("status") == response)
            for response in ("going", "some", "maybe", "not-going")
        },
        "activity_summaries": summaries,
        "day_summaries": day_summaries,
        "activity_rosters": rosters,
        "overlaps": overlap_pairs(agenda, event_doc.get("timezone", "UTC")),
        "missing_venue_activity_ids": [
            item.get("id")
            for item in agenda
            if not item.get("location_tba")
            and not item.get("venue_name")
            and not item.get("virtual_link")
        ],
        "recent_changes": recent,
    }


@router.post("/events/{event_id}/checklist-items", response_model=EventPublic)
async def add_checklist_item(
    event_id: str,
    payload: ChecklistItemRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    checklist = event_doc.get("planning_checklist", [])
    checklist.append(
        {
            "id": str(uuid.uuid4()),
            "category": payload.category.strip(),
            "title": payload.title.strip(),
            "completed": False,
        }
    )
    event_doc["planning_checklist"] = checklist
    await events_collection.update_one(
        {"id": event_id}, {"$set": {"planning_checklist": checklist}}
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/checklist-toggle")
async def toggle_checklist_item(
    event_id: str,
    payload: ChecklistToggleRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event_doc = await get_event_for_user(event_id, current_user)
    checklist = event_doc.get("planning_checklist", [])
    updated = False
    for item in checklist:
        if item.get("id") == payload.item_id:
            item["completed"] = not item.get("completed", False)
            updated = True
            break
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found."
        )
    event_doc["planning_checklist"] = checklist
    await events_collection.update_one(
        {"id": event_id}, {"$set": {"planning_checklist": checklist}}
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/volunteer-slots", response_model=EventPublic)
async def add_volunteer_slot(
    event_id: str,
    payload: VolunteerSlotRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    slots = event_doc.get("volunteer_slots", [])
    slots.append(
        {
            "id": str(uuid.uuid4()),
            "title": payload.title.strip(),
            "needed_count": payload.needed_count,
            "assigned_members": [],
        }
    )
    event_doc["volunteer_slots"] = slots
    await events_collection.update_one(
        {"id": event_id}, {"$set": {"volunteer_slots": slots}}
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/volunteer-signup")
async def volunteer_signup(
    event_id: str,
    payload: VolunteerSignupRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await get_event_for_user(event_id, current_user)

    def mutate(event_doc: dict[str, Any]) -> dict[str, Any]:
        slots = [dict(slot) for slot in event_doc.get("volunteer_slots", [])]
        slot = next((item for item in slots if item.get("id") == payload.slot_id), None)
        if not slot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "contribution_unavailable",
                    "message": "This volunteer role is unavailable.",
                },
            )
        assigned_ids = list(dict.fromkeys(slot.get("assigned_member_ids") or []))
        assigned_names = list(dict.fromkeys(slot.get("assigned_members") or []))
        already_mine = current_user["id"] in assigned_ids or (
            not assigned_ids and current_user.get("full_name") in assigned_names
        )
        if already_mine:
            return {"volunteer_slots": slots}
        needed = max(1, int(slot.get("needed_count", 1) or 1))
        if max(len(assigned_ids), len(assigned_names)) >= needed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "contribution_full",
                    "message": "This volunteer role was just filled.",
                },
            )
        assigned_ids.append(current_user["id"])
        assigned_names.append(current_user.get("full_name", ""))
        slot["assigned_member_ids"] = assigned_ids
        slot["assigned_members"] = assigned_names
        return {"volunteer_slots": slots}

    try:
        event_doc = await compare_and_swap_event(
            events_collection,
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            mutate,
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "contribution_write_conflict", "message": str(exc)},
        ) from exc
    if not event_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found."
        )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/volunteer-release")
async def volunteer_release(
    event_id: str,
    payload: VolunteerSignupRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await get_event_for_user(event_id, current_user)

    def mutate(event_doc: dict[str, Any]) -> dict[str, Any]:
        slots = [dict(slot) for slot in event_doc.get("volunteer_slots", [])]
        slot = next((item for item in slots if item.get("id") == payload.slot_id), None)
        if not slot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "contribution_unavailable",
                    "message": "This volunteer role is unavailable.",
                },
            )
        assigned_ids = list(dict.fromkeys(slot.get("assigned_member_ids") or []))
        assigned_names = list(dict.fromkeys(slot.get("assigned_members") or []))
        owns_by_id = current_user["id"] in assigned_ids
        owns_legacy = (
            not assigned_ids and current_user.get("full_name") in assigned_names
        )
        if owns_by_id:
            assigned_ids = [
                value for value in assigned_ids if value != current_user["id"]
            ]
            assigned_names = [
                value
                for value in assigned_names
                if value != current_user.get("full_name")
            ]
        elif owns_legacy:
            assigned_names = [
                value
                for value in assigned_names
                if value != current_user.get("full_name")
            ]
        slot["assigned_member_ids"] = assigned_ids
        slot["assigned_members"] = assigned_names
        return {"volunteer_slots": slots}

    try:
        event_doc = await compare_and_swap_event(
            events_collection,
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            mutate,
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "contribution_write_conflict", "message": str(exc)},
        ) from exc
    if not event_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found."
        )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/potluck-items", response_model=EventPublic)
async def add_potluck_item(
    event_id: str,
    payload: PotluckItemRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    items = event_doc.get("potluck_items", [])
    items.append(
        {
            "id": str(uuid.uuid4()),
            "item_name": payload.item_name.strip(),
            "assigned_to": "",
        }
    )
    event_doc["potluck_items"] = items
    await events_collection.update_one(
        {"id": event_id}, {"$set": {"potluck_items": items}}
    )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/potluck-claim")
async def claim_potluck_item(
    event_id: str,
    payload: PotluckClaimRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await get_event_for_user(event_id, current_user)

    def mutate(event_doc: dict[str, Any]) -> dict[str, Any]:
        items = [dict(item) for item in event_doc.get("potluck_items", [])]
        item = next(
            (value for value in items if value.get("id") == payload.item_id), None
        )
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "contribution_unavailable",
                    "message": "This potluck item is unavailable.",
                },
            )
        assigned_id = str(item.get("assigned_to_id") or "")
        assigned_name = str(item.get("assigned_to") or "")
        if assigned_id == current_user["id"] or (
            not assigned_id and assigned_name == current_user.get("full_name")
        ):
            return {"potluck_items": items}
        if assigned_id or assigned_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "contribution_claimed",
                    "message": "This potluck item was just claimed.",
                },
            )
        item["assigned_to_id"] = current_user["id"]
        item["assigned_to"] = current_user.get("full_name", "")
        return {"potluck_items": items}

    try:
        event_doc = await compare_and_swap_event(
            events_collection,
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            mutate,
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "contribution_write_conflict", "message": str(exc)},
        ) from exc
    if not event_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found."
        )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )


@router.post("/events/{event_id}/potluck-release")
async def release_potluck_item(
    event_id: str,
    payload: PotluckClaimRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await get_event_for_user(event_id, current_user)

    def mutate(event_doc: dict[str, Any]) -> dict[str, Any]:
        items = [dict(item) for item in event_doc.get("potluck_items", [])]
        item = next(
            (value for value in items if value.get("id") == payload.item_id), None
        )
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "contribution_unavailable",
                    "message": "This potluck item is unavailable.",
                },
            )
        assigned_id = str(item.get("assigned_to_id") or "")
        assigned_name = str(item.get("assigned_to") or "")
        owns = assigned_id == current_user["id"] or (
            not assigned_id and assigned_name == current_user.get("full_name")
        )
        if owns:
            item["assigned_to_id"] = ""
            item["assigned_to"] = ""
        elif assigned_id or assigned_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "contribution_not_owned",
                    "message": "Only the person who claimed this item can release it.",
                },
            )
        return {"potluck_items": items}

    try:
        event_doc = await compare_and_swap_event(
            events_collection,
            {
                "id": event_id,
                "community_id": current_user["community_id"],
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            mutate,
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "contribution_write_conflict", "message": str(exc)},
        ) from exc
    if not event_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found."
        )
    return serialize_event_for_user(
        _event_with_activity_summaries(event_doc), current_user
    )
