"""Disposable-Mongo proof that a reminder stamp survives a concurrent RSVP."""

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

from invitation_delivery import _mark_invite_reminded
from models import RSVPRequest
from routes import events

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


def _event():
    return {
        "id": "synthetic-holiday",
        "community_id": "synthetic-family",
        "created_by": ORGANIZER["id"],
        "title": "Synthetic holiday dinner",
        "event_template": "holiday_meal",
        "publication_state": "published",
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
        "hidden_from_user_ids": [],
    }


@pytest.mark.asyncio
async def test_reminder_stamp_and_rsvp_both_persist(monkeypatch):
    client = AsyncIOMotorClient(DISPOSABLE_URL)
    collection = client[DB_NAME][f"release15_{uuid.uuid4().hex}"]
    await collection.insert_one(dict(_event()))

    async def fake_event(_event_id, _user):
        return dict(_event())

    monkeypatch.setattr(events, "events_collection", collection)
    monkeypatch.setattr(events, "get_event_for_user", fake_event)

    await asyncio.gather(
        _mark_invite_reminded(
            collection, "synthetic-holiday", "cred-a", "2026-11-20", lambda: "t0"
        ),
        events.update_rsvp("synthetic-holiday", RSVPRequest(status="going"), MEMBER),
    )

    durable = await collection.find_one({"id": "synthetic-holiday"}, {"_id": 0})
    invite = durable["event_invites"][0]
    assert invite.get("reminder_sent_at") == "t0"  # reminder stamp survived
    assert invite.get("last_reminder_bucket") == "2026-11-20"
    assert invite.get("rsvp_status") == "going"  # RSVP survived
    assert durable["rsvp_revision"] == 2  # both writes serialized

    await collection.drop()
    client.close()
