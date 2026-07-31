"""Privacy-safe reunion completion, recap, and carry-forward projections."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from event_privacy import rsvp_summary
from itinerary import (
    activity_summaries,
    parse_local_datetime,
    valid_timezone,
)
from rsvp_integrity import member_invite_aliases

RECAP_STATES = {"ready", "published", "unpublished", "legacy_conflict"}


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def reunion_completion(
    event: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    """Return the canonical, mutation-free completion state.

    A reunion completes at the latest valid end among its event end and every
    published structured activity. The reunion timezone, event start, and all
    present published activity boundaries must be valid and unambiguous.
    Ambiguous, nonexistent, malformed, or insufficient legacy data fails closed.
    """
    timezone_name = str(event.get("timezone") or "")
    if not timezone_name or not valid_timezone(timezone_name):
        return {"state": "legacy_conflict", "boundary": "invalid_timezone"}
    event_start = parse_local_datetime(str(event.get("start_at") or ""), timezone_name)
    if not event_start:
        return {"state": "legacy_conflict", "boundary": "invalid_start"}

    ends: list[datetime] = []
    event_end_value = str(event.get("end_at") or "")
    if event_end_value:
        event_end = parse_local_datetime(event_end_value, timezone_name)
        if not event_end or event_end <= event_start:
            return {"state": "legacy_conflict", "boundary": "invalid_end"}
        ends.append(event_end)

    for activity in event.get("agenda") or []:
        if activity.get("visibility") != "published":
            continue
        activity_timezone = str(activity.get("timezone") or timezone_name)
        if not valid_timezone(activity_timezone):
            return {"state": "legacy_conflict", "boundary": "invalid_activity_timezone"}
        start = parse_local_datetime(str(activity.get("start_at") or ""), activity_timezone)
        end = parse_local_datetime(str(activity.get("end_at") or ""), activity_timezone)
        if not start or not end or end <= start:
            return {"state": "legacy_conflict", "boundary": "invalid_activity_boundary"}
        ends.append(end)

    if not ends:
        return {"state": "legacy_conflict", "boundary": "missing_final_end"}
    final_end = max(ends).astimezone(timezone.utc)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "state": "ready" if current >= final_end else "not_ready",
        "boundary": "at_or_after_final_end" if current >= final_end else "before_final_end",
        "completed_at": _iso_utc(final_end),
    }


def recap_state(
    event: dict[str, Any], recap: dict[str, Any] | None, *, now: datetime | None = None
) -> str:
    completion = reunion_completion(event, now=now)
    if completion["state"] != "ready":
        return completion["state"]
    stored = str((recap or {}).get("state") or "ready")
    return stored if stored in RECAP_STATES - {"legacy_conflict"} else "ready"


def _latest_own_response(
    rows: list[dict[str, Any]], key: str, aliases: set[str]
) -> dict[str, Any] | None:
    matches = [row for row in rows if row.get(key) in aliases]
    return max(matches, key=lambda row: str(row.get("updated_at") or "")) if matches else None


def build_recap_projection(
    event: dict[str, Any],
    recap: dict[str, Any] | None,
    memories: list[dict[str, Any]],
    user: dict[str, Any],
    *,
    organizer_preview: bool,
    next_gathering_started: bool,
    published_memory_count: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build an allowlisted recap with no internal identifiers or named roster."""
    state = recap_state(event, recap, now=now)
    aliases = member_invite_aliases(event, user)
    own_rsvp = _latest_own_response(event.get("rsvp_records") or [], "user_id", aliases)
    own_activity = {
        row.get("activity_id"): row.get("status")
        for row in event.get("activity_rsvps") or []
        if row.get("respondent_id") in aliases and row.get("activity_id")
    }
    summaries = activity_summaries(event)
    itinerary = []
    for position, activity in enumerate(
        [item for item in event.get("agenda") or [] if item.get("visibility") == "published"],
        start=1,
    ):
        activity_id = activity.get("id")
        itinerary.append(
            {
                "position": position,
                "title": str(activity.get("title") or ""),
                "start_at": str(activity.get("start_at") or ""),
                "end_at": str(activity.get("end_at") or ""),
                "timezone": str(activity.get("timezone") or event.get("timezone") or "UTC"),
                "my_response": str(own_activity.get(activity_id) or "no_response"),
                "participation": {
                    "coming": int(summaries.get(activity_id, {}).get("coming", 0) or 0),
                    "maybe": int(summaries.get(activity_id, {}).get("maybe", 0) or 0),
                    "not_coming": int(summaries.get(activity_id, {}).get("not_coming", 0) or 0),
                },
            }
        )

    published_memories = [
        memory
        for memory in memories
        if memory.get("capsule_status", "published") == "published"
    ]
    own_memories = [
        memory for memory in memories if memory.get("created_by") == user.get("id")
    ]
    own_memory = max(
        own_memories,
        key=lambda memory: str(memory.get("updated_at") or memory.get("created_at") or ""),
        default=None,
    )
    contributions = {
        "available_categories": len(event.get("potluck_items") or [])
        + len(event.get("volunteer_slots") or []),
        "claimed_categories": sum(
            1
            for item in event.get("potluck_items") or []
            if item.get("assigned_to_id") or item.get("assigned_to")
        )
        + sum(
            min(
                max(
                    len(item.get("assigned_member_ids") or []),
                    len(item.get("assigned_members") or []),
                ),
                max(1, int(item.get("needed_count", 1) or 1)),
            )
            for item in event.get("volunteer_slots") or []
        ),
    }
    overall = rsvp_summary(event)
    result = {
        "state": state,
        "revision": max(0, int((recap or {}).get("revision", 0) or 0)),
        "viewer_role": "organizer" if user.get("role") in {"host", "organizer"} else "member",
        "reunion": {
            "title": str(event.get("title") or ""),
            "start_at": str(event.get("start_at") or ""),
            "end_at": str(event.get("end_at") or ""),
            "timezone": str(event.get("timezone") or "UTC"),
        },
        "itinerary": itinerary,
        "my_participation": {
            "rsvp_status": str((own_rsvp or {}).get("status") or "no_response"),
            "guest_count": max(0, int((own_rsvp or {}).get("guests", 0) or 0)),
        },
        "aggregate_participation": {
            "going": overall["going"],
            "some": overall["some"],
            "maybe": overall["maybe"],
            "not_going": overall["not_going"],
            **contributions,
            "published_memory_count": (
                len(published_memories)
                if published_memory_count is None
                else max(0, int(published_memory_count))
            ),
        },
        "memory_capsule": {"available": True},
        "next_gathering": {
            "state": "draft_started" if next_gathering_started else "not_started"
        },
    }
    if state in {"not_ready", "legacy_conflict"}:
        next_action = "wait_for_completion"
    elif organizer_preview and state in {"ready", "unpublished"}:
        next_action = "publish_recap"
    elif organizer_preview and not next_gathering_started:
        next_action = "start_next_gathering"
    elif (own_memory or {}).get("capsule_status") == "draft":
        next_action = "finish_memory_draft"
    elif not any(
        memory.get("capsule_status", "published") == "published"
        for memory in own_memories
    ):
        next_action = "contribute_memory"
    else:
        next_action = "review_memories"
    result["next_action"] = {"code": next_action}
    if recap and (organizer_preview or state == "published"):
        result["message"] = str(recap.get("message") or "")
    if organizer_preview:
        result["message_author"] = {
            "category": "former_organizer" if (recap or {}).get("author_tombstone") else "organizer"
        }
    return result


