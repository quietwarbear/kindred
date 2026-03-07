import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ai_tagging import generate_memory_tags
from dotenv import load_dotenv
from emergentintegrations.payments.stripe.checkout import (
    CheckoutSessionRequest,
    StripeCheckout,
)
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
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
events_collection = db.events
memories_collection = db.memories
threads_collection = db.threads
payments_collection = db.payment_transactions

app = FastAPI(title="Gathering Cypher API")
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_community_type(value: str) -> str:
    return value.strip().lower() if value else "community"


def sanitize_doc(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    clean = {k: v for k, v in document.items() if k != "_id"}
    return clean


def build_auth_response(user_doc: dict[str, Any], community_doc: dict[str, Any]) -> dict[str, Any]:
    user_safe = sanitize_doc(user_doc) or {}
    user_safe.pop("password_hash", None)
    token = create_access_token(user_safe["id"], {"community_id": user_safe["community_id"], "role": user_safe["role"]})
    return {
        "token": token,
        "user": user_safe,
        "community": sanitize_doc(community_doc),
    }


def ensure_minimum_role(user: dict[str, Any], minimum_role: Literal["member", "organizer", "host"]):
    if ROLE_ORDER.get(user["role"], 0) < ROLE_ORDER[minimum_role]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to perform this action.")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict[str, Any]:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user_doc = await users_collection.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user_doc


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


def build_stripe_checkout(request: Request) -> StripeCheckout:
    api_key = os.environ["STRIPE_API_KEY"]
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    return StripeCheckout(api_key=api_key, webhook_url=webhook_url)


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
    email: EmailStr
    role: str
    community_id: str
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
    event_template: Literal["general", "family-reunion", "church-gathering"] = "general"
    special_focus: str | None = ""


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
    agenda: list[dict[str, Any]] = []
    volunteer_slots: list[dict[str, Any]] = []
    potluck_items: list[dict[str, Any]] = []
    rsvp_records: list[dict[str, Any]] = []
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
    tags: list[str] = []
    ai_summary: str | None = ""
    comments: list[dict[str, Any]] = []
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
    comments: list[dict[str, Any]] = []
    created_at: str


class PaymentCheckoutRequest(BaseModel):
    package_id: str
    origin_url: str


class PaymentTransactionPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    session_id: str
    package_id: str
    contribution_label: str
    amount: float
    currency: str
    status: str
    payment_status: str
    user_email: EmailStr
    created_at: str
    completed_at: str | None = None


class DashboardOverview(BaseModel):
    community: CommunityPublic
    user: UserPublic
    stats: dict[str, Any]
    upcoming_events: list[EventPublic]
    recent_memories: list[MemoryPublic]
    recent_threads: list[ThreadPublic]
    pending_invites: list[InvitePublic]


@api_router.get("/")
async def root():
    return {"message": "Gathering Cypher API is ready."}


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
        "email": email,
        "password_hash": hash_password(payload.password),
        "role": "host",
        "community_id": community_id,
        "created_at": created_at,
    }

    await communities_collection.insert_one(community_doc.copy())
    await users_collection.insert_one(user_doc.copy())
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
        "email": email,
        "password_hash": hash_password(payload.password),
        "role": invite_doc["role"],
        "community_id": invite_doc["community_id"],
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


@api_router.get("/community/overview", response_model=DashboardOverview)
async def get_overview(current_user: dict[str, Any] = Depends(get_current_user)):
    community_doc = await get_community_for_user(current_user)
    community_id = current_user["community_id"]

    member_count = await users_collection.count_documents({"community_id": community_id})
    event_count = await events_collection.count_documents({"community_id": community_id})
    memory_count = await memories_collection.count_documents({"community_id": community_id})
    thread_count = await threads_collection.count_documents({"community_id": community_id})
    pending_invites = await invites_collection.find({"community_id": community_id, "status": "pending"}, {"_id": 0}).to_list(20)
    total_raised = await payments_collection.find({"community_id": community_id, "payment_status": "paid"}, {"_id": 0}).to_list(1000)
    upcoming_events = await events_collection.find({"community_id": community_id}, {"_id": 0}).sort("start_at", 1).to_list(5)
    recent_memories = await memories_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(6)
    recent_threads = await threads_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(6)

    return {
        "community": community_doc,
        "user": sanitize_doc({k: v for k, v in current_user.items() if k != "password_hash"}),
        "stats": {
            "members": member_count,
            "events": event_count,
            "memories": memory_count,
            "threads": thread_count,
            "funds_raised": round(sum(txn.get("amount", 0) for txn in total_raised), 2),
        },
        "upcoming_events": upcoming_events,
        "recent_memories": recent_memories,
        "recent_threads": recent_threads,
        "pending_invites": pending_invites,
    }


@api_router.get("/community/members")
async def get_members(current_user: dict[str, Any] = Depends(get_current_user)):
    members = await users_collection.find(
        {"community_id": current_user["community_id"]},
        {"_id": 0, "password_hash": 0},
    ).sort("created_at", -1).to_list(500)
    return {"members": members}


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
    return invite_doc


@api_router.get("/invites")
async def list_invites(current_user: dict[str, Any] = Depends(get_current_user)):
    invites = await invites_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"invites": invites}


