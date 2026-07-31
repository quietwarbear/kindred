"""Strict reunion attendee projection and deterministic next-action helpers.

This module is intentionally pure. It never logs, sends, tags, or calls a
provider. Event invitation credentials, named rosters, organizer planning
state, and private activity rows are excluded by construction.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from event_privacy import rsvp_summary
from itinerary import activity_summaries, parse_local_datetime, published_activities
from rsvp_integrity import member_invite_aliases

ATTENDEE_ACTION_PRIORITY = (
    "respond_to_reunion",
    "complete_activity_responses",
    "choose_contribution",
    "review_itinerary",
    "share_a_memory",
    "reunion_plan_complete",
)


def _latest_matching(
    rows: list[dict[str, Any]],
    *,
    identity_key: str,
    aliases: set[str],
) -> dict[str, Any] | None:
    matches = [row for row in rows if row.get(identity_key) in aliases]
    return max(matches, key=lambda row: row.get("updated_at", "")) if matches else None


def _response_open(activity: dict[str, Any], event: dict[str, Any]) -> bool:
    deadline_value = activity.get("rsvp_deadline", "")
    if not deadline_value:
        return True
    deadline = parse_local_datetime(
        deadline_value,
        activity.get("timezone") or event.get("timezone", "UTC"),
    )
    return bool(deadline and datetime.now(timezone.utc) <= deadline)


def _member_owns_potluck(
    item: dict[str, Any],
    user: dict[str, Any],
) -> bool:
    assigned_id = str(item.get("assigned_to_id") or "")
    if assigned_id:
        return assigned_id == user.get("id")
    return bool(
        item.get("assigned_to") and item.get("assigned_to") == user.get("full_name")
    )


def _member_owns_volunteer_slot(
    slot: dict[str, Any],
    user: dict[str, Any],
) -> bool:
    assigned_ids = set(slot.get("assigned_member_ids") or [])
    if assigned_ids:
        return user.get("id") in assigned_ids
    return user.get("full_name") in (slot.get("assigned_members") or [])


def safe_contributions(
    event: dict[str, Any],
    user: dict[str, Any],
) -> dict[str, Any]:
    """Return contribution availability without exposing anyone else's name."""
    potluck = []
    own_potluck = []
    for source in event.get("potluck_items", []):
        item = deepcopy(source)
        is_mine = _member_owns_potluck(item, user)
        claimed = bool(item.get("assigned_to_id") or item.get("assigned_to"))
        safe = {
            "id": str(item.get("id") or ""),
            "item_name": str(item.get("item_name") or ""),
            "claimed": claimed,
            "is_mine": is_mine,
        }
        potluck.append(safe)
        if is_mine:
            own_potluck.append(safe)

    volunteer = []
    own_volunteer = []
    for source in event.get("volunteer_slots", []):
        slot = deepcopy(source)
        assigned_ids = list(dict.fromkeys(slot.get("assigned_member_ids") or []))
        assigned_names = list(dict.fromkeys(slot.get("assigned_members") or []))
        filled_count = max(len(assigned_ids), len(assigned_names))
        needed_count = max(1, int(slot.get("needed_count", 1) or 1))
        is_mine = _member_owns_volunteer_slot(slot, user)
        safe = {
            "id": str(slot.get("id") or ""),
            "title": str(slot.get("title") or ""),
            "needed_count": needed_count,
            "filled_count": min(filled_count, needed_count),
            "openings": max(0, needed_count - filled_count),
            "is_mine": is_mine,
        }
        volunteer.append(safe)
        if is_mine:
            own_volunteer.append(safe)

    return {
        "potluck": potluck,
        "volunteer": volunteer,
        "own_commitments": {
            "potluck": own_potluck,
            "volunteer": own_volunteer,
            "count": len(own_potluck) + len(own_volunteer),
        },
    }


