"""K9 (second half): find and merge duplicate people inside one event.

The first half (``registrant_import``) stops an import from creating a second
invitation for a name that already exists under another email. This module
handles duplicates that already exist: two invitations for the same person.

Detection (``possible_duplicates``) pairs active invitations that share a
normalized email or a normalized name. An organizer can merge a pair or mark
it "not the same person" (remembered per pair, so it is not raised again).

Merging (``merge_invitations``) keeps one invitation and folds the other into
it:

- Responses move. The event answer and every activity answer recorded under
  the merged invitation (or its member account) are rewritten to the kept
  person. Where both people answered the same question, the most recent
  answer wins.
- Contributions move. Potluck claims, volunteer slots and memories are keyed
  by member account, so when only the merged invitation was linked to an
  account, the kept invitation takes that link and they follow it. Two
  invitations linked to two different accounts are refused: that would be an
  account merge, which this does not do.
- Invitations move. The merged invitation is retired (``superseded``) with
  ``merged_into`` pointing at the kept one. Sends, reminders and counts
  already skip superseded invitations, and the merged person's old link opens
  the kept invitation, so nobody is locked out. Its email is kept as an
  alternate address, so a later registrant import for that email lands on the
  kept invitation instead of creating a third.

Everything here is pure (no I/O) so it runs inside the event compare-and-swap.
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Any

from itinerary import activity_summaries
from organizer_command_center import invitation_is_active

REASON_SAME_EMAIL = "same_email"
REASON_SAME_NAME = "same_name"
MAX_MERGE_HISTORY = 200


class MergeError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _email(value: Any) -> str:
    return str(value or "").strip().lower()


def _name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).casefold()


def pair_key(first_id: str, second_id: str) -> str:
    """Order-independent, opaque key for one pair of invitations."""
    low, high = sorted([str(first_id), str(second_id)])
    return hashlib.sha256(f"dup-pair:{low}:{high}".encode()).hexdigest()[:24]


def resolve_merged_invite(event: dict[str, Any], invite: dict[str, Any] | None) -> dict[str, Any] | None:
    """Follow ``merged_into`` to the invitation that now holds this person."""
    by_id = {str(i.get("id")): i for i in event.get("event_invites", []) if i.get("id")}
    seen: set[str] = set()
    current = invite
    while current and current.get("merged_into"):
        current_id = str(current.get("id") or "")
        if current_id in seen:
            return None
        seen.add(current_id)
        current = by_id.get(str(current["merged_into"]))
    return current


def _identity(invite: dict[str, Any]) -> str:
    member_id = str(invite.get("member_id") or "")
    return member_id or f"invite:{invite.get('id')}"


def _invite_summary(event: dict[str, Any], invite: dict[str, Any]) -> dict[str, Any]:
    aliases = {f"invite:{invite.get('id')}"}
    if invite.get("member_id"):
        aliases.add(str(invite["member_id"]))
    answered = {
        str(row.get("activity_id"))
        for row in event.get("activity_rsvps", [])
        if row.get("respondent_id") in aliases and row.get("activity_id")
    }
    return {
        "invite_id": str(invite.get("id") or ""),
        "name": str(invite.get("invitee_name") or ""),
        "email": _email(invite.get("email")),
        "has_account": bool(invite.get("member_id")),
        "source": str(invite.get("invite_source") or ""),
        "imported": bool(invite.get("imported_via") or invite.get("import_source")),
        "rsvp_status": str(invite.get("rsvp_status") or "pending"),
        "activity_answers": len(answered),
        "created_at": str(invite.get("created_at") or ""),
    }


def possible_duplicates(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Pairs of active invitations that look like the same person."""
    dismissed = set(event.get("duplicate_dismissals") or [])
    invites = [
        invite
        for invite in event.get("event_invites", [])
        if invite.get("id") and not invite.get("merged_into") and invitation_is_active(invite)
    ]
    pairs: dict[str, dict[str, Any]] = {}
    for index, first in enumerate(invites):
        for second in invites[index + 1:]:
            first_member = str(first.get("member_id") or "")
            second_member = str(second.get("member_id") or "")
            if first_member and first_member == second_member:
                reason = REASON_SAME_EMAIL  # one account holding two invitations
            elif _email(first.get("email")) and _email(first.get("email")) == _email(second.get("email")):
                reason = REASON_SAME_EMAIL
            elif _name(first.get("invitee_name")) and _name(first.get("invitee_name")) == _name(
                second.get("invitee_name")
            ):
                reason = REASON_SAME_NAME
            else:
                continue
            key = pair_key(first["id"], second["id"])
            if key in dismissed:
                continue
            older, newer = sorted(
                (first, second), key=lambda i: (str(i.get("created_at") or ""), str(i.get("id")))
            )
            pairs[key] = {
                "pair_key": key,
                "reason": reason,
                "people": [_invite_summary(event, older), _invite_summary(event, newer)],
                # Suggest keeping the older record unless only the newer has an account.
                "suggested_keep_invite_id": str(
                    newer["id"] if newer.get("member_id") and not older.get("member_id") else older["id"]
                ),
            }
    return sorted(pairs.values(), key=lambda pair: (pair["reason"] != REASON_SAME_EMAIL, pair["people"][0]["name"].casefold()))


