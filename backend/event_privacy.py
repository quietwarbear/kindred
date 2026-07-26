"""Role-aware event response serialization.

Invitation IDs are bearer credentials. Generic event responses must therefore
never expose invitation records or named RSVP data to ordinary members.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


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
        respondent_id = alias_map.get(record.get("user_id", ""), record.get("user_id", ""))
        existing = by_respondent.get(respondent_id)
        if not existing or record.get("updated_at", "") >= existing.get("updated_at", ""):
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


def serialize_event_for_user(event: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """Return a detached event view appropriate for the authenticated role."""
    view = deepcopy(event)
    view["rsvp_summary"] = rsvp_summary(event)
    if user.get("role") in ORGANIZER_ROLES:
        return view

    user_id = user.get("id", "")
    own_overall = next(
        (record for record in event.get("rsvp_records", []) if record.get("user_id") == user_id),
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
