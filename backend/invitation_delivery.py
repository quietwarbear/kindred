"""Disabled-by-default first-send delivery for gathering invitations.

This module reuses the reviewed ``ResendInvitationDeliveryProvider`` and the
signed ``verify_resend_delivery_event`` webhook contract. It never logs or
stores recipient identity, message content, links, or credentials in a report:

- the provider only ever receives an OPAQUE ``target_id`` (never the invitation
  credential), so its sanitized logs cannot leak a bearer token;
- the outbox maps an opaque provider message id to the invitation server-side;
- delivery is confirmed ONLY by a signed provider callback, never by polling;
- the delivered timestamp is monotonic and first-write-wins.

It performs no send unless BOTH ``INVITATION_FIRST_SEND_ENABLED`` is "true" AND
the provider preflight passes. Every other path fails closed with a categorical
status. This is a draft capability: it stays inert until an owner configures the
provider, verified sender, and webhook secret, and it must pass an independent
adversarial review before activation.
"""

from __future__ import annotations

import hashlib
import html
import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from pymongo.errors import DuplicateKeyError

from dependencies import now_iso
from invitation_redelivery import (
    DeliveryEnvelope,
    InvitationDeliveryProvider,
    ProviderStatus,
)
from invitation_redelivery_provider import ResendInvitationDeliveryProvider
from invitation_redelivery_webhook import VerifiedDeliveryEvent
from organizer_command_center import invitation_is_active
from rsvp_integrity import RSVPWriteConflict, compare_and_swap_event


def first_send_enabled() -> bool:
    """Delivery is off unless explicitly enabled by deployment configuration."""
    return os.environ.get("INVITATION_FIRST_SEND_ENABLED", "").lower() == "true"


def reminders_enabled() -> bool:
    """Reminder delivery is off unless explicitly enabled by configuration."""
    return os.environ.get("INVITATION_REMINDERS_ENABLED", "").lower() == "true"


def build_invitation_delivery_provider() -> InvitationDeliveryProvider | None:
    """Construct the Resend provider only when fully configured."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_address = os.environ.get("INVITATION_FROM_ADDRESS", "").strip()
    verified_domain = os.environ.get("INVITATION_VERIFIED_DOMAIN", "").strip()
    if not (api_key and from_address and verified_domain):
        return None
    return ResendInvitationDeliveryProvider(
        api_key=api_key,
        from_address=from_address,
        verified_domain=verified_domain,
    )


def _idempotency_key(event_id: str, invite_id: str) -> str:
    """Deterministic, opaque per-invitation key so provider retries dedupe."""
    digest = hashlib.sha256(f"invite-first-send:{event_id}:{invite_id}".encode())
    return f"ifs_{digest.hexdigest()}"


def _reminder_idempotency_key(event_id: str, invite_id: str, day_bucket: str) -> str:
    """Per-invite, per-day key so a reminder round dedupes but later days don't."""
    digest = hashlib.sha256(
        f"invite-reminder:{event_id}:{invite_id}:{day_bucket}".encode()
    )
    return f"ifr_{digest.hexdigest()}"


def _reminder_subject(event: dict[str, Any]) -> str:
    title = str(event.get("title") or "your gathering").strip() or "your gathering"
    return f"A reminder: {title}"


def _reminder_html(event: dict[str, Any], rsvp_link: str) -> str:
    title = html.escape(str(event.get("title") or "A gathering"))
    when = html.escape(str(event.get("start_at") or ""))
    where = html.escape(str(event.get("location") or "Location shared inside"))
    link = html.escape(rsvp_link, quote=True)
    return (
        '<!doctype html><html><body style="font-family:-apple-system,Segoe UI,'
        'Roboto,sans-serif;background:#f9f5f0;margin:0;padding:32px;">'
        '<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;'
        'padding:32px;">'
        '<p style="color:#9A3412;font-size:13px;letter-spacing:.12em;'
        'text-transform:uppercase;margin:0 0 8px;">A friendly reminder</p>'
        f'<h1 style="font-size:22px;color:#2d1810;margin:0 0 8px;">{title}</h1>'
        f'<p style="color:#5a4a3a;margin:0 0 4px;">{when}</p>'
        f'<p style="color:#5a4a3a;margin:0 0 20px;">{where}</p>'
        f'<a href="{link}" style="display:inline-block;background:#9A3412;color:#fff;'
        'border-radius:999px;padding:12px 28px;text-decoration:none;font-weight:600;">'
        "Let them know</a>"
        '<p style="color:#9a8a7a;font-size:12px;margin:20px 0 0;">This private link '
        "is just for you. Please don't forward it.</p>"
        "</div></body></html>"
    )


