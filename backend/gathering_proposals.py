"""Content-safe policy and projection helpers for private gathering proposals."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from typing import Any

from itinerary import parse_local_datetime, valid_timezone

PROPOSAL_STATES = {
    "submitted", "published", "declined", "withdrawn", "converted", "expired", "conflict",
}
TERMINAL_STATES = {"declined", "withdrawn", "converted", "expired", "conflict"}
GATHERING_TYPES = {"family_reunion", "holiday", "milestone", "day_trip", "virtual", "other"}
INTEREST_RESPONSES = {"interested", "maybe", "not_available"}
DECLINE_REASONS = {"not_a_fit", "needs_more_detail", "timing_not_workable", "duplicate", "other"}
GATHERING_FORMATS = {"in-person", "online", "hybrid"}


class ProposalValidationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def clean_private_text(value: Any, *, maximum: int, required: bool = False) -> str:
    raw = str(value or "")
    if any(unicodedata.category(character).startswith("C") and character not in {"\n", "\t"} for character in raw):
        raise ProposalValidationError("unsupported_characters")
    normalized = " ".join(unicodedata.normalize("NFKC", raw).split())
    if required and not normalized:
        raise ProposalValidationError("required_text")
    if len(normalized) > maximum:
        raise ProposalValidationError("text_too_long")
    return normalized


def digest_payload(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def aggregate_interest(
    responses: list[dict[str, Any]], eligible_user_ids: set[str]
) -> dict[str, int]:
    totals = {category: 0 for category in sorted(INTEREST_RESPONSES)}
    for response in responses:
        if response.get("user_id") not in eligible_user_ids:
            continue
        category = response.get("response")
        if category in totals:
            totals[category] += 1
    return {**totals, "total": sum(totals.values())}


def member_projection(
    proposal: dict[str, Any],
    *,
    viewer_id: str,
    responses: list[dict[str, Any]],
    eligible_user_ids: set[str],
    organizer: bool = False,
) -> dict[str, Any]:
    own = next((item for item in responses if item.get("user_id") == viewer_id), None)
    state = proposal.get("state") if proposal.get("state") in PROPOSAL_STATES else "conflict"
    result: dict[str, Any] = {
        "proposal_reference": str(proposal.get("public_reference") or ""),
        "state": state,
        "revision": max(0, int(proposal.get("revision", 0) or 0)),
        "working_title": str(proposal.get("working_title") or ""),
        "gathering_type": proposal.get("gathering_type") if proposal.get("gathering_type") in GATHERING_TYPES else "other",
        "broad_date_window": str(proposal.get("broad_date_window") or ""),
        "location_suggestion": str(proposal.get("location_suggestion") or ""),
        "interest": {
            "aggregate": aggregate_interest(responses, eligible_user_ids),
            "my_response": (own or {}).get("response") if (own or {}).get("response") in INTEREST_RESPONSES else "none",
            "my_revision": max(0, int((own or {}).get("revision", 0) or 0)),
        },
        "is_mine": proposal.get("proposer_user_id") == viewer_id,
    }
    if result["is_mine"]:
        result["organizer_note"] = str(proposal.get("organizer_note") or "")
    if organizer:
        result.update({
            "proposer_display_name": str(proposal.get("proposer_display_name") or "Former family member"),
            "organizer_note": str(proposal.get("organizer_note") or ""),
            "moderation_reason": str(proposal.get("moderation_reason") or ""),
            "proposer_tombstone": bool(proposal.get("proposer_tombstone")),
        })
    return result


def conversion_preview_value(
    *,
    title: Any,
    start_at: Any,
    end_at: Any,
    timezone_name: Any,
    location: Any,
    gathering_format: Any,
    max_attendees: Any,
    organizer_display_name: str,
) -> dict[str, Any]:
    clean_title = clean_private_text(title, maximum=160, required=True)
    clean_location = clean_private_text(location, maximum=160)
    timezone_value = str(timezone_name or "").strip()
    if not valid_timezone(timezone_value):
        raise ProposalValidationError("invalid_timezone")
    start_value = str(start_at or "").strip()
    end_value = str(end_at or "").strip()
    start = parse_local_datetime(start_value, timezone_value)
    end = parse_local_datetime(end_value, timezone_value)
    if not start or not end or end <= start:
        raise ProposalValidationError("invalid_boundary")
    format_value = str(gathering_format or "")
    if format_value not in GATHERING_FORMATS:
        raise ProposalValidationError("invalid_gathering_format")
    if isinstance(max_attendees, bool) or not isinstance(max_attendees, int) or not 1 <= max_attendees <= 10000:
        raise ProposalValidationError("invalid_capacity")
    proposal = {
        "new_gathering": {
            "title": clean_title,
            "start_at": start_value,
            "end_at": end_value,
            "timezone": timezone_value,
            "location": clean_location,
            "gathering_format": format_value,
            "max_attendees": max_attendees,
            "organizer_display_name": organizer_display_name,
            "publication_state": "organizer_draft",
        },
        "guarantees": {
            "zero_invitations": True,
            "zero_responses": True,
            "zero_assignments": True,
            "zero_memories": True,
            "no_proposer_identity": True,
            "new_structural_identifiers": True,
        },
    }
    return {"proposal": proposal, "preview_digest": digest_payload(proposal)}


def new_draft_document(
    *,
    community_id: str,
    organizer: dict[str, Any],
    proposal_id: str,
    preview: dict[str, Any],
    timestamp: str,
) -> dict[str, Any]:
    gathering = preview["proposal"]["new_gathering"]
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"kindred-gathering-proposal:{proposal_id}")),
        "community_id": community_id,
        "created_by": organizer["id"],
        "created_by_name": organizer.get("full_name", "Organizer"),
        "title": gathering["title"],
        "description": "",
        "start_at": gathering["start_at"],
        "end_at": gathering["end_at"],
        "timezone": gathering["timezone"],
        "location": gathering["location"],
        "event_template": "reunion",
        "gathering_format": gathering["gathering_format"],
        "max_attendees": gathering["max_attendees"],
        "publication_state": "organizer_draft",
        "hidden_from_user_ids": [],
        "event_invites": [],
        "rsvp_records": [],
        "activity_rsvps": [],
        "agenda": [],
        "potluck_items": [],
        "volunteer_slots": [],
        "planning_checklist": [],
        "event_role_assignments": [],
        "assigned_roles": [],
        "rsvp_revision": 0,
        "created_at": timestamp,
        "client_request_id": "",
    }
