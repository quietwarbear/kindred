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
from dependencies import (
    ensure_minimum_role,
    get_current_user,
    get_thread_for_user,
    now_iso,
    visible_event_query_for_user,
)
from memory_privacy import visible_memory_query_for_user
from legacy_table_sync import DEFAULT_BASE_URL, push_recipe, sso_secret
from models import LegacyTableConfigRequest

router = APIRouter(prefix="/api")


@router.get("/legacy-table/status")
async def legacy_table_status(current_user: dict[str, Any] = Depends(get_current_user)):
    community_id = current_user["community_id"]
    config = (
        await legacy_table_collection.find_one(
            {"community_id": community_id}, {"_id": 0}
        )
        or {}
    )
    enabled = bool(sso_secret())
    recipes_synced = await threads_collection.count_documents(
        {"community_id": community_id, "legacy_table_recipe_id": {"$nin": [None, ""]}}
    )
    return {
        "connection_status": "connected" if enabled else "pending-setup",
        "is_connected": enabled,
        "sso_enabled": enabled,
        "base_url": config.get("base_url", ""),
        "connected_as": current_user.get("full_name") or current_user.get("email", ""),
        "recipes_synced": recipes_synced,
        "last_sync_at": config.get("last_sync_at"),
        "last_sync_result": config.get("last_sync_result"),
        "message": (
            "Your Kindred identity carries into Legacy Table."
            if enabled
            else "Legacy Table sync switches on once the shared SSO secret is set on both apps."
        ),
        "capabilities": ["recipe sync", "story export", "gathering export"],
    }


@router.post("/legacy-table/config")
async def save_legacy_table_config(
    payload: LegacyTableConfigRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    config_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "base_url": (payload.base_url or DEFAULT_BASE_URL).strip(),
        "auth_type": "ubuntu-sso",
        "sync_preferences": {
            "members": payload.sync_members,
            "stories": payload.sync_stories,
            "events": payload.sync_events,
            "relationships": payload.sync_relationships,
        },
        "capabilities": ["recipe sync", "story export", "gathering export"],
        "updated_at": now_iso(),
    }
    await legacy_table_collection.update_one(
        {"community_id": current_user["community_id"]},
        {"$set": config_doc},
        upsert=True,
    )
    config_doc["sso_enabled"] = bool(sso_secret())
    return config_doc


@router.post("/legacy-table/sync-recipe/{thread_id}")
async def sync_recipe_to_legacy_table(
    thread_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    """Push a Recipe/Tradition Legacy Thread into Legacy Table ('where recipes live forever')."""
    ensure_minimum_role(current_user, "organizer")
    thread = await get_thread_for_user(thread_id, current_user)

    config = (
        await legacy_table_collection.find_one(
            {"community_id": current_user["community_id"]}, {"_id": 0}
        )
        or {}
    )
    base_url = config.get("base_url") or DEFAULT_BASE_URL

    community = await communities_collection.find_one(
        {"id": current_user["community_id"]}, {"_id": 0, "name": 1}
    )
    community_name = (
        community.get("name", "a Kindred community")
        if community
        else "a Kindred community"
    )

    teller = (thread.get("elder_name") or thread.get("created_by_name") or "").strip()
    story_parts = []
    if teller:
        story_parts.append(f"As told by {teller}.")
    story_parts.append(f"Preserved from {community_name} on Kindred.")

    recipe = {
        "title": thread.get("title", "Untitled recipe"),
        "ingredients": [],
        "instructions": (thread.get("body", "") or "").strip()
        or "(See the story for details.)",
        "story": " ".join(story_parts),
        "photos": [],
        "cooking_time": 0,
        "servings": 0,
        "category": "Family Tradition",
        "difficulty": "easy",
    }

    result = await push_recipe(
        base_url,
        current_user.get("email", ""),
        recipe,
        current_user.get("full_name", ""),
        community_name,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "Recipe sync failed."),
        )

    synced_at = now_iso()
    await threads_collection.update_one(
        {"id": thread_id, "community_id": current_user["community_id"]},
        {
            "$set": {
                "legacy_table_recipe_id": result.get("recipe_id", ""),
                "legacy_table_synced_at": synced_at,
            }
        },
    )
    family_note = (
        f" Created the '{community_name}' family."
        if result.get("family_created")
        else ""
    )
    await legacy_table_collection.update_one(
        {"community_id": current_user["community_id"]},
        {
            "$set": {
                "last_sync_at": synced_at,
                "last_sync_result": f"Recipe '{recipe['title']}' sent to Legacy Table.{family_note}",
            }
        },
    )
    return {
        "ok": True,
        "recipe_id": result.get("recipe_id", ""),
        "family_id": result.get("family_id"),
        "family_created": result.get("family_created", False),
        "synced_at": synced_at,
    }


@router.post("/legacy-table/sync-preview")
async def legacy_table_sync_preview(
    current_user: dict[str, Any] = Depends(get_current_user),
):
    ensure_minimum_role(current_user, "organizer")
    community_id = current_user["community_id"]
    config = await legacy_table_collection.find_one(
        {"community_id": community_id}, {"_id": 0}
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save a Legacy Table configuration first.",
        )

    preview = {
        "members": await users_collection.count_documents(
            {"community_id": community_id}
        ),
        "kinships": await kinships_collection.count_documents(
            {"community_id": community_id}
        ),
        "events": await events_collection.count_documents(
            visible_event_query_for_user(current_user)
        ),
        "memories": await memories_collection.count_documents(
            await visible_memory_query_for_user(current_user)
        ),
        "threads": await threads_collection.count_documents(
            {"community_id": community_id}
        ),
    }
    updated = {
        **config,
        "last_sync_at": now_iso(),
        "last_sync_result": "Preview generated. Awaiting live credentials for external sync execution.",
        "preview_counts": preview,
    }
    await legacy_table_collection.update_one(
        {"community_id": community_id}, {"$set": updated}
    )
    return updated
