"""Disposable-Mongo proof that activation signals survive concurrent RSVP writes."""

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

DISPOSABLE_URL = os.environ.get("KINDRED_DISPOSABLE_MONGO_URL", "")
DB_NAME = os.environ.get("DB_NAME", "")
if not DISPOSABLE_URL:
    pytest.skip(
        "A disposable MongoDB replica set is required.", allow_module_level=True
    )
if DISPOSABLE_URL == os.environ.get("PRODUCTION_MONGO_URL"):
    raise RuntimeError("Refusing to run against a production MongoDB URL.")
if not DB_NAME.startswith("kindred_disposable_"):
    raise RuntimeError("Disposable database name must start with kindred_disposable_.")

os.environ["MONGO_URL"] = DISPOSABLE_URL

from models import InvitationActivationSignalRequest, RSVPRequest
from routes import events, public

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


def _published_event():
    return {
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
                "invite_source": "member",
                "member_id": MEMBER["id"],
                "email": MEMBER["email"],
                "invitee_name": "Synthetic Member",
                "status": "invited",
                "rsvp_status": "pending",
            }
        ],
        "rsvp_records": [],
        "agenda": [],
        "activity_rsvps": [],
        "volunteer_slots": [],
        "potluck_items": [],
        "hidden_from_user_ids": [],
    }


@pytest.mark.asyncio
async def test_share_signal_and_rsvp_both_persist_under_contention(monkeypatch):
    client = AsyncIOMotorClient(DISPOSABLE_URL)
    collection = client[DB_NAME][f"release14_{uuid.uuid4().hex}"]
    await collection.insert_one(dict(_published_event()))

    async def fake_event(_event_id, _user):
        return dict(_published_event())

    monkeypatch.setattr(events, "events_collection", collection)
    monkeypatch.setattr(events, "get_event_for_user", fake_event)

    await asyncio.gather(
        events.record_invitation_activation_signal(
            "synthetic-holiday",
            "cred-a",
            InvitationActivationSignalRequest(signal="shared"),
            ORGANIZER,
        ),
        events.update_rsvp("synthetic-holiday", RSVPRequest(status="going"), MEMBER),
    )

    durable = await collection.find_one({"id": "synthetic-holiday"}, {"_id": 0})
    invite = durable["event_invites"][0]
    assert invite.get("shared_at")  # organizer signal survived
    assert invite.get("rsvp_status") == "going"  # RSVP survived
    assert durable["rsvp_revision"] == 2  # both writes serialized

    await collection.drop()
    client.close()


@pytest.mark.asyncio
async def test_opened_at_is_first_write_wins(monkeypatch):
    client = AsyncIOMotorClient(DISPOSABLE_URL)
    collection = client[DB_NAME][f"release14_{uuid.uuid4().hex}"]
    await collection.insert_one(dict(_published_event()))
    monkeypatch.setattr(public, "events_collection", collection)

    await public._mark_invitation_opened("synthetic-holiday", "cred-a")
    after_first = await collection.find_one({"id": "synthetic-holiday"}, {"_id": 0})
    first_opened = after_first["event_invites"][0]["opened_at"]
    assert first_opened

    await public._mark_invitation_opened("synthetic-holiday", "cred-a")
    after_second = await collection.find_one({"id": "synthetic-holiday"}, {"_id": 0})
    assert after_second["event_invites"][0]["opened_at"] == first_opened

    await collection.drop()
    client.close()
