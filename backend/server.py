import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError
from urllib.request import Request as UrlRequest, urlopen

from ai_tagging import generate_memory_tags
from courtyard_helpers import (
    ROLE_TOOLING,
    build_default_subyards,
    build_planning_checklist,
    build_recurring_dates,
    build_role_suggestions,
    countdown_days,
    years_since,
)
from dotenv import load_dotenv
from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest, StripeCheckout
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from security import create_access_token, decode_token, hash_password, verify_password
from starlette.middleware.cors import CORSMiddleware


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

users_collection = db.users
communities_collection = db.communities
invites_collection = db.invites
user_sessions_collection = db.user_sessions
password_resets_collection = db.password_resets
subyards_collection = db.subyards
kinships_collection = db.kinship_relationships
events_collection = db.events
memories_collection = db.memories
threads_collection = db.threads
payments_collection = db.payment_transactions
travel_plans_collection = db.travel_plans
budget_plans_collection = db.budget_plans
legacy_table_collection = db.legacy_table_configs
announcements_collection = db.announcements
chat_rooms_collection = db.chat_rooms
notification_events_collection = db.notification_events
notification_preferences_collection = db.notification_preferences
polls_collection = db.polls

app = FastAPI(title="Kindred API")
api_router = APIRouter(prefix="/api")
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
                    "title": f"You haven’t seen {kinship['person_name']} in {years} years",
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
    existing_rooms = await chat_rooms_collection.find({"community_id": community_id}, {"_id": 0}).to_list(200)
    existing_keys = {(room.get("room_scope"), room.get("subyard_id") or "") for room in existing_rooms}
    rooms_to_create: list[dict[str, Any]] = []

    if ("courtyard", "") not in existing_keys:
        rooms_to_create.append(
            {
                "id": str(uuid.uuid4()),
                "community_id": community_id,
                "room_scope": "courtyard",
                "subyard_id": "",
                "name": f"{community_name} General Chat",
                "messages": [],
                "created_at": now_iso(),
            }
        )

    for subyard in subyards:
        key = ("subyard", subyard["id"])
        if key in existing_keys:
            continue
        rooms_to_create.append(
            {
                "id": str(uuid.uuid4()),
                "community_id": community_id,
                "room_scope": "subyard",
                "subyard_id": subyard["id"],
                "name": f"{subyard['name']} Chat",
                "messages": [],
                "created_at": now_iso(),
            }
        )

    if rooms_to_create:
        await chat_rooms_collection.insert_many([item.copy() for item in rooms_to_create])


async def get_chat_room_for_user(room_id: str, user: dict[str, Any]) -> dict[str, Any]:
    room_doc = await chat_rooms_collection.find_one({"id": room_id, "community_id": user["community_id"]}, {"_id": 0})
    if not room_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found.")
    return room_doc


async def get_notification_preferences_for_user(user: dict[str, Any]) -> dict[str, Any]:
    prefs = await notification_preferences_collection.find_one(
        {"community_id": user["community_id"], "user_id": user["id"]},
        {"_id": 0},
    )
    if prefs:
        return prefs
    return {
        "user_id": user["id"],
        "community_id": user["community_id"],
        "reminder_notifications": True,
        "announcement_notifications": True,
        "chat_notifications": True,
        "invite_notifications": True,
        "rsvp_notifications": True,
        "muted_room_ids": [],
        "muted_announcement_scopes": [],
        "updated_at": now_iso(),
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


async def get_user_from_session_token(session_token: str) -> dict[str, Any] | None:
    session_doc = await user_sessions_collection.find_one({"session_token": session_token}, {"_id": 0})
    if not session_doc:
        return None

    expires_at = session_doc.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        return None

    return await users_collection.find_one({"id": session_doc.get("user_id")}, {"_id": 0})


async def get_current_user(request: Request) -> dict[str, Any]:
    session_token = request.cookies.get("session_token")
    if session_token:
        user_doc = await get_user_from_session_token(session_token)
        if user_doc:
            return user_doc

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            payload = decode_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        user_doc = await users_collection.find_one({"id": payload.get("sub")}, {"_id": 0})
        if user_doc:
            return user_doc

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")


async def get_community_for_user(user: dict[str, Any]) -> dict[str, Any]:
    community_doc = await communities_collection.find_one({"id": user["community_id"]}, {"_id": 0})
    if not community_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found.")
    return community_doc


async def get_event_for_user(event_id: str, user: dict[str, Any]) -> dict[str, Any]:
    event_doc = await events_collection.find_one({"id": event_id, "community_id": user["community_id"]}, {"_id": 0})
    if not event_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return event_doc


async def get_memory_for_user(memory_id: str, user: dict[str, Any]) -> dict[str, Any]:
    memory_doc = await memories_collection.find_one({"id": memory_id, "community_id": user["community_id"]}, {"_id": 0})
    if not memory_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found.")
    return memory_doc


async def get_thread_for_user(thread_id: str, user: dict[str, Any]) -> dict[str, Any]:
    thread_doc = await threads_collection.find_one({"id": thread_id, "community_id": user["community_id"]}, {"_id": 0})
    if not thread_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legacy thread not found.")
    return thread_doc


async def get_subyard_for_user(subyard_id: str, user: dict[str, Any]) -> dict[str, Any]:
    subyard_doc = await subyards_collection.find_one({"id": subyard_id, "community_id": user["community_id"]}, {"_id": 0})
    if not subyard_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subyard not found.")
    return subyard_doc


class CommunityBootstrapRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=8)
    community_name: str
    community_type: str
    location: str
    description: str
    motto: str | None = ""


class InviteRegistrationRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=8)
    invite_code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionRequest(BaseModel):
    session_id: str


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr


class PasswordRecoveryVerifyRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(min_length=8)


class ProfileUpdateRequest(BaseModel):
    full_name: str
    nickname: str | None = ""
    phone_number: str | None = ""
    profile_image_url: str | None = ""


class GoogleOnboardingRequest(BaseModel):
    full_name: str
    nickname: str | None = ""
    phone_number: str | None = ""
    profile_image_url: str | None = ""
    community_name: str | None = ""
    community_type: str | None = ""
    location: str | None = ""
    motto: str | None = ""
    first_subyard_name: str | None = ""
    first_subyard_description: str | None = ""
    first_gathering_title: str | None = ""
    first_gathering_template: str | None = ""
    first_gathering_start_at: str | None = None
    first_gathering_location: str | None = ""
    invite_emails: list[EmailStr] = Field(default_factory=list)


class CommunityPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    community_type: str
    location: str
    description: str
    motto: str | None = ""
    created_at: str
    owner_user_id: str


class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    full_name: str
    nickname: str | None = ""
    email: EmailStr
    phone_number: str | None = ""
    profile_image_url: str | None = ""
    google_picture: str | None = ""
    role: str
    community_id: str
    auth_provider: str | None = "password"
    onboarding_completed: bool = True
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic
    community: CommunityPublic


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: Literal["organizer", "member"]


class InvitePublic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    code: str
    email: EmailStr
    role: str
    status: str
    community_id: str
    created_by: str
    created_at: str


class AgendaItemRequest(BaseModel):
    time_label: str
    title: str
    notes: str | None = ""


class VolunteerSlotRequest(BaseModel):
    title: str
    needed_count: int = Field(default=1, ge=1, le=20)


class VolunteerSignupRequest(BaseModel):
    slot_id: str


class PotluckItemRequest(BaseModel):
    item_name: str


class PotluckClaimRequest(BaseModel):
    item_id: str


class RSVPRequest(BaseModel):
    status: Literal["going", "maybe", "not-going"]
    guests: int = Field(default=0, ge=0, le=20)


class EventCreateRequest(BaseModel):
    title: str
    description: str
    start_at: str
    location: str
    map_url: str | None = ""
    event_template: str = "general"
    special_focus: str | None = ""
    gathering_format: Literal["in-person", "online", "hybrid"] = "in-person"
    max_attendees: int | None = Field(default=None, ge=1, le=5000)
    subyard_id: str | None = ""
    assigned_roles: list[str] = Field(default_factory=list)
    suggested_contribution: float = Field(default=0.0, ge=0.0)
    travel_coordination_notes: str | None = ""
    recurrence_frequency: Literal["none", "daily", "weekly", "monthly", "yearly"] = "none"
    zoom_link: str | None = ""


class ChecklistItemRequest(BaseModel):
    category: str
    title: str


class ChecklistToggleRequest(BaseModel):
    item_id: str


class EventInviteCreateRequest(BaseModel):
    member_ids: list[str] = Field(default_factory=list)
    guest_emails: list[str] = Field(default_factory=list)
    note: str | None = ""


