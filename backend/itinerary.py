"""Pure helpers for backward-compatible gathering itineraries.

Existing agenda rows only contain ``time_label``, ``title``, and ``notes``.
Structured reunion activities add fields without invalidating those rows.
Attendance is stored separately on the event so activity edits never erase
response history.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone as datetime_timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ACTIVITY_RESPONSES = {"coming", "not-coming", "maybe"}
OVERALL_RESPONSES = {"going", "some", "maybe", "not-going"}

# Organizer-defined attendance options per activity (for example "In person"
# and "Remote"). A choice is stored on the response row, never on the activity.
MAX_RESPONSE_CHOICES = 6
MAX_RESPONSE_CHOICE_LENGTH = 60
# Statuses that may carry a choice. "not-coming" never does.
CHOICE_STATUSES = {"coming", "maybe"}

# Shown in place of an activity's virtual link to anyone who has not answered
# "coming" for that activity.
VIRTUAL_LINK_WITHHELD_NOTICE = "Link shared with registered attendees."


def normalize_response_choices(value: Any) -> list[str]:
    """Return trimmed, de-duplicated, bounded organizer choice labels."""
    if not isinstance(value, (list, tuple)):
        return []
    choices: list[str] = []
    seen: set[str] = set()
    for item in value:
        label = " ".join(str(item or "").split())[:MAX_RESPONSE_CHOICE_LENGTH]
        key = label.casefold()
        if not label or key in seen:
            continue
        seen.add(key)
        choices.append(label)
        if len(choices) >= MAX_RESPONSE_CHOICES:
            break
    return choices


def resolve_response_choice(
    activity: dict[str, Any], status: str, choice: Any
) -> str:
    """Validate one submitted choice against the activity's current options.

    Returns the canonical label ("" when no choice applies). Raises
    ``ValueError`` when a choice is supplied that the activity does not offer.
    """
    label = " ".join(str(choice or "").split())
    if not label or status not in CHOICE_STATUSES:
        return ""
    for option in activity.get("response_choices") or []:
        if option.casefold() == label.casefold():
            return option
    raise ValueError("invalid_response_choice")


def effective_response_choice(
    activity: dict[str, Any],
    status: str,
    submitted: str | None,
    previous: str = "",
) -> str:
    """Resolve the choice to store for one response.

    ``submitted=None`` means the client did not send a choice (an older app
    build): keep the previous one if it is still offered, else drop it. An
    explicitly submitted choice must be offered, or ``ValueError`` is raised.
    """
    if submitted is None:
        try:
            return resolve_response_choice(activity, status, previous)
        except ValueError:
            return ""
    return resolve_response_choice(activity, status, submitted)


def activity_response_close_at(
    activity: dict[str, Any], event_timezone: str = "UTC"
) -> tuple[datetime | None, bool]:
    """Return ``(close_at, invalid)`` for an activity's response window.

    The organizer's RSVP deadline wins. Without one, responses close when the
    activity ends. ``invalid`` is true only when an explicit deadline cannot be
    parsed, which callers treat as closed (fail closed, as before).
    """
    timezone_name = activity.get("timezone") or event_timezone or "UTC"
    deadline_value = str(activity.get("rsvp_deadline") or "")
    if deadline_value:
        deadline = parse_local_datetime(deadline_value, timezone_name)
        return deadline, deadline is None
    end_value = str(activity.get("end_at") or "")
    if end_value:
        return parse_local_datetime(end_value, timezone_name), False
    return None, False


def activity_response_open(
    activity: dict[str, Any],
    event_timezone: str = "UTC",
    *,
    now: datetime | None = None,
) -> bool:
    close_at, invalid = activity_response_close_at(activity, event_timezone)
    if invalid:
        return False
    if close_at is None:
        return True
    current = now or datetime.now(datetime_timezone.utc)
    return current <= close_at


def own_activity_responses(
    event: dict[str, Any], aliases: set[str]
) -> dict[str, dict[str, Any]]:
    """Return the respondent's latest response row per activity."""
    latest: dict[str, dict[str, Any]] = {}
    for row in event.get("activity_rsvps", []):
        activity_id = row.get("activity_id")
        if not activity_id or row.get("respondent_id") not in aliases:
            continue
        existing = latest.get(activity_id)
        if not existing or str(row.get("updated_at") or "") >= str(
            existing.get("updated_at") or ""
        ):
            latest[activity_id] = row
    return latest


def can_view_activity_link(my_status: str, *, privileged: bool) -> bool:
    return privileged or my_status == "coming"


def activity_link_fields(
    activity: dict[str, Any], my_status: str, *, privileged: bool
) -> dict[str, Any]:
    """Return the virtual-link fields a given viewer may see for one activity."""
    link = str(activity.get("virtual_link") or "")
    if not link or can_view_activity_link(my_status, privileged=privileged):
        return {
            "virtual_link": link,
            "virtual_link_withheld": False,
            "virtual_link_notice": "",
        }
    return {
        "virtual_link": "",
        "virtual_link_withheld": True,
        "virtual_link_notice": VIRTUAL_LINK_WITHHELD_NOTICE,
    }


