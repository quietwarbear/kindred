"""Role-aware event response serialization.

Invitation IDs are bearer credentials. Generic event responses must therefore
never expose invitation records or named RSVP data to ordinary members.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from itinerary import (
    activity_summaries,
    parse_local_datetime,
    published_activities,
)
from rsvp_integrity import public_respondent_identity

ORGANIZER_ROLES = {"host", "organizer"}
SENSITIVE_EVENT_FIELDS = {
    "activity_rsvps",
    "attendees",
    "event_invites",
    "event_role_assignments",
    "role_assignments",
    "rsvp_records",
}


def rsvp_summary(event: dict[str, Any]) -> dict[str, int]:
    alias_map = {
        f"invite:{invite.get('id')}": invite.get("member_id")
        for invite in event.get("event_invites", [])
        if invite.get("id") and invite.get("member_id")
    }
    by_respondent: dict[str, dict[str, Any]] = {}
    for record in event.get("rsvp_records", []):
        respondent_id = alias_map.get(
            record.get("user_id", ""), record.get("user_id", "")
        )
        existing = by_respondent.get(respondent_id)
        if not existing or record.get("updated_at", "") >= existing.get(
            "updated_at", ""
        ):
            by_respondent[respondent_id] = record
    records = list(by_respondent.values())
    return {
        "going": sum(1 for record in records if record.get("status") == "going"),
        "some": sum(1 for record in records if record.get("status") == "some"),
        "maybe": sum(1 for record in records if record.get("status") == "maybe"),
        "not_going": sum(
            1 for record in records if record.get("status") == "not-going"
        ),
    }


def serialize_event_for_user(
    event: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """Return a detached event view appropriate for the authenticated role."""
    view = deepcopy(event)
    view["rsvp_summary"] = rsvp_summary(event)
    if user.get("role") in ORGANIZER_ROLES:
        return view

    user_id = user.get("id", "")
    own_overall = next(
        (
            record
            for record in event.get("rsvp_records", [])
            if record.get("user_id") == user_id
        ),
        None,
    )
    view["my_rsvp_status"] = (own_overall or {}).get("status", "")
    view["my_rsvp_guests"] = max(0, int((own_overall or {}).get("guests", 0) or 0))
    view["my_activity_responses"] = {
        response.get("activity_id", ""): response.get("status", "")
        for response in event.get("activity_rsvps", [])
        if response.get("respondent_id") == user_id and response.get("activity_id")
    }
    for field in SENSITIVE_EVENT_FIELDS:
        view.pop(field, None)
    return view


def serialize_event_for_guest(
    event: dict[str, Any], invite: dict[str, Any]
) -> dict[str, Any]:
    """Return the canonical no-account guest view, also used by guest preview."""
    fmt = event.get("gathering_format", "in-person")
    summaries = activity_summaries(event)
    _invite_identity, respondent_aliases = public_respondent_identity(invite)
    own_activity_responses = {
        response.get("activity_id", ""): response.get("status", "")
        for response in event.get("activity_rsvps", [])
        if response.get("respondent_id") in respondent_aliases
    }
    activities = []
    for activity in published_activities(event):
        activity_id = activity.get("id", "")
        deadline = parse_local_datetime(
            activity.get("rsvp_deadline", ""),
            activity.get("timezone") or event.get("timezone", "UTC"),
        )
        deadline_value = activity.get("rsvp_deadline", "")
        response_open = not deadline_value or bool(
            deadline and datetime.now(timezone.utc) <= deadline
        )
        activities.append(
            {
                "id": activity_id,
                "title": activity.get("title", ""),
                "description": activity.get("description", ""),
                "start_at": activity.get("start_at", ""),
                "end_at": activity.get("end_at", ""),
                "timezone": activity.get("timezone") or event.get("timezone", "UTC"),
                "venue_name": activity.get("venue_name", ""),
                "venue_address": activity.get("venue_address", ""),
                "venue_detail": activity.get("venue_detail", ""),
                "map_url": activity.get("map_url", ""),
                "virtual_link": activity.get("virtual_link", ""),
                "location_tba": bool(activity.get("location_tba", False)),
                "capacity": activity.get("capacity"),
                "rsvp_deadline": activity.get("rsvp_deadline", ""),
                "response_open": response_open,
                "attendance_requested": bool(
                    activity.get("attendance_requested", True)
                ),
                "notes": activity.get("notes", ""),
                "featured": bool(activity.get("featured", False)),
                "attendance": summaries.get(activity_id, {}),
                "my_response": own_activity_responses.get(activity_id, "no-response"),
            }
        )
    return {
        "invitee_name": invite.get("invitee_name", ""),
        "rsvp_status": invite.get("rsvp_status", "pending"),
        "gathering": {
            "title": event.get("title", ""),
            "start_at": event.get("start_at", ""),
            "end_at": event.get("end_at", ""),
            "timezone": event.get("timezone", "UTC"),
            "location": event.get("location", ""),
            "gathering_format": fmt,
            "zoom_link": (
                event.get("zoom_link", "") if fmt in {"online", "hybrid"} else ""
            ),
            "description": event.get("description", ""),
            "event_template": event.get("event_template", "custom"),
            "activity_count": len(activities),
            "activities": activities,
        },
    }
