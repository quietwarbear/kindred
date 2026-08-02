"""Release 15 — reminder + follow-up loop (synthetic, no network)."""

import os
from copy import deepcopy
from datetime import datetime, timezone

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_release15_unit")

import pytest

import push_sender
from holiday_pilot import build_holiday_pilot_readiness
from invitation_delivery import (
    _reminder_idempotency_key,
    _select_reminder_invites,
    apply_first_send_delivery_event,
    reminders_enabled,
    send_reminders,
)
from invitation_redelivery import (
    ProviderReceipt,
    ProviderStatus,
    PreflightResult,
    SafeErrorCode,
)
from invitation_redelivery_webhook import VerifiedDeliveryEvent
from routes import events

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
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
        "created_by": ORGANIZER["id"],
        "title": "Synthetic holiday dinner",
        "start_at": "2026-11-26T16:00:00-08:00",
        "end_at": "2026-11-26T20:00:00-08:00",
        "rsvp_deadline": "2026-11-19T18:00:00-08:00",
        "timezone": "America/Los_Angeles",
        "location": "Synthetic home",
        "event_template": "holiday_meal",
        "publication_state": "published",
        "max_attendees": 12,
        "rsvp_revision": 0,
        "event_invites": [
            {
                "id": "cred-a",
                "email": "guest-a@example.invalid",
                "invitee_name": "Guest A",
                "status": "invited",
                "rsvp_status": "pending",
            }
        ],
        "rsvp_records": [],
        "agenda": [],
        "activity_rsvps": [],
        "volunteer_slots": [],
        "potluck_items": [],
    }
    event.update(overrides)
    return event


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count
        self.modified_count = matched_count


class _CasEvents:
    def __init__(self, event=None):
        self.event = deepcopy(event) if event else None
        self.writes = 0

    async def find_one(self, _query, _projection=None):
        return deepcopy(self.event) if self.event is not None else None

    async def update_one(self, query, update, array_filters=None):
        self.writes += 1
        if self.event is None:
            return _Result(0)
        guard = query.get("rsvp_revision")
        current = int(self.event.get("rsvp_revision", 0) or 0)
        if guard is not None and not isinstance(guard, dict) and guard != current:
            return _Result(0)
        for key, value in update.get("$set", {}).items():
            self.event[key] = deepcopy(value)
        for key, value in update.get("$inc", {}).items():
            self.event[key] = int(self.event.get(key, 0) or 0) + value
        return _Result(1)

    def invite(self, invite_id):
        for item in (self.event or {}).get("event_invites", []):
            if item.get("id") == invite_id:
                return item
        return None


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
        return self._receipt or ProviderReceipt(
            status=ProviderStatus.ACCEPTED,
            provider_message_id="rmsg_" + str(len(self.sent)),
        )


class _FakeOutbox:
    def __init__(self, record=None):
        self.record = record
        self.upserts = []
        self.updates = []

    async def update_one(self, query, update, upsert=False, array_filters=None):
        (self.upserts if upsert else self.updates).append((query, update))

    async def find_one(self, query, _projection=None):
        return self.record


# --------------------------------------------------------------------------
# Gating + selection
# --------------------------------------------------------------------------


def test_reminders_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INVITATION_REMINDERS_ENABLED", raising=False)
    assert reminders_enabled() is False
    monkeypatch.setenv("INVITATION_REMINDERS_ENABLED", "true")
    assert reminders_enabled() is True


def test_reminder_selection_targets_only_unanswered_not_reminded_today():
    event = _published_event(
        event_invites=[
            {"id": "pending", "email": "a@example.invalid", "rsvp_status": "pending"},
            {"id": "answered", "email": "b@example.invalid", "rsvp_status": "going"},
            {
                "id": "reminded-today",
                "email": "c@example.invalid",
                "rsvp_status": "pending",
                "last_reminder_bucket": "2026-11-20",
            },
            {"id": "no-email", "rsvp_status": "pending"},
        ]
    )
    eligible, skipped = _select_reminder_invites(event, None, "2026-11-20")
    assert [i["id"] for i in eligible] == ["pending"]
    # answered + reminded-today are skipped-with-count; no-email is silently ignored
    assert skipped == 2


def test_reminder_idempotency_key_is_per_day():
    same = _reminder_idempotency_key("e", "i", "2026-11-20")
    assert same == _reminder_idempotency_key("e", "i", "2026-11-20")
    assert same != _reminder_idempotency_key("e", "i", "2026-11-21")
    assert same.startswith("ifr_")


