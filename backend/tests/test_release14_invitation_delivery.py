"""Release 14 — disabled-by-default first-send delivery (synthetic, no network)."""

import os
import re
import uuid
from copy import deepcopy

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_release14_delivery_unit")

import pytest
from fastapi import HTTPException

from invitation_delivery import (
    DeliverySendReport,
    apply_first_send_delivery_event,
    build_invitation_delivery_provider,
    first_send_enabled,
    send_first_invitations,
)
from invitation_redelivery import (
    PreflightResult,
    ProviderReceipt,
    ProviderStatus,
    SafeErrorCode,
)
from invitation_redelivery_webhook import VerifiedDeliveryEvent
from models import InvitationSendRequest
from routes import events

HEX32 = re.compile(r"^[0-9a-f]{32}$")

ORGANIZER = {
    "id": "synthetic-organizer",
    "community_id": "synthetic-family",
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
    "role": "organizer",
}


def _published_event(**overrides):
    event = {
        "id": "synthetic-holiday",
        "community_id": "synthetic-family",
        "title": "Synthetic holiday dinner",
        "start_at": "2026-11-26T16:00:00-08:00",
        "location": "Synthetic home",
        "event_template": "holiday_meal",
        "publication_state": "published",
        "event_invites": [
            {
                "id": "cred-a",
                "email": "guest-a@example.invalid",
                "invitee_name": "Guest A",
                "status": "invited",
                "rsvp_status": "pending",
            }
        ],
    }
    event.update(overrides)
    return event


class _FakeProvider:
    def __init__(self, ready=True, receipt=None):
        self._preflight = PreflightResult(
            ready=ready,
            error_code=(
                SafeErrorCode.NONE if ready else SafeErrorCode.CONFIGURATION_UNAVAILABLE
            ),
        )
        self.sent = []
        self._receipt = receipt

    async def preflight(self):
        return self._preflight

    async def send(self, envelope):
        self.sent.append(envelope)
        if self._receipt is not None:
            return self._receipt
        return ProviderReceipt(
            status=ProviderStatus.ACCEPTED,
            provider_message_id="msg_" + uuid.uuid4().hex,
        )


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count
        self.modified_count = matched_count


class _CasEvents:
    """Events collection honoring the rsvp_revision guard (delivery goes via CAS)."""

    def __init__(self, event=None):
        self.event = deepcopy(event) if event else None
        self.writes = 0

    async def find_one(self, _query, _projection=None):
        return deepcopy(self.event) if self.event is not None else None

    async def update_one(self, query, update, array_filters=None):
        self.writes += 1
        if self.event is None:
            return _Result(matched_count=0)
        guard = query.get("rsvp_revision")
        current = int(self.event.get("rsvp_revision", 0) or 0)
        if guard is not None and not isinstance(guard, dict) and guard != current:
            return _Result(matched_count=0)
        for key, value in update.get("$set", {}).items():
            self.event[key] = deepcopy(value)
        for key, value in update.get("$inc", {}).items():
            self.event[key] = int(self.event.get(key, 0) or 0) + value
        return _Result(matched_count=1)

    def invite(self, invite_id):
        for item in (self.event or {}).get("event_invites", []):
            if item.get("id") == invite_id:
                return item
        return None


class _FakeOutbox:
    def __init__(self, record=None):
        self.record = record
        self.upserts = []
        self.updates = []

    async def update_one(self, query, update, upsert=False, array_filters=None):
        if upsert:
            self.upserts.append((query, update))
        else:
            self.updates.append((query, update))

    async def find_one(self, query, _projection=None):
        return self.record


# --------------------------------------------------------------------------
# Gating: off by default, fails closed
# --------------------------------------------------------------------------


def test_first_send_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INVITATION_FIRST_SEND_ENABLED", raising=False)
    assert first_send_enabled() is False
    monkeypatch.setenv("INVITATION_FIRST_SEND_ENABLED", "false")
    assert first_send_enabled() is False
    monkeypatch.setenv("INVITATION_FIRST_SEND_ENABLED", "true")
    assert first_send_enabled() is True


