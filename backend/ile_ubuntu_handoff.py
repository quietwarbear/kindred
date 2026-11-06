"""X2: send an event's attendees to Ile Ubuntu after it ends.

The organizer maps each activity to an Ile Ubuntu course once. Sending then
hands Ile Ubuntu every registered person who was marked "coming" for at least
one mapped activity, with the courses for those activities. Ile Ubuntu runs
its roster import (idempotent: a resend only adds what's new), creates invited
accounts, enrolls people and emails each a sign-in link, then returns a
report that Kindred shows the organizer. No shared login.

Authorization on the Ile Ubuntu side has two parts:
- every request is signed with a secret both servers hold
  (ILE_UBUNTU_HANDOFF_SECRET here, KINDRED_HANDOFF_SECRET there), and
- it carries a connection key that the course's teacher issued in Ile Ubuntu
  and gave the organizer. The import runs as that teacher, so it can only
  reach courses they teach.

The connection key is a credential, so it is kept in its own collection
(``ile_ubuntu_handoff_connections``), never on the event document, which
organizers and co-hosts can read in full. Responses show its last four
characters only.

What is sent: name, email and course ids, nothing else. People with no email
on file, and people not marked coming for any mapped activity, are left out
and counted in the report.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from itinerary import parse_local_datetime
from organizer_command_center import (
    _active_invite_identities,
    _activity_ended,
    _latest_activity_responses,
)

SIGNATURE_VERSION = "v1"
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_ATTENDEES = 5000
KEY_PREFIX = "kh_"


class HandoffError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def handoff_settings() -> tuple[str, str]:
    base = os.environ.get("ILE_UBUNTU_API_URL", "").strip().rstrip("/")
    secret = os.environ.get("ILE_UBUNTU_HANDOFF_SECRET", "").strip()
    return base, secret


def handoff_configured() -> bool:
    base, secret = handoff_settings()
    return bool(base and secret)


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Same format Ile Ubuntu verifies (backend/kindred_handoff.py there)."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"{SIGNATURE_VERSION}={mac.hexdigest()}"


def valid_key_shape(key: Any) -> bool:
    return isinstance(key, str) and key.startswith(KEY_PREFIX) and 10 < len(key) <= 200


def event_has_ended(event: dict[str, Any], now: datetime | None = None) -> bool:
    """The event's end (or start) has passed, or every activity has ended."""
    now = now or datetime.now(timezone.utc)
    tz = str(event.get("timezone") or "UTC")
    for key in ("end_at", "start_at"):
        value = str(event.get(key) or "")
        if value:
            instant = parse_local_datetime(value, tz)
            if instant:
                return instant < now
            break
    activities = [a for a in event.get("agenda", []) if a.get("visibility") != "archived"]
    return bool(activities) and all(_activity_ended(a, tz, now) for a in activities)


def clean_course_map(event: dict[str, Any], course_map: Any) -> dict[str, str]:
    """Keep only current activities mapped to a plausible course id."""
    if not isinstance(course_map, dict):
        return {}
    activity_ids = {str(a.get("id")) for a in event.get("agenda", []) if a.get("id")}
    return {
        str(activity_id): str(course_id).strip()[:128]
        for activity_id, course_id in course_map.items()
        if str(activity_id) in activity_ids and isinstance(course_id, str) and course_id.strip()
    }


def handoff_attendees(
    event: dict[str, Any],
    course_map: dict[str, str],
    *,
    members_by_id: dict[str, dict[str, Any]],
    member_ids_by_email: dict[str, str] | None = None,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Who to send and to which courses. Returns ``(attendees, counts)``."""
    aliases, invite_by_identity = _active_invite_identities(
        event, member_ids_by_email=member_ids_by_email, now=now
    )
    latest = _latest_activity_responses(event, aliases)
    coming: dict[str, list[str]] = {}
    for (activity_id, identity), row in latest.items():
        if str(row.get("status") or "") == "coming" and activity_id in course_map:
            coming.setdefault(identity, []).append(activity_id)

    attendees: list[dict[str, Any]] = []
    counts = {"people_coming": 0, "no_email": 0, "not_registered": 0}
    order = {str(a.get("id")): i for i, a in enumerate(event.get("agenda", []))}
    for identity, activity_ids in coming.items():
        counts["people_coming"] += 1
        invite = invite_by_identity.get(identity)
        member_id = ""
        if identity.startswith("member:"):
            member_id = identity.split(":", 1)[1]
        elif identity.startswith("respondent:") and identity[len("respondent:"):] in members_by_id:
            member_id = identity[len("respondent:"):]
        member = members_by_id.get(member_id) or {}
        if not invite and not member:
            # Answered on an invitation that is no longer active.
            counts["not_registered"] += 1
            continue
        email = str((invite or {}).get("email") or member.get("email") or "").strip()
        if not email:
            counts["no_email"] += 1
            continue
        name = str((invite or {}).get("invitee_name") or member.get("full_name") or "").strip()
        course_ids: list[str] = []
        for activity_id in sorted(activity_ids, key=lambda a: order.get(a, 0)):
            course_id = course_map[activity_id]
            if course_id not in course_ids:
                course_ids.append(course_id)
        attendees.append({"name": name, "email": email, "course_ids": course_ids})
    attendees.sort(key=lambda a: a["email"].lower())
    counts["sending"] = len(attendees)
    return attendees, counts


async def call_ile_ubuntu(path: str, payload: dict[str, Any], *, transport=None) -> dict[str, Any]:
    base, secret = handoff_settings()
    if not base or not secret:
        raise HandoffError(503, "handoff_not_configured", "Sending to Ile Ubuntu isn't set up on this server yet.")
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-Handoff-Timestamp": timestamp,
        "X-Handoff-Signature": sign(secret, timestamp, body),
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.post(f"{base}/api/kindred-handoff/{path}", content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise HandoffError(502, "ile_ubuntu_unreachable", "Ile Ubuntu didn't respond. Try again in a minute.") from exc
    if response.status_code == 403:
        raise HandoffError(
            403,
            "connection_key_invalid",
            "Ile Ubuntu didn't accept the connection key. Ask the course's teacher for a new one.",
        )
    if response.status_code in (401, 503):
        raise HandoffError(502, "handoff_not_configured", "Ile Ubuntu isn't set up to receive from Kindred yet.")
    if response.status_code == 429:
        raise HandoffError(429, "ile_ubuntu_busy", "Ile Ubuntu is busy. Try again in a few minutes.")
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        message = detail if isinstance(detail, str) else "Ile Ubuntu couldn't process this request."
        raise HandoffError(502, "ile_ubuntu_error", message)
    try:
        return response.json()
    except ValueError as exc:
        raise HandoffError(502, "ile_ubuntu_error", "Ile Ubuntu sent an unreadable reply.") from exc