@api_router.get("/events", response_model=list[EventPublic])
async def list_events(current_user: dict[str, Any] = Depends(get_current_user)):
    events = await events_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("start_at", 1).to_list(200)
    return events


@api_router.post("/events", response_model=EventPublic)
async def create_event(payload: EventCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
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
        "agenda": [],
        "volunteer_slots": [],
        "potluck_items": [],
        "rsvp_records": [],
        "created_at": now_iso(),
    }
    await events_collection.insert_one(event_doc.copy())
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
    await events_collection.update_one({"id": event_id}, {"$set": {"rsvp_records": next_records}})
    return event_doc


@api_router.post("/events/{event_id}/agenda", response_model=EventPublic)
async def add_agenda_item(event_id: str, payload: AgendaItemRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    event_doc = await get_event_for_user(event_id, current_user)
    agenda = event_doc.get("agenda", [])
    agenda.append(
        {
            "id": str(uuid.uuid4()),
            "time_label": payload.time_label.strip(),
            "title": payload.title.strip(),
            "notes": (payload.notes or "").strip(),
        }
    )
    event_doc["agenda"] = agenda
    await events_collection.update_one({"id": event_id}, {"$set": {"agenda": agenda}})
    return event_doc


@api_router.post("/events/{event_id}/volunteer-slots", response_model=EventPublic)
async def add_volunteer_slot(event_id: str, payload: VolunteerSlotRequest, current_user: dict[str, Any] = Depends(get_current_user)):
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
    await events_collection.update_one({"id": event_id}, {"$set": {"volunteer_slots": slots}})
    return event_doc


@api_router.post("/events/{event_id}/volunteer-signup", response_model=EventPublic)
async def volunteer_signup(event_id: str, payload: VolunteerSignupRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    event_doc = await get_event_for_user(event_id, current_user)
    slots = event_doc.get("volunteer_slots", [])
    updated = False
    for slot in slots:
        assigned_members = slot.get("assigned_members", [])
        if slot.get("id") == payload.slot_id and current_user["full_name"] not in assigned_members:
            if len(assigned_members) < slot.get("needed_count", 1):
                assigned_members.append(current_user["full_name"])
                slot["assigned_members"] = assigned_members
                updated = True
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
    items.append(
        {
            "id": str(uuid.uuid4()),
            "item_name": payload.item_name.strip(),
            "assigned_to": "",
        }
    )
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
    if not claimed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This potluck item is already claimed or unavailable.")
    event_doc["potluck_items"] = items
    await events_collection.update_one({"id": event_id}, {"$set": {"potluck_items": items}})
    return event_doc


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
    comments.append(
        {
            "id": str(uuid.uuid4()),
            "author_name": current_user["full_name"],
            "text": payload.text.strip(),
            "created_at": now_iso(),
        }
    )
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
    comments.append(
        {
            "id": str(uuid.uuid4()),
            "author_name": current_user["full_name"],
            "text": payload.text.strip(),
            "created_at": now_iso(),
        }
    )
    thread_doc["comments"] = comments
    await threads_collection.update_one({"id": thread_id}, {"$set": {"comments": comments}})
    return thread_doc


@api_router.get("/payments/summary")
async def payment_summary(current_user: dict[str, Any] = Depends(get_current_user)):
    transactions = await payments_collection.find(
        {"community_id": current_user["community_id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    total_paid = round(sum(txn.get("amount", 0) for txn in transactions if txn.get("payment_status") == "paid"), 2)
    return {
        "packages": list(CONTRIBUTION_PACKAGES.values()),
        "total_paid": total_paid,
        "transactions": transactions,
    }


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
        success_url=f"{payload.origin_url.rstrip('/')}/contributions?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{payload.origin_url.rstrip('/')}/contributions",
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
    transaction_doc = await payments_collection.find_one(
        {"session_id": session_id, "community_id": current_user["community_id"]},
        {"_id": 0},
    )
    if not transaction_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment session not found.")

    stripe_checkout = build_stripe_checkout(request)
    checkout_status = await stripe_checkout.get_checkout_status(session_id)

    next_status = checkout_status.status
    next_payment_status = checkout_status.payment_status
    update_payload = {
        "status": next_status,
        "payment_status": next_payment_status,
        "amount": transaction_doc.get("amount", 0),
        "currency": transaction_doc.get("currency", "usd"),
    }
    if next_payment_status == "paid" and not transaction_doc.get("completed_at"):
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


@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    stripe_checkout = build_stripe_checkout(request)
    request_body = await request.body()
    webhook_response = await stripe_checkout.handle_webhook(request_body, request.headers.get("Stripe-Signature"))

    session_id = getattr(webhook_response, "session_id", None)
    payment_status = getattr(webhook_response, "payment_status", None)
    event_type = getattr(webhook_response, "event_type", None)
    if session_id:
        update_payload = {
            "status": event_type or "webhook-received",
            "payment_status": payment_status or "unpaid",
        }
        if payment_status == "paid":
            update_payload["completed_at"] = now_iso()
        await payments_collection.update_one({"session_id": session_id}, {"$set": update_payload})

    return {
        "received": True,
        "session_id": session_id,
        "payment_status": payment_status,
        "event_type": event_type,
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()