"""Release 14 — privacy-safe activation-signal regressions (synthetic only)."""

import os
from copy import deepcopy
from datetime import datetime, timezone

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_release14_unit")

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from holiday_pilot import build_holiday_pilot_readiness
from models import InvitationActivationSignalRequest
from routes import events, public

NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
ORGANIZER = {
    "id": "synthetic-organizer",
    "community_id": "synthetic-family",
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
    "role": "organizer",
}
MEMBER = {
    "id": "synthetic-member",
    "community_id": "synthetic-family",
    "full_name": "Synthetic Member",
    "email": "member@example.invalid",
    "role": "member",
}


def holiday_event(**overrides):
    event = {
        "id": "synthetic-holiday",
        "community_id": "synthetic-family",
        "created_by": ORGANIZER["id"],
        "created_by_name": ORGANIZER["full_name"],
        "title": "Synthetic holiday dinner",
        "description": "Synthetic-only pilot",
        "start_at": "2026-11-26T16:00:00-08:00",
        "end_at": "2026-11-26T20:00:00-08:00",
        "rsvp_deadline": "2026-11-19T18:00:00-08:00",
        "timezone": "America/Los_Angeles",
        "location": "Synthetic home",
        "event_template": "holiday_meal",
        "publication_state": "published",
        "max_attendees": 12,
        "holiday_pilot_confirmations": [],
        "holiday_setup_revision": 0,
        "rsvp_revision": 0,
        "event_invites": [],
        "rsvp_records": [],
        "agenda": [],
        "activity_rsvps": [],
        "volunteer_slots": [{"title": "Setup", "needed_count": 2}],
        "potluck_items": [{"item_name": "Synthetic side"}],
        "assigned_roles": ["organizer"],
    }
    event.update(overrides)
    return event


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count
        self.modified_count = matched_count


class _CasEvents:
    """Minimal in-memory events collection honoring the rsvp_revision guard."""

    def __init__(self, event):
        self.event = deepcopy(event)
        self.updates = []

    async def find_one(self, _query, _projection=None):
        return deepcopy(self.event)

    async def update_one(self, query, update, array_filters=None):
        self.updates.append((query, update, array_filters))
        guard = query.get("rsvp_revision")
        current = int(self.event.get("rsvp_revision", 0) or 0)
        if guard is not None and not isinstance(guard, dict) and guard != current:
            return _Result(matched_count=0)
        for key, value in update.get("$set", {}).items():
            self.event[key] = deepcopy(value)
        for key, value in update.get("$inc", {}).items():
            self.event[key] = int(self.event.get(key, 0) or 0) + value
        return _Result(matched_count=1)


class _CaptureEvents:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update, array_filters=None):
        self.calls.append((query, update, array_filters))
        return _Result(matched_count=1)


# --------------------------------------------------------------------------
# Readiness aggregate reflects signals and stays content-free
# --------------------------------------------------------------------------


def test_aggregate_counts_reflect_signals_and_are_content_free():
    event = holiday_event(
        event_invites=[
            {
                "id": "cred-a",
                "email": "guest-a@example.invalid",
                "invitee_name": "Guest A",
                "rsvp_status": "pending",
                "shared_at": "2026-11-02T00:00:00+00:00",
            },
            {
                "id": "cred-b",
                "email": "guest-b@example.invalid",
                "invitee_name": "Guest B",
                "rsvp_status": "pending",
                "link_copied_at": "2026-11-02T00:00:00+00:00",
                "opened_at": "2026-11-02T01:00:00+00:00",
            },
            {
                "id": "cred-c",
                "email": "guest-c@example.invalid",
                "invitee_name": "Guest C",
                "rsvp_status": "going",
                "delivered_at": "2026-11-02T00:30:00+00:00",
                "opened_at": "2026-11-02T00:40:00+00:00",
            },
        ],
    )
    counts = build_holiday_pilot_readiness(event, now=NOW)["aggregate_counts"]
    assert counts["active_invitations"] == 3
    assert counts["invitations_shared"] == 2  # cred-a shared, cred-b copied
    assert counts["invitations_opened"] == 2  # cred-b, cred-c
    assert counts["invitations_delivered"] == 1  # cred-c
    assert counts["responses_received"] == 1  # cred-c responded

    serialized = repr(build_holiday_pilot_readiness(event, now=NOW)).lower()
    for prohibited in (
        "guest a",
        "guest-a@example.invalid",
        "cred-a",
        "synthetic holiday dinner",
        "synthetic home",
        "2026-11-02",
    ):
        assert prohibited not in serialized


def test_share_signal_alone_advances_stage_to_invitations_sent():
    event = holiday_event(
        holiday_pilot_confirmations=[
            "privacy_reviewed",
            "guest_plan_reviewed",
            "organizer_previewed",
        ],
        event_invites=[
            {
                "id": "cred-a",
                "rsvp_status": "pending",
                "shared_at": "2026-11-02T00:00:00+00:00",
            }
        ],
    )
    readiness = build_holiday_pilot_readiness(event, now=NOW)
    assert readiness["pilot_stage"] == "invitations_sent"


def test_counts_are_capped_and_never_negative():
    invites = [
        {"id": f"cred-{i}", "rsvp_status": "pending", "opened_at": "x"}
        for i in range(10_050)
    ]
    counts = build_holiday_pilot_readiness(
        holiday_event(event_invites=invites), now=NOW
    )["aggregate_counts"]
    assert counts["invitations_opened"] == 10_000
    assert counts["active_invitations"] == 10_000


# --------------------------------------------------------------------------
# Signal request model allowlist
# --------------------------------------------------------------------------