def _invitation_subject(event: dict[str, Any]) -> str:
    title = str(event.get("title") or "your gathering").strip() or "your gathering"
    return f"You're invited: {title}"


def _invitation_html(event: dict[str, Any], rsvp_link: str) -> str:
    title = html.escape(str(event.get("title") or "A gathering"))
    when = html.escape(str(event.get("start_at") or ""))
    where = html.escape(str(event.get("location") or "Location shared inside"))
    link = html.escape(rsvp_link, quote=True)
    return (
        '<!doctype html><html><body style="font-family:-apple-system,Segoe UI,'
        'Roboto,sans-serif;background:#f9f5f0;margin:0;padding:32px;">'
        '<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;'
        'padding:32px;">'
        f'<h1 style="font-size:22px;color:#2d1810;margin:0 0 8px;">{title}</h1>'
        f'<p style="color:#5a4a3a;margin:0 0 4px;">{when}</p>'
        f'<p style="color:#5a4a3a;margin:0 0 20px;">{where}</p>'
        f'<a href="{link}" style="display:inline-block;background:#9A3412;color:#fff;'
        'border-radius:999px;padding:12px 28px;text-decoration:none;font-weight:600;">'
        "View & RSVP</a>"
        '<p style="color:#9a8a7a;font-size:12px;margin:20px 0 0;">This private link '
        "is just for you. Please don't forward it.</p>"
        "</div></body></html>"
    )


@dataclass(frozen=True)
class DeliverySendReport:
    """Content-free outcome of a first-send batch."""

    status: str
    error_code: str = ""
    submitted: int = 0
    rejected: int = 0
    ambiguous: int = 0
    failed: int = 0
    skipped: int = 0

    def safe_document(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error_code": self.error_code,
            "counts": {
                "submitted": self.submitted,
                "rejected": self.rejected,
                "ambiguous": self.ambiguous,
                "failed": self.failed,
                "skipped": self.skipped,
            },
        }


def _select_invites(
    event: dict[str, Any], invite_ids: Iterable[str] | None
) -> tuple[list[dict[str, Any]], int]:
    """Return (eligible invites, count skipped because already sent/in-flight).

    An invite is skipped when it is already delivered OR currently ``submitting``
    (a send was accepted but the delivery callback has not resolved yet). This
    prevents a repeat call from re-sending an in-flight invitation after the
    provider idempotency window would have lapsed.
    """
    wanted = {str(i) for i in invite_ids} if invite_ids else None
    eligible: list[dict[str, Any]] = []
    skipped = 0
    for invite in event.get("event_invites", []):
        invite_id = str(invite.get("id") or "")
        if not invite_id or not invite.get("email"):
            continue
        if wanted is not None and invite_id not in wanted:
            continue
        if not invitation_is_active(invite):
            continue
        if invite.get("delivered_at") or invite.get("delivery_status") == "submitting":
            skipped += 1  # already delivered or in-flight; never re-send
            continue
        eligible.append(invite)
    return eligible, skipped


async def _mark_invite_submitting(
    events_collection,
    event_id: str,
    invite_id: str,
    now_fn: Callable[[], str],
) -> None:
    """Record the cosmetic in-flight status through the RSVP revision protocol.

    Best-effort: a concurrent RSVP may win the revision race; the outbox row is
    the authoritative record of the send, so a lost status stamp is harmless.
    """

    def mutate(current_event: dict[str, Any]) -> dict[str, Any]:
        invites = current_event.get("event_invites", [])
        target = next((i for i in invites if i.get("id") == invite_id), None)
        if target is not None:
            target["delivery_status"] = "submitting"
            target["delivery_submitted_at"] = now_fn()
        return {"event_invites": invites}

    try:
        await compare_and_swap_event(
            events_collection,
            {"id": event_id, "event_invites.id": invite_id},
            mutate,
        )
    except RSVPWriteConflict:
        return