def is_event_link_privileged(event: dict[str, Any], user: dict[str, Any]) -> bool:
    """Organizers and the event's planning team see every activity link."""
    if user.get("role") in {"host", "organizer"}:
        return True
    user_id = user.get("id")
    return bool(user_id) and user_id in (event.get("planning_team_member_ids") or [])


def safe_roster_row_key(scope_id: str, respondent_id: str) -> str:
    """Return a stable UI key without exposing member IDs or invite tokens."""
    source = f"{scope_id}:{respondent_id}".encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:24]


def valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value or "UTC")
        return True
    except ZoneInfoNotFoundError:
        return False


def parse_local_datetime(value: str, timezone: str = "UTC") -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        zone = ZoneInfo(timezone or "UTC")
        if parsed.tzinfo is not None:
            return parsed.astimezone(zone)

        candidates = []
        for fold in (0, 1):
            candidate = parsed.replace(tzinfo=zone, fold=fold)
            round_trip = candidate.astimezone(datetime_timezone.utc).astimezone(zone)
            if round_trip.replace(tzinfo=None) == parsed:
                candidates.append(candidate)
        unique_offsets = {candidate.utcoffset() for candidate in candidates}
        if len(unique_offsets) != 1:
            # No candidates means a nonexistent wall time. Multiple offsets mean
            # an ambiguous fall-back time; require an explicit ISO offset.
            return None
        return candidates[0]
    except (ValueError, ZoneInfoNotFoundError):
        return None


def normalize_activity(source: dict[str, Any], *, activity_id: str) -> dict[str, Any]:
    """Normalize a structured activity while accepting legacy agenda keys."""
    start_at = str(source.get("start_at") or "").strip()
    end_at = str(source.get("end_at") or "").strip()
    timezone = str(source.get("timezone") or "").strip()
    capacity = source.get("capacity")
    try:
        capacity = int(capacity) if capacity not in (None, "") else None
    except (TypeError, ValueError):
        capacity = None
    return {
        "id": activity_id,
        "time_label": str(source.get("time_label") or "").strip()[:80],
        "title": str(source.get("title") or "").strip()[:160],
        "description": str(source.get("description") or "").strip()[:2000],
        "start_at": start_at,
        "end_at": end_at,
        "timezone": timezone,
        "venue_name": str(source.get("venue_name") or "").strip()[:160],
        "venue_address": str(source.get("venue_address") or "").strip()[:300],
        "venue_detail": str(source.get("venue_detail") or "").strip()[:160],
        "map_url": str(source.get("map_url") or "").strip()[:500],
        "virtual_link": str(source.get("virtual_link") or "").strip()[:500],
        "location_tba": bool(source.get("location_tba", False)),
        "capacity": max(1, capacity) if capacity is not None else None,
        "rsvp_deadline": str(source.get("rsvp_deadline") or "").strip(),
        "response_choices": normalize_response_choices(source.get("response_choices")),
        "attendance_requested": bool(source.get("attendance_requested", True)),
        "notes": str(source.get("notes") or "").strip()[:2000],
        "visibility": source.get("visibility") if source.get("visibility") in {"draft", "published", "archived"} else "draft",
        "featured": bool(source.get("featured", False)),
        "created_at": str(source.get("created_at") or ""),
        "updated_at": str(source.get("updated_at") or ""),
        "revision_history": list(source.get("revision_history") or []),
    }


def validate_activity(activity: dict[str, Any], reunion_timezone: str) -> list[str]:
    errors: list[str] = []
    if not activity.get("title"):
        errors.append("Activity title is required.")
    timezone = activity.get("timezone") or reunion_timezone or "UTC"
    if not valid_timezone(timezone):
        errors.append("Activity timezone is not valid.")
    start = parse_local_datetime(activity.get("start_at", ""), timezone)
    end = parse_local_datetime(activity.get("end_at", ""), timezone)
    if not start:
        errors.append("Activity start date and time are required.")
    if not end:
        errors.append("Activity end date and time are required.")
    if start and end and end <= start:
        errors.append("Activity end must be after its start.")
    deadline_value = activity.get("rsvp_deadline", "")
    if deadline_value and not parse_local_datetime(deadline_value, timezone):
        errors.append(
            "RSVP deadline must be a valid, unambiguous date and time in the activity timezone."
        )
    return errors


def local_day_key(value: str, timezone_name: str = "UTC") -> str:
    parsed = parse_local_datetime(value, timezone_name)
    if not parsed:
        return ""
    return parsed.astimezone(ZoneInfo(timezone_name or "UTC")).date().isoformat()


def published_activities(event: dict[str, Any]) -> list[dict[str, Any]]:
    activities = [
        item for item in event.get("agenda", [])
        if item.get("visibility") == "published" and item.get("start_at")
    ]
    return sorted(activities, key=lambda item: (item.get("start_at", ""), item.get("title", "")))