def test_provider_none_when_unconfigured(monkeypatch):
    for var in (
        "RESEND_API_KEY",
        "INVITATION_FROM_ADDRESS",
        "INVITATION_VERIFIED_DOMAIN",
    ):
        monkeypatch.delenv(var, raising=False)
    assert build_invitation_delivery_provider() is None


@pytest.mark.asyncio
async def test_send_endpoint_unavailable_when_disabled(monkeypatch):
    async def fake_event(_event_id, _user):
        return _published_event()

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "first_send_enabled", lambda: False)
    result = await events.send_event_invitations(
        "synthetic-holiday", InvitationSendRequest(), ORGANIZER
    )
    assert result["status"] == "unavailable"
    assert result["error_code"] == "delivery_disabled"
    assert result["counts"]["submitted"] == 0


@pytest.mark.asyncio
async def test_send_endpoint_unavailable_when_provider_unconfigured(monkeypatch):
    async def fake_event(_event_id, _user):
        return _published_event()

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "first_send_enabled", lambda: True)
    monkeypatch.setattr(events, "build_invitation_delivery_provider", lambda: None)
    result = await events.send_event_invitations(
        "synthetic-holiday", InvitationSendRequest(), ORGANIZER
    )
    assert result["status"] == "unavailable"
    assert result["error_code"] == "provider_unconfigured"


@pytest.mark.asyncio
async def test_send_endpoint_blocks_private_draft(monkeypatch):
    async def fake_event(_event_id, _user):
        return _published_event(publication_state="organizer_draft")

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "first_send_enabled", lambda: True)
    with pytest.raises(HTTPException) as rejected:
        await events.send_event_invitations(
            "synthetic-holiday", InvitationSendRequest(), ORGANIZER
        )
    assert rejected.value.status_code == 409
    assert rejected.value.detail["code"] == "organizer_draft_send_blocked"


# --------------------------------------------------------------------------
# Send behavior: privacy, preflight, idempotency
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_uses_opaque_target_never_the_credential():
    provider = _FakeProvider()
    events_col = _CasEvents(_published_event())
    outbox = _FakeOutbox()
    report = await send_first_invitations(
        event=_published_event(),
        invite_ids=None,
        provider=provider,
        events_collection=events_col,
        outbox_collection=outbox,
        app_url="https://www.heykindred.org",
        now_fn=lambda: "2026-11-02T00:00:00+00:00",
    )
    assert report.status == "processed"
    assert report.submitted == 1
    envelope = provider.sent[0]
    # The provider's logged target_id must be opaque, never the bearer credential.
    assert HEX32.fullmatch(envelope.target_id)
    assert envelope.target_id != "cred-a"
    assert HEX32.fullmatch(envelope.operation_id)
    assert envelope.recipient == "guest-a@example.invalid"
    # The recipient's own fragment link legitimately carries their credential.
    assert "/rsvp#cred-a" in envelope.html_body
    # Outbox maps the opaque message id to the invite server-side.
    assert outbox.upserts
    setoninsert = outbox.upserts[0][1]["$setOnInsert"]
    assert setoninsert["invite_id"] == "cred-a"
    assert setoninsert["status"] == "submitting"
    # The in-flight status was stamped through the revision protocol.
    assert events_col.invite("cred-a")["delivery_status"] == "submitting"
    assert events_col.event["rsvp_revision"] == 1


@pytest.mark.asyncio
async def test_send_does_not_gate_on_local_preflight():
    # The strict DNS/region preflight no longer blocks: Resend enforces domain
    # verification at send time. A provider whose preflight is "not ready" still
    # attempts the send (which Resend would reject for a real unverified domain).
    provider = _FakeProvider(ready=False)  # would previously have short-circuited
    events_col = _CasEvents(_published_event())
    report = await send_first_invitations(
        event=_published_event(),
        invite_ids=None,
        provider=provider,
        events_collection=events_col,
        outbox_collection=_FakeOutbox(),
        app_url="https://www.heykindred.org",
    )
    assert provider.sent  # the send was attempted, not blocked by preflight
    assert report.submitted == 1


