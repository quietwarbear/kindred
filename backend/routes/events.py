"""Events and gatherings routes."""

import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from courtyard_helpers import build_planning_checklist, build_recurring_dates, build_role_suggestions
from db import events_collection, users_collection
from dependencies import (
    build_invite_reminders_for_user,
    ensure_minimum_role,
    get_current_user,
    get_event_for_user,
    get_subyard_for_user,
    log_notification_event,
    normalize_email,
    now_iso,
    GATHERING_TEMPLATES,
)
from models import (
    AgendaItemRequest,
    ChecklistItemRequest,
    ChecklistToggleRequest,
    EventCreateRequest,
    EventInviteCreateRequest,
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


@router.get("/gatherings/templates")
async def gathering_templates(current_user: dict[str, Any] = Depends(get_current_user)):
    _ = current_user
    return {"templates": GATHERING_TEMPLATES}


@router.post("/gatherings/{event_id}/send-reminders")
async def send_gathering_reminders(event_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    pending_invites = [invite for invite in event_doc.get("event_invites", []) if invite.get("rsvp_status", "pending") == "pending"]
    delivery_status = "email-ready" if os.environ.get("RESEND_API_KEY") else "connection-ready"
    sent_at = now_iso()
    for invite in pending_invites:
        invite["reminder_sent_at"] = sent_at
        invite["reminder_delivery_status"] = delivery_status
    await events_collection.update_one({"id": event_id}, {"$set": {"event_invites": event_doc.get("event_invites", [])}})
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="reminder-send",
        title=f"Reminder batch created for {event_doc['title']}",
        description=f"{len(pending_invites)} recurring invite reminder(s) prepared.",
        related_id=event_id,
        audience_scope="event",
    )
    return {"sent_count": len(pending_invites), "delivery_status": delivery_status, "event": event_doc}


@router.get("/gatherings/reminders")
async def gatherings_reminders(current_user: dict[str, Any] = Depends(get_current_user)):
    events = await events_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("start_at", 1).to_list(200)
    return {"reminders": build_invite_reminders_for_user(current_user, events)}


@router.get("/events", response_model=list[EventPublic])
async def list_events(current_user: dict[str, Any] = Depends(get_current_user)):
    events = await events_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("start_at", 1).to_list(200)
    return events


@router.put("/events/{event_id}", response_model=EventPublic)
async def update_event(event_id: str, payload: EventUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    updates = {}
    if payload.title.strip():
        updates["title"] = payload.title.strip()
    if payload.description is not None and payload.description != "":
        updates["description"] = payload.description.strip()
    if payload.start_at:
        updates["start_at"] = payload.start_at
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
    if updates:
        await events_collection.update_one({"id": event_id}, {"$set": updates})
        event_doc.update(updates)
    return event_doc


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    await get_event_for_user(event_id, current_user)
    await events_collection.delete_one({"id": event_id})
    return {"ok": True}


@router.post("/events", response_model=EventPublic)
async def create_event(payload: EventCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    subyard_name = ""
    if payload.subyard_id:
        subyard_doc = await get_subyard_for_user(payload.subyard_id, current_user)
        subyard_name = subyard_doc["name"]

    assigned_roles = payload.assigned_roles or build_role_suggestions(payload.event_template)
    series_id = str(uuid.uuid4()) if payload.recurrence_frequency != "none" else ""
    event_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "start_at": payload.start_at,
        "location": payload.location.strip(),
        "map_url": (payload.map_url or "").strip(),
        "event_template": payload.event_template,
        "special_focus": (payload.special_focus or "").strip(),
        "gathering_format": payload.gathering_format,
        "max_attendees": payload.max_attendees,
        "subyard_id": payload.subyard_id,
        "subyard_name": subyard_name,
        "assigned_roles": assigned_roles,
        "planning_checklist": build_planning_checklist(payload.event_template, payload.gathering_format),
        "travel_coordination_notes": (payload.travel_coordination_notes or "").strip(),
        "suggested_contribution": float(payload.suggested_contribution or 0.0),
        "recurrence_frequency": payload.recurrence_frequency,
        "series_id": series_id,
        "is_recurring_instance": False,
        "parent_event_id": "",
        "zoom_link": (payload.zoom_link or "").strip(),
        "event_invites": [],
        "event_role_assignments": [
            {"id": str(uuid.uuid4()), "role_name": role, "assignees": []}
            for role in assigned_roles
        ],
        "agenda": [],
        "volunteer_slots": [],
        "potluck_items": [],
        "rsvp_records": [],
        "created_at": now_iso(),
    }
    await events_collection.insert_one(event_doc.copy())

    recurring_dates = build_recurring_dates(payload.start_at, payload.recurrence_frequency)
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
                    "volunteer_slots": [],
                    "potluck_items": [],
                    "rsvp_records": [],
                    "planning_checklist": build_planning_checklist(payload.event_template, payload.gathering_format),
                    "created_at": now_iso(),
                }
            )
        await events_collection.insert_many([item.copy() for item in recurring_docs])
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="event-create",
        title=f"New gathering: {event_doc['title']}",
        description=f"{current_user['full_name']} created a {payload.gathering_format} gathering at {event_doc['location']}.",
        related_id=event_doc["id"],
        audience_scope="community",
    )
    return event_doc


