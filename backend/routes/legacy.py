"""Legacy Table routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import (
    events_collection,
    kinships_collection,
    legacy_table_collection,
    memories_collection,
    threads_collection,
    users_collection,
)
from dependencies import ensure_minimum_role, get_current_user, now_iso
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
    return config


@router.post("/legacy-table/config")
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