@pytest.mark.asyncio
async def test_unverified_domain_rejects_safely_via_provider():
    # An unverified domain / bad config surfaces as the provider REJECTING the
    # send (Resend returns non-2xx) — no email, no outbox row.
    provider = _FakeProvider(
        receipt=ProviderReceipt(
            status=ProviderStatus.REJECTED, error_code=SafeErrorCode.PROVIDER_REJECTED
        )
    )
    outbox = _FakeOutbox()
    report = await send_first_invitations(
        event=_published_event(),
        invite_ids=None,
        provider=provider,
        events_collection=_CasEvents(_published_event()),
        outbox_collection=outbox,
        app_url="https://www.heykindred.org",
    )
    assert provider.sent  # attempted
    assert report.rejected == 1
    assert report.submitted == 0
    assert outbox.upserts == []  # nothing recorded, no email


@pytest.mark.asyncio
async def test_send_skips_already_delivered_invites():
    provider = _FakeProvider()
    event = _published_event(
        event_invites=[
            {
                "id": "cred-a",
                "email": "guest-a@example.invalid",
                "status": "invited",
                "delivered_at": "2026-11-01T00:00:00+00:00",
            }
        ]
    )
    report = await send_first_invitations(
        event=event,
        invite_ids=None,
        provider=provider,
        events_collection=_CasEvents(),
        outbox_collection=_FakeOutbox(),
        app_url="https://www.heykindred.org",
    )
    assert provider.sent == []
    assert report.submitted == 0
    assert report.skipped == 1  # already delivered → counted, not re-sent


@pytest.mark.asyncio
async def test_send_skips_in_flight_submitting_invites():
    # An invite already submitted but not yet confirmed delivered must not be
    # re-sent — this is the guard against a duplicate email once the provider
    # idempotency window lapses.
    provider = _FakeProvider()
    event = _published_event(
        event_invites=[
            {
                "id": "cred-a",
                "email": "guest-a@example.invalid",
                "status": "invited",
                "delivery_status": "submitting",
            }
        ]
    )
    report = await send_first_invitations(
        event=event,
        invite_ids=None,
        provider=provider,
        events_collection=_CasEvents(),
        outbox_collection=_FakeOutbox(),
        app_url="https://www.heykindred.org",
    )
    assert provider.sent == []
    assert report.submitted == 0
    assert report.skipped == 1


@pytest.mark.asyncio
async def test_duplicate_key_on_outbox_upsert_is_swallowed():
    # A concurrent identical send makes Resend return the same provider message
    # id; the unique-index insert race must not 500 the request.
    from pymongo.errors import DuplicateKeyError

    class _DupOutbox:
        def __init__(self):
            self.find_calls = 0

        async def update_one(self, query, update, upsert=False, array_filters=None):
            if upsert:
                raise DuplicateKeyError("E11000 duplicate key")

        async def find_one(self, *_a, **_k):
            return None

    provider = _FakeProvider(
        receipt=ProviderReceipt(
            status=ProviderStatus.ACCEPTED, provider_message_id="msg_shared0000001"
        )
    )
    events_col = _CasEvents(_published_event())
    report = await send_first_invitations(
        event=_published_event(),
        invite_ids=None,
        provider=provider,
        events_collection=events_col,
        outbox_collection=_DupOutbox(),
        app_url="https://www.heykindred.org",
    )
    # The send is still counted; no exception escaped.
    assert report.submitted == 1
    assert events_col.invite("cred-a")["delivery_status"] == "submitting"


@pytest.mark.asyncio
async def test_rejected_receipt_records_no_delivery():
    provider = _FakeProvider(
        receipt=ProviderReceipt(
            status=ProviderStatus.REJECTED, error_code=SafeErrorCode.PROVIDER_REJECTED
        )
    )
    outbox = _FakeOutbox()
    report = await send_first_invitations(
        event=_published_event(),
        invite_ids=None,
        provider=provider,
        events_collection=_CasEvents(),
        outbox_collection=outbox,
        app_url="https://www.heykindred.org",
    )
    assert report.rejected == 1
    assert report.submitted == 0
    assert outbox.upserts == []


def test_send_report_is_content_free():
    doc = DeliverySendReport(status="processed", submitted=3).safe_document()
    assert set(doc) == {"status", "error_code", "counts"}
    assert set(doc["counts"]) == {
        "submitted",
        "rejected",
        "ambiguous",
        "failed",
        "skipped",
    }