def test_signal_model_rejects_unlisted_codes():
    assert InvitationActivationSignalRequest(signal="shared").signal == "shared"
    assert (
        InvitationActivationSignalRequest(signal="link_copied").signal == "link_copied"
    )
    for bad in ("delivered", "opened", "responded", "", "SHARED"):
        with pytest.raises(ValidationError):
            InvitationActivationSignalRequest(signal=bad)


# --------------------------------------------------------------------------
# Activation-signal endpoint authorization + fail-closed behavior
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activation_signal_blocked_on_private_draft(monkeypatch):
    collection = _CasEvents(holiday_event(publication_state="organizer_draft"))

    async def fake_event(_event_id, _user):
        return holiday_event(publication_state="organizer_draft")

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "events_collection", collection)
    with pytest.raises(HTTPException) as rejected:
        await events.record_invitation_activation_signal(
            "synthetic-holiday",
            "cred-a",
            InvitationActivationSignalRequest(signal="shared"),
            ORGANIZER,
        )
    assert rejected.value.status_code == 409
    assert rejected.value.detail["code"] == "organizer_draft_activation_signal_blocked"
    assert collection.updates == []


@pytest.mark.asyncio
async def test_activation_signal_requires_organizer(monkeypatch):
    collection = _CasEvents(holiday_event())
    monkeypatch.setattr(events, "events_collection", collection)
    with pytest.raises(HTTPException) as rejected:
        await events.record_invitation_activation_signal(
            "synthetic-holiday",
            "cred-a",
            InvitationActivationSignalRequest(signal="shared"),
            MEMBER,
        )
    assert rejected.value.status_code == 403
    assert collection.updates == []


@pytest.mark.asyncio
async def test_activation_signal_unknown_invite_fails_closed(monkeypatch):
    collection = _CasEvents(holiday_event(event_invites=[{"id": "cred-a"}]))

    async def fake_event(_event_id, _user):
        return holiday_event(event_invites=[{"id": "cred-a"}])

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "events_collection", collection)
    with pytest.raises(HTTPException) as rejected:
        await events.record_invitation_activation_signal(
            "synthetic-holiday",
            "does-not-exist",
            InvitationActivationSignalRequest(signal="shared"),
            ORGANIZER,
        )
    assert rejected.value.status_code == 404
    assert rejected.value.detail["code"] == "invitation_not_found"


@pytest.mark.asyncio
async def test_activation_signal_is_monotonic_first_write_wins(monkeypatch):
    event = holiday_event(event_invites=[{"id": "cred-a", "rsvp_status": "pending"}])
    collection = _CasEvents(event)

    async def fake_event(_event_id, _user):
        return deepcopy(event)

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "events_collection", collection)

    await events.record_invitation_activation_signal(
        "synthetic-holiday",
        "cred-a",
        InvitationActivationSignalRequest(signal="shared"),
        ORGANIZER,
    )
    first = collection.event["event_invites"][0]["shared_at"]
    assert first

    await events.record_invitation_activation_signal(
        "synthetic-holiday",
        "cred-a",
        InvitationActivationSignalRequest(signal="shared"),
        ORGANIZER,
    )
    # Second signal must not overwrite the first timestamp.
    assert collection.event["event_invites"][0]["shared_at"] == first
    # Both writes still incremented the RSVP revision (CAS path).
    assert collection.event["rsvp_revision"] == 2


# --------------------------------------------------------------------------
# opened_at stamped on genuine resolve, idempotent, content-free
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_stamps_opened_at_once(monkeypatch):
    capture = _CaptureEvents()

    async def fake_find(_token):
        return (
            {"id": "synthetic-holiday", "community_id": "synthetic-family"},
            {"id": "cred-a", "invitee_name": "Guest A", "rsvp_status": "pending"},
        )

    monkeypatch.setattr(public, "_find_event_and_invite", fake_find)
    monkeypatch.setattr(public, "events_collection", capture)

    async def fake_community(*_a, **_k):
        return {"name": "Synthetic Family"}

    async def fake_user(*_a, **_k):
        return {"full_name": "Synthetic Organizer"}

    monkeypatch.setattr(
        public.communities_collection, "find_one", fake_community, raising=False
    )
    monkeypatch.setattr(public.users_collection, "find_one", fake_user, raising=False)

    await public._public_rsvp_view("cred-a")
    assert len(capture.calls) == 1
    query, update, array_filters = capture.calls[0]
    assert query == {"id": "synthetic-holiday", "event_invites.id": "cred-a"}
    assert set(update["$set"]) == {"event_invites.$[inv].opened_at"}
    assert array_filters == [{"inv.id": "cred-a", "inv.opened_at": {"$exists": False}}]


@pytest.mark.asyncio
async def test_resolve_skips_stamp_when_already_opened(monkeypatch):
    capture = _CaptureEvents()

    async def fake_find(_token):
        return (
            {"id": "synthetic-holiday", "community_id": "synthetic-family"},
            {
                "id": "cred-a",
                "invitee_name": "Guest A",
                "rsvp_status": "pending",
                "opened_at": "2026-11-02T00:00:00+00:00",
            },
        )

    monkeypatch.setattr(public, "_find_event_and_invite", fake_find)
    monkeypatch.setattr(public, "events_collection", capture)

    async def fake_community(*_a, **_k):
        return {"name": "Synthetic Family"}

    async def fake_user(*_a, **_k):
        return {"full_name": "Synthetic Organizer"}

    monkeypatch.setattr(
        public.communities_collection, "find_one", fake_community, raising=False
    )
    monkeypatch.setattr(public.users_collection, "find_one", fake_user, raising=False)

    await public._public_rsvp_view("cred-a")
    assert capture.calls == []