# --------------------------------------------------------------------------
# send_reminders behavior
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_reminders_stamps_through_cas_and_records_reminder_kind():
    provider = _FakeProvider()
    events_col = _CasEvents(_published_event())
    outbox = _FakeOutbox()
    report = await send_reminders(
        event=_published_event(),
        invite_ids=None,
        provider=provider,
        events_collection=events_col,
        outbox_collection=outbox,
        app_url="https://www.heykindred.org",
        now_fn=lambda: "2026-11-20T12:00:00+00:00",
    )
    assert report.status == "processed"
    assert report.submitted == 1
    # Opaque target, reminder subject, recipient's own link.
    env = provider.sent[0]
    assert env.target_id != "cred-a"
    assert "reminder" in env.subject.lower()
    assert "/rsvp#cred-a" in env.html_body
    # Outbox row is tagged reminder.
    assert outbox.upserts[0][1]["$setOnInsert"]["kind"] == "reminder"
    # Invite stamped through the revision protocol.
    invite = events_col.invite("cred-a")
    assert invite["reminder_sent_at"] == "2026-11-20T12:00:00+00:00"
    assert invite["last_reminder_bucket"] == "2026-11-20"
    assert invite["reminder_delivery_status"] == "submitting"
    assert events_col.event["rsvp_revision"] == 1


@pytest.mark.asyncio
async def test_send_reminders_fails_closed_on_preflight_and_draft():
    # preflight not ready → no send
    provider = _FakeProvider(ready=False)
    report = await send_reminders(
        event=_published_event(),
        invite_ids=None,
        provider=provider,
        events_collection=_CasEvents(_published_event()),
        outbox_collection=_FakeOutbox(),
        app_url="https://www.heykindred.org",
    )
    assert report.status == "unavailable"
    assert provider.sent == []

    # draft → no send, no preflight
    provider2 = _FakeProvider()
    report2 = await send_reminders(
        event=_published_event(publication_state="organizer_draft"),
        invite_ids=None,
        provider=provider2,
        events_collection=_CasEvents(),
        outbox_collection=_FakeOutbox(),
        app_url="https://www.heykindred.org",
    )
    assert report2.status == "unavailable"
    assert report2.error_code == "draft_or_missing"
    assert provider2.sent == []


@pytest.mark.asyncio
async def test_reminder_not_re_sent_same_day():
    # An invite already reminded today is skipped, not sent again.
    provider = _FakeProvider()
    event = _published_event(
        event_invites=[
            {
                "id": "cred-a",
                "email": "guest-a@example.invalid",
                "rsvp_status": "pending",
                "last_reminder_bucket": "2026-11-20",
            }
        ]
    )
    report = await send_reminders(
        event=event,
        invite_ids=None,
        provider=provider,
        events_collection=_CasEvents(event),
        outbox_collection=_FakeOutbox(),
        app_url="https://www.heykindred.org",
        now_fn=lambda: "2026-11-20T18:00:00+00:00",
    )
    assert provider.sent == []
    assert report.submitted == 0
    assert report.skipped == 1


@pytest.mark.asyncio
async def test_reminder_claim_prevents_second_send_even_with_stale_snapshot():
    # Two rounds against the SAME collection with a fresh (bucket-unset) snapshot
    # each time. The claim on the durable record must stop the second send.
    provider = _FakeProvider()
    events_col = _CasEvents(_published_event())

    first = await send_reminders(
        event=_published_event(),
        invite_ids=None,
        provider=provider,
        events_collection=events_col,
        outbox_collection=_FakeOutbox(),
        app_url="https://www.heykindred.org",
        now_fn=lambda: "2026-11-20T12:00:00+00:00",
    )
    second = await send_reminders(
        event=_published_event(),  # stale: bucket not yet set in this snapshot
        invite_ids=None,
        provider=provider,
        events_collection=events_col,
        outbox_collection=_FakeOutbox(),
        app_url="https://www.heykindred.org",
        now_fn=lambda: "2026-11-20T18:00:00+00:00",
    )
    assert first.submitted == 1
    assert second.submitted == 0
    assert second.skipped == 1
    assert len(provider.sent) == 1  # exactly one email over both rounds


# --------------------------------------------------------------------------
# Delivery callback distinguishes reminder from first-send
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reminder_delivered_stamps_reminder_field_only():
    events_col = _CasEvents(
        {
            "id": "synthetic-holiday",
            "rsvp_revision": 0,
            "event_invites": [{"id": "cred-a", "rsvp_status": "pending"}],
        }
    )
    outbox = _FakeOutbox(
        record={
            "provider_message_id": "rmsg_1",
            "event_id": "synthetic-holiday",
            "invite_id": "cred-a",
            "kind": "reminder",
            "status": "submitting",
        }
    )
    result = await apply_first_send_delivery_event(
        events_collection=events_col,
        outbox_collection=outbox,
        event=VerifiedDeliveryEvent(
            event_id="evt_" + "a" * 12,
            provider_message_id="rmsg_1",
            provider_status=ProviderStatus.DELIVERED,
            occurred_at="2026-11-20T13:00:00+00:00",
        ),
        now_fn=lambda: "2026-11-20T13:00:00+00:00",
    )
    assert result == "delivered"
    invite = events_col.invite("cred-a")
    assert invite["reminder_delivered_at"] == "2026-11-20T13:00:00+00:00"
    assert invite["reminder_delivery_status"] == "delivered"
    # A reminder callback must NOT set the first-send delivered field.
    assert invite.get("delivered_at") is None