# --------------------------------------------------------------------------
# Delivery confirmation via signed webhook payload: monotonic + idempotent
# --------------------------------------------------------------------------


def _delivered_event(message_id="msg_abc123deadbeef01"):
    return VerifiedDeliveryEvent(
        event_id="evt_" + "a" * 12,
        provider_message_id=message_id,
        provider_status=ProviderStatus.DELIVERED,
        occurred_at="2026-11-02T00:00:00+00:00",
    )


def _event_with_pending_invite():
    return {
        "id": "synthetic-holiday",
        "community_id": "synthetic-family",
        "rsvp_revision": 0,
        "event_invites": [{"id": "cred-a", "rsvp_status": "pending"}],
    }


@pytest.mark.asyncio
async def test_delivered_event_stamps_invite_through_cas():
    events_col = _CasEvents(_event_with_pending_invite())
    outbox = _FakeOutbox(
        record={
            "provider_message_id": "msg_abc123deadbeef01",
            "event_id": "synthetic-holiday",
            "invite_id": "cred-a",
            "status": "submitting",
        }
    )
    result = await apply_first_send_delivery_event(
        events_collection=events_col,
        outbox_collection=outbox,
        event=_delivered_event(),
        now_fn=lambda: "2026-11-02T01:00:00+00:00",
    )
    assert result == "delivered"
    invite = events_col.invite("cred-a")
    assert invite["delivered_at"] == "2026-11-02T01:00:00+00:00"
    assert invite["delivery_verified_at"] == "2026-11-02T01:00:00+00:00"
    assert invite["delivery_status"] == "delivered"
    # Stamped through the revision protocol, not a bare positional write.
    assert events_col.event["rsvp_revision"] == 1
    # Outbox transition guards against re-marking a delivered target.
    assert outbox.updates[0][0]["status"] == {"$ne": "delivered"}


@pytest.mark.asyncio
async def test_duplicate_delivered_is_idempotent_noop():
    events_col = _CasEvents(_event_with_pending_invite())
    outbox = _FakeOutbox(
        record={
            "provider_message_id": "msg_abc123deadbeef01",
            "event_id": "synthetic-holiday",
            "invite_id": "cred-a",
            "status": "delivered",  # already delivered
        }
    )
    result = await apply_first_send_delivery_event(
        events_collection=events_col,
        outbox_collection=outbox,
        event=_delivered_event(),
    )
    assert result == "delivered"
    assert events_col.writes == 0  # no event write on a duplicate callback
    assert events_col.invite("cred-a").get("delivered_at") is None


@pytest.mark.asyncio
async def test_unknown_provider_message_is_ignored():
    events_col = _CasEvents(_event_with_pending_invite())
    outbox = _FakeOutbox(record=None)
    result = await apply_first_send_delivery_event(
        events_collection=events_col,
        outbox_collection=outbox,
        event=_delivered_event("msg_unknown0000001"),
    )
    assert result == "ignored_unknown"
    assert events_col.writes == 0


@pytest.mark.asyncio
async def test_failure_event_never_downgrades_delivered():
    events_col = _CasEvents(_event_with_pending_invite())
    outbox = _FakeOutbox(
        record={
            "provider_message_id": "msg_abc123deadbeef01",
            "event_id": "synthetic-holiday",
            "invite_id": "cred-a",
            "status": "delivered",
        }
    )
    failed = VerifiedDeliveryEvent(
        event_id="evt_" + "b" * 12,
        provider_message_id="msg_abc123deadbeef01",
        provider_status=ProviderStatus.FAILED,
        occurred_at="2026-11-02T02:00:00+00:00",
    )
    result = await apply_first_send_delivery_event(
        events_collection=events_col,
        outbox_collection=outbox,
        event=failed,
    )
    assert result == "failed"
    assert events_col.writes == 0  # no invite mutation on failure
    # The outbox guard refuses to overwrite a delivered target.
    assert outbox.updates[0][0]["status"] == {"$nin": ["delivered", "failed"]}
    # The outbox guard refuses to overwrite a delivered target.
    assert outbox.updates[0][0]["status"] == {"$nin": ["delivered", "failed"]}
