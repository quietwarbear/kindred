"""Role-aware event response serialization.

Invitation IDs are bearer credentials. Generic event responses must therefore
never expose invitation records or named RSVP data to ordinary members.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from itinerary import (
    activity_choice_summaries,
    activity_link_fields,
    activity_material_fields,
    activity_material_files,
    activity_response_open,
    activity_summaries,
    is_event_link_privileged,
    own_activity_responses,
    published_activities,
)
from rsvp_integrity import member_invite_aliases, public_respondent_identity

ORGANIZER_ROLES = {"host", "organizer"}
SENSITIVE_EVENT_FIELDS = {
    "activity_materials",
    "activity_rsvps",
    "attendee_hub_reviewed_by",
    "attendees",
    "assigned_roles",
    "checklist",
    "client_request_id",
    "duplicate_dismissals",
    "duplicate_merges",
    "event_invites",
    "event_role_assignments",
    "hidden_from_member_ids",
    "hidden_from_user_ids",
    "ile_ubuntu_course_map",
    "ile_ubuntu_handoff_last",
    "holiday_pilot_confirmations",
    "holiday_pilot_readiness",
    "holiday_setup_revision",
    "memory_capsule_reviewed_by",
    "memory_capsule_withdrawal_hashes",
    "planning_checklist",
    "planning_team_member_ids",
    "role_assignments",
    "rsvp_records",
    "rsvp_revision",
    "special_focus",
    "suggested_contribution",
    "travel_coordination_notes",
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
    view["activity_choice_summaries"] = activity_choice_summaries(event)
    if user.get("role") in ORGANIZER_ROLES:
        view.pop("holiday_pilot_confirmations", None)
        view.pop("holiday_setup_revision", None)
        for item in view.get("agenda") or []:
            item["materials"] = activity_material_files(event, str(item.get("id") or ""))
        view.pop("activity_materials", None)
        return view

    user_id = user.get("id", "")
    aliases = member_invite_aliases(event, user)
    own_matches = [
        record
        for record in event.get("rsvp_records", [])
        if record.get("user_id") in aliases
    ]
    own_overall = (
        max(own_matches, key=lambda record: record.get("updated_at", ""))
        if own_matches
        else None
    )
    view["my_rsvp_status"] = (own_overall or {}).get("status", "")
    view["my_rsvp_guests"] = max(0, int((own_overall or {}).get("guests", 0) or 0))
    own_rows = own_activity_responses(event, aliases)
    view["my_activity_responses"] = {
        activity_id: row.get("status", "") for activity_id, row in own_rows.items()
    }
    view["my_activity_choices"] = {
        activity_id: str(row.get("choice") or "")
        for activity_id, row in own_rows.items()
        if row.get("choice")
    }
    privileged = is_event_link_privileged(event, user)
    view["agenda"] = []
    for source in published_activities(event):
        activity = deepcopy(source)
        my_status = view["my_activity_responses"].get(source.get("id", ""), "")
        activity.update(
            activity_link_fields(source, my_status, privileged=privileged)
        )
        activity.update(
            activity_material_fields(
                event, source, my_status, privileged=privileged
            )
        )
        activity["response_open"] = activity_response_open(
            source, event.get("timezone", "UTC")
        )
        view["agenda"].append(activity)
    published_ids = {
        activity.get("id") for activity in view["agenda"] if activity.get("id")
    }
    view["activity_rsvp_summaries"] = {
        activity_id: summary
        for activity_id, summary in activity_summaries(event).items()
        if activity_id in published_ids
    }
    view["potluck_items"] = [
        {
            "id": item.get("id", ""),
            "item_name": item.get("item_name", ""),
            "claimed": bool(item.get("assigned_to_id") or item.get("assigned_to")),
            "is_mine": (
                item.get("assigned_to_id") == user_id
                or (
                    not item.get("assigned_to_id")
                    and item.get("assigned_to")
                    and item.get("assigned_to") == user.get("full_name")
                )
            ),
        }
        for item in event.get("potluck_items", [])
    ]
    view["volunteer_slots"] = []
    for slot in event.get("volunteer_slots", []):
        assigned_ids = list(dict.fromkeys(slot.get("assigned_member_ids") or []))
        assigned_names = list(dict.fromkeys(slot.get("assigned_members") or []))
        needed_count = max(1, int(slot.get("needed_count", 1) or 1))
        filled_count = min(
            max(len(assigned_ids), len(assigned_names)),
            needed_count,
        )
        view["volunteer_slots"].append(
            {
                "id": slot.get("id", ""),
                "title": slot.get("title", ""),
                "needed_count": needed_count,
                "filled_count": filled_count,
                "openings": max(0, needed_count - filled_count),
                "is_mine": (
                    user_id in assigned_ids
                    or (not assigned_ids and user.get("full_name") in assigned_names)
                ),
            }
        )
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
    own_rows = own_activity_responses(event, respondent_aliases)
    activities = []
    for activity in published_activities(event):
        activity_id = activity.get("id", "")
        own_row = own_rows.get(activity_id) or {}
        my_status = str(own_row.get("status") or "no-response")
        response_open = activity_response_open(activity, event.get("timezone", "UTC"))
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
                # Guests are never privileged: the link follows their own answer.
                **activity_link_fields(activity, my_status, privileged=False),
                **activity_material_fields(
                    event, activity, my_status, privileged=False
                ),
                "location_tba": bool(activity.get("location_tba", False)),
                "capacity": activity.get("capacity"),
                "rsvp_deadline": activity.get("rsvp_deadline", ""),
                "response_open": response_open,
                "response_choices": list(activity.get("response_choices") or []),
                "attendance_requested": bool(
                    activity.get("attendance_requested", True)
                ),
                "notes": activity.get("notes", ""),
                "featured": bool(activity.get("featured", False)),
                "attendance": summaries.get(activity_id, {}),
                "my_response": my_status,
                "my_choice": str(own_row.get("choice") or ""),
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
