"""Community, courtyard, subyards, kinship, and invites routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from courtyard_helpers import ROLE_TOOLING, countdown_days
from db import (
    announcements_collection,
    budget_plans_collection,
    chat_rooms_collection,
    communities_collection,
    events_collection,
    invites_collection,
    kinships_collection,
    memories_collection,
    payments_collection,
    subyards_collection,
    threads_collection,
    users_collection,
)
from dependencies import (
    build_invite_reminders_for_user,
    build_notifications,
    ensure_chat_rooms_for_community,
    ensure_minimum_role,
    get_community_for_user,
    get_current_user,
    get_subyard_for_user,
    log_notification_event,
    normalize_email,
    now_iso,
    sanitize_doc,
)
from models import (
    DashboardOverview,
    InviteCreateRequest,
    InvitePublic,
    KinshipCreateRequest,
    SubyardCreateRequest,
)

router = APIRouter(prefix="/api")


@router.get("/community/members")
async def list_community_members(current_user: dict[str, Any] = Depends(get_current_user)):
    members = await users_collection.find(
        {"community_id": current_user["community_id"]},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1, "profile_image_url": 1, "google_picture": 1},
    ).to_list(500)
    return {"members": members}


@router.get("/community/overview", response_model=DashboardOverview)
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


@router.get("/courtyard/home")
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


@router.get("/courtyard/structure")
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


@router.get("/subyards")
async def list_subyards(current_user: dict[str, Any] = Depends(get_current_user)):
    subyards = await subyards_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"subyards": subyards}


@router.post("/subyards")
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


@router.put("/subyards/{subyard_id}")
async def update_subyard(subyard_id: str, payload: SubyardCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    existing = await get_subyard_for_user(subyard_id, current_user)
    role_focus = [role.strip().lower() for role in payload.role_focus if role.strip()] if hasattr(payload, 'role_focus') and payload.role_focus else existing.get("role_focus", [])
    updates = {
        "name": payload.name.strip() or existing["name"],
        "description": payload.description.strip() if payload.description else existing.get("description", ""),
        "role_focus": role_focus,
        "assigned_tools": sorted({tool for role in role_focus for tool in ROLE_TOOLING.get(role, [])}),
    }
    await subyards_collection.update_one({"id": subyard_id}, {"$set": updates})
    updated = await subyards_collection.find_one({"id": subyard_id}, {"_id": 0})
    return updated


@router.delete("/subyards/{subyard_id}")
async def delete_subyard(subyard_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    await get_subyard_for_user(subyard_id, current_user)
    await subyards_collection.delete_one({"id": subyard_id})
    await chat_rooms_collection.delete_many({"subyard_id": subyard_id})
    return {"ok": True}


@router.get("/kinship")
async def list_kinship(current_user: dict[str, Any] = Depends(get_current_user)):
    relationships = await kinships_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"relationships": relationships}


@router.post("/kinship")
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


@router.delete("/kinship/{kinship_id}")
async def delete_kinship(kinship_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    result = await kinships_collection.delete_one({"id": kinship_id, "community_id": current_user["community_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kinship relationship not found.")
    return {"ok": True}


@router.post("/invites", response_model=InvitePublic)
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


@router.get("/invites")
async def list_invites(current_user: dict[str, Any] = Depends(get_current_user)):
    invites = await invites_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"invites": invites}
