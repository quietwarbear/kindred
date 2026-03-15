"""Shared dependencies: auth, role checking, helpers, constants."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from emergentintegrations.payments.stripe.checkout import StripeCheckout
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from courtyard_helpers import countdown_days, years_since
from db import (
    communities_collection,
    notification_events_collection,
    notification_preferences_collection,
    user_sessions_collection,
    users_collection,
)
from security import create_access_token, decode_token

bearer_scheme = HTTPBearer(auto_error=False)
ROLE_ORDER = {"member": 1, "organizer": 2, "host": 3}

CONTRIBUTION_PACKAGES = {
    "community-dues": {
        "id": "community-dues",
        "label": "Community Dues",
        "amount": 25.00,
        "description": "Support day-to-day coordination, reminders, and planning.",
    },
    "reunion-fund": {
        "id": "reunion-fund",
        "label": "Reunion Fund",
        "amount": 50.00,
        "description": "Help cover venue, food, keepsakes, and travel support.",
    },
    "legacy-circle": {
        "id": "legacy-circle",
        "label": "Legacy Circle",
        "amount": 100.00,
        "description": "Strengthen archives, oral histories, and scholarship pools.",
    },
}

GATHERING_TEMPLATES = [
    {
        "id": "reunion",
        "label": "Reunion",
        "description": "Family-wide gathering with roll call, shared meals, and memory capture.",
        "roles": ["organizer", "historian", "treasurer", "communications lead"],
    },
    {
        "id": "birthday",
        "label": "Birthday",
        "description": "Celebration-focused planning with tributes, food, and guest coordination.",
        "roles": ["organizer", "historian", "contributor"],
    },
    {
        "id": "wedding",
        "label": "Wedding",
        "description": "Vendor, seating, travel, and budget planning for milestone moments.",
        "roles": ["organizer", "treasurer", "communications lead"],
    },
    {
        "id": "holiday",
        "label": "Holiday",
        "description": "Seasonal coordination for meals, travel, and attendance reminders.",
        "roles": ["organizer", "historian", "contributor"],
    },
    {
        "id": "custom",
        "label": "Custom",
        "description": "Start from a blank canvas and shape the gathering around your people.",
        "roles": ["organizer", "historian", "contributor"],
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_community_type(value: str) -> str:
    return value.strip().lower() if value else "community"


def sanitize_doc(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    return {key: value for key, value in document.items() if key != "_id"}


def build_auth_response(user_doc: dict[str, Any], community_doc: dict[str, Any]) -> dict[str, Any]:
    user_safe = sanitize_doc(user_doc) or {}
    user_safe.pop("password_hash", None)
    token = create_access_token(
        user_safe["id"],
        {"community_id": user_safe["community_id"], "role": user_safe["role"]},
    )
    return {"token": token, "user": user_safe, "community": sanitize_doc(community_doc)}


def apply_session_cookie(response, session_token: str):
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


def ensure_minimum_role(user: dict[str, Any], minimum_role: Literal["member", "organizer", "host"]):
    if ROLE_ORDER.get(user["role"], 0) < ROLE_ORDER[minimum_role]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to perform this action.")


def build_stripe_checkout(request: Request) -> StripeCheckout:
    api_key = os.environ["STRIPE_API_KEY"]
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    return StripeCheckout(api_key=api_key, webhook_url=webhook_url)


def parse_datetime_safe(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


async def get_user_from_session_token(session_token: str) -> dict[str, Any] | None:
    session_doc = await user_sessions_collection.find_one({"session_token": session_token}, {"_id": 0})
    if not session_doc:
        return None
    user_doc = await users_collection.find_one({"id": session_doc["user_id"]}, {"_id": 0})
    return user_doc


async def get_current_user(request: Request) -> dict[str, Any]:
    # Try bearer token first
    credentials: HTTPAuthorizationCredentials | None = await bearer_scheme(request)
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload:
            user = await users_collection.find_one({"id": payload["sub"]}, {"_id": 0})
            if user:
                user.pop("password_hash", None)
                return user
    # Try session cookie
    session_token = request.cookies.get("session_token")
    if session_token:
        user = await get_user_from_session_token(session_token)
        if user:
            user.pop("password_hash", None)
            return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")


async def get_community_for_user(user: dict[str, Any]) -> dict[str, Any]:
    community = await communities_collection.find_one({"id": user["community_id"]}, {"_id": 0})
    if not community:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found.")
    return community


async def get_notification_preferences_for_user(user: dict[str, Any]) -> dict[str, Any]:
    prefs = await notification_preferences_collection.find_one({"user_id": user["id"]}, {"_id": 0})
    if prefs:
        return prefs
    return {
        "user_id": user["id"],
        "reminder_notifications": True,
        "announcement_notifications": True,
        "chat_notifications": True,
        "invite_notifications": True,
        "rsvp_notifications": True,
        "muted_room_ids": [],
        "muted_announcement_scopes": [],
    }


async def log_notification_event(
    *,
    community_id: str,
    actor_name: str,
    event_type: str,
    title: str,
    description: str,
    related_id: str = "",
    audience_scope: str = "community",
):
    event_doc = {
        "id": str(uuid.uuid4()),
        "community_id": community_id,
        "actor_name": actor_name,
        "event_type": event_type,
        "title": title,
        "description": description,
        "related_id": related_id,
        "audience_scope": audience_scope,
        "read_by_user_ids": [],
        "created_at": now_iso(),
    }
    await notification_events_collection.insert_one(event_doc.copy())


def build_notifications(
    kinships: list[dict[str, Any]],
    pending_invites: list[dict[str, Any]],
    upcoming_events: list[dict[str, Any]],
    budgets: list[dict[str, Any]],
    announcements: list[dict[str, Any]] | None = None,
    invite_reminders: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []

    for kinship in kinships:
        years = years_since(kinship.get("last_seen_at"))
        if years and years >= 3:
            notifications.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "relationship",
                    "title": f"You haven't seen {kinship['person_name']} in {years} years",
                    "description": f"Consider inviting them through the {kinship['relationship_type']} circle.",
                }
            )

    if pending_invites:
        notifications.append(
            {
                "id": str(uuid.uuid4()),
                "type": "membership",
                "title": f"{len(pending_invites)} invitation(s) still pending",
                "description": "Follow up with organizers, cousins, or ministry leads before the next gathering.",
            }
        )

    for budget in budgets:
        if budget.get("target_amount", 0) > 0 and budget.get("current_amount", 0) < budget.get("target_amount", 0):
            notifications.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "funding",
                    "title": f"{budget['title']} is below target",
                    "description": "Prompt contributors or open a contribution package to close the gap.",
                }
            )

    if upcoming_events:
        next_event = upcoming_events[0]
        notifications.append(
            {
                "id": str(uuid.uuid4()),
                "type": "timeline",
                "title": f"Next gathering: {next_event['title']}",
                "description": "Refresh travel coordination, checklist items, and memory capture assignments.",
            }
        )

    if announcements:
        latest = announcements[0]
        notifications.append(
            {
                "id": str(uuid.uuid4()),
                "type": "announcement",
                "title": latest["title"],
                "description": latest["body"],
            }
        )

    if invite_reminders:
        notifications.extend(invite_reminders[:3])

    return notifications[:6]


def build_invite_reminders_for_user(user: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reminders: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for event in events:
        if event.get("recurrence_frequency") == "none":
            continue
        start_at = parse_datetime_safe(event.get("start_at"))
        if not start_at:
            continue
        days_until = (start_at - now).days
        if days_until < 0 or days_until > 14:
            continue

        invites = event.get("event_invites", [])
        pending_invites = [invite for invite in invites if invite.get("rsvp_status", "pending") == "pending"]
        if user.get("role") in {"host", "organizer"} and pending_invites:
            reminders.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "invite-reminder",
                    "title": f"Recurring reminder: {event['title']}",
                    "description": f"{len(pending_invites)} invitee(s) still have not RSVPed for the next {event.get('recurrence_frequency')} gathering.",
                    "event_id": event["id"],
                }
            )
            continue

        if any(normalize_email(invite.get("email", "")) == normalize_email(user.get("email", "")) and invite.get("rsvp_status", "pending") == "pending" for invite in invites):
            reminders.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "invite-reminder",
                    "title": f"RSVP reminder for {event['title']}",
                    "description": f"You're invited to this upcoming recurring {event.get('recurrence_frequency')} gathering. Please RSVP soon.",
                    "event_id": event["id"],
                }
            )

    return reminders[:6]


async def ensure_chat_rooms_for_community(
    community_id: str,
    community_name: str,
    subyards: list[dict[str, Any]],
):
    from db import chat_rooms_collection

    existing_rooms = await chat_rooms_collection.find({"community_id": community_id}, {"_id": 0}).to_list(200)
    existing_subyard_ids = {room.get("subyard_id", "") for room in existing_rooms}

    if not any(room.get("room_type") == "courtyard" for room in existing_rooms):
        courtyard_room = {
            "id": str(uuid.uuid4()),
            "community_id": community_id,
            "room_type": "courtyard",
            "subyard_id": "",
            "name": f"{community_name} – Main Chat",
            "created_at": now_iso(),
        }
        await chat_rooms_collection.insert_one(courtyard_room.copy())

    for subyard in subyards:
        if subyard["id"] not in existing_subyard_ids:
            subyard_room = {
                "id": str(uuid.uuid4()),
                "community_id": community_id,
                "room_type": "subyard",
                "subyard_id": subyard["id"],
                "name": f"{subyard['name']} Chat",
                "created_at": now_iso(),
            }
            await chat_rooms_collection.insert_one(subyard_room.copy())


async def get_chat_room_for_user(room_id: str, user: dict[str, Any]) -> dict[str, Any]:
    from db import chat_rooms_collection

    room_doc = await chat_rooms_collection.find_one({"id": room_id, "community_id": user["community_id"]}, {"_id": 0})
    if not room_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found.")
    return room_doc
