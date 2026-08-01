"""Synthetic Thanksgiving pilot readiness and privacy regressions."""

import os
from datetime import datetime, timezone

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_release13_unit")

import pytest
from fastapi import HTTPException

from event_privacy import serialize_event_for_user
from holiday_pilot import build_holiday_pilot_readiness
from models import EventCreateRequest, EventInviteCreateRequest
from routes import events, public

NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
ORGANIZER = {
    "id": "synthetic-organizer",
    "community_id": "synthetic-family",
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
    "role": "organizer",
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
        "publication_state": "organizer_draft",
        "max_attendees": 12,
        "holiday_pilot_confirmations": [],
        "holiday_setup_revision": 0,
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


def test_readiness_is_content_free_and_requires_explicit_organizer_review():
    event = holiday_event(
        guest_name="Private Guest",
        guest_email="private@example.invalid",
        event_invites=[
            {
                "id": "synthetic-private-credential",
                "email": "private@example.invalid",
                "invitee_name": "Private Guest",
                "rsvp_status": "pending",
            }
        ],
    )
    readiness = build_holiday_pilot_readiness(event, now=NOW)

    assert readiness["pilot_stage"] == "draft"
    assert readiness["can_finish_setup"] is False
    assert readiness["next_action_code"] == "privacy_reviewed"
    assert readiness["aggregate_counts"]["active_invitations"] == 1
    serialized = repr(readiness).lower()
    for prohibited in (
        "private guest",
        "private@example.invalid",
        "synthetic-private-credential",
        "synthetic holiday dinner",
        "synthetic home",
    ):
        assert prohibited not in serialized


def test_ready_draft_and_lifecycle_stages_are_deterministic():
    confirmations = [
        "privacy_reviewed",
        "guest_plan_reviewed",
        "organizer_previewed",
    ]
    draft = holiday_event(holiday_pilot_confirmations=confirmations)
    readiness = build_holiday_pilot_readiness(draft, now=NOW)
    assert readiness["can_finish_setup"] is True
    assert readiness["next_action_code"] == "finish_setup"

    published = holiday_event(
        publication_state="published",
        holiday_pilot_confirmations=confirmations,
    )
    assert (
        build_holiday_pilot_readiness(published, now=NOW)["pilot_stage"]
        == "ready_to_invite"
    )

    sent = holiday_event(
        publication_state="published",
        holiday_pilot_confirmations=[*confirmations, "invitations_shared"],
        event_invites=[{"id": "synthetic-credential", "rsvp_status": "pending"}],
    )
    assert (
        build_holiday_pilot_readiness(sent, now=NOW)["pilot_stage"]
        == "invitations_sent"
    )

    completed = holiday_event(
        publication_state="published",
        end_at="2026-10-31T20:00:00-07:00",
    )
    assert (
        build_holiday_pilot_readiness(completed, now=NOW)["pilot_stage"] == "completed"
    )


def test_member_projection_removes_pilot_state_and_internal_revision():
    event = holiday_event(
        holiday_pilot_readiness={"pilot_stage": "draft"},
        holiday_setup_revision=7,
    )
    view = serialize_event_for_user(
        event,
        {
            "id": "synthetic-member",
            "community_id": "synthetic-family",
            "full_name": "Synthetic Member",
            "email": "member@example.invalid",
            "role": "member",
        },
    )
    assert "holiday_pilot_readiness" not in view
    assert "holiday_pilot_confirmations" not in view
    assert "holiday_setup_revision" not in view


def test_organizer_projection_reports_readiness_without_internal_storage_fields():
    event = holiday_event(
        holiday_pilot_readiness={"pilot_stage": "draft"},
        holiday_setup_revision=7,
    )
    view = serialize_event_for_user(event, ORGANIZER)
    assert view["holiday_pilot_readiness"] == {"pilot_stage": "draft"}
    assert "holiday_pilot_confirmations" not in view
    assert "holiday_setup_revision" not in view


class _Result:
    def __init__(self, modified_count=0):
        self.modified_count = modified_count


class _NoMutationEvents:
    def __init__(self, event=None, modified_count=0):
        self.event = event
        self.modified_count = modified_count
        self.inserts = []
        self.updates = []

    async def find_one(self, *_args, **_kwargs):
        return self.event

    async def insert_one(self, document):
        self.inserts.append(document)

    async def update_one(self, query, update):
        self.updates.append((query, update))
        return _Result(self.modified_count)


@pytest.mark.asyncio
async def test_invalid_holiday_deadline_fails_before_insert(monkeypatch):
    collection = _NoMutationEvents()
    monkeypatch.setattr(events, "events_collection", collection)
    payload = EventCreateRequest(
        title="Synthetic dinner",
        start_at="2026-11-26T16:00:00",
        end_at="2026-11-26T20:00:00",
        rsvp_deadline="2026-11-01T01:30:00",
        timezone="America/New_York",
        location="Synthetic home",
        event_template="holiday_meal",
        client_request_id="synthetic-request-0001",
    )
    with pytest.raises(HTTPException) as rejected:
        await events.create_event(payload, ORGANIZER)
    assert rejected.value.status_code == 422
    assert collection.inserts == []
    assert collection.updates == []


@pytest.mark.asyncio
async def test_private_draft_cannot_create_invitation_credentials(monkeypatch):
    collection = _NoMutationEvents()

    async def fake_event(_event_id, _user):
        return holiday_event()

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "events_collection", collection)
    with pytest.raises(HTTPException) as rejected:
        await events.create_event_invites(
            "synthetic-holiday",
            EventInviteCreateRequest(guest_emails=["guest@example.invalid"]),
            ORGANIZER,
        )
    assert rejected.value.status_code == 409
    assert rejected.value.detail["code"] == "organizer_draft_invitation_blocked"
    assert collection.updates == []


@pytest.mark.asyncio
async def test_public_rsvp_lookup_fails_closed_for_private_draft(monkeypatch):
    collection = _NoMutationEvents(
        holiday_event(
            event_invites=[
                {"id": "synthetic-private-credential", "invite_source": "guest"}
            ]
        )
    )
    monkeypatch.setattr(public, "events_collection", collection)
    assert await public._find_event_and_invite("synthetic-private-credential") == (
        None,
        None,
    )


@pytest.mark.asyncio
async def test_publish_uses_setup_revision_compare_and_swap(monkeypatch):
    event = holiday_event(
        holiday_pilot_confirmations=[
            "privacy_reviewed",
            "guest_plan_reviewed",
            "organizer_previewed",
        ],
        holiday_setup_revision=3,
    )
    collection = _NoMutationEvents(modified_count=0)

    async def fake_event(_event_id, _user):
        return dict(event)

    monkeypatch.setattr(events, "get_event_for_user", fake_event)
    monkeypatch.setattr(events, "events_collection", collection)
    with pytest.raises(HTTPException) as conflict:
        await events.publish_holiday_draft(event["id"], ORGANIZER)
    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "holiday_pilot_publish_conflict"
    assert collection.updates[0][0]["holiday_setup_revision"] == 3
    assert collection.updates[0][1]["$inc"] == {"holiday_setup_revision": 1}