@router.post("/events/{event_id}/rsvp", response_model=EventPublic)
async def update_rsvp(event_id: str, payload: RSVPRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    event_doc = await get_event_for_user(event_id, current_user)
    next_records = [record for record in event_doc.get("rsvp_records", []) if record.get("user_id") != current_user["id"]]
    next_records.append(
        {
            "user_id": current_user["id"],
            "user_name": current_user["full_name"],
            "status": payload.status,
            "guests": payload.guests,
            "updated_at": now_iso(),
        }
    )
    event_doc["rsvp_records"] = next_records
    event_invites = event_doc.get("event_invites", [])
    for invite in event_invites:
        if normalize_email(invite.get("email", "")) == normalize_email(current_user.get("email", "")):
            invite["rsvp_status"] = payload.status
    event_doc["event_invites"] = event_invites
    await events_collection.update_one({"id": event_id}, {"$set": {"rsvp_records": next_records, "event_invites": event_invites}})
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="rsvp-update",
        title=f"RSVP updated for {event_doc['title']}",
        description=f"{current_user['full_name']} responded: {payload.status}",
        related_id=event_id,
        audience_scope="event",
    )
    return event_doc


@router.post("/events/{event_id}/meeting-link", response_model=EventPublic)
async def save_meeting_link(event_id: str, payload: EventMeetingLinkRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    event_doc["zoom_link"] = payload.zoom_link.strip()
    await events_collection.update_one({"id": event_id}, {"$set": {"zoom_link": event_doc["zoom_link"]}})
    return event_doc


@router.post("/events/{event_id}/invites", response_model=EventPublic)
async def create_event_invites(event_id: str, payload: EventInviteCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    existing_invites = event_doc.get("event_invites", [])
    existing_emails = {invite.get("email", "").lower() for invite in existing_invites}
    invite_records = existing_invites[:]

    if payload.member_ids:
        members = await users_collection.find(
            {"community_id": current_user["community_id"], "id": {"$in": payload.member_ids}},
            {"_id": 0, "password_hash": 0},
        ).to_list(500)
        for member in members:
            email = member["email"].lower()
            if email in existing_emails:
                continue
            invite_records.append(
                {
                    "id": str(uuid.uuid4()),
                    "invitee_name": member["full_name"],
                    "email": member["email"],
                    "invite_source": "member",
                    "status": "invited",
                    "rsvp_status": "pending",
                    "note": (payload.note or "").strip(),
                    "zoom_link": event_doc.get("zoom_link", "") if event_doc.get("gathering_format") in {"online", "hybrid"} else "",
                    "share_message": f"You're invited to {event_doc['title']} on {event_doc['start_at']}." + (f" Join via Zoom: {event_doc.get('zoom_link', '')}" if event_doc.get("gathering_format") in {"online", "hybrid"} and event_doc.get("zoom_link") else ""),
                    "delivery_status": "ready-for-email",
                    "created_at": now_iso(),
                }
            )
            existing_emails.add(email)

    for guest_email in payload.guest_emails:
        email = normalize_email(guest_email)
        if not email or email in existing_emails:
            continue
        invite_records.append(
            {
                "id": str(uuid.uuid4()),
                "invitee_name": email.split("@")[0],
                "email": email,
                "invite_source": "guest",
                "status": "invited",
                "rsvp_status": "pending",
                "note": (payload.note or "").strip(),
                "zoom_link": event_doc.get("zoom_link", "") if event_doc.get("gathering_format") in {"online", "hybrid"} else "",
                "share_message": f"You're invited to {event_doc['title']} on {event_doc['start_at']}." + (f" Join via Zoom: {event_doc.get('zoom_link', '')}" if event_doc.get("gathering_format") in {"online", "hybrid"} and event_doc.get("zoom_link") else ""),
                "delivery_status": "ready-for-email",
                "created_at": now_iso(),
            }
        )
        existing_emails.add(email)

    event_doc["event_invites"] = invite_records
    await events_collection.update_one({"id": event_id}, {"$set": {"event_invites": invite_records}})
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="event-invite",
        title=f"Gathering invites prepared for {event_doc['title']}",
        description=f"{len(invite_records)} invite record(s) currently attached to this gathering.",
        related_id=event_id,
        audience_scope="event",
    )
    return event_doc


@router.post("/events/{event_id}/role-assignments", response_model=EventPublic)
async def assign_event_roles(event_id: str, payload: EventRoleAssignmentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
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
        assignments.append({"id": str(uuid.uuid4()), "role_name": payload.role_name.strip(), "assignees": normalized_assignees})

    event_doc["event_role_assignments"] = assignments
    await events_collection.update_one({"id": event_id}, {"$set": {"event_role_assignments": assignments}})
    return event_doc


@router.post("/events/{event_id}/agenda", response_model=EventPublic)
async def add_agenda_item(event_id: str, payload: AgendaItemRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    agenda = event_doc.get("agenda", [])
    agenda.append({"id": str(uuid.uuid4()), "time_label": payload.time_label.strip(), "title": payload.title.strip(), "notes": (payload.notes or "").strip()})
    event_doc["agenda"] = agenda
    await events_collection.update_one({"id": event_id}, {"$set": {"agenda": agenda}})
    return event_doc


@router.post("/events/{event_id}/checklist-items", response_model=EventPublic)
async def add_checklist_item(event_id: str, payload: ChecklistItemRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    checklist = event_doc.get("planning_checklist", [])
    checklist.append({"id": str(uuid.uuid4()), "category": payload.category.strip(), "title": payload.title.strip(), "completed": False})
    event_doc["planning_checklist"] = checklist
    await events_collection.update_one({"id": event_id}, {"$set": {"planning_checklist": checklist}})
    return event_doc


@router.post("/events/{event_id}/checklist-toggle", response_model=EventPublic)
async def toggle_checklist_item(event_id: str, payload: ChecklistToggleRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    event_doc = await get_event_for_user(event_id, current_user)
    checklist = event_doc.get("planning_checklist", [])
    updated = False
    for item in checklist:
        if item.get("id") == payload.item_id:
            item["completed"] = not item.get("completed", False)
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found.")
    event_doc["planning_checklist"] = checklist
    await events_collection.update_one({"id": event_id}, {"$set": {"planning_checklist": checklist}})
    return event_doc


@router.post("/events/{event_id}/volunteer-slots", response_model=EventPublic)
async def add_volunteer_slot(event_id: str, payload: VolunteerSlotRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    slots = event_doc.get("volunteer_slots", [])
    slots.append({"id": str(uuid.uuid4()), "title": payload.title.strip(), "needed_count": payload.needed_count, "assigned_members": []})
    event_doc["volunteer_slots"] = slots
    await events_collection.update_one({"id": event_id}, {"$set": {"volunteer_slots": slots}})
    return event_doc


@router.post("/events/{event_id}/volunteer-signup", response_model=EventPublic)
async def volunteer_signup(event_id: str, payload: VolunteerSignupRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    event_doc = await get_event_for_user(event_id, current_user)
    slots = event_doc.get("volunteer_slots", [])
    updated = False
    for slot in slots:
        assigned_members = slot.get("assigned_members", [])
        if slot.get("id") == payload.slot_id and current_user["full_name"] not in assigned_members and len(assigned_members) < slot.get("needed_count", 1):
            assigned_members.append(current_user["full_name"])
            slot["assigned_members"] = assigned_members
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This volunteer slot is already full or unavailable.")
    event_doc["volunteer_slots"] = slots
    await events_collection.update_one({"id": event_id}, {"$set": {"volunteer_slots": slots}})
    return event_doc


@router.post("/events/{event_id}/potluck-items", response_model=EventPublic)
async def add_potluck_item(event_id: str, payload: PotluckItemRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    items = event_doc.get("potluck_items", [])
    items.append({"id": str(uuid.uuid4()), "item_name": payload.item_name.strip(), "assigned_to": ""})
    event_doc["potluck_items"] = items
    await events_collection.update_one({"id": event_id}, {"$set": {"potluck_items": items}})
    return event_doc


@router.post("/events/{event_id}/potluck-claim", response_model=EventPublic)
async def claim_potluck_item(event_id: str, payload: PotluckClaimRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    event_doc = await get_event_for_user(event_id, current_user)
    items = event_doc.get("potluck_items", [])
    claimed = False
    for item in items:
        if item.get("id") == payload.item_id and not item.get("assigned_to"):
            item["assigned_to"] = current_user["full_name"]
            claimed = True
            break
    if not claimed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This potluck item is already claimed or unavailable.")
    event_doc["potluck_items"] = items
    await events_collection.update_one({"id": event_id}, {"$set": {"potluck_items": items}})
    return event_doc
