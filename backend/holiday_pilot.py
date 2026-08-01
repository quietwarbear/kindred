"""Privacy-safe readiness policy for the holiday-meal pilot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from itinerary import parse_local_datetime, valid_timezone
from organizer_command_center import invitation_is_active

HOLIDAY_PILOT_CONFIRMATION_CODES = frozenset(
    {
        "guest_plan_reviewed",
        "invitations_shared",
        "organizer_previewed",
        "privacy_reviewed",
        "reminder_plan_reviewed",
    }
)

REQUIRED_SETUP_CODES = (
    "essential_details",
    "schedule_and_timezone",
    "rsvp_window",
    "privacy_reviewed",
    "guest_plan_reviewed",
    "organizer_previewed",
)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _confirmation_codes(event: dict[str, Any]) -> set[str]:
    return {
        value
        for value in event.get("holiday_pilot_confirmations", [])
        if value in HOLIDAY_PILOT_CONFIRMATION_CODES
    }


def _has_delivery_evidence(invite: dict[str, Any]) -> bool:
    return bool(
        invite.get("delivered_at")
        or invite.get("delivery_verified_at")
        or invite.get("opened_at")
        or invite.get("shared_at")
        or invite.get("link_copied_at")
        or invite.get("rsvp_status", "pending") != "pending"
    )


def _was_shared(invite: dict[str, Any]) -> bool:
    return bool(invite.get("shared_at") or invite.get("link_copied_at"))


def _was_opened(invite: dict[str, Any]) -> bool:
    return bool(invite.get("opened_at"))


def _was_delivered(invite: dict[str, Any]) -> bool:
    return bool(invite.get("delivered_at") or invite.get("delivery_verified_at"))


def _stage(
    event: dict[str, Any],
    confirmations: set[str],
    start: datetime | None,
    end: datetime | None,
    now: datetime,
) -> str:
    if event.get("archived_at"):
        return "archived"
    if event.get("publication_state") == "organizer_draft":
        return "draft"
    if end and now >= _utc(end):
        return "completed"
    if start and now >= _utc(start):
        return "active"
    active_invites = [
        invite
        for invite in event.get("event_invites", [])
        if invitation_is_active(invite)
    ]
    if "invitations_shared" in confirmations or any(
        _has_delivery_evidence(invite) for invite in active_invites
    ):
        return "invitations_sent"
    return "ready_to_invite"


def build_holiday_pilot_readiness(
    event: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    """Return bounded categories and counts, never organizer or guest content."""
    if event.get("event_template") != "holiday_meal":
        return {}

    current = _utc(now or datetime.now(timezone.utc))
    timezone_name = event.get("timezone", "")
    timezone_ok = valid_timezone(timezone_name)
    start = (
        parse_local_datetime(event.get("start_at", ""), timezone_name)
        if timezone_ok
        else None
    )
    end = (
        parse_local_datetime(event.get("end_at", ""), timezone_name)
        if timezone_ok
        else None
    )
    deadline = (
        parse_local_datetime(event.get("rsvp_deadline", ""), timezone_name)
        if timezone_ok
        else None
    )
    confirmations = _confirmation_codes(event)
    active_invites = [
        invite
        for invite in event.get("event_invites", [])
        if invitation_is_active(invite)
    ]
    responses = [
        invite
        for invite in active_invites
        if invite.get("rsvp_status", "pending") != "pending"
    ]
    volunteer_need = sum(
        max(0, int(slot.get("needed_count", 0) or 0))
        for slot in event.get("volunteer_slots", [])
        if isinstance(slot, dict)
    )

    checks = {
        "essential_details": bool(
            str(event.get("title", "")).strip()
            and str(event.get("location", "")).strip()
            and int(event.get("max_attendees", 0) or 0) > 0
        ),
        "schedule_and_timezone": bool(
            timezone_ok and start and end and _utc(end) > _utc(start)
        ),
        "rsvp_window": bool(deadline and start and _utc(deadline) <= _utc(start)),
        "privacy_reviewed": "privacy_reviewed" in confirmations,
        "guest_plan_reviewed": "guest_plan_reviewed" in confirmations,
        "food_coordination": bool(
            event.get("potluck_items") or event.get("volunteer_slots")
        ),
        "reminder_plan_reviewed": "reminder_plan_reviewed" in confirmations,
        "organizer_previewed": "organizer_previewed" in confirmations,
        "invitations_shared": bool(
            active_invites
            and (
                "invitations_shared" in confirmations
                or any(_has_delivery_evidence(invite) for invite in active_invites)
            )
        ),
    }
    checklist = [
        {
            "code": code,
            "status": "complete" if complete else "incomplete",
            "required_for_setup": code in REQUIRED_SETUP_CODES,
            "confirmation_action": (
                code if code in HOLIDAY_PILOT_CONFIRMATION_CODES else None
            ),
        }
        for code, complete in checks.items()
    ]
    incomplete_required = [code for code in REQUIRED_SETUP_CODES if not checks[code]]
    stage = _stage(event, confirmations, start, end, current)
    if incomplete_required:
        next_action = incomplete_required[0]
    elif stage == "draft":
        next_action = "finish_setup"
    elif not active_invites:
        next_action = "prepare_invitations"
    elif not checks["invitations_shared"]:
        next_action = "share_invitations"
    elif len(responses) < len(active_invites):
        next_action = "review_response_gaps"
    elif stage in {"completed", "archived"}:
        next_action = "review_recap"
    else:
        next_action = "review_pilot"

    return {
        "pilot_stage": stage,
        "can_finish_setup": not incomplete_required,
        "required_complete_count": len(REQUIRED_SETUP_CODES) - len(incomplete_required),
        "required_total_count": len(REQUIRED_SETUP_CODES),
        "next_action_code": next_action,
        "checklist": checklist,
        "aggregate_counts": {
            "active_invitations": min(len(active_invites), 10_000),
            "invitations_shared": min(
                sum(1 for invite in active_invites if _was_shared(invite)), 10_000
            ),
            "invitations_opened": min(
                sum(1 for invite in active_invites if _was_opened(invite)), 10_000
            ),
            "invitations_delivered": min(
                sum(1 for invite in active_invites if _was_delivered(invite)), 10_000
            ),
            "responses_received": min(len(responses), 10_000),
            "potluck_items": min(len(event.get("potluck_items", [])), 10_000),
            "volunteer_positions": min(volunteer_need, 10_000),
        },
    }
