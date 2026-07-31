"""Deterministic, aggregate-only reunion command-center derivation.

This module intentionally contains no analytics or logging. Returned values are
limited to counts, timestamps, categorical states, and stable action codes.
Recipient-facing details remain in explicitly authorized invitation surfaces.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from itinerary import parse_local_datetime, published_activities, valid_timezone

RESPONSE_STATUSES = ("going", "some", "maybe", "not-going", "pending")
INACTIVE_INVITATION_STATES = {
    "expired",
    "revoked",
    "rotated",
    "superseded",
}
APPROACHING_WINDOW = timedelta(days=14)
NEAR_EVENT_WINDOW = timedelta(days=14)


def _normalized_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _parsed_instant(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def invitation_is_active(
    invite: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether one invitation represents a currently usable response."""
    now = now or datetime.now(timezone.utc)
    states = {
        str(invite.get(field) or "").strip().lower()
        for field in ("status", "credential_state", "rotation_state")
    }
    if states & INACTIVE_INVITATION_STATES:
        return False
    if invite.get("revoked_at") or invite.get("superseded_at"):
        return False
    expires_at = _parsed_instant(invite.get("expires_at"))
    return not expires_at or expires_at > now


def canonical_response_summary(
    event: dict[str, Any],
    *,
    member_ids_by_email: dict[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reconcile invitation and RSVP state without merging unrelated guests."""
    member_ids_by_email = {
        _normalized_email(email): member_id
        for email, member_id in (member_ids_by_email or {}).items()
        if _normalized_email(email) and member_id
    }
    active_invites = [
        invite
        for invite in event.get("event_invites", [])
        if invite.get("id") and invitation_is_active(invite, now=now)
    ]

    aliases: dict[str, str] = {}
    invite_by_identity: dict[str, dict[str, Any]] = {}
    for invite in active_invites:
        invite_id = str(invite["id"])
        member_id = str(invite.get("member_id") or "")
        if not member_id and invite.get("invite_source") == "member":
            member_id = member_ids_by_email.get(
                _normalized_email(invite.get("email")),
                "",
            )
        identity = f"member:{member_id}" if member_id else f"invite:{invite_id}"
        aliases[f"invite:{invite_id}"] = identity
        if member_id:
            aliases[member_id] = identity
        existing = invite_by_identity.get(identity)
        if not existing or str(invite.get("created_at") or "") >= str(
            existing.get("created_at") or ""
        ):
            invite_by_identity[identity] = invite

    records_by_identity: dict[str, dict[str, Any]] = {}
    for record in event.get("rsvp_records", []):
        record_id = str(record.get("user_id") or "")
        identity = aliases.get(record_id)
        if not identity or identity not in invite_by_identity:
            continue
        existing = records_by_identity.get(identity)
        if not existing or str(record.get("updated_at") or "") >= str(
            existing.get("updated_at") or ""
        ):
            records_by_identity[identity] = record

    counts = {status: 0 for status in RESPONSE_STATUSES}
    responded = 0
    for identity, invite in invite_by_identity.items():
        record = records_by_identity.get(identity)
        status_value = (
            (record or {}).get("status") or invite.get("rsvp_status") or "pending"
        )
        status_value = status_value if status_value in RESPONSE_STATUSES else "pending"
        counts[status_value] += 1
        if status_value != "pending":
            responded += 1

    total = len(invite_by_identity)
    return {
        "total": total,
        "responded": responded,
        "missing": counts["pending"],
        "counts": counts,
        "reconciles": total == sum(counts.values()),
    }


def deadline_summary(
    event: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Classify event/activity deadlines using their intended timezone."""
    now = now or datetime.now(timezone.utc)
    timezone_name = event.get("timezone", "UTC")
    candidates: list[dict[str, str]] = []
    if event.get("rsvp_deadline"):
        candidates.append(
            {
                "kind": "overall_rsvp",
                "value": str(event["rsvp_deadline"]),
                "timezone": str(timezone_name),
            }
        )
    for activity in event.get("agenda", []):
        if activity.get("visibility") == "archived":
            continue
        if activity.get("rsvp_deadline"):
            candidates.append(
                {
                    "kind": "activity_rsvp",
                    "value": str(activity["rsvp_deadline"]),
                    "timezone": str(activity.get("timezone") or timezone_name),
                }
            )

    valid: list[tuple[datetime, dict[str, str]]] = []
    invalid_count = 0
    for candidate in candidates:
        parsed = parse_local_datetime(
            candidate["value"],
            candidate["timezone"],
        )
        if not parsed:
            invalid_count += 1
            continue
        valid.append((parsed, candidate))
    valid.sort(key=lambda item: item[0])
    upcoming = [item for item in valid if item[0] >= now]
    approaching = [item for item in upcoming if item[0] - now <= APPROACHING_WINDOW]
    next_deadline = upcoming[0] if upcoming else None
    return {
        "total": len(candidates),
        "valid": len(valid),
        "invalid": invalid_count,
        "expired": sum(1 for instant, _ in valid if instant < now),
        "approaching": len(approaching),
        "next": (
            {
                "kind": next_deadline[1]["kind"],
                "at": next_deadline[0].isoformat(),
            }
            if next_deadline
            else None
        ),
    }


def _completion_status(done: int, total: int) -> dict[str, Any]:
    if total <= 0:
        return {"status": "not_started", "done": 0, "total": 0}
    if done <= 0:
        status = "not_started"
    elif done >= total:
        status = "complete"
    else:
        status = "in_progress"
    return {"status": status, "done": min(done, total), "total": total}


def planning_progress(
    event: dict[str, Any],
    *,
    travel_plans: list[dict[str, Any]],
    budgets: list[dict[str, Any]],
    planning_team_assigned: int,
    planning_team_pending: int,
) -> dict[str, Any]:
    """Return honest progress; absent records never become fabricated success."""
    agenda = [
        item for item in event.get("agenda", []) if item.get("visibility") != "archived"
    ]
    published = published_activities(event)
    potluck = event.get("potluck_items", [])
    volunteers = event.get("volunteer_slots", [])
    roles = event.get("event_role_assignments", [])
    checklist = event.get("planning_checklist", [])
    travel_started = bool(
        travel_plans or str(event.get("travel_coordination_notes") or "").strip()
    )
    budget_for_event = [
        budget for budget in budgets if budget.get("event_id") == event.get("id")
    ]
    return {
        "itinerary": _completion_status(len(published), len(agenda)),
        "checklist": _completion_status(
            sum(1 for item in checklist if item.get("completed")),
            len(checklist),
        ),
        "potluck": _completion_status(
            sum(1 for item in potluck if item.get("assigned_to")),
            len(potluck),
        ),
        "volunteer_roles": _completion_status(
            sum(
                min(
                    len(slot.get("assigned_members", [])),
                    max(1, int(slot.get("needed_count", 1) or 1)),
                )
                for slot in volunteers
            ),
            sum(max(1, int(slot.get("needed_count", 1) or 1)) for slot in volunteers),
        ),
        "event_roles": _completion_status(
            sum(1 for item in roles if item.get("assignees")),
            len(roles),
        ),
        "travel": {
            "status": "in_progress" if travel_started else "not_started",
            "plans": len(travel_plans),
        },
        "budget": (
            {
                "status": (
                    "complete"
                    if all(
                        float(item.get("current_amount", 0) or 0)
                        >= float(item.get("target_amount", 0) or 0)
                        for item in budget_for_event
                    )
                    else "in_progress"
                ),
                "plans": len(budget_for_event),
            }
            if budget_for_event
            else None
        ),
        "planning_team": {
            "status": (
                "active"
                if planning_team_assigned
                else "invited" if planning_team_pending else "not_started"
            ),
            "assigned": planning_team_assigned,
            "pending_invitations": planning_team_pending,
        },
    }


def next_best_action(
    event: dict[str, Any],
    *,
    responses: dict[str, Any],
    deadlines: dict[str, Any],
    progress: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return exactly one stable action using the documented priority order."""
    now = now or datetime.now(timezone.utc)
    details_missing = (
        not str(event.get("title") or "").strip()
        or not parse_local_datetime(
            str(event.get("start_at") or ""),
            str(event.get("timezone") or "UTC"),
        )
        or not valid_timezone(str(event.get("timezone") or ""))
        or not str(event.get("location") or "").strip()
    )
    if details_missing:
        return {"code": "complete_reunion_details", "count": 1}
    if progress["itinerary"]["status"] != "complete":
        return {
            "code": "confirm_itinerary",
            "count": max(
                1,
                progress["itinerary"]["total"] - progress["itinerary"]["done"],
            ),
        }
    if responses["total"] == 0:
        return {"code": "create_first_invitation", "count": 1}
    invitation_evidence = any(
        (invite.get("rsvp_status") or "pending") != "pending"
        or invite.get("opened_at")
        or invite.get("delivery_verified_at")
        or invite.get("shared_at")
        for invite in event.get("event_invites", [])
        if invitation_is_active(invite, now=now)
    )
    if not invitation_evidence:
        return {"code": "share_invitations", "count": responses["total"]}
    if deadlines["approaching"] and responses["missing"]:
        return {
            "code": "resolve_approaching_deadline",
            "count": responses["missing"],
        }
    if responses["missing"]:
        return {"code": "follow_up_missing_responses", "count": responses["missing"]}
    if progress["event_roles"]["status"] != "complete":
        return {
            "code": "fill_planning_roles",
            "count": max(
                1,
                progress["event_roles"]["total"] - progress["event_roles"]["done"],
            ),
        }
    contribution_gap = max(
        0, progress["potluck"]["total"] - progress["potluck"]["done"]
    ) + max(
        0,
        progress["volunteer_roles"]["total"] - progress["volunteer_roles"]["done"],
    )
    if contribution_gap:
        return {"code": "resolve_contribution_gaps", "count": contribution_gap}
    event_start = parse_local_datetime(
        str(event.get("start_at") or ""),
        str(event.get("timezone") or "UTC"),
    )
    if (
        progress["travel"]["status"] == "not_started"
        and event_start
        and now <= event_start <= now + timedelta(days=30)
    ):
        return {"code": "review_travel_gaps", "count": 1}
    if event_start and now <= event_start <= now + NEAR_EVENT_WINDOW:
        return {"code": "prepare_story_prompts", "count": 1}
    return {"code": "review_reunion_plan", "count": 1}


def build_command_center(
    event: dict[str, Any],
    *,
    member_ids_by_email: dict[str, str],
    travel_plans: list[dict[str, Any]],
    budgets: list[dict[str, Any]],
    planning_team_assigned: int,
    planning_team_pending: int,
    recent_changes: list[dict[str, str]],
    reminder_preflight: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    responses = canonical_response_summary(
        event,
        member_ids_by_email=member_ids_by_email,
        now=now,
    )
    deadlines = deadline_summary(event, now=now)
    progress = planning_progress(
        event,
        travel_plans=travel_plans,
        budgets=budgets,
        planning_team_assigned=planning_team_assigned,
        planning_team_pending=planning_team_pending,
    )
    action = next_best_action(
        event,
        responses=responses,
        deadlines=deadlines,
        progress=progress,
        now=now,
    )
    return {
        "event_timezone": event.get("timezone", "UTC"),
        "next_action": action,
        "responses": responses,
        "deadlines": deadlines,
        "progress": progress,
        "reminders": reminder_preflight,
        "recent_changes": recent_changes[:8],
        "guest_preview_available": True,
    }
