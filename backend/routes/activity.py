"""Activity Feed routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import (
    announcements_collection,
    events_collection,
    memories_collection,
    notification_events_collection,
    polls_collection,
    threads_collection,
    users_collection,
)
from dependencies import get_current_user, now_iso

router = APIRouter(prefix="/api")


@router.get("/activity-feed")
async def get_activity_feed(
    page: int = 1,
    page_size: int = 30,
    event_type: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Return a paginated activity feed for the community."""
    community_id = current_user["community_id"]
    query = {"community_id": community_id}
    if event_type:
        query["event_type"] = event_type

    skip = (max(page, 1) - 1) * page_size
    total = await notification_events_collection.count_documents(query)
    items = (
        await notification_events_collection.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
        .to_list(page_size)
    )

    # Enrich with read status
    for item in items:
        item["is_read"] = current_user["id"] in item.get("read_by_user_ids", [])
        item.pop("read_by_user_ids", None)

    # Get distinct event types for filter options
    event_types = await notification_events_collection.distinct("event_type", {"community_id": community_id})

    # Get community stats for the feed header
    member_count = await users_collection.count_documents({"community_id": community_id})

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
        "event_types": sorted(event_types),
        "community_member_count": member_count,
    }
