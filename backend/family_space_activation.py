"""Deterministic, content-free family-space lifecycle and readiness policy."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from organizer_command_center import invitation_is_active

PROVISIONAL = "provisional"
ACTIVE = "active"
LEGACY_UNCHANGED = "legacy_unchanged"
READINESS_THRESHOLDS = {
    "verified_invitations": 3,
    "accepted_responses": 2,
    "non_host_participants": 1,
}

_SCRIPT_LIKE = re.compile(
    r"(?:<|>|javascript\s*:|data\s*:\s*text/html|on(?:error|load)\s*=)",
    re.IGNORECASE,
)


class FamilySpaceNameError(ValueError):
    """A safe categorical validation error that never includes input text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def community_lifecycle_state(community: dict[str, Any]) -> str:
    """Interpret only explicit durable state; never infer from a display name."""
    value = community.get("lifecycle_state")
    return value if value in {PROVISIONAL, ACTIVE} else LEGACY_UNCHANGED


def public_community_display_name(community: dict[str, Any] | None) -> str:
    """Keep provisional internal names out of unauthenticated surfaces."""
    if community and community_lifecycle_state(community) != PROVISIONAL:
        return str(community.get("name") or "")
    return ""


def normalize_family_space_name(value: str) -> str:
    """Normalize a minimal enduring name or raise a content-free error code."""
    raw = str(value or "")
    if any(unicodedata.category(char).startswith("C") for char in raw):
        raise FamilySpaceNameError("unsupported_characters")
    normalized = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not 2 <= len(normalized) <= 80:
        raise FamilySpaceNameError("invalid_length")
    if _SCRIPT_LIKE.search(normalized):
        raise FamilySpaceNameError("unsafe_markup")
    if not any(unicodedata.category(char)[0] in {"L", "N"} for char in normalized):
        raise FamilySpaceNameError("letters_or_numbers_required")
    return normalized


