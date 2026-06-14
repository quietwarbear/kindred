"""Legacy Table routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import (
    communities_collection,
    events_collection,
    kinships_collection,
    legacy_table_collection,
    memories_collection,
    threads_collection,
    users_collection,
)
from dependencies import ensure_minimum_role, get_current_user, get_thread_for_user, now_iso
from legacy_table_sync import DEFAULT_BASE_URL, push_recipe
from models import LegacyTableConfigRequest

router = APIRouter(prefix="/api")


@router.get("/legacy-table/status")
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
    # Never expose the stored account password to clients.
    safe = {k: v for k, v in config.items() if k != "account_password"}
    safe["is_connected"] = bool(config.get("account_email") and config.get("account_password"))
    return safe


@router.post("/legacy-table/config")
async def save_legacy_table_config(payload: LegacyTableConfigRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    connected = bool(payload.account_email and payload.account_password)
    config_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "connection_status": "connected" if connected else "configured",
        "is_connected": connected,
        "base_url": (payload.base_url or DEFAULT_BASE_URL).strip(),
        "auth_type": payload.auth_type,
        "account_email": (payload.account_email or "").strip(),
        "account_password": payload.account_password or "",
        "message": "Legacy Table account connected." if connected else "Connection saved. Add an account email and password to enable recipe sync.",
        "sync_preferences": {
            "members": payload.sync_members,
            "stories": payload.sync_stories,
            "events": payload.sync_events,
            "relationships": payload.sync_relationships,
        },
        "capabilities": ["recipe sync", "story export", "gathering export"],
        "last_sync_at": None,
        "last_sync_result": "Not yet attempted",
        "updated_at": now_iso(),
    }
    await legacy_table_collection.update_one(
        {"community_id": current_user["community_id"]},
        {"$set": config_doc},
        upsert=True,
    )
    # Never echo the password back to the client.
    return {k: v for k, v in config_doc.items() if k != "account_password"}


@router.post("/legacy-table/sync-recipe/{thread_id}")
async def sync_recipe_to_legacy_table(thread_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    """Push a Recipe/Tradition Legacy Thread into Legacy Table ('where recipes live forever')."""
    ensure_minimum_role(current_user, "organizer")
    thread = await get_thread_for_user(thread_id, current_user)

    config = await legacy_table_collection.find_one(
        {"community_id": current_user["community_id"]}, {"_id": 0}
    )
    if not config or not config.get("account_email") or not config.get("account_password"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connect a Legacy Table account first (Legacy Threads → Connect Legacy Table).",
        )

    community = await communities_collection.find_one(
        {"id": current_user["community_id"]}, {"_id": 0, "name": 1}
    )
    community_name = community.get("name", "a Kindred community") if community else "a Kindred community"

    teller = (thread.get("elder_name") or thread.get("created_by_name") or "").strip()
    story_parts = []
    if teller:
        story_parts.append(f"As told by {teller}.")
    story_parts.append(f"Preserved from {community_name} on Kindred.")

    recipe = {
        "title": thread.get("title", "Untitled recipe"),
        "ingredients": [],
        "instructions": (thread.get("body", "") or "").strip() or "(See the story for details.)",
        "story": " ".join(story_parts),
        "photos": [],
        "cooking_time": 0,
        "servings": 0,
        "category": "Family Tradition",
        "difficulty": "easy",
    }

    result = await push_recipe(config, recipe)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.get("error", "Recipe sync failed."))

    synced_at = now_iso()
    await threads_collection.update_one(
        {"id": thread_id, "community_id": current_user["community_id"]},
        {"$set": {"legacy_table_recipe_id": result.get("recipe_id", ""), "legacy_table_synced_at": synced_at}},
    )
    await legacy_table_collection.update_one(
        {"community_id": current_user["community_id"]},
        {"$set": {"last_sync_at": synced_at, "last_sync_result": f"Recipe '{recipe['title']}' sent to Legacy Table."}},
    )
    return {"ok": True, "recipe_id": result.get("recipe_id", ""), "synced_at": synced_at}


@router.post("/legacy-table/sync-preview")
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
