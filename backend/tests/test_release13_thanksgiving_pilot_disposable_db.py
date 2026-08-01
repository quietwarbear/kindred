"""Disposable-Mongo concurrency proof for the Thanksgiving pilot publish gate."""

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
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

from routes import events

ORGANIZER = {
    "id": "synthetic-organizer",
    "community_id": "synthetic-family",
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
    "role": "organizer",
}


@pytest.mark.asyncio
async def test_only_one_concurrent_process_can_publish_a_ready_draft(monkeypatch):
    client = AsyncIOMotorClient(DISPOSABLE_URL)
    collection = client[DB_NAME][f"release13_{uuid.uuid4().hex}"]
    event = {
        "id": "synthetic-holiday",
        "community_id": ORGANIZER["community_id"],
        "created_by": ORGANIZER["id"],
        "created_by_name": ORGANIZER["full_name"],
        "title": "Synthetic holiday dinner",
        "description": "Synthetic only",
        "start_at": "2026-11-26T16:00:00-08:00",
        "end_at": "2026-11-26T20:00:00-08:00",
        "rsvp_deadline": "2026-11-19T18:00:00-08:00",
        "timezone": "America/Los_Angeles",
        "location": "Synthetic home",
        "event_template": "holiday_meal",
        "publication_state": "organizer_draft",
        "max_attendees": 12,
        "holiday_pilot_confirmations": [
            "privacy_reviewed",
            "guest_plan_reviewed",
            "organizer_previewed",
        ],
        "holiday_setup_revision": 0,
        "event_invites": [],
        "rsvp_records": [],
        "agenda": [],
        "activity_rsvps": [],
        "volunteer_slots": [],
        "potluck_items": [],
        "assigned_roles": ["organizer"],
    }
    await collection.insert_one(dict(event))

    async def same_snapshot(_event_id, _user):
        return dict(event)

    monkeypatch.setattr(events, "events_collection", collection)
    monkeypatch.setattr(events, "get_event_for_user", same_snapshot)
    results = await asyncio.gather(
        events.publish_holiday_draft(event["id"], ORGANIZER),
        events.publish_holiday_draft(event["id"], ORGANIZER),
        return_exceptions=True,
    )

    successes = [item for item in results if isinstance(item, dict)]
    conflicts = [item for item in results if isinstance(item, HTTPException)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert conflicts[0].status_code == 409
    durable = await collection.find_one({"id": event["id"]}, {"_id": 0})
    assert durable["publication_state"] == "published"
    assert durable["holiday_setup_revision"] == 1

    await collection.drop()
    client.close()
