"""Pure, content-free policy helpers for the authenticated Family Today view."""

from __future__ import annotations

import hashlib
from typing import Any

ORGANIZER_PRIORITY = (
    "activate_family_space",
    "finish_holiday_meal_setup",
    "prepare_holiday_invitation",
    "review_holiday_response_gaps",
    "fill_holiday_contribution_gaps",
    "preserve_holiday_recipe",
    "review_holiday_recap",
    "finish_reunion_draft",
    "prepare_first_invitation",
    "review_family_access_requests",
    "resolve_rsvp_attention",
    "complete_command_task",
    "review_recap",
    "review_gathering_proposal",
    "continue_converted_draft",
    "open_command_center",
)

MEMBER_PRIORITY = (
    "confirm_family_access",
    "complete_holiday_rsvp",
    "review_holiday_schedule",
    "claim_holiday_contribution",
    "add_holiday_recipe",
    "view_holiday_recap",
    "complete_reunion_rsvp",
    "complete_activity_responses",
    "review_updated_itinerary",
    "manage_contribution",
    "respond_to_gathering_pulse",
    "continue_memory_contribution",
    "view_published_recap",
    "check_family_access_status",
    "open_family_home",
)

ACTION_CODES = frozenset(ORGANIZER_PRIORITY + MEMBER_PRIORITY)
ACTION_STATES = frozenset(
    {
        "active",
        "approaching",
        "approved",
        "available",
        "draft",
        "missing",
        "open",
        "pending",
        "provisional",
        "published",
        "ready",
        "waiting",
    }
)
DESTINATION_CATEGORIES = frozenset(
    {
        "attendee_hub",
        "family_access",
        "family_activation",
        "family_home",
        "gathering_proposals",
        "gatherings",
        "legacy_threads",
        "memory_capsule",
        "organizer_command_center",
        "reunion_activation",
        "reunion_recap",
    }
)
NAVIGATION_CATEGORIES = frozenset(
    {"today", "gatherings", "proposals", "activity", "family_activation"}
)
RECENT_CHANGE_CATEGORIES = frozenset(
    {
        "family_access",
        "family_update",
        "gathering_update",
        "organizer_review",
        "reunion_recap",
        "gathering_pulse",
    }
)
MILESTONE_CODES = frozenset({"first_rsvp_received", "family_access_approved"})


def opaque_action_reference(
    *, community_id: str, user_id: str, action_code: str, subject: str
) -> str:
    """Create a deterministic, non-reversible action reference."""
    value = f"{community_id}\n{user_id}\n{action_code}\n{subject}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:32]


def notification_category(event_type: Any) -> str:
    value = str(event_type or "")
    if value == "reunion-recap-published":
        return "reunion_recap"
    if value == "gathering-proposal-published":
        return "gathering_pulse"
    if value in {"family-access-request", "gathering-proposal-submitted"}:
        return "organizer_review"
    if value == "family-access-status":
        return "family_access"
    if value.startswith("event-") or value in {"rsvp-update", "reminder-send"}:
        return "gathering_update"
    return "family_update"


def safe_recent_changes(
    rows: list[dict[str, Any]], viewer_id: str
) -> list[dict[str, Any]]:
    """Project existing authorized notifications without content or identifiers."""
    return [
        {
            "category": notification_category(row.get("event_type")),
            "is_read": viewer_id in (row.get("read_by_user_ids") or []),
        }
        for row in rows[:4]
    ]


def _public_action(candidate: dict[str, Any]) -> dict[str, str]:
    code = candidate.get("code")
    state = candidate.get("state")
    destination = candidate.get("destination_category")
    if (
        code not in ACTION_CODES
        or state not in ACTION_STATES
        or destination not in DESTINATION_CATEGORIES
    ):
        return {
            "code": "open_family_home",
            "state": "available",
            "destination_category": "family_home",
        }
    result = {
        "code": code,
        "state": state,
        "destination_category": destination,
    }
    if candidate.get("action_reference"):
        result["action_reference"] = str(candidate["action_reference"])
    return result


def build_today_projection(
    *,
    viewer_role: str,
    lifecycle_state: str,
    candidates: list[dict[str, Any]],
    recent_changes: list[dict[str, Any]],
    milestone_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Choose exactly one primary action and at most three stable secondaries."""
    priority = (
        ORGANIZER_PRIORITY if viewer_role in {"organizer", "host"} else MEMBER_PRIORITY
    )
    priority_index = {code: position for position, code in enumerate(priority)}
    valid = [
        candidate for candidate in candidates if candidate.get("code") in priority_index
    ]
    valid.sort(
        key=lambda item: (
            priority_index[item["code"]],
            str(item.get("tie_breaker") or ""),
            str(item.get("action_reference") or ""),
        )
    )

    chosen: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for candidate in valid:
        if candidate["code"] in seen_codes:
            continue
        seen_codes.add(candidate["code"])
        chosen.append(_public_action(candidate))
        if len(chosen) == 4:
            break
    if not chosen:
        chosen = [
            _public_action(
                {
                    "code": "open_family_home",
                    "state": "available",
                    "destination_category": "family_home",
                }
            )
        ]

    if lifecycle_state == "provisional":
        navigation = ["today", "family_activation", "gatherings"]
    elif viewer_role in {"organizer", "host"}:
        navigation = ["today", "gatherings", "proposals", "activity"]
    else:
        navigation = ["today", "gatherings", "proposals", "activity"]

    milestones = [code for code in (milestone_codes or []) if code in MILESTONE_CODES]
    return {
        "viewer_role": viewer_role,
        "lifecycle_state": lifecycle_state,
        "primary_action_code": chosen[0]["code"],
        "primary_action": chosen[0],
        "secondary_actions": chosen[1:4],
        "recent_changes": recent_changes[:4],
        "navigation_categories": [
            item for item in navigation if item in NAVIGATION_CATEGORIES
        ],
        "milestone_codes": list(dict.fromkeys(milestones))[:2],
        "refresh_state": "current",
    }