async def send_first_invitations(
    *,
    event: dict[str, Any],
    invite_ids: Iterable[str] | None,
    provider: InvitationDeliveryProvider,
    events_collection,
    outbox_collection,
    app_url: str,
    now_fn: Callable[[], str] = now_iso,
) -> DeliverySendReport:
    """Send the current invitation credential to selected invites, fail-closed."""
    event_id = str(event.get("id") or "")
    if not event_id or event.get("publication_state") == "organizer_draft":
        return DeliverySendReport(status="unavailable", error_code="draft_or_missing")

    preflight = await provider.preflight()
    if not preflight.ready:
        return DeliverySendReport(
            status="unavailable", error_code=preflight.error_code.value
        )

    eligible, skipped = _select_invites(event, invite_ids)
    submitted = rejected = ambiguous = failed = 0
    for invite in eligible:
        invite_id = str(invite["id"])
        opaque_target_id = uuid.uuid4().hex
        operation_id = uuid.uuid4().hex
        rsvp_link = f"{app_url.rstrip('/')}/rsvp#{invite_id}"
        envelope = DeliveryEnvelope(
            recipient=str(invite.get("email")),
            subject=_invitation_subject(event),
            html_body=_invitation_html(event, rsvp_link),
            idempotency_key=_idempotency_key(event_id, invite_id),
            operation_id=operation_id,
            target_id=opaque_target_id,  # opaque, never the invite credential
        )
        receipt = await provider.send(envelope)
        if receipt.status == ProviderStatus.ACCEPTED and receipt.provider_message_id:
            try:
                await outbox_collection.update_one(
                    {"provider_message_id": receipt.provider_message_id},
                    {
                        "$setOnInsert": {
                            "id": uuid.uuid4().hex,
                            "provider_message_id": receipt.provider_message_id,
                            "event_id": event_id,
                            "invite_id": invite_id,
                            "opaque_target_id": opaque_target_id,
                            "kind": "first_send",
                            "status": "submitting",
                            "created_at": now_fn(),
                        }
                    },
                    upsert=True,
                )
            except DuplicateKeyError:
                # A concurrent identical send already recorded this provider
                # message id (Resend returns the same id for the same
                # idempotency key). The row exists; treat as recorded.
                pass
            await _mark_invite_submitting(
                events_collection, event_id, invite_id, now_fn
            )
            submitted += 1
        elif receipt.status == ProviderStatus.REJECTED:
            rejected += 1
        elif receipt.status == ProviderStatus.AMBIGUOUS:
            ambiguous += 1
        else:
            failed += 1
    return DeliverySendReport(
        status="processed",
        submitted=submitted,
        rejected=rejected,
        ambiguous=ambiguous,
        failed=failed,
        skipped=skipped,
    )


def _select_reminder_invites(
    event: dict[str, Any], invite_ids: Iterable[str] | None, day_bucket: str
) -> tuple[list[dict[str, Any]], int]:
    """Return (invites to remind, count skipped).

    Reminders target invites that are active, still unanswered, and have not
    already been reminded today (a per-day bucket dedupes rapid re-triggers).
    """
    wanted = {str(i) for i in invite_ids} if invite_ids else None
    eligible: list[dict[str, Any]] = []
    skipped = 0
    for invite in event.get("event_invites", []):
        invite_id = str(invite.get("id") or "")
        if not invite_id or not invite.get("email"):
            continue
        if wanted is not None and invite_id not in wanted:
            continue
        if not invitation_is_active(invite):
            continue
        if invite.get("rsvp_status", "pending") != "pending":
            skipped += 1  # already responded — nothing to remind
            continue
        if invite.get("last_reminder_bucket") == day_bucket:
            skipped += 1  # already reminded today
            continue
        eligible.append(invite)
    return eligible, skipped


async def _mark_invite_reminded(
    events_collection,
    event_id: str,
    invite_id: str,
    day_bucket: str,
    now_fn: Callable[[], str],
) -> None:
    """Record the reminder through the revision protocol (best-effort)."""

    def mutate(current_event: dict[str, Any]) -> dict[str, Any]:
        invites = current_event.get("event_invites", [])
        target = next((i for i in invites if i.get("id") == invite_id), None)
        if target is not None:
            target["reminder_sent_at"] = now_fn()
            target["last_reminder_bucket"] = day_bucket
            target["reminder_delivery_status"] = "submitting"
        return {"event_invites": invites}

    try:
        await compare_and_swap_event(
            events_collection,
            {"id": event_id, "event_invites.id": invite_id},
            mutate,
        )
    except RSVPWriteConflict:
        return