class EventRoleAssignmentRequest(BaseModel):
    role_name: str
    assignees: list[str] = Field(default_factory=list)


class EventMeetingLinkRequest(BaseModel):
    zoom_link: str


class EventPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    community_id: str
    created_by: str
    title: str
    description: str
    start_at: str
    location: str
    map_url: str | None = ""
    event_template: str
    special_focus: str | None = ""
    gathering_format: str = "in-person"
    max_attendees: int | None = None
    subyard_id: str | None = ""
    subyard_name: str | None = ""
    assigned_roles: list[str] = Field(default_factory=list)
    planning_checklist: list[dict[str, Any]] = Field(default_factory=list)
    travel_coordination_notes: str | None = ""
    suggested_contribution: float = 0.0
    recurrence_frequency: str = "none"
    series_id: str | None = ""
    is_recurring_instance: bool = False
    parent_event_id: str | None = ""
    zoom_link: str | None = ""
    event_invites: list[dict[str, Any]] = Field(default_factory=list)
    event_role_assignments: list[dict[str, Any]] = Field(default_factory=list)
    agenda: list[dict[str, Any]] = Field(default_factory=list)
    volunteer_slots: list[dict[str, Any]] = Field(default_factory=list)
    potluck_items: list[dict[str, Any]] = Field(default_factory=list)
    rsvp_records: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class MemoryCreateRequest(BaseModel):
    event_id: str
    title: str
    description: str
    image_data_url: str | None = None
    voice_note_data_url: str | None = None


class CommentRequest(BaseModel):
    text: str


class MemoryPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    community_id: str
    event_id: str
    event_title: str
    title: str
    description: str
    image_data_url: str | None = None
    voice_note_data_url: str | None = None
    uploaded_by: str
    uploaded_by_name: str
    tags: list[str] = Field(default_factory=list)
    ai_summary: str | None = ""
    comments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class ThreadCreateRequest(BaseModel):
    title: str
    category: Literal["oral-history", "sermon", "youth-reflection", "community-dialogue"]
    body: str
    elder_name: str | None = ""
    voice_note_data_url: str | None = None


class ThreadPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    community_id: str
    created_by: str
    created_by_name: str
    title: str
    category: str
    body: str
    elder_name: str | None = ""
    voice_note_data_url: str | None = None
    comments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class PaymentCheckoutRequest(BaseModel):
    package_id: str
    origin_url: str


class DashboardOverview(BaseModel):
    community: CommunityPublic
    user: UserPublic
    stats: dict[str, Any]
    upcoming_events: list[EventPublic]
    recent_memories: list[MemoryPublic]
    recent_threads: list[ThreadPublic]
    pending_invites: list[InvitePublic]


class SubyardCreateRequest(BaseModel):
    name: str
    description: str
    inherited_roles: bool = True
    role_focus: list[str] = Field(default_factory=list)
    visibility: Literal["shared", "private"] = "shared"


class KinshipCreateRequest(BaseModel):
    person_name: str
    related_to_name: str
    relationship_type: str
    relationship_scope: Literal["blood", "chosen", "mentor", "neighbor", "honorary elder"]
    notes: str | None = ""
    last_seen_at: str | None = None


class TravelPlanCreateRequest(BaseModel):
    event_id: str
    title: str
    travel_type: Literal["hotel", "flight", "carpool", "shuttle"]
    details: str
    coordinator_name: str | None = ""
    amount_estimate: float = Field(default=0.0, ge=0.0)
    payment_status: Literal["pending", "partially-funded", "funded"] = "pending"
    seats_available: int = Field(default=0, ge=0, le=500)


class BudgetCreateRequest(BaseModel):
    title: str
    event_id: str | None = None
    target_amount: float = Field(default=0.0, ge=0.0)
    current_amount: float = Field(default=0.0, ge=0.0)
    suggested_contribution: float = Field(default=0.0, ge=0.0)
    notes: str | None = ""


class LegacyTableConfigRequest(BaseModel):
    base_url: str | None = ""
    auth_type: Literal["api-key", "oauth", "bearer", "none"] = "api-key"
    sync_members: bool = True
    sync_stories: bool = True
    sync_events: bool = True
    sync_relationships: bool = True


class FileAttachmentPayload(BaseModel):
    name: str
    data_url: str
    mime_type: str | None = ""


class AnnouncementCreateRequest(BaseModel):
    title: str
    body: str
    scope: Literal["courtyard", "subyard"]
    subyard_id: str | None = ""
    attachments: list[FileAttachmentPayload] = Field(default_factory=list)


class ChatMessageCreateRequest(BaseModel):
    text: str
    attachments: list[FileAttachmentPayload] = Field(default_factory=list)


class CommunicationUnreadSummary(BaseModel):
    announcements_unread: int
    chat_unread: int
    total_unread: int


class NotificationPreferencesUpdateRequest(BaseModel):
    reminder_notifications: bool = True
    announcement_notifications: bool = True
    chat_notifications: bool = True
    invite_notifications: bool = True
    rsvp_notifications: bool = True
    muted_room_ids: list[str] = Field(default_factory=list)
    muted_announcement_scopes: list[str] = Field(default_factory=list)


class PollOptionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class PollCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    options: list[PollOptionRequest] = Field(min_length=2, max_length=10)
    allow_multiple: bool = False
    closes_at: str = ""


class PollVoteRequest(BaseModel):
    option_ids: list[str] = Field(min_length=1)


@api_router.get("/")
async def root():
    return {"message": "Kindred API is ready."}


@api_router.get("/gatherings/templates")
async def gathering_templates(current_user: dict[str, Any] = Depends(get_current_user)):
    _ = current_user
    return {"templates": GATHERING_TEMPLATES}


