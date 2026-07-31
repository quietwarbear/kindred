"""Strict projections for the private reunion memory capsule."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from itinerary import published_activities

CAPSULE_ACTION_PRIORITY = (
    "share_first_memory",
    "finish_memory_draft",
    "review_reunion_memories",
    "reunion_capsule_complete",
)


def is_capsule_draft(memory: dict[str, Any]) -> bool:
    return memory.get("capsule_status") == "draft"


def is_capsule_published(memory: dict[str, Any]) -> bool:
    return memory.get("capsule_status", "published") == "published"


def capsule_next_action(
    *,
    published_count: int,
    own_status: str,
    reviewed: bool,
) -> dict[str, str]:
    """Return exactly one stable action without inspecting story content."""
    if published_count == 0 and own_status != "draft":
        code = "share_first_memory"
    elif own_status == "draft":
        code = "finish_memory_draft"
    elif published_count > 0 and not reviewed:
        code = "review_reunion_memories"
    else:
        code = "reunion_capsule_complete"
    return {"code": code}


def _safe_activity(activity: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(activity.get("id") or ""),
        "title": str(activity.get("title") or ""),
        "start_at": str(activity.get("start_at") or ""),
        "end_at": str(activity.get("end_at") or ""),
        "timezone": str(activity.get("timezone") or event.get("timezone") or "UTC"),
        "venue_name": str(activity.get("venue_name") or ""),
        "venue_detail": str(activity.get("venue_detail") or ""),
        "location_tba": bool(activity.get("location_tba", False)),
    }


def _safe_shared_memory(
    memory: dict[str, Any],
    user: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": str(memory.get("id") or ""),
        "story": str(memory.get("description") or ""),
        "contributor_name": str(memory.get("created_by_name") or ""),
        "created_at": str(memory.get("created_at") or ""),
        "updated_at": str(memory.get("updated_at") or ""),
        "is_mine": memory.get("created_by") == user.get("id"),
    }


def _safe_own_contribution(memory: dict[str, Any] | None) -> dict[str, Any] | None:
    if not memory:
        return None
    return {
        "id": str(memory.get("id") or ""),
        "story": str(memory.get("description") or ""),
        "status": str(memory.get("capsule_status") or "published"),
        "created_at": str(memory.get("created_at") or ""),
        "updated_at": str(memory.get("updated_at") or ""),
    }


def build_reunion_memory_capsule(
    event: dict[str, Any],
    memories: list[dict[str, Any]],
    user: dict[str, Any],
) -> dict[str, Any]:
    """Build an allowlisted attendee projection from authorized records."""
    detached = [deepcopy(memory) for memory in memories]
    published = [memory for memory in detached if is_capsule_published(memory)]
    own_candidates = [
        memory for memory in detached if memory.get("created_by") == user.get("id")
    ]
    own = (
        max(
            own_candidates,
            key=lambda memory: memory.get("updated_at")
            or memory.get("created_at")
            or "",
        )
        if own_candidates
        else None
    )
    reviewed = user.get("id") in (event.get("memory_capsule_reviewed_by") or [])
    return {
        "reunion": {
            "id": str(event.get("id") or ""),
            "title": str(event.get("title") or ""),
            "start_at": str(event.get("start_at") or ""),
            "end_at": str(event.get("end_at") or ""),
            "timezone": str(event.get("timezone") or "UTC"),
        },
        "itinerary": [
            _safe_activity(activity, event) for activity in published_activities(event)
        ],
        "memories": [_safe_shared_memory(memory, user) for memory in published],
        "memory_count": len(published),
        "own_contribution": _safe_own_contribution(own),
        "visibility": {
            "code": "private_community",
            "label": "Your private Kindred community",
            "explanation": (
                "Community members who can see this reunion can revisit "
                "published stories in this capsule."
            ),
        },
        "reviewed": reviewed,
        "next_action": capsule_next_action(
            published_count=len(published),
            own_status=str((own or {}).get("capsule_status") or ""),
            reviewed=reviewed,
        ),
    }
