"""Content-free policy helpers for guest-to-family-member continuity."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from organizer_command_center import invitation_is_active

REQUEST_STATES = {
    "pending",
    "approved",
    "declined",
    "cancelled",
    "expired",
    "conflict",
}
TERMINAL_STATES = REQUEST_STATES - {"pending"}


def parse_instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_expired(value: Any, *, now: datetime | None = None) -> bool:
    parsed = parse_instant(value)
    return not parsed or parsed <= (now or datetime.now(timezone.utc))


def invitation_relationship_fingerprint(event_id: str, invite: dict[str, Any]) -> str:
    """Identify one durable invite relationship across credential replacement.

    Email is included only as an internal collision-resistant attribute. Possession
    of the invitation and continuity credentials remains the authorization proof.
    """
    parts = (
        event_id,
        str(invite.get("created_at") or ""),
        str(invite.get("invite_source") or ""),
        str(invite.get("email") or "").strip().casefold(),
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def find_relationship_invite(event: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    matches = [
        invite
        for invite in event.get("event_invites") or []
        if invitation_relationship_fingerprint(str(event.get("id") or ""), invite)
        == fingerprint
    ]
    if len(matches) != 1:
        return None
    return matches[0] if invitation_is_active(matches[0]) else None


def safe_status_projection(request: dict[str, Any], community_name: str = "") -> dict[str, Any]:
    status = request.get("status") if request.get("status") in REQUEST_STATES else "conflict"
    next_actions = {
        "pending": ["wait_for_organizer", "cancel_request"],
        "approved": ["open_family_home"],
        "declined": ["return_to_reunion"],
        "cancelled": ["return_to_reunion"],
        "expired": ["request_fresh_invitation"],
        "conflict": ["contact_organizer"],
    }
    result = {
        "status": status,
        "revision": max(0, int(request.get("revision", 0) or 0)),
        "next_action_codes": next_actions[status],
    }
    if status == "approved" and community_name:
        result["family_space_name"] = community_name
    return result


def safe_organizer_projection(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_reference": str(request.get("public_reference") or ""),
        "applicant_name": str(request.get("applicant_name") or "Family guest")[:80],
        "status": request.get("status") if request.get("status") in REQUEST_STATES else "conflict",
        "revision": max(0, int(request.get("revision", 0) or 0)),
        "requested_at": str(request.get("created_at") or ""),
    }