def activity_response_summary(
    activity_id: str,
    responses: list[dict[str, Any]],
    invite_count: int = 0,
) -> dict[str, int]:
    relevant = [item for item in responses if item.get("activity_id") == activity_id]
    coming = sum(1 for item in relevant if item.get("status") == "coming")
    maybe = sum(1 for item in relevant if item.get("status") == "maybe")
    declined = sum(1 for item in relevant if item.get("status") == "not-coming")
    party_size = sum(
        max(1, int(item.get("party_size", 1) or 1))
        for item in relevant if item.get("status") == "coming"
    )
    return {
        "coming": coming,
        "maybe": maybe,
        "not_coming": declined,
        "no_response": max(0, invite_count - len(relevant)),
        "party_size": party_size,
    }


def canonical_activity_responses(event: dict[str, Any]) -> list[dict[str, Any]]:
    alias_map = {
        f"invite:{invite.get('id')}": invite.get("member_id")
        for invite in event.get("event_invites", [])
        if invite.get("id") and invite.get("member_id")
    }
    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for index, response in enumerate(event.get("activity_rsvps", [])):
        respondent_id = response.get("respondent_id", "")
        canonical_id = alias_map.get(
            respondent_id,
            respondent_id or f"legacy-anonymous:{index}",
        )
        key = (response.get("activity_id", ""), canonical_id)
        candidate = {**response, "respondent_id": canonical_id}
        existing = deduplicated.get(key)
        if not existing or candidate.get("updated_at", "") >= existing.get("updated_at", ""):
            deduplicated[key] = candidate
    return list(deduplicated.values())


def activity_summaries(event: dict[str, Any]) -> dict[str, dict[str, int]]:
    responses = canonical_activity_responses(event)
    invite_count = len(event.get("event_invites", []))
    return {
        activity.get("id", ""): activity_response_summary(
            activity.get("id", ""),
            responses,
            invite_count if activity.get("attendance_requested", True) else 0,
        )
        for activity in event.get("agenda", [])
        if activity.get("id")
    }


def activity_choice_summaries(event: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Count coming/maybe respondents per organizer choice, per activity.

    Only choices the activity currently offers are counted; a response whose
    choice was later removed by the organizer falls into ``unspecified``.
    """
    responses = canonical_activity_responses(event)
    result: dict[str, dict[str, Any]] = {}
    for activity in event.get("agenda", []):
        activity_id = activity.get("id")
        choices = list(activity.get("response_choices") or [])
        if not activity_id or not choices:
            continue
        counts = {
            label: {"coming": 0, "maybe": 0, "party_size": 0} for label in choices
        }
        unspecified = {"coming": 0, "maybe": 0, "party_size": 0}
        for row in responses:
            if row.get("activity_id") != activity_id:
                continue
            status = row.get("status")
            if status not in CHOICE_STATUSES:
                continue
            bucket = counts.get(str(row.get("choice") or ""), unspecified)
            bucket[status] += 1
            if status == "coming":
                bucket["party_size"] += max(1, int(row.get("party_size", 1) or 1))
        result[activity_id] = {"choices": counts, "unspecified": unspecified}
    return result


def derive_overall_suggestion(
    explicit_status: str,
    activity_responses: dict[str, str],
) -> str:
    """Suggest an overall state without overwriting an explicit valid choice."""
    if explicit_status in OVERALL_RESPONSES:
        return explicit_status
    values = list(activity_responses.values())
    if any(value == "coming" for value in values):
        return "some"
    if values and all(value == "not-coming" for value in values):
        return "not-going"
    if any(value == "maybe" for value in values):
        return "maybe"
    return "maybe"


def replace_respondent_activity_responses(
    responses: list[dict[str, Any]],
    respondent_id: str,
    replacements: list[dict[str, Any]],
    respondent_aliases: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Atomically replace one respondent's supplied activity choices."""
    replacement_ids = {
        item.get("activity_id") for item in replacements if item.get("activity_id")
    }
    aliases = {respondent_id, *(respondent_aliases or set())}
    preserved = [
        item for item in responses
        if not (
            item.get("respondent_id") in aliases
            and item.get("activity_id") in replacement_ids
        )
    ]
    return [*preserved, *replacements]


def overlap_pairs(activities: list[dict[str, Any]], reunion_timezone: str) -> list[tuple[str, str]]:
    structured = []
    for activity in activities:
        timezone = activity.get("timezone") or reunion_timezone or "UTC"
        start = parse_local_datetime(activity.get("start_at", ""), timezone)
        end = parse_local_datetime(activity.get("end_at", ""), timezone)
        if start and end:
            structured.append((activity.get("id", ""), start, end))
    overlaps: list[tuple[str, str]] = []
    for index, (left_id, left_start, left_end) in enumerate(structured):
        for right_id, right_start, right_end in structured[index + 1:]:
            if left_start < right_end and right_start < left_end:
                overlaps.append((left_id, right_id))
    return overlaps