async def send_reminders(
    *,
    event: dict[str, Any],
    invite_ids: Iterable[str] | None,
    provider: InvitationDeliveryProvider,
    events_collection,
    outbox_collection,
    app_url: str,
    now_fn: Callable[[], str] = now_iso,
) -> DeliverySendReport:
    """Send a reminder to unanswered invites, fail-closed and once-per-day."""
    event_id = str(event.get("id") or "")
    if not event_id or event.get("publication_state") == "organizer_draft":
        return DeliverySendReport(status="unavailable", error_code="draft_or_missing")

    preflight = await provider.preflight()
    if not preflight.ready:
        return DeliverySendReport(
            status="unavailable", error_code=preflight.error_code.value
        )

    day_bucket = now_fn()[:10]  # YYYY-MM-DD; one reminder per invite per day
    eligible, skipped = _select_reminder_invites(event, invite_ids, day_bucket)
    submitted = rejected = ambiguous = failed = 0
    for invite in eligible:
        invite_id = str(invite["id"])
        opaque_target_id = uuid.uuid4().hex
        operation_id = uuid.uuid4().hex
        rsvp_link = f"{app_url.rstrip('/')}/rsvp#{invite_id}"
        envelope = DeliveryEnvelope(
            recipient=str(invite.get("email")),
            subject=_reminder_subject(event),
            html_body=_reminder_html(event, rsvp_link),
            idempotency_key=_reminder_idempotency_key(event_id, invite_id, day_bucket),
            operation_id=operation_id,
            target_id=opaque_target_id,  # opaque, never the invite credential
        )
        receipt = await provider.send(envelope)
        if receipt.status == ProviderStatus.ACCEPTED and receipt.provider_message_id:
            try:
                await outbox_collection.update_one(
                    {"provider_message_id": receipt.provider_message_id},
                    {
                        "$setOnInsert": {
                            "id": uuid.uuid4().hex,
                            "provider_message_id": receipt.provider_message_id,
                            "event_id": event_id,
                            "invite_id": invite_id,
                            "opaque_target_id": opaque_target_id,
                            "kind": "reminder",
                            "status": "submitting",
                            "created_at": now_fn(),
                        }
                    },
                    upsert=True,
                )
            except DuplicateKeyError:
                pass
            await _mark_invite_reminded(
                events_collection, event_id, invite_id, day_bucket, now_fn
            )
            submitted += 1
        elif receipt.status == ProviderStatus.REJECTED:
            rejected += 1
        elif receipt.status == ProviderStatus.AMBIGUOUS:
            ambiguous += 1
        else:
            failed += 1
    return DeliverySendReport(
        status="processed",
        submitted=submitted,
        rejected=rejected,
        ambiguous=ambiguous,
        failed=failed,
        skipped=skipped,
    )


async def apply_first_send_delivery_event(
    *,
    events_collection,
    outbox_collection,
    event: VerifiedDeliveryEvent,
    now_fn: Callable[[], str] = now_iso,
) -> str:
    """Apply one verified provider callback; monotonic and idempotent.

    Delivered events stamp the mapped invitation exactly once — ``delivered_at``
    for a first send, ``reminder_delivered_at`` for a reminder. Failure events
    never downgrade a delivered target. Unknown references are ignored (they may
    belong to another surface).
    """
    record = await outbox_collection.find_one(
        {"provider_message_id": event.provider_message_id}, {"_id": 0}
    )
    if not record:
        return "ignored_unknown"
    event_id = str(record.get("event_id") or "")
    invite_id = str(record.get("invite_id") or "")
    if not event_id or not invite_id:
        return "ignored_unknown"

    is_reminder = record.get("kind") == "reminder"

    if event.provider_status == ProviderStatus.DELIVERED:
        # Idempotent: a duplicate delivered callback is a cheap no-op.
        if record.get("status") == "delivered":
            return "delivered"

        # Stamp through the RSVP revision protocol so a concurrent RSVP or
        # activation write cannot silently erase the delivered state with a
        # stale whole-array replacement. First-write-wins on the timestamp.
        def mark_delivered(current_event: dict[str, Any]) -> dict[str, Any]:
            invites = current_event.get("event_invites", [])
            target = next((i for i in invites if i.get("id") == invite_id), None)
            if target is not None:
                stamp = now_fn()
                if is_reminder:
                    if not target.get("reminder_delivered_at"):
                        target["reminder_delivered_at"] = stamp
                        target["reminder_delivery_status"] = "delivered"
                elif not target.get("delivered_at"):
                    target["delivered_at"] = stamp
                    target["delivery_verified_at"] = stamp
                    target["delivery_status"] = "delivered"
            return {"event_invites": invites}

        try:
            updated = await compare_and_swap_event(
                events_collection,
                {"id": event_id, "event_invites.id": invite_id},
                mark_delivered,
            )
        except RSVPWriteConflict:
            return "conflict"  # webhook returns 503 so the provider retries
        if updated is None:
            return "ignored_unknown"
        await outbox_collection.update_one(
            {
                "provider_message_id": event.provider_message_id,
                "status": {"$ne": "delivered"},
            },
            {"$set": {"status": "delivered", "delivered_at": now_fn()}},
        )
        return "delivered"

    if event.provider_status == ProviderStatus.FAILED:
        await outbox_collection.update_one(
            {
                "provider_message_id": event.provider_message_id,
                "status": {"$nin": ["delivered", "failed"]},
            },
            {"$set": {"status": "failed", "failed_at": now_fn()}},
        )
        return "failed"

    return "ignored"