# --------------------------------------------------------------------------
# Awaiting-response nudge (holiday pilot readiness)
# --------------------------------------------------------------------------


def test_awaiting_response_count_and_nudge():
    event = _published_event(
        holiday_pilot_confirmations=[
            "privacy_reviewed",
            "guest_plan_reviewed",
            "organizer_previewed",
            "invitations_shared",
        ],
        event_invites=[
            {
                "id": "reached-pending",
                "rsvp_status": "pending",
                "opened_at": "2026-11-19T00:00:00+00:00",
            },
            {"id": "not-reached", "rsvp_status": "pending"},
            {
                "id": "answered",
                "rsvp_status": "going",
                "opened_at": "2026-11-19T00:00:00+00:00",
            },
        ],
    )
    readiness = build_holiday_pilot_readiness(event, now=NOW)
    assert readiness["aggregate_counts"]["invitations_awaiting_response"] == 1
    assert readiness["next_action_code"] == "send_reminders"


# --------------------------------------------------------------------------
# send-reminders endpoint gating
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reminder_endpoint_unavailable_when_disabled(monkeypatch):
    async def fake_event(_event_id, _user):
        return _published_event()

    async def no_log(**_k):
        return None

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "log_notification_event", no_log)
    monkeypatch.setattr(events, "events_collection", _CasEvents(_published_event()))
    monkeypatch.setattr(events, "reminders_enabled", lambda: False)
    result = await events.send_gathering_reminders("synthetic-holiday", ORGANIZER)
    assert result["delivery"]["status"] == "unavailable"
    assert result["delivery"]["error_code"] == "delivery_disabled"


@pytest.mark.asyncio
async def test_reminder_endpoint_calls_delivery_when_enabled(monkeypatch):
    async def fake_event(_event_id, _user):
        return _published_event()

    async def no_log(**_k):
        return None

    calls = {}

    async def fake_send(**kwargs):
        calls["ran"] = True
        from invitation_delivery import DeliverySendReport

        return DeliverySendReport(status="processed", submitted=1)

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "log_notification_event", no_log)
    monkeypatch.setattr(events, "events_collection", _CasEvents(_published_event()))
    monkeypatch.setattr(events, "reminders_enabled", lambda: True)
    monkeypatch.setattr(
        events, "build_invitation_delivery_provider", lambda: _FakeProvider()
    )
    monkeypatch.setattr(events, "send_reminders", fake_send)
    result = await events.send_gathering_reminders("synthetic-holiday", ORGANIZER)
    assert calls.get("ran") is True
    assert result["delivery"]["status"] == "processed"
    assert result["delivery"]["counts"]["submitted"] == 1


# --------------------------------------------------------------------------
# notify_community
# --------------------------------------------------------------------------


class _FakeUsersFind:
    def __init__(self, recipients):
        self._recipients = recipients
        self.pulls = []

    def find(self, _query, _projection=None):
        recipients = self._recipients

        class _Cursor:
            async def to_list(self, _cap):
                return list(recipients)

        return _Cursor()

    async def find_one(self, _query, _projection=None):
        return {"id": "irrelevant", "push_tokens": []}

    async def update_one(self, query, update):
        self.pulls.append((query, update))


class _RecordingClient:
    def __init__(self):
        self.calls = []

    async def deliver(self, device_token, notification):
        self.calls.append((device_token, notification))
        return push_sender.PushOutcome.DELIVERED


@pytest.mark.asyncio
async def test_notify_community_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(push_sender, "push_enabled", lambda: False)
    built = {"factory": False}

    def factory():
        built["factory"] = True
        return _RecordingClient()

    await push_sender.notify_community(
        users_collection=_FakeUsersFind([{"id": "u1"}]),
        community_id="c1",
        template_code="new_gathering",
        client_factory=factory,
    )
    assert built["factory"] is False


@pytest.mark.asyncio
async def test_notify_community_excludes_actor_and_swallows_errors(monkeypatch):
    monkeypatch.setattr(push_sender, "push_enabled", lambda: True)

    # send_push_to_user reads each user's tokens via find_one; give one token.
    class _Users(_FakeUsersFind):
        async def find_one(self, _query, _projection=None):
            return {"id": "x", "push_tokens": ["tok"]}

    users = _Users([{"id": "actor"}, {"id": "member-1"}, {"id": "member-2"}])
    client = _RecordingClient()
    await push_sender.notify_community(
        users_collection=users,
        community_id="c1",
        template_code="new_gathering",
        exclude_user_ids=("actor",),
        client_factory=lambda: client,
    )
    # Only the two non-excluded members were contacted.
    assert len(client.calls) == 2
    assert client.calls[0][1] == push_sender.PUSH_TEMPLATES["new_gathering"]

    # A broken client factory must never raise into the caller.
    def broken():
        raise RuntimeError("boom")

    await push_sender.notify_community(
        users_collection=users,
        community_id="c1",
        template_code="new_gathering",
        client_factory=broken,
    )
