"""Community, courtyard, subyards, kinship, and invites routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from courtyard_helpers import ALL_MODULE_KEYS, MODULE_CATALOG, ROLE_TOOLING, countdown_days, resolve_modules
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
    event_derived_query_for_user,
    enforce_member_limit,
    enforce_subyard_limit,
    get_community_for_user,
    get_current_user,
    get_subyard_for_user,
    log_notification_event,
    normalize_email,
    now_iso,
    sanitize_doc,
    visible_event_query_for_user,
)
from event_privacy import serialize_event_for_user
from models import (
    DashboardOverview,
    InviteCreateRequest,
    InvitePublic,
    KinshipCreateRequest,
    ModulesUpdateRequest,
    SubyardCreateRequest,
)

router = APIRouter(prefix="/api")


@router.get("/community/modules")
async def get_community_modules(current_user: dict[str, Any] = Depends(get_current_user)):
    """The community's enabled modules (its saved config, else the type default) + catalog."""
    community = await get_community_for_user(current_user)
    return {"enabled": resolve_modules(community), "catalog": MODULE_CATALOG, "community_type": community.get("community_type", "")}


@router.put("/community/modules")
async def set_community_modules(payload: ModulesUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    """Steward-set which modules this community runs. Validates against the catalog."""
    ensure_minimum_role(current_user, "organizer")
    enabled = [m for m in payload.modules if m in ALL_MODULE_KEYS]
    await communities_collection.update_one(
        {"id": current_user["community_id"]}, {"$set": {"modules": enabled}}
    )
    return {"enabled": enabled, "catalog": MODULE_CATALOG}


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
    event_count = await events_collection.count_documents(
        visible_event_query_for_user(current_user)
    )
    memory_query = await event_derived_query_for_user(current_user)
    memory_count = await memories_collection.count_documents(memory_query)
    thread_count = await threads_collection.count_documents({"community_id": community_id})
    pending_invites = await invites_collection.find({"community_id": community_id, "status": "pending"}, {"_id": 0}).to_list(20)
    funds_agg = await payments_collection.aggregate([
        {"$match": {"community_id": community_id, "payment_status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    funds_raised = round(funds_agg[0]["total"], 2) if funds_agg else 0.0
    upcoming_events = await events_collection.find({"community_id": community_id, "hidden_from_user_ids": {"$ne": current_user["id"]}}, {"_id": 0}).sort("start_at", 1).to_list(5)
    recent_memories = await memories_collection.find(
        memory_query,
        {"_id": 0},
    ).sort("created_at", -1).to_list(6)
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
        "upcoming_events": [
            serialize_event_for_user(event, current_user)
            for event in upcoming_events
        ],
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
    upcoming_events = await events_collection.find({"community_id": community_id, "hidden_from_user_ids": {"$ne": current_user["id"]}}, {"_id": 0}).sort("start_at", 1).to_list(5)
    memories = await memories_collection.find(
        await event_derived_query_for_user(current_user),
        {"_id": 0},
    ).sort("created_at", -1).to_list(6)
    threads = await threads_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(6)
    pending_invites = await invites_collection.find({"community_id": community_id, "status": "pending"}, {"_id": 0}).to_list(20)
    funds_agg = await payments_collection.aggregate([
        {"$match": {"community_id": community_id, "payment_status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    funds_total = round(funds_agg[0]["total"], 2) if funds_agg else 0.0
    budgets = await budget_plans_collection.find(
        await event_derived_query_for_user(current_user),
        {"_id": 0},
    ).sort("created_at", -1).to_list(20)
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
        subyard_event_count = await events_collection.count_documents({
            "community_id": community_id,
            "subyard_id": subyard["id"],
            "hidden_from_user_ids": {"$ne": current_user["id"]},
        })
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
        gatherings.append(
            {
                **serialize_event_for_user(event, current_user),
                "countdown_days": countdown_days(event.get("start_at")),
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


@router.get("/subyards/{subyard_id}")
async def get_subyard(subyard_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    subyard_doc = await get_subyard_for_user(subyard_id, current_user)
    community_doc = await get_community_for_user(current_user)
    community_id = current_user["community_id"]
    members = await users_collection.find({"community_id": community_id}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    invites = await invites_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    announcements = await announcements_collection.find({"community_id": community_id, "$or": [{"scope": "courtyard"}, {"subyard_id": subyard_id}]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    chat_room = await chat_rooms_collection.find_one({"community_id": community_id, "subyard_id": subyard_id}, {"_id": 0})
    kinships = await kinships_collection.find({"community_id": community_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {
        "subyard": subyard_doc,
        "courtyard": community_doc,
        "members": members,
        "invites": invites,
        "announcements": announcements,
        "chat_room": chat_room,
        "kinships": kinships,
    }


@router.post("/subyards")
async def create_subyard(payload: SubyardCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    await enforce_subyard_limit(current_user["community_id"])
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


@router.get("/kinship/graph")
async def kinship_graph(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return kinship data formatted for network graph visualization."""
    community_id = current_user["community_id"]
    relationships = await kinships_collection.find(
        {"community_id": community_id}, {"_id": 0}
    ).to_list(500)

    members = await users_collection.find(
        {"community_id": community_id},
        {"_id": 0, "id": 1, "full_name": 1, "role": 1, "profile_image_url": 1},
    ).to_list(500)

    by_id = {m["id"]: m for m in members}
    by_name = {m["full_name"]: m for m in members}

    # Member nodes are keyed by user_id (so they're navigable); non-member
    # people fall back to a name-keyed node so legacy relationships still render.
    node_map = {}
    for m in members:
        node_map[m["id"]] = {
            "id": m["id"], "name": m["full_name"], "group": "member",
            "role": m.get("role", "member"), "user_id": m["id"],
        }

    def resolve(name, user_id):
        if user_id and user_id in by_id:
            return user_id
        if name and name in by_name:
            return by_name[name]["id"]
        key = (name or "Unknown").strip() or "Unknown"
        if key not in node_map:
            node_map[key] = {"id": key, "name": key, "group": "kinship", "role": "kinship", "user_id": None}
        return key

    links = []
    for rel in relationships:
        source = resolve(rel.get("person_name", ""), rel.get("person_user_id", ""))
        target = resolve(rel.get("related_to_name", ""), rel.get("related_to_user_id", ""))
        links.append({
            "source": source,
            "target": target,
            "label": rel.get("relationship_type", ""),
            "kinship_id": rel["id"],
        })

    rel_types = sorted({rel["relationship_type"] for rel in relationships if rel.get("relationship_type")})

    return {
        "nodes": list(node_map.values()),
        "links": links,
        "relationship_types": rel_types,
        "total_nodes": len(node_map),
        "total_links": len(links),
    }


@router.post("/kinship")
async def create_kinship(payload: KinshipCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    relationship_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "person_name": payload.person_name.strip(),
        "related_to_name": payload.related_to_name.strip(),
        "person_user_id": (payload.person_user_id or "").strip(),
        "related_to_user_id": (payload.related_to_user_id or "").strip(),
        "relationship_type": payload.relationship_type.strip(),
        "relationship_scope": payload.relationship_scope,
        "notes": (payload.notes or "").strip(),
        "last_seen_at": payload.last_seen_at,
        "created_by": current_user["id"],
        "created_at": now_iso(),
    }
    await kinships_collection.insert_one(relationship_doc.copy())
    return relationship_doc


@router.get("/kinship/person/{user_id}")
async def kinship_person(user_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    """A person's place in the community: their relationships, gatherings, memories, stories.

    Community-scoped and read-only. Powers tapping a node in the kinship graph.
    """
    community_id = current_user["community_id"]
    person = await users_collection.find_one(
        {"id": user_id, "community_id": community_id},
        {"_id": 0, "id": 1, "full_name": 1, "role": 1, "profile_image_url": 1, "created_at": 1},
    )
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found in this community.")

    relationships = await kinships_collection.find(
        {
            "community_id": community_id,
            "$or": [
                {"person_user_id": user_id},
                {"related_to_user_id": user_id},
                {"person_name": person["full_name"]},
                {"related_to_name": person["full_name"]},
            ],
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)

    gatherings = await events_collection.find(
        {
            "community_id": community_id,
            "rsvp_records.user_id": user_id,
            "hidden_from_user_ids": {"$ne": current_user["id"]},
        },
        {"_id": 0, "id": 1, "title": 1, "start_at": 1, "location": 1},
    ).sort("start_at", -1).to_list(20)

    memories = await memories_collection.find(
        await event_derived_query_for_user(current_user, created_by=user_id),
        {"_id": 0, "id": 1, "title": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(20)

    threads = await threads_collection.find(
        {"community_id": community_id, "created_by": user_id},
        {"_id": 0, "id": 1, "title": 1, "category": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(20)

    return {
        "person": person,
        "relationships": relationships,
        "gatherings": gatherings,
        "memories": memories,
        "threads": threads,
    }


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



@router.get("/kinship/groups")
async def kinship_groups(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return kinship relationships grouped by type for quick-invite shortcuts."""
    relationships = await kinships_collection.find(
        {"community_id": current_user["community_id"]}, {"_id": 0}
    ).sort("relationship_type", 1).to_list(500)

    groups = {}
    for rel in relationships:
        rtype = rel.get("relationship_type", "other")
        if rtype not in groups:
            groups[rtype] = []
        groups[rtype].append({
            "id": rel["id"],
            "person_name": rel.get("person_name", ""),
            "related_to_name": rel.get("related_to_name", ""),
            "notes": rel.get("notes", ""),
        })

    members = await users_collection.find(
        {"community_id": current_user["community_id"]},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1},
    ).to_list(500)

    return {"groups": groups, "members": members}


@router.get("/communities/mine")
async def list_my_communities(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return all communities the current user belongs to."""
    community_ids = current_user.get("community_ids", [current_user["community_id"]])
    communities = await communities_collection.find(
        {"id": {"$in": community_ids}}, {"_id": 0}
    ).to_list(50)
    # Enrich with member count
    for c in communities:
        c["member_count"] = await users_collection.count_documents({"community_id": c["id"]})
        c["is_active"] = c["id"] == current_user["community_id"]
    return {"communities": communities, "active_community_id": current_user["community_id"]}


@router.post("/communities/switch")
async def switch_community(body: dict, current_user: dict[str, Any] = Depends(get_current_user)):
    """Switch the user's active community."""
    from dependencies import build_auth_response
    target_id = body.get("community_id", "")
    if not target_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="community_id is required.")

    community_ids = current_user.get("community_ids", [current_user["community_id"]])
    if target_id not in community_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of that community.")

    await users_collection.update_one({"id": current_user["id"]}, {"$set": {"community_id": target_id}})
    user_doc = await users_collection.find_one({"id": current_user["id"]}, {"_id": 0})
    community_doc = await communities_collection.find_one({"id": target_id}, {"_id": 0})
    return build_auth_response(user_doc, community_doc)


@router.post("/communities/join")
async def join_community_with_invite(body: dict, current_user: dict[str, Any] = Depends(get_current_user)):
    """Join an additional community using an invite code (while already logged in)."""
    from dependencies import build_auth_response
    invite_code = (body.get("invite_code") or "").strip().upper()
    if not invite_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invite_code is required.")

    invite_doc = await invites_collection.find_one({"code": invite_code, "status": "pending"}, {"_id": 0})
    if not invite_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code is invalid or already used.")

    email = current_user["email"]
    if normalize_email(invite_doc.get("email", "")) != normalize_email(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This invite was not sent to your email address.")

    target_community_id = invite_doc["community_id"]
    await enforce_member_limit(target_community_id)
    community_ids = current_user.get("community_ids", [current_user["community_id"]])
    if target_community_id in community_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You are already a member of this community.")

    new_ids = list(set(community_ids + [target_community_id]))
    await users_collection.update_one(
        {"id": current_user["id"]},
        {"$set": {"community_id": target_community_id, "community_ids": new_ids}},
    )
    await invites_collection.update_one(
        {"id": invite_doc["id"]},
        {"$set": {"status": "accepted", "accepted_at": now_iso()}},
    )

    user_doc = await users_collection.find_one({"id": current_user["id"]}, {"_id": 0})
    community_doc = await communities_collection.find_one({"id": target_community_id}, {"_id": 0})
    return build_auth_response(user_doc, community_doc)