def selection_reference(event_id: str, kind: str, source_id: str) -> str:
    return hashlib.sha256(f"{event_id}\n{kind}\n{source_id}".encode()).hexdigest()[:24]


def carry_forward_catalog(event: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return organizer-safe structural choices using opaque selection references."""
    return {
        "itinerary_templates": [
            {
                "selection_reference": selection_reference(event["id"], "activity", str(item.get("id") or "")),
                "title": str(item.get("title") or ""),
                "attendance_requested": bool(item.get("attendance_requested", True)),
            }
            for item in event.get("agenda") or []
            if item.get("visibility") == "published" and item.get("id") and item.get("title")
        ],
        "contribution_categories": [
            {
                "selection_reference": selection_reference(event["id"], "potluck", str(item.get("id") or "")),
                "kind": "potluck",
                "label": str(item.get("item_name") or ""),
            }
            for item in event.get("potluck_items") or []
            if item.get("id") and item.get("item_name")
        ]
        + [
            {
                "selection_reference": selection_reference(event["id"], "volunteer", str(item.get("id") or "")),
                "kind": "volunteer",
                "label": str(item.get("title") or ""),
            }
            for item in event.get("volunteer_slots") or []
            if item.get("id") and item.get("title")
        ],
    }


def preview_digest(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