def _latest_by(rows: list[dict[str, Any]], key_of) -> list[dict[str, Any]]:
    """Keep the most recent row per key, preserving the first-seen order."""
    latest: dict[Any, dict[str, Any]] = {}
    order: list[Any] = []
    for row in rows:
        key = key_of(row)
        if key not in latest:
            order.append(key)
            latest[key] = row
        elif str(row.get("updated_at") or "") >= str(latest[key].get("updated_at") or ""):
            latest[key] = row
    return [latest[key] for key in order]


def merge_invitations(
    event: dict[str, Any],
    *,
    keep_invite_id: str,
    merge_invite_id: str,
    actor_id: str,
    now: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fold ``merge_invite_id`` into ``keep_invite_id``. Returns ``(updates, report)``."""
    if keep_invite_id == merge_invite_id:
        raise MergeError("same_invitation", "Choose two different people to merge.", 422)
    invites = [dict(invite) for invite in event.get("event_invites", [])]
    keep = next((i for i in invites if i.get("id") == keep_invite_id), None)
    merged = next((i for i in invites if i.get("id") == merge_invite_id), None)
    if keep is None or merged is None:
        raise MergeError("invitation_not_found", "One of these people is no longer on the guest list.", 404)
    if keep.get("merged_into") or merged.get("merged_into"):
        raise MergeError("already_merged", "One of these people was already merged.")
    if not invitation_is_active(keep):
        raise MergeError("keep_inactive", "Keep a person whose invitation is still active.")
    keep_member = str(keep.get("member_id") or "")
    merged_member = str(merged.get("member_id") or "")
    if keep_member and merged_member and keep_member != merged_member:
        raise MergeError(
            "two_accounts",
            "Both people have their own Kindred account, so their records can't be merged here.",
        )

    member_id = keep_member or merged_member
    old_aliases = {f"invite:{merge_invite_id}"}
    if merged_member and merged_member != keep_member:
        old_aliases.add(merged_member)
    # Once the kept invitation carries an account, its own token answers move
    # to the account too, so one person has one identity.
    if member_id and not keep_member:
        old_aliases.add(f"invite:{keep_invite_id}")
    target = member_id or f"invite:{keep_invite_id}"

    # Event-level answers.
    moved_event = 0
    records = []
    for record in event.get("rsvp_records", []):
        record = dict(record)
        if record.get("user_id") in old_aliases:
            record["user_id"] = target
            moved_event += 1
        records.append(record)
    identity_of = {target}
    if member_id:
        identity_of.add(f"invite:{keep_invite_id}")
    records_before = len(records)
    records = _latest_by(
        records,
        lambda r: target if r.get("user_id") in identity_of else r.get("user_id"),
    )

    # Activity answers.
    moved_activity = 0
    responses = []
    for row in event.get("activity_rsvps", []):
        row = dict(row)
        if row.get("respondent_id") in old_aliases:
            row["respondent_id"] = target
            moved_activity += 1
        responses.append(row)
    before = len(responses)
    responses = _latest_by(
        responses,
        lambda r: (
            r.get("activity_id"),
            target if r.get("respondent_id") in identity_of else r.get("respondent_id"),
        ),
    )
    collapsed = before - len(responses)

    # The kept invitation absorbs what the merged one knew.
    if member_id:
        keep["member_id"] = member_id
        keep["invite_source"] = "member"
    if str(keep.get("rsvp_status") or "pending") == "pending" and merged.get("rsvp_status") not in (None, "", "pending"):
        keep["rsvp_status"] = merged.get("rsvp_status")
        keep["guests"] = merged.get("guests", keep.get("guests", 0))
    alternates = [
        email
        for email in dict.fromkeys(
            [*(keep.get("alternate_emails") or []), _email(merged.get("email")), *(merged.get("alternate_emails") or [])]
        )
        if email and email != _email(keep.get("email"))
    ]
    if alternates:
        keep["alternate_emails"] = alternates
    if not keep.get("invitee_name") and merged.get("invitee_name"):
        keep["invitee_name"] = merged["invitee_name"]

    merged.update(
        {
            "status": "superseded",
            "superseded_at": now,
            "merged_into": keep_invite_id,
            "merged_at": now,
            "merged_by": actor_id,
        }
    )
    invites = [keep if i.get("id") == keep_invite_id else merged if i.get("id") == merge_invite_id else i for i in invites]

    report = {
        "kept_invite_id": keep_invite_id,
        "merged_invite_id": merge_invite_id,
        "moved_event_answers": moved_event,
        "moved_activity_answers": moved_activity,
        # Questions both people had answered, where only the newest answer stays.
        "overlapping_answers_resolved": collapsed + (records_before - len(records)),
        "account_linked": bool(member_id and not keep_member),
    }
    history = list(event.get("duplicate_merges") or [])
    history.append(
        {
            "kept_invite_id": keep_invite_id,
            "merged_invite_id": merge_invite_id,
            "merged_at": now,
            "merged_by": actor_id,
            "moved_event_answers": moved_event,
            "moved_activity_answers": moved_activity,
        }
    )
    snapshot = {**event, "event_invites": invites, "rsvp_records": records, "activity_rsvps": responses}
    updates = {
        "event_invites": invites,
        "rsvp_records": records,
        "activity_rsvps": responses,
        "activity_rsvp_summaries": activity_summaries(snapshot),
        "duplicate_merges": history[-MAX_MERGE_HISTORY:],
    }
    return updates, report


def dismiss_pair(event: dict[str, Any], key: str) -> dict[str, Any]:
    """Remember that the organizer said this pair is two different people."""
    dismissed = list(dict.fromkeys([*(event.get("duplicate_dismissals") or []), key]))
    return {"duplicate_dismissals": dismissed[-1000:]}