def elapsed_day_bucket(created_at: Any, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    try:
        created = datetime.fromisoformat(str(created_at or "").replace("Z", "+00:00"))
        if not created.tzinfo:
            created = created.replace(tzinfo=timezone.utc)
        days = max(0, (now - created).days)
    except (TypeError, ValueError):
        return "unknown"
    if days <= 1:
        return "0_1"
    if days <= 7:
        return "2_7"
    if days <= 30:
        return "8_30"
    return "31_plus"


def _normalized_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _event_evidence(
    event: dict[str, Any],
    *,
    member_ids_by_email: dict[str, str],
    host_user_ids: set[str],
    memories: list[dict[str, Any]],
    now: datetime | None,
) -> dict[str, Any]:
    aliases: dict[str, str] = {}
    invite_by_identity: dict[str, dict[str, Any]] = {}
    for invite in event.get("event_invites", []):
        if not invite.get("id") or not invitation_is_active(invite, now=now):
            continue
        invite_id = str(invite["id"])
        member_id = str(invite.get("member_id") or "")
        if not member_id and invite.get("invite_source") == "member":
            member_id = member_ids_by_email.get(
                _normalized_email(invite.get("email")), ""
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

    records: dict[str, dict[str, Any]] = {}
    for record in event.get("rsvp_records", []):
        identity = aliases.get(str(record.get("user_id") or ""))
        if not identity or identity not in invite_by_identity:
            continue
        existing = records.get(identity)
        if not existing or str(record.get("updated_at") or "") >= str(
            existing.get("updated_at") or ""
        ):
            records[identity] = record

    verified = 0
    accepted = 0
    participants: set[str] = set()
    for identity, invite in invite_by_identity.items():
        response = records.get(identity)
        response_status = str(
            (response or {}).get("status") or invite.get("rsvp_status") or "pending"
        )
        has_evidence = bool(
            response_status != "pending"
            or invite.get("opened_at")
            or invite.get("delivery_verified_at")
        )
        if has_evidence:
            verified += 1
        if response_status in {"going", "some"}:
            accepted += 1
        member_id = (
            identity.removeprefix("member:") if identity.startswith("member:") else ""
        )
        if response_status != "pending" and (
            not member_id or member_id not in host_user_ids
        ):
            participants.add(identity)

    for item in event.get("potluck_items", []):
        member_id = str(item.get("assigned_to_id") or "")
        if member_id and member_id not in host_user_ids:
            participants.add(f"member:{member_id}")
    for slot in event.get("volunteer_slots", []):
        for member_id in slot.get("assigned_member_ids") or []:
            if member_id and member_id not in host_user_ids:
                participants.add(f"member:{member_id}")
    for memory in memories:
        if memory.get("event_id") != event.get("id"):
            continue
        member_id = str(memory.get("created_by") or "")
        if (
            member_id
            and member_id not in host_user_ids
            and memory.get("capsule_status", "published") != "draft"
        ):
            participants.add(f"member:{member_id}")

    counts = {
        "verified_invitations": verified,
        "accepted_responses": accepted,
        "non_host_participants": len(participants),
    }
    met = sum(
        counts[key] >= threshold for key, threshold in READINESS_THRESHOLDS.items()
    )
    return {
        "counts": counts,
        "ready": met == len(READINESS_THRESHOLDS),
        "conditions_met": met,
        "created_at": str(event.get("created_at") or ""),
        "stable_id": str(event.get("id") or ""),
    }


def build_family_space_readiness(
    community: dict[str, Any],
    events: list[dict[str, Any]],
    members: list[dict[str, Any]],
    memories: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return an aggregate-only report with exactly one stable next action."""
    lifecycle = community_lifecycle_state(community)
    revision = max(0, int(community.get("lifecycle_revision", 0) or 0))
    if lifecycle == ACTIVE:
        return {
            "lifecycle_state": ACTIVE,
            "lifecycle_revision": revision,
            "readiness_status": "active",
            "ready": True,
            "aggregate_counts": {
                "reunions": len(events),
                "verified_invitations": 0,
                "accepted_responses": 0,
                "non_host_participants": 0,
            },
            "unmet_condition_codes": [],
            "elapsed_day_bucket": "unknown",
            "next_action": {"code": "open_family_home"},
        }
    if lifecycle != PROVISIONAL:
        return {
            "lifecycle_state": LEGACY_UNCHANGED,
            "lifecycle_revision": revision,
            "readiness_status": LEGACY_UNCHANGED,
            "ready": False,
            "aggregate_counts": {
                "reunions": len(events),
                "verified_invitations": 0,
                "accepted_responses": 0,
                "non_host_participants": 0,
            },
            "unmet_condition_codes": ["explicit_provisional_state_required"],
            "elapsed_day_bucket": "unknown",
            "next_action": {"code": "continue_current_family_space"},
        }

    host_ids = {
        str(member.get("id")) for member in members if member.get("role") == "host"
    }
    if community.get("owner_user_id"):
        host_ids.add(str(community["owner_user_id"]))
    member_ids_by_email = {
        _normalized_email(member.get("email_normalized") or member.get("email")): str(
            member.get("id") or ""
        )
        for member in members
        if member.get("id")
        and _normalized_email(member.get("email_normalized") or member.get("email"))
    }
    evidence = [
        _event_evidence(
            event,
            member_ids_by_email=member_ids_by_email,
            host_user_ids=host_ids,
            memories=memories,
            now=now,
        )
        for event in events
    ]
    best = max(
        evidence,
        key=lambda item: (
            item["ready"],
            item["conditions_met"],
            item["counts"]["non_host_participants"],
            item["counts"]["accepted_responses"],
            item["counts"]["verified_invitations"],
            item["created_at"],
            item["stable_id"],
        ),
        default=None,
    )
    counts = (best or {}).get(
        "counts",
        {
            "verified_invitations": 0,
            "accepted_responses": 0,
            "non_host_participants": 0,
        },
    )
    unmet = []
    if not events:
        unmet.append("persisted_reunion_required")
    else:
        for key, threshold in READINESS_THRESHOLDS.items():
            if counts[key] < threshold:
                unmet.append(f"{key}_required")
    ready = bool(best and best["ready"])
    if ready:
        action = "activate_family_space"
    elif not events:
        action = "create_reunion"
    elif counts["verified_invitations"] < READINESS_THRESHOLDS["verified_invitations"]:
        action = "collect_verified_invitation_evidence"
    elif counts["accepted_responses"] < READINESS_THRESHOLDS["accepted_responses"]:
        action = "receive_more_accepted_responses"
    else:
        action = "invite_non_host_participation"
    return {
        "lifecycle_state": PROVISIONAL,
        "lifecycle_revision": revision,
        "readiness_status": "ready" if ready else "not_ready",
        "ready": ready,
        "aggregate_counts": {"reunions": len(events), **counts},
        "unmet_condition_codes": unmet,
        "elapsed_day_bucket": elapsed_day_bucket(
            (best or {}).get("created_at"), now=now
        ),
        "next_action": {"code": action},
    }