def next_attendee_action(
    *,
    overall_status: str,
    activities: list[dict[str, Any]],
    contributions: dict[str, Any],
    itinerary_reviewed: bool,
    has_memory: bool,
) -> dict[str, str]:
    """Return exactly one action using the documented stable priority."""
    if overall_status not in {"going", "some", "maybe", "not-going"}:
        code = "respond_to_reunion"
    elif any(
        activity.get("attendance_requested")
        and activity.get("response_open")
        and activity.get("my_response") == "no-response"
        for activity in activities
    ):
        code = "complete_activity_responses"
    elif contributions["own_commitments"]["count"] == 0 and (
        any(not item["claimed"] for item in contributions["potluck"])
        or any(item["openings"] > 0 for item in contributions["volunteer"])
    ):
        code = "choose_contribution"
    elif activities and not itinerary_reviewed:
        code = "review_itinerary"
    elif not has_memory:
        code = "share_a_memory"
    else:
        code = "reunion_plan_complete"
    return {"code": code}


def build_attendee_hub(
    event: dict[str, Any],
    user: dict[str, Any],
    *,
    has_memory: bool,
) -> dict[str, Any]:
    """Build the complete attendee-safe projection for one visible event."""
    aliases = member_invite_aliases(event, user)
    own_overall = _latest_matching(
        event.get("rsvp_records", []),
        identity_key="user_id",
        aliases=aliases,
    )
    own_activity = {
        row.get("activity_id", ""): row.get("status", "")
        for row in event.get("activity_rsvps", [])
        if row.get("respondent_id") in aliases and row.get("activity_id")
    }
    summaries = activity_summaries(event)
    activities = []
    for activity in published_activities(event):
        activity_id = str(activity.get("id") or "")
        activities.append(
            {
                "id": activity_id,
                "title": str(activity.get("title") or ""),
                "description": str(activity.get("description") or ""),
                "start_at": str(activity.get("start_at") or ""),
                "end_at": str(activity.get("end_at") or ""),
                "timezone": str(
                    activity.get("timezone") or event.get("timezone") or "UTC"
                ),
                "venue_name": str(activity.get("venue_name") or ""),
                "venue_address": str(activity.get("venue_address") or ""),
                "venue_detail": str(activity.get("venue_detail") or ""),
                "map_url": str(activity.get("map_url") or ""),
                "virtual_link": str(activity.get("virtual_link") or ""),
                "location_tba": bool(activity.get("location_tba", False)),
                "capacity": activity.get("capacity"),
                "rsvp_deadline": str(activity.get("rsvp_deadline") or ""),
                "response_open": _response_open(activity, event),
                "attendance_requested": bool(
                    activity.get("attendance_requested", True)
                ),
                "notes": str(activity.get("notes") or ""),
                "featured": bool(activity.get("featured", False)),
                "attendance": summaries.get(activity_id, {}),
                "my_response": own_activity.get(activity_id, "no-response"),
            }
        )

    contributions = safe_contributions(event, user)
    fmt = event.get("gathering_format", "in-person")
    reviewed = user.get("id") in (event.get("attendee_hub_reviewed_by") or [])
    overall_status = (own_overall or {}).get("status", "")
    return {
        "gathering": {
            "id": str(event.get("id") or ""),
            "title": str(event.get("title") or ""),
            "description": str(event.get("description") or ""),
            "start_at": str(event.get("start_at") or ""),
            "end_at": str(event.get("end_at") or ""),
            "timezone": str(event.get("timezone") or "UTC"),
            "location": str(event.get("location") or ""),
            "gathering_format": fmt,
            "zoom_link": (
                str(event.get("zoom_link") or "") if fmt in {"online", "hybrid"} else ""
            ),
            "event_template": str(event.get("event_template") or "custom"),
        },
        "rsvp": {
            "my_status": overall_status,
            "my_guests": max(0, int((own_overall or {}).get("guests", 0) or 0)),
            "summary": rsvp_summary(event),
        },
        "itinerary": {
            "activities": activities,
            "reviewed": reviewed,
        },
        "contributions": contributions,
        "memory_prompt": {
            "available": True,
            "code": "reunion_story",
            "title": "Keep one story from this reunion",
            "question": "What is one family story you want everyone to remember?",
            "sharing_boundary": (
                "Your story is saved to this private Kindred community. "
                "It is not published to the open web."
            ),
            "completed": has_memory,
            "capsule_path": f"/reunion/memories/{event.get('id', '')}",
        },
        "next_action": next_attendee_action(
            overall_status=overall_status,
            activities=activities,
            contributions=contributions,
            itinerary_reviewed=reviewed,
            has_memory=has_memory,
        ),
    }
