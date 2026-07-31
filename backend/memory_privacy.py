"""Shared memory visibility and ownership helpers."""

from __future__ import annotations

from typing import Any

from dependencies import event_derived_query_for_user


async def visible_memory_query_for_user(
    user: dict[str, Any],
    *,
    include_own_capsule_drafts: bool = False,
    **extra_filters: Any,
) -> dict[str, Any]:
    """Exclude hidden-event memories and every other member's capsule draft."""
    scoped = await event_derived_query_for_user(user, **extra_filters)
    if include_own_capsule_drafts:
        visibility = {
            "$or": [
                {"capsule_status": {"$ne": "draft"}},
                {"created_by": user["id"]},
            ]
        }
    else:
        visibility = {"capsule_status": {"$ne": "draft"}}
    return {"$and": [scoped, visibility]}


def is_memory_owner(memory: dict[str, Any], user: dict[str, Any]) -> bool:
    owner_id = memory.get("created_by") or memory.get("created_by_id")
    return bool(owner_id and owner_id == user.get("id"))
