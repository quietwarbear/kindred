"""Database-safe RSVP update and respondent identity helpers."""

from __future__ import annotations

import re
from typing import Any, Callable


MAX_RSVP_WRITE_ATTEMPTS = 32


class RSVPWriteConflict(RuntimeError):
    pass


async def find_community_member_by_email(
    collection,
    community_id: str,
    email: str,
) -> dict[str, Any] | None:
    """Resolve a member email within one community, including legacy mixed-case rows."""
    normalized_email = str(email or "").strip().lower()
    if not community_id or not normalized_email:
        return None
    member = await collection.find_one(
        {"community_id": community_id, "email_normalized": normalized_email},
        {"_id": 0, "id": 1},
    )
    if member:
        return member
    return await collection.find_one(
        {
            "community_id": community_id,
            "email": {
                "$regex": f"^{re.escape(normalized_email)}$",
                "$options": "i",
            },
        },
        {"_id": 0, "id": 1},
    )


async def compare_and_swap_event(
    collection,
    query: dict[str, Any],
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any] | None:
    """Apply one event mutation without allowing stale snapshots to win."""
    for _attempt in range(MAX_RSVP_WRITE_ATTEMPTS):
        event = await collection.find_one(query, {"_id": 0})
        if not event:
            return None
        revision = int(event.get("rsvp_revision", 0) or 0)
        updates = mutate(event)
        guarded_query = dict(query)
        if "rsvp_revision" in event:
            guarded_query["rsvp_revision"] = revision
        else:
            guarded_query["rsvp_revision"] = {"$exists": False}
        result = await collection.update_one(
            guarded_query,
            {
                "$set": updates,
                "$inc": {"rsvp_revision": 1},
            },
        )
        if result.matched_count == 1:
            event.update(updates)
            event["rsvp_revision"] = revision + 1
            return event
    raise RSVPWriteConflict("The RSVP changed concurrently. Please retry.")


def member_invite_aliases(event: dict[str, Any], user: dict[str, Any]) -> set[str]:
    """Return legacy public-link identities that belong to this exact member."""
    user_id = user.get("id", "")
    user_email = str(user.get("email") or "").strip().lower()
    aliases = {user_id} if user_id else set()
    for invite in event.get("event_invites", []):
        member_id = invite.get("member_id", "")
        legacy_member_match = (
            not member_id
            and invite.get("invite_source") == "member"
            and user_email
            and str(invite.get("email") or "").strip().lower() == user_email
        )
        if member_id == user_id or legacy_member_match:
            invite_id = invite.get("id", "")
            if invite_id:
                aliases.add(f"invite:{invite_id}")
    return aliases


def public_respondent_identity(invite: dict[str, Any]) -> tuple[str, set[str]]:
    """Return the canonical identity and any safe legacy aliases."""
    invite_id = invite.get("id", "")
    token_identity = f"invite:{invite_id}"
    member_id = invite.get("member_id", "")
    if member_id:
        return member_id, {token_identity, member_id}
    return token_identity, {token_identity}