@api_router.post("/auth/bootstrap", response_model=AuthResponse)
async def bootstrap_community(payload: CommunityBootstrapRequest):
    email = normalize_email(payload.email)
    existing_user = await users_collection.find_one({"email": email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    community_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    created_at = now_iso()
    community_doc = {
        "id": community_id,
        "name": payload.community_name.strip(),
        "community_type": normalize_community_type(payload.community_type),
        "location": payload.location.strip(),
        "description": payload.description.strip(),
        "motto": (payload.motto or "").strip(),
        "owner_user_id": user_id,
        "created_at": created_at,
    }
    user_doc = {
        "id": user_id,
        "full_name": payload.full_name.strip(),
        "nickname": "",
        "email": email,
        "phone_number": "",
        "profile_image_url": "",
        "google_picture": "",
        "password_hash": hash_password(payload.password),
        "role": "host",
        "community_id": community_id,
        "auth_provider": "password",
        "onboarding_completed": True,
        "created_at": created_at,
    }

    await communities_collection.insert_one(community_doc.copy())
    await users_collection.insert_one(user_doc.copy())

    default_subyards = []
    for template in build_default_subyards(community_doc["community_type"]):
        default_subyards.append(
            {
                "id": str(uuid.uuid4()),
                "community_id": community_id,
                "name": template["name"],
                "description": template["description"],
                "inherited_roles": True,
                "role_focus": template["role_focus"],
                "assigned_tools": sorted({tool for role in template["role_focus"] for tool in ROLE_TOOLING.get(role, [])}),
                "visibility": "shared",
                "created_by": user_id,
                "created_at": created_at,
            }
        )
    if default_subyards:
        await subyards_collection.insert_many([item.copy() for item in default_subyards])
        await ensure_chat_rooms_for_community(community_id, community_doc["name"], default_subyards)
    else:
        await ensure_chat_rooms_for_community(community_id, community_doc["name"], [])

    return build_auth_response(user_doc, community_doc)


@api_router.post("/auth/register-with-invite", response_model=AuthResponse)
async def register_with_invite(payload: InviteRegistrationRequest):
    email = normalize_email(payload.email)
    invite_doc = await invites_collection.find_one({"code": payload.invite_code.strip().upper()}, {"_id": 0})
    if not invite_doc or invite_doc["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code is invalid or already used.")
    if normalize_email(invite_doc["email"]) != email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite code does not match this email address.")

    existing_user = await users_collection.find_one({"email": email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    created_at = now_iso()
    user_doc = {
        "id": str(uuid.uuid4()),
        "full_name": payload.full_name.strip(),
        "nickname": "",
        "email": email,
        "phone_number": "",
        "profile_image_url": "",
        "google_picture": "",
        "password_hash": hash_password(payload.password),
        "role": invite_doc["role"],
        "community_id": invite_doc["community_id"],
        "auth_provider": "password",
        "onboarding_completed": True,
        "created_at": created_at,
    }
    await users_collection.insert_one(user_doc.copy())
    await invites_collection.update_one({"id": invite_doc["id"]}, {"$set": {"status": "accepted", "accepted_at": created_at}})

    community_doc = await communities_collection.find_one({"id": invite_doc["community_id"]}, {"_id": 0})
    return build_auth_response(user_doc, community_doc)


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest):
    email = normalize_email(payload.email)
    user_doc = await users_collection.find_one({"email": email}, {"_id": 0})
    if not user_doc or not verify_password(payload.password, user_doc["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    community_doc = await communities_collection.find_one({"id": user_doc["community_id"]}, {"_id": 0})
    return build_auth_response(user_doc, community_doc)


@api_router.get("/auth/me", response_model=AuthResponse)
async def me(current_user: dict[str, Any] = Depends(get_current_user)):
    community_doc = await get_community_for_user(current_user)
    return build_auth_response(current_user, community_doc)


@api_router.post("/auth/google/session")
async def google_session_login(payload: GoogleSessionRequest, response: Response):
    try:
        req = UrlRequest(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": payload.session_id},
            method="GET",
        )
        with urlopen(req, timeout=20) as res:
            session_payload = json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to validate Google session.") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google session validation failed.") from exc

    google_user = {
        "email": session_payload.get("email", ""),
        "name": session_payload.get("name", ""),
        "picture": session_payload.get("picture", ""),
    }
    email = normalize_email(google_user.get("email", ""))
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account did not return a usable email.")

    user_doc = await users_collection.find_one({"email": email}, {"_id": 0})
    if user_doc:
        update_payload = {
            "full_name": google_user.get("name") or user_doc.get("full_name"),
            "google_picture": google_user.get("picture", ""),
            "auth_provider": "google",
        }
        if user_doc.get("auth_provider") != "google" or "onboarding_completed" not in user_doc:
            update_payload["onboarding_completed"] = False
        await users_collection.update_one(
            {"id": user_doc["id"]},
            {"$set": update_payload},
        )
        user_doc = await users_collection.find_one({"id": user_doc["id"]}, {"_id": 0})
    else:
        invite_doc = await invites_collection.find_one({"email": email, "status": "pending"}, {"_id": 0})
        created_at = now_iso()
        user_id = str(uuid.uuid4())

        if invite_doc:
            user_doc = {
                "id": user_id,
                "full_name": google_user.get("name") or email.split("@")[0],
                "nickname": "",
                "email": email,
                "phone_number": "",
                "profile_image_url": "",
                "google_picture": google_user.get("picture", ""),
                "password_hash": "",
                "role": invite_doc["role"],
                "community_id": invite_doc["community_id"],
                "auth_provider": "google",
                "onboarding_completed": False,
                "created_at": created_at,
            }
            await users_collection.insert_one(user_doc.copy())
            await invites_collection.update_one({"id": invite_doc["id"]}, {"$set": {"status": "accepted", "accepted_at": created_at}})
        else:
            community_id = str(uuid.uuid4())
            display_name = (google_user.get("name") or email.split("@")[0]).split(" ")[0]
            community_doc = {
                "id": community_id,
                "name": f"{display_name}'s Circle",
                "community_type": "community",
                "location": "",
                "description": "A new Kindred courtyard created through Google sign up.",
                "motto": "",
                "owner_user_id": user_id,
                "created_at": created_at,
            }
            user_doc = {
                "id": user_id,
                "full_name": google_user.get("name") or display_name,
                "nickname": "",
                "email": email,
                "phone_number": "",
                "profile_image_url": "",
                "google_picture": google_user.get("picture", ""),
                "password_hash": "",
                "role": "host",
                "community_id": community_id,
                "auth_provider": "google",
                "onboarding_completed": False,
                "created_at": created_at,
            }
            await communities_collection.insert_one(community_doc.copy())
            await users_collection.insert_one(user_doc.copy())

            default_subyards = []
            for template in build_default_subyards(community_doc["community_type"]):
                default_subyards.append(
                    {
                        "id": str(uuid.uuid4()),
                        "community_id": community_id,
                        "name": template["name"],
                        "description": template["description"],
                        "inherited_roles": True,
                        "role_focus": template["role_focus"],
                        "assigned_tools": sorted({tool for role in template["role_focus"] for tool in ROLE_TOOLING.get(role, [])}),
                        "visibility": "shared",
                        "created_by": user_id,
                        "created_at": created_at,
                    }
                )
            if default_subyards:
                await subyards_collection.insert_many([item.copy() for item in default_subyards])
                await ensure_chat_rooms_for_community(community_id, community_doc["name"], default_subyards)
            else:
                await ensure_chat_rooms_for_community(community_id, community_doc["name"], [])

    session_token = session_payload.get("session_token")
    if session_token:
        await user_sessions_collection.update_one(
            {"session_token": session_token},
            {
                "$set": {
                    "session_token": session_token,
                    "user_id": user_doc["id"],
                    "email": email,
                    "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                    "created_at": now_iso(),
                }
            },
            upsert=True,
        )
        apply_session_cookie(response, session_token)

    community_doc = await get_community_for_user(user_doc)
    return build_auth_response(user_doc, community_doc)


@api_router.post("/auth/password-recovery/request")
async def request_password_recovery(payload: PasswordRecoveryRequest):
    email = normalize_email(payload.email)
    user_doc = await users_collection.find_one({"email": email}, {"_id": 0})
    if not user_doc:
        return {"ok": True, "delivery_status": "silent"}

    code = f"{secrets.randbelow(1000000):06d}"
    await password_resets_collection.update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "code": code,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                "created_at": now_iso(),
            }
        },
        upsert=True,
    )

    if os.environ.get("RESEND_API_KEY"):
        delivery_status = "email-sent"
    else:
        delivery_status = "connection-ready"

    return {"ok": True, "delivery_status": delivery_status}


@api_router.post("/auth/password-recovery/verify")
async def verify_password_recovery(payload: PasswordRecoveryVerifyRequest):
    email = normalize_email(payload.email)
    reset_doc = await password_resets_collection.find_one({"email": email}, {"_id": 0})
    if not reset_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No recovery request found for this email.")
    if reset_doc.get("code") != payload.code.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recovery code is invalid.")
    expires_at = datetime.fromisoformat(reset_doc["expires_at"].replace("Z", "+00:00"))
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recovery code has expired.")

    await users_collection.update_one({"email": email}, {"$set": {"password_hash": hash_password(payload.new_password)}})
    await password_resets_collection.delete_one({"email": email})
    return {"ok": True}


@api_router.put("/auth/profile", response_model=UserPublic)
async def update_profile(payload: ProfileUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    update_payload = {
        "full_name": payload.full_name.strip(),
        "nickname": (payload.nickname or "").strip(),
        "phone_number": (payload.phone_number or "").strip(),
        "profile_image_url": (payload.profile_image_url or "").strip(),
    }
    await users_collection.update_one({"id": current_user["id"]}, {"$set": update_payload})
    updated_user = await users_collection.find_one({"id": current_user["id"]}, {"_id": 0})
    updated_user.pop("password_hash", None)
    return updated_user


@api_router.post("/auth/onboarding/complete", response_model=AuthResponse)
async def complete_google_onboarding(payload: GoogleOnboardingRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    profile_updates = {
        "full_name": payload.full_name.strip() or current_user.get("full_name", ""),
        "nickname": (payload.nickname or "").strip(),
        "phone_number": (payload.phone_number or "").strip(),
        "profile_image_url": (payload.profile_image_url or "").strip(),
        "onboarding_completed": True,
    }
    await users_collection.update_one({"id": current_user["id"]}, {"$set": profile_updates})

    refreshed_user = await users_collection.find_one({"id": current_user["id"]}, {"_id": 0})
    community_doc = await get_community_for_user(refreshed_user)

    if refreshed_user["role"] in {"host", "organizer"}:
        community_updates = {
            "name": (payload.community_name or community_doc.get("name", "")).strip() or community_doc.get("name", ""),
            "community_type": normalize_community_type(payload.community_type or community_doc.get("community_type", "community")),
            "location": (payload.location or community_doc.get("location", "")).strip(),
            "motto": (payload.motto or community_doc.get("motto", "")).strip(),
        }
        await communities_collection.update_one({"id": community_doc["id"]}, {"$set": community_updates})
        community_doc = await communities_collection.find_one({"id": community_doc["id"]}, {"_id": 0})

        if (payload.first_subyard_name or "").strip():
            existing_subyard = await subyards_collection.find_one(
                {"community_id": community_doc["id"], "name": payload.first_subyard_name.strip()},
                {"_id": 0},
            )
            if not existing_subyard:
                subyard_doc = {
                    "id": str(uuid.uuid4()),
                    "community_id": community_doc["id"],
                    "name": payload.first_subyard_name.strip(),
                    "description": (payload.first_subyard_description or "").strip() or "Starter subyard created during onboarding.",
                    "inherited_roles": True,
                    "role_focus": ["organizer", "historian"],
                    "assigned_tools": sorted({tool for role in ["organizer", "historian"] for tool in ROLE_TOOLING.get(role, [])}),
                    "visibility": "shared",
                    "created_by": refreshed_user["id"],
                    "created_at": now_iso(),
                }
                await subyards_collection.insert_one(subyard_doc.copy())
                await ensure_chat_rooms_for_community(community_doc["id"], community_doc["name"], [subyard_doc])

        if (
            (payload.first_gathering_title or "").strip()
            and payload.first_gathering_start_at
            and (payload.first_gathering_location or "").strip()
        ):
            existing_event = await events_collection.find_one(
                {
                    "community_id": community_doc["id"],
                    "title": payload.first_gathering_title.strip(),
                    "start_at": payload.first_gathering_start_at,
                },
                {"_id": 0},
            )
            if not existing_event:
                template = payload.first_gathering_template or "reunion"
                event_doc = {
                    "id": str(uuid.uuid4()),
                    "community_id": community_doc["id"],
                    "created_by": refreshed_user["id"],
                    "title": payload.first_gathering_title.strip(),
                    "description": "Starter gathering created during Google onboarding.",
                    "start_at": payload.first_gathering_start_at,
                    "location": payload.first_gathering_location.strip(),
                    "map_url": "",
                    "event_template": template,
                    "special_focus": "",
                    "gathering_format": "in-person",
                    "max_attendees": None,
                    "subyard_id": "",
                    "subyard_name": "",
                    "assigned_roles": build_role_suggestions(template),
                    "planning_checklist": build_planning_checklist(template, "in-person"),
                    "travel_coordination_notes": "",
                    "suggested_contribution": 0.0,
                    "recurrence_frequency": "none",
                    "series_id": "",
                    "is_recurring_instance": False,
                    "parent_event_id": "",
                    "zoom_link": "",
                    "event_invites": [],
                    "event_role_assignments": [
                        {"id": str(uuid.uuid4()), "role_name": role, "assignees": []}
                        for role in build_role_suggestions(template)
                    ],
                    "agenda": [],
                    "volunteer_slots": [],
                    "potluck_items": [],
                    "rsvp_records": [],
                    "created_at": now_iso(),
                }
                await events_collection.insert_one(event_doc.copy())

        for invite_email in payload.invite_emails:
            email = normalize_email(invite_email)
            existing_member = await users_collection.find_one({"community_id": community_doc["id"], "email": email}, {"_id": 0})
            existing_invite = await invites_collection.find_one({"community_id": community_doc["id"], "email": email, "status": "pending"}, {"_id": 0})
            if existing_member or existing_invite:
                continue
            invite_doc = {
                "id": str(uuid.uuid4()),
                "code": uuid.uuid4().hex[:8].upper(),
                "email": email,
                "role": "member",
                "status": "pending",
                "community_id": community_doc["id"],
                "created_by": refreshed_user["id"],
                "created_at": now_iso(),
            }
            await invites_collection.insert_one(invite_doc.copy())

    refreshed_user = await users_collection.find_one({"id": current_user["id"]}, {"_id": 0})
    community_doc = await get_community_for_user(refreshed_user)
    return build_auth_response(refreshed_user, community_doc)


@api_router.get("/community/overview", response_model=DashboardOverview)
async def get_overview(current_user: dict[str, Any] = Depends(get_current_user)):
    community_doc = await get_community_for_user(current_user)
    community_id = current_user["community_id"]
    member_count = await users_collection.count_documents({"community_id": community_id})
    event_count = await events_collection.count_documents({"community_id": community_id})
    memory_count = await memories_collection.count_documents({"community_id": community_id})
    thread_count = await threads_collection.count_documents({"community_id": community_id})
    pending_invites = await invites_collection.find({"community_id": community_id, "status": "pending"}, {"_id": 0}).to_list(20)
    funds_agg = await payments_collection.aggregate([
        {"$match": {"community_id": community_id, "payment_status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    funds_raised = round(funds_agg[0]["total"], 2) if funds_agg else 0.0
    upcoming_events = await events_collection.find({"community_id": community_id}, {"_id": 0}).sort("start_at", 1).to_list(5)
    recent_memories = await memories_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(6)
    recent_threads = await threads_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(6)

    return {
        "community": community_doc,
        "user": sanitize_doc({key: value for key, value in current_user.items() if key != "password_hash"}),
        "stats": {
            "members": member_count,
            "events": event_count,
            "memories": memory_count,
            "threads": thread_count,
            "funds_raised": funds_raised,
        },
        "upcoming_events": upcoming_events,
        "recent_memories": recent_memories,
        "recent_threads": recent_threads,
        "pending_invites": pending_invites,
    }


@api_router.get("/courtyard/home")
async def courtyard_home(current_user: dict[str, Any] = Depends(get_current_user)):
    community_doc = await get_community_for_user(current_user)
    community_id = current_user["community_id"]
    members = await users_collection.find({"community_id": community_id}, {"_id": 0, "password_hash": 0}).to_list(500)
    subyards = await subyards_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    upcoming_events = await events_collection.find({"community_id": community_id}, {"_id": 0}).sort("start_at", 1).to_list(5)
    memories = await memories_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(6)
    threads = await threads_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(6)
    pending_invites = await invites_collection.find({"community_id": community_id, "status": "pending"}, {"_id": 0}).to_list(20)
    funds_agg = await payments_collection.aggregate([
        {"$match": {"community_id": community_id, "payment_status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    funds_total = round(funds_agg[0]["total"], 2) if funds_agg else 0.0
    budgets = await budget_plans_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
    kinships = await kinships_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    announcements = await announcements_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(10)
    invite_reminders = build_invite_reminders_for_user(current_user, upcoming_events)

    notifications = build_notifications(kinships, pending_invites, upcoming_events, budgets, announcements, invite_reminders)
    active_courtyards = [
        {
            "id": community_doc["id"],
            "name": community_doc["name"],
            "kind": "courtyard",
            "members": len(members),
            "upcoming_gatherings": len(upcoming_events),
            "unread_updates": len(notifications),
        }
    ]
    for subyard in subyards:
        subyard_event_count = await events_collection.count_documents({"community_id": community_id, "subyard_id": subyard["id"]})
        active_courtyards.append(
            {
                "id": subyard["id"],
                "name": subyard["name"],
                "kind": "subyard",
                "members": len(members),
                "upcoming_gatherings": subyard_event_count,
                "unread_updates": max(len(subyard.get("role_focus", [])), 0),
                "description": subyard["description"],
            }
        )

    gatherings = []
    for event in upcoming_events:
        rsvp_records = event.get("rsvp_records", [])
        gatherings.append(
            {
                **event,
                "countdown_days": countdown_days(event.get("start_at")),
                "rsvp_summary": {
                    "going": len([record for record in rsvp_records if record.get("status") == "going"]),
                    "maybe": len([record for record in rsvp_records if record.get("status") == "maybe"]),
                    "not_going": len([record for record in rsvp_records if record.get("status") == "not-going"]),
                },
            }
        )

    return {
        "courtyard": community_doc,
        "user": sanitize_doc({key: value for key, value in current_user.items() if key != "password_hash"}),
        "stats": {
            "members": len(members),
            "subyards": len(subyards),
            "gatherings": len(upcoming_events),
            "timeline_updates": len(memories) + len(threads),
            "funds_total": funds_total,
        },
        "upcoming_gatherings": gatherings,
        "active_courtyards": active_courtyards,
        "quick_actions": [
            {"id": "plan-gathering", "label": "Plan New Gathering", "target": "/gatherings"},
            {"id": "upload-story", "label": "Upload Photos/Stories", "target": "/timeline"},
            {"id": "check-funds", "label": "Check Shared Funds", "target": "/funds-travel"},
        ],
        "notifications": notifications,
        "invite_reminders": invite_reminders,
        "relationship_groups": sorted({kinship["relationship_type"] for kinship in kinships})[:10],
        "recent_timeline": [
            *memories[:3],
            *threads[:3],
        ],
        "role_catalog": [{"role": role, "tools": tools} for role, tools in ROLE_TOOLING.items()],
    }


@api_router.get("/courtyard/structure")
async def courtyard_structure(current_user: dict[str, Any] = Depends(get_current_user)):
    community_doc = await get_community_for_user(current_user)
    community_id = current_user["community_id"]
    subyards = await subyards_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
    kinships = await kinships_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    members = await users_collection.find({"community_id": community_id}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    invites = await invites_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    await ensure_chat_rooms_for_community(community_id, community_doc["name"], subyards)
    chat_rooms = await chat_rooms_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {
        "courtyard": community_doc,
        "subyards": subyards,
        "kinships": kinships,
        "members": members,
        "invites": invites,
        "chat_rooms": chat_rooms,
        "role_catalog": [{"role": role, "tools": tools} for role, tools in ROLE_TOOLING.items()],
    }


@api_router.get("/community/members")
async def get_members(current_user: dict[str, Any] = Depends(get_current_user)):
    members = await users_collection.find(
        {"community_id": current_user["community_id"]},
        {"_id": 0, "password_hash": 0},
    ).sort("created_at", -1).to_list(500)
    return {"members": members}


@api_router.get("/subyards")
async def list_subyards(current_user: dict[str, Any] = Depends(get_current_user)):
    subyards = await subyards_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"subyards": subyards}


@api_router.post("/subyards")
async def create_subyard(payload: SubyardCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    role_focus = [role.strip().lower() for role in payload.role_focus if role.strip()]
    subyard_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "inherited_roles": payload.inherited_roles,
        "role_focus": role_focus,
        "assigned_tools": sorted({tool for role in role_focus for tool in ROLE_TOOLING.get(role, [])}),
        "visibility": payload.visibility,
        "created_by": current_user["id"],
        "created_at": now_iso(),
    }
    await subyards_collection.insert_one(subyard_doc.copy())
    await ensure_chat_rooms_for_community(current_user["community_id"], (await get_community_for_user(current_user))["name"], [subyard_doc])
    return subyard_doc


@api_router.get("/kinship")
async def list_kinship(current_user: dict[str, Any] = Depends(get_current_user)):
    relationships = await kinships_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"relationships": relationships}


@api_router.post("/kinship")
async def create_kinship(payload: KinshipCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    relationship_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "person_name": payload.person_name.strip(),
        "related_to_name": payload.related_to_name.strip(),
        "relationship_type": payload.relationship_type.strip(),
        "relationship_scope": payload.relationship_scope,
        "notes": (payload.notes or "").strip(),
        "last_seen_at": payload.last_seen_at,
        "created_by": current_user["id"],
        "created_at": now_iso(),
    }
    await kinships_collection.insert_one(relationship_doc.copy())
    return relationship_doc


@api_router.post("/invites", response_model=InvitePublic)
async def create_invite(payload: InviteCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    invite_email = normalize_email(payload.email)
    existing_member = await users_collection.find_one({"email": invite_email, "community_id": current_user["community_id"]}, {"_id": 0})
    if existing_member:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That person is already a member of this community.")

    invite_doc = {
        "id": str(uuid.uuid4()),
        "code": uuid.uuid4().hex[:8].upper(),
        "email": invite_email,
        "role": payload.role,
        "status": "pending",
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_at": now_iso(),
    }
    await invites_collection.insert_one(invite_doc.copy())
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="member-invite",
        title=f"Member invite created for {invite_doc['email']}",
        description=f"Role assigned: {invite_doc['role']}",
        related_id=invite_doc["id"],
        audience_scope="community",
    )
    return invite_doc


@api_router.get("/invites")
async def list_invites(current_user: dict[str, Any] = Depends(get_current_user)):
    invites = await invites_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"invites": invites}


@api_router.get("/announcements")
async def list_announcements(current_user: dict[str, Any] = Depends(get_current_user)):
    prefs = await get_notification_preferences_for_user(current_user)
    base_query = {"community_id": current_user["community_id"]}
    if prefs.get("muted_announcement_scopes"):
        base_query["scope"] = {"$nin": prefs.get("muted_announcement_scopes", [])}
    unread_before_view = await announcements_collection.count_documents({
        **base_query,
        "read_by_ids": {"$ne": current_user["id"]},
    })
    await announcements_collection.update_many(
        base_query,
        {"$addToSet": {"read_by_ids": current_user["id"]}},
    )
    announcements = await announcements_collection.find(base_query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"announcements": announcements, "unread_before_view": unread_before_view}


@api_router.post("/announcements")
async def create_announcement(payload: AnnouncementCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    subyard_name = ""
    if payload.scope == "subyard":
        if not payload.subyard_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subyard announcements require a subyard.")
        subyard_doc = await get_subyard_for_user(payload.subyard_id, current_user)
        subyard_name = subyard_doc["name"]

    announcement_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "scope": payload.scope,
        "subyard_id": payload.subyard_id,
        "subyard_name": subyard_name,
        "title": payload.title.strip(),
        "body": payload.body.strip(),
        "attachments": [item.model_dump() for item in payload.attachments],
        "comments": [],
        "read_by_ids": [current_user["id"]],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "created_at": now_iso(),
    }
    await announcements_collection.insert_one(announcement_doc.copy())
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="announcement",
        title=f"Announcement posted: {announcement_doc['title']}",
        description=announcement_doc["body"],
        related_id=announcement_doc["id"],
        audience_scope=announcement_doc["scope"],
    )
    return announcement_doc


@api_router.post("/announcements/{announcement_id}/comments")
async def add_announcement_comment(announcement_id: str, payload: CommentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    announcement_doc = await announcements_collection.find_one({"id": announcement_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not announcement_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")
    comments = announcement_doc.get("comments", [])
    comments.append({"id": str(uuid.uuid4()), "author_name": current_user["full_name"], "text": payload.text.strip(), "created_at": now_iso()})
    await announcements_collection.update_one(
        {"id": announcement_id},
        {"$set": {"comments": comments}, "$addToSet": {"read_by_ids": current_user["id"]}},
    )
    announcement_doc["comments"] = comments
    announcement_doc["read_by_ids"] = list(set(announcement_doc.get("read_by_ids", []) + [current_user["id"]]))
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="announcement-comment",
        title=f"Comment on announcement: {announcement_doc['title']}",
        description=payload.text.strip(),
        related_id=announcement_id,
        audience_scope=announcement_doc.get("scope", "community"),
    )
    return announcement_doc


@api_router.get("/chat/rooms")
async def list_chat_rooms(current_user: dict[str, Any] = Depends(get_current_user)):
    community_doc = await get_community_for_user(current_user)
    subyards = await subyards_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).to_list(200)
    await ensure_chat_rooms_for_community(current_user["community_id"], community_doc["name"], subyards)
    prefs = await get_notification_preferences_for_user(current_user)
    rooms = await chat_rooms_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", 1).to_list(200)
    for room in rooms:
        room["is_muted"] = room["id"] in prefs.get("muted_room_ids", [])
        room["unread_count"] = 0 if room["is_muted"] else len([message for message in room.get("messages", []) if current_user["id"] not in message.get("read_by_ids", [])])
    return {"rooms": rooms}


@api_router.get("/chat/rooms/{room_id}")
async def view_chat_room(room_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    room_doc = await get_chat_room_for_user(room_id, current_user)
    messages = room_doc.get("messages", [])
    changed = False
    for message in messages:
        readers = message.get("read_by_ids", [])
        if current_user["id"] not in readers:
            readers.append(current_user["id"])
            message["read_by_ids"] = readers
            changed = True
    if changed:
        await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": messages}})
    room_doc["messages"] = messages
    room_doc["unread_count"] = 0
    return room_doc


@api_router.post("/chat/rooms/{room_id}/messages")
async def create_chat_message(room_id: str, payload: ChatMessageCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    room_doc = await get_chat_room_for_user(room_id, current_user)
    messages = room_doc.get("messages", [])
    messages.append(
        {
            "id": str(uuid.uuid4()),
            "author_id": current_user["id"],
            "author_name": current_user["full_name"],
            "text": payload.text.strip(),
            "attachments": [item.model_dump() for item in payload.attachments],
            "comments": [],
            "is_pinned": False,
            "read_by_ids": [current_user["id"]],
            "created_at": now_iso(),
        }
    )
    await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": messages}})
    room_doc["messages"] = messages
    room_doc["unread_count"] = len([message for message in messages if current_user["id"] not in message.get("read_by_ids", [])])
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="chat-message",
        title=f"New message in {room_doc['name']}",
        description=payload.text.strip(),
        related_id=room_id,
        audience_scope=room_doc.get("room_scope", "community"),
    )
    return room_doc


@api_router.post("/chat/rooms/{room_id}/messages/{message_id}/pin")
async def pin_chat_message(room_id: str, message_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    room_doc = await get_chat_room_for_user(room_id, current_user)
    updated = False
    for message in room_doc.get("messages", []):
        if message.get("id") == message_id:
            message["is_pinned"] = not message.get("is_pinned", False)
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
    await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": room_doc.get("messages", [])}})
    room_doc["unread_count"] = len([message for message in room_doc.get("messages", []) if current_user["id"] not in message.get("read_by_ids", [])])
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="chat-comment",
        title=f"New reply in {room_doc['name']}",
        description=payload.text.strip(),
        related_id=room_id,
        audience_scope=room_doc.get("room_scope", "community"),
    )
    return room_doc


@api_router.post("/chat/rooms/{room_id}/messages/{message_id}/comments")
async def comment_on_chat_message(room_id: str, message_id: str, payload: CommentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    room_doc = await get_chat_room_for_user(room_id, current_user)
    updated = False
    for message in room_doc.get("messages", []):
        if message.get("id") == message_id:
            comments = message.get("comments", [])
            comments.append({"id": str(uuid.uuid4()), "author_name": current_user["full_name"], "text": payload.text.strip(), "created_at": now_iso()})
            message["comments"] = comments
            readers = message.get("read_by_ids", [])
            if current_user["id"] not in readers:
                readers.append(current_user["id"])
                message["read_by_ids"] = readers
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
    await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": room_doc.get("messages", [])}})
    room_doc["unread_count"] = len([message for message in room_doc.get("messages", []) if current_user["id"] not in message.get("read_by_ids", [])])
    return room_doc


@api_router.get("/communications/unread-summary", response_model=CommunicationUnreadSummary)
async def communications_unread_summary(current_user: dict[str, Any] = Depends(get_current_user)):
    prefs = await get_notification_preferences_for_user(current_user)
    announcements_unread = await announcements_collection.count_documents({
        "community_id": current_user["community_id"],
        "scope": {"$nin": prefs.get("muted_announcement_scopes", [])},
        "read_by_ids": {"$ne": current_user["id"]},
    })
    rooms = await chat_rooms_collection.find({"community_id": current_user["community_id"]}, {"_id": 0, "messages": 1}).to_list(200)
    chat_unread = 0
    for room in rooms:
        if room.get("id") in prefs.get("muted_room_ids", []):
            continue
        chat_unread += len([message for message in room.get("messages", []) if current_user["id"] not in message.get("read_by_ids", [])])
    return {"announcements_unread": announcements_unread, "chat_unread": chat_unread, "total_unread": announcements_unread + chat_unread}


@api_router.get("/notifications/history")
async def notification_history(current_user: dict[str, Any] = Depends(get_current_user)):
    items = await notification_events_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for item in items:
        item["is_read"] = current_user["id"] in item.get("read_by_user_ids", [])
        item.pop("read_by_user_ids", None)
    return {"items": items}


@api_router.get("/notifications/preferences")
async def notification_preferences(current_user: dict[str, Any] = Depends(get_current_user)):
    return await get_notification_preferences_for_user(current_user)


@api_router.put("/notifications/preferences")
async def update_notification_preferences(payload: NotificationPreferencesUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    prefs_doc = {
        "user_id": current_user["id"],
        "community_id": current_user["community_id"],
        "reminder_notifications": payload.reminder_notifications,
        "announcement_notifications": payload.announcement_notifications,
        "chat_notifications": payload.chat_notifications,
        "invite_notifications": payload.invite_notifications,
        "rsvp_notifications": payload.rsvp_notifications,
        "muted_room_ids": payload.muted_room_ids,
        "muted_announcement_scopes": payload.muted_announcement_scopes,
        "updated_at": now_iso(),
    }
    await notification_preferences_collection.update_one(
        {"community_id": current_user["community_id"], "user_id": current_user["id"]},
        {"$set": prefs_doc},
        upsert=True,
    )
    return prefs_doc


@api_router.get("/notifications/unread-count")
async def notification_unread_count(current_user: dict[str, Any] = Depends(get_current_user)):
    count = await notification_events_collection.count_documents({
        "community_id": current_user["community_id"],
        "read_by_user_ids": {"$nin": [current_user["id"]]},
    })
    return {"unread_count": count}


@api_router.post("/notifications/mark-read")
async def mark_notifications_read(current_user: dict[str, Any] = Depends(get_current_user)):
    result = await notification_events_collection.update_many(
        {
            "community_id": current_user["community_id"],
            "read_by_user_ids": {"$nin": [current_user["id"]]},
        },
        {"$addToSet": {"read_by_user_ids": current_user["id"]}},
    )
    return {"marked_count": result.modified_count}


@api_router.post("/gatherings/{event_id}/send-reminders")
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


@api_router.get("/gatherings/reminders")
async def gatherings_reminders(current_user: dict[str, Any] = Depends(get_current_user)):
    events = await events_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("start_at", 1).to_list(200)
    return {"reminders": build_invite_reminders_for_user(current_user, events)}


@api_router.get("/events", response_model=list[EventPublic])
async def list_events(current_user: dict[str, Any] = Depends(get_current_user)):
    events = await events_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("start_at", 1).to_list(200)
    return events


@api_router.post("/events", response_model=EventPublic)
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


@api_router.post("/events/{event_id}/rsvp", response_model=EventPublic)
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


@api_router.post("/events/{event_id}/meeting-link", response_model=EventPublic)
async def save_meeting_link(event_id: str, payload: EventMeetingLinkRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    event_doc["zoom_link"] = payload.zoom_link.strip()
    await events_collection.update_one({"id": event_id}, {"$set": {"zoom_link": event_doc["zoom_link"]}})
    return event_doc


@api_router.post("/events/{event_id}/invites", response_model=EventPublic)
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


@api_router.post("/events/{event_id}/role-assignments", response_model=EventPublic)
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


@api_router.post("/events/{event_id}/agenda", response_model=EventPublic)
async def add_agenda_item(event_id: str, payload: AgendaItemRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    agenda = event_doc.get("agenda", [])
    agenda.append({"id": str(uuid.uuid4()), "time_label": payload.time_label.strip(), "title": payload.title.strip(), "notes": (payload.notes or "").strip()})
    event_doc["agenda"] = agenda
    await events_collection.update_one({"id": event_id}, {"$set": {"agenda": agenda}})
    return event_doc


@api_router.post("/events/{event_id}/checklist-items", response_model=EventPublic)
async def add_checklist_item(event_id: str, payload: ChecklistItemRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    checklist = event_doc.get("planning_checklist", [])
    checklist.append({"id": str(uuid.uuid4()), "category": payload.category.strip(), "title": payload.title.strip(), "completed": False})
    event_doc["planning_checklist"] = checklist
    await events_collection.update_one({"id": event_id}, {"$set": {"planning_checklist": checklist}})
    return event_doc


@api_router.post("/events/{event_id}/checklist-toggle", response_model=EventPublic)
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


@api_router.post("/events/{event_id}/volunteer-slots", response_model=EventPublic)
async def add_volunteer_slot(event_id: str, payload: VolunteerSlotRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    slots = event_doc.get("volunteer_slots", [])
    slots.append({"id": str(uuid.uuid4()), "title": payload.title.strip(), "needed_count": payload.needed_count, "assigned_members": []})
    event_doc["volunteer_slots"] = slots
    await events_collection.update_one({"id": event_id}, {"$set": {"volunteer_slots": slots}})
    return event_doc


@api_router.post("/events/{event_id}/volunteer-signup", response_model=EventPublic)
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


@api_router.post("/events/{event_id}/potluck-items", response_model=EventPublic)
async def add_potluck_item(event_id: str, payload: PotluckItemRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    items = event_doc.get("potluck_items", [])
    items.append({"id": str(uuid.uuid4()), "item_name": payload.item_name.strip(), "assigned_to": ""})
    event_doc["potluck_items"] = items
    await events_collection.update_one({"id": event_id}, {"$set": {"potluck_items": items}})
    return event_doc


@api_router.post("/events/{event_id}/potluck-claim", response_model=EventPublic)
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


@api_router.get("/timeline/archive")
async def timeline_archive(current_user: dict[str, Any] = Depends(get_current_user)):
    community_id = current_user["community_id"]
    events = await events_collection.find({"community_id": community_id}, {"_id": 0}).to_list(300)
    memories = await memories_collection.find({"community_id": community_id}, {"_id": 0}).to_list(300)
    threads = await threads_collection.find({"community_id": community_id}, {"_id": 0}).to_list(300)

    timeline_items = []
    for event in events:
        timeline_items.append(
            {
                "id": event["id"],
                "type": "gathering",
                "title": event["title"],
                "subtitle": event.get("subyard_name") or event.get("event_template"),
                "description": event["description"],
                "occurred_at": event["start_at"],
                "tags": event.get("assigned_roles", []),
            }
        )
    for memory in memories:
        timeline_items.append(
            {
                "id": memory["id"],
                "type": "memory",
                "title": memory["title"],
                "subtitle": memory["event_title"],
                "description": memory.get("ai_summary") or memory["description"],
                "occurred_at": memory["created_at"],
                "tags": memory.get("tags", []),
                "image_data_url": memory.get("image_data_url"),
                "voice_note_data_url": memory.get("voice_note_data_url"),
            }
        )
    for thread in threads:
        timeline_items.append(
            {
                "id": thread["id"],
                "type": "story",
                "title": thread["title"],
                "subtitle": thread.get("elder_name") or thread.get("category"),
                "description": thread["body"],
                "occurred_at": thread["created_at"],
                "tags": [thread.get("category", "story")],
                "voice_note_data_url": thread.get("voice_note_data_url"),
            }
        )

    timeline_items.sort(key=lambda item: parse_datetime_safe(item.get("occurred_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    today = datetime.now(timezone.utc)
    anniversaries = [
        event for event in events
        if (parsed := parse_datetime_safe(event.get("start_at"))) and parsed.month == today.month and parsed.day == today.day
    ]
    return {"timeline_items": timeline_items[:300], "on_this_day": anniversaries[:5]}


@api_router.get("/memories", response_model=list[MemoryPublic])
async def list_memories(current_user: dict[str, Any] = Depends(get_current_user)):
    memories = await memories_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return memories


@api_router.post("/memories", response_model=MemoryPublic)
async def create_memory(payload: MemoryCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    event_doc = await get_event_for_user(payload.event_id, current_user)
    community_doc = await get_community_for_user(current_user)
    tag_payload = await generate_memory_tags(
        api_key=os.environ.get("EMERGENT_LLM_KEY", ""),
        model=os.environ.get("GEMINI_MODEL", ""),
        community_name=community_doc["name"],
        community_type=community_doc["community_type"],
        title=payload.title.strip(),
        description=payload.description.strip(),
        event_title=event_doc["title"],
        special_focus=event_doc.get("special_focus", ""),
        image_data_url=payload.image_data_url,
    )
    memory_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "event_id": payload.event_id,
        "event_title": event_doc["title"],
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "image_data_url": payload.image_data_url,
        "voice_note_data_url": payload.voice_note_data_url,
        "uploaded_by": current_user["id"],
        "uploaded_by_name": current_user["full_name"],
        "tags": tag_payload.get("tags", []),
        "ai_summary": tag_payload.get("summary", ""),
        "comments": [],
        "created_at": now_iso(),
    }
    await memories_collection.insert_one(memory_doc.copy())
    return memory_doc


@api_router.post("/memories/{memory_id}/comments", response_model=MemoryPublic)
async def add_memory_comment(memory_id: str, payload: CommentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    memory_doc = await get_memory_for_user(memory_id, current_user)
    comments = memory_doc.get("comments", [])
    comments.append({"id": str(uuid.uuid4()), "author_name": current_user["full_name"], "text": payload.text.strip(), "created_at": now_iso()})
    memory_doc["comments"] = comments
    await memories_collection.update_one({"id": memory_id}, {"$set": {"comments": comments}})
    return memory_doc


@api_router.get("/threads", response_model=list[ThreadPublic])
async def list_threads(current_user: dict[str, Any] = Depends(get_current_user)):
    threads = await threads_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return threads


@api_router.post("/threads", response_model=ThreadPublic)
async def create_thread(payload: ThreadCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    thread_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "title": payload.title.strip(),
        "category": payload.category,
        "body": payload.body.strip(),
        "elder_name": (payload.elder_name or "").strip(),
        "voice_note_data_url": payload.voice_note_data_url,
        "comments": [],
        "created_at": now_iso(),
    }
    await threads_collection.insert_one(thread_doc.copy())
    return thread_doc


@api_router.post("/threads/{thread_id}/comments", response_model=ThreadPublic)
async def add_thread_comment(thread_id: str, payload: CommentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    thread_doc = await get_thread_for_user(thread_id, current_user)
    comments = thread_doc.get("comments", [])
    comments.append({"id": str(uuid.uuid4()), "author_name": current_user["full_name"], "text": payload.text.strip(), "created_at": now_iso()})
    thread_doc["comments"] = comments
    await threads_collection.update_one({"id": thread_id}, {"$set": {"comments": comments}})
    return thread_doc


@api_router.get("/travel-plans")
async def list_travel_plans(
    current_user: dict[str, Any] = Depends(get_current_user),
    event_id: str | None = Query(default=None),
):
    query = {"community_id": current_user["community_id"]}
    if event_id:
        query["event_id"] = event_id
    plans = await travel_plans_collection.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)
    return {"travel_plans": plans}


@api_router.post("/travel-plans")
async def create_travel_plan(payload: TravelPlanCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(payload.event_id, current_user)
    travel_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "event_id": payload.event_id,
        "event_title": event_doc["title"],
        "title": payload.title.strip(),
        "travel_type": payload.travel_type,
        "details": payload.details.strip(),
        "coordinator_name": (payload.coordinator_name or current_user["full_name"]).strip(),
        "amount_estimate": float(payload.amount_estimate),
        "payment_status": payload.payment_status,
        "seats_available": payload.seats_available,
        "assigned_members": [],
        "created_at": now_iso(),
    }
    await travel_plans_collection.insert_one(travel_doc.copy())
    return travel_doc


@api_router.post("/travel-plans/{plan_id}/assign-self")
async def assign_self_to_travel(plan_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    plan_doc = await travel_plans_collection.find_one({"id": plan_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not plan_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Travel plan not found.")
    assigned = plan_doc.get("assigned_members", [])
    if current_user["full_name"] not in assigned:
        assigned.append(current_user["full_name"])
    await travel_plans_collection.update_one({"id": plan_id}, {"$set": {"assigned_members": assigned}})
    updated = await travel_plans_collection.find_one({"id": plan_id}, {"_id": 0})
    return updated


@api_router.get("/budget-plans")
async def list_budget_plans(current_user: dict[str, Any] = Depends(get_current_user)):
    budgets = await budget_plans_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(300)
    return {"budget_plans": budgets}


@api_router.post("/budget-plans")
async def create_budget_plan(payload: BudgetCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_title = ""
    if payload.event_id:
        event_doc = await get_event_for_user(payload.event_id, current_user)
        event_title = event_doc["title"]
    budget_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "event_id": payload.event_id,
        "event_title": event_title,
        "title": payload.title.strip(),
        "target_amount": float(payload.target_amount),
        "current_amount": float(payload.current_amount),
        "suggested_contribution": float(payload.suggested_contribution),
        "notes": (payload.notes or "").strip(),
        "created_by": current_user["id"],
        "created_at": now_iso(),
    }
    await budget_plans_collection.insert_one(budget_doc.copy())
    return budget_doc


@api_router.get("/payments/summary")
async def payment_summary(current_user: dict[str, Any] = Depends(get_current_user)):
    transactions = await payments_collection.find(
        {"community_id": current_user["community_id"]},
        {"_id": 0, "id": 1, "session_id": 1, "package_id": 1, "contribution_label": 1, "amount": 1, "currency": 1, "status": 1, "payment_status": 1, "user_email": 1, "created_at": 1, "completed_at": 1},
    ).sort("created_at", -1).to_list(200)
    paid_agg = await payments_collection.aggregate([
        {"$match": {"community_id": current_user["community_id"], "payment_status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    total_paid = round(paid_agg[0]["total"], 2) if paid_agg else 0.0
    return {"packages": list(CONTRIBUTION_PACKAGES.values()), "total_paid": total_paid, "transactions": transactions}


@api_router.get("/funds-travel/overview")
async def funds_travel_overview(current_user: dict[str, Any] = Depends(get_current_user)):
    payment_summary_payload = await payment_summary(current_user)
    budgets = await budget_plans_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    travel_plans = await travel_plans_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    pending_travel_total = round(sum(item.get("amount_estimate", 0) for item in travel_plans), 2)
    return {**payment_summary_payload, "budgets": budgets, "travel_plans": travel_plans, "pending_travel_total": pending_travel_total}


@api_router.post("/payments/checkout/session")
async def create_checkout_session(
    payload: PaymentCheckoutRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    package = CONTRIBUTION_PACKAGES.get(payload.package_id)
    if not package:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contribution package.")

    stripe_checkout = build_stripe_checkout(request)
    checkout_request = CheckoutSessionRequest(
        amount=float(package["amount"]),
        currency="usd",
        success_url=f"{payload.origin_url.rstrip('/')}/funds-travel?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{payload.origin_url.rstrip('/')}/funds-travel",
        metadata={
            "community_id": current_user["community_id"],
            "user_id": current_user["id"],
            "user_email": current_user["email"],
            "package_id": package["id"],
            "contribution_label": package["label"],
        },
    )
    session = await stripe_checkout.create_checkout_session(checkout_request)

    transaction_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "user_id": current_user["id"],
        "user_email": current_user["email"],
        "package_id": package["id"],
        "contribution_label": package["label"],
        "amount": float(package["amount"]),
        "currency": "usd",
        "metadata": checkout_request.metadata,
        "session_id": session.session_id,
        "payment_id": "",
        "status": "initiated",
        "payment_status": "unpaid",
        "created_at": now_iso(),
        "completed_at": None,
    }
    await payments_collection.insert_one(transaction_doc.copy())
    return {"url": session.url, "session_id": session.session_id}


@api_router.get("/payments/checkout/status/{session_id}")
async def get_checkout_status(session_id: str, request: Request, current_user: dict[str, Any] = Depends(get_current_user)):
    transaction_doc = await payments_collection.find_one({"session_id": session_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not transaction_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment session not found.")

    stripe_checkout = build_stripe_checkout(request)
    checkout_status = await stripe_checkout.get_checkout_status(session_id)
    update_payload = {
        "status": checkout_status.status,
        "payment_status": checkout_status.payment_status,
        "amount": transaction_doc.get("amount", 0),
        "currency": transaction_doc.get("currency", "usd"),
    }
    if checkout_status.payment_status == "paid" and not transaction_doc.get("completed_at"):
        update_payload["completed_at"] = now_iso()
    await payments_collection.update_one({"session_id": session_id}, {"$set": update_payload})
    updated_transaction = await payments_collection.find_one({"session_id": session_id}, {"_id": 0})
    return {
        "status": checkout_status.status,
        "payment_status": checkout_status.payment_status,
        "amount_total": checkout_status.amount_total,
        "currency": checkout_status.currency,
        "metadata": checkout_status.metadata,
        "transaction": updated_transaction,
    }


@api_router.get("/legacy-table/status")
async def legacy_table_status(current_user: dict[str, Any] = Depends(get_current_user)):
    config = await legacy_table_collection.find_one({"community_id": current_user["community_id"]}, {"_id": 0})
    if not config:
        return {
            "connection_status": "connection-ready",
            "is_connected": False,
            "base_url": "",
            "auth_type": "api-key",
            "message": "Legacy Table integration is architected and awaiting API docs or credentials.",
            "sync_preferences": {
                "members": True,
                "stories": True,
                "events": True,
                "relationships": True,
            },
            "capabilities": ["member import", "kinship sync", "story export", "gathering export"],
        }
    return config


@api_router.post("/legacy-table/config")
async def save_legacy_table_config(payload: LegacyTableConfigRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    config_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "connection_status": "configured-awaiting-credentials",
        "is_connected": False,
        "base_url": (payload.base_url or "").strip(),
        "auth_type": payload.auth_type,
        "message": "Connection saved. Final live sync will activate when Legacy Table API details are provided.",
        "sync_preferences": {
            "members": payload.sync_members,
            "stories": payload.sync_stories,
            "events": payload.sync_events,
            "relationships": payload.sync_relationships,
        },
        "capabilities": ["member import", "kinship sync", "story export", "gathering export"],
        "last_sync_at": None,
        "last_sync_result": "Not yet attempted",
        "updated_at": now_iso(),
    }
    await legacy_table_collection.update_one(
        {"community_id": current_user["community_id"]},
        {"$set": config_doc},
        upsert=True,
    )
    return config_doc


@api_router.post("/legacy-table/sync-preview")
async def legacy_table_sync_preview(current_user: dict[str, Any] = Depends(get_current_user)):
    community_id = current_user["community_id"]
    config = await legacy_table_collection.find_one({"community_id": community_id}, {"_id": 0})
    if not config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save a Legacy Table configuration first.")

    preview = {
        "members": await users_collection.count_documents({"community_id": community_id}),
        "kinships": await kinships_collection.count_documents({"community_id": community_id}),
        "events": await events_collection.count_documents({"community_id": community_id}),
        "memories": await memories_collection.count_documents({"community_id": community_id}),
        "threads": await threads_collection.count_documents({"community_id": community_id}),
    }
    updated = {
        **config,
        "last_sync_at": now_iso(),
        "last_sync_result": "Preview generated. Awaiting live credentials for external sync execution.",
        "preview_counts": preview,
    }
    await legacy_table_collection.update_one({"community_id": community_id}, {"$set": updated})
    return updated


@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    stripe_checkout = build_stripe_checkout(request)
    request_body = await request.body()
    webhook_response = await stripe_checkout.handle_webhook(request_body, request.headers.get("Stripe-Signature"))

    session_id = getattr(webhook_response, "session_id", None)
    payment_status = getattr(webhook_response, "payment_status", None)
    event_type = getattr(webhook_response, "event_type", None)
    if session_id:
        update_payload = {"status": event_type or "webhook-received", "payment_status": payment_status or "unpaid"}
        if payment_status == "paid":
            update_payload["completed_at"] = now_iso()
        await payments_collection.update_one({"session_id": session_id}, {"$set": update_payload})

    return {"received": True, "session_id": session_id, "payment_status": payment_status, "event_type": event_type}


@api_router.get("/polls")
async def list_polls(current_user: dict[str, Any] = Depends(get_current_user)):
    polls = await polls_collection.find(
        {"community_id": current_user["community_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    for poll in polls:
        for option in poll.get("options", []):
            option["vote_count"] = len(option.get("voter_ids", []))
            option["voted_by_me"] = current_user["id"] in option.get("voter_ids", [])
            option.pop("voter_ids", None)
        poll["total_votes"] = sum(o["vote_count"] for o in poll.get("options", []))
    return {"polls": polls}


@api_router.post("/polls")
async def create_poll(payload: PollCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    poll_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "options": [
            {"id": str(uuid.uuid4()), "text": opt.text.strip(), "voter_ids": []}
            for opt in payload.options
        ],
        "allow_multiple": payload.allow_multiple,
        "is_active": True,
        "closes_at": payload.closes_at,
        "created_at": now_iso(),
    }
    await polls_collection.insert_one(poll_doc.copy())
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="poll-create",
        title=f"New poll: {poll_doc['title']}",
        description=f"{current_user['full_name']} started a vote with {len(payload.options)} options.",
        related_id=poll_doc["id"],
        audience_scope="community",
    )
    for option in poll_doc["options"]:
        option["vote_count"] = 0
        option["voted_by_me"] = False
        option.pop("voter_ids", None)
    poll_doc["total_votes"] = 0
    return poll_doc


@api_router.post("/polls/{poll_id}/vote")
async def vote_on_poll(poll_id: str, payload: PollVoteRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    poll_doc = await polls_collection.find_one(
        {"id": poll_id, "community_id": current_user["community_id"]}, {"_id": 0}
    )
    if not poll_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found.")
    if not poll_doc.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This poll is closed.")

    options = poll_doc.get("options", [])
    valid_option_ids = {o["id"] for o in options}
    for oid in payload.option_ids:
        if oid not in valid_option_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid option: {oid}")

    if not poll_doc.get("allow_multiple") and len(payload.option_ids) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This poll only allows a single vote.")

    # Remove existing votes from this user
    for option in options:
        voter_ids = option.get("voter_ids", [])
        if current_user["id"] in voter_ids:
            voter_ids.remove(current_user["id"])
        option["voter_ids"] = voter_ids

    # Add new votes
    for option in options:
        if option["id"] in payload.option_ids:
            option["voter_ids"].append(current_user["id"])

    await polls_collection.update_one({"id": poll_id}, {"$set": {"options": options}})

    for option in options:
        option["vote_count"] = len(option.get("voter_ids", []))
        option["voted_by_me"] = current_user["id"] in option.get("voter_ids", [])
        option.pop("voter_ids", None)
    poll_doc["options"] = options
    poll_doc["total_votes"] = sum(o["vote_count"] for o in options)
    return poll_doc


@api_router.post("/polls/{poll_id}/close")
async def close_poll(poll_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    poll_doc = await polls_collection.find_one(
        {"id": poll_id, "community_id": current_user["community_id"]}, {"_id": 0}
    )
    if not poll_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found.")
    await polls_collection.update_one({"id": poll_id}, {"$set": {"is_active": False}})
    return {"status": "closed"}


@api_router.delete("/polls/{poll_id}")
async def delete_poll(poll_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    result = await polls_collection.delete_one(
        {"id": poll_id, "community_id": current_user["community_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found.")
    return {"status": "deleted"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()