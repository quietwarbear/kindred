"""Disposable-Mongo proof for K5: no double sends across replicas.

Runs the reminder planner and the outbox drain against a real MongoDB replica
set with the production indexes, from several independent Motor clients at
once (standing in for several Railway replicas hit by overlapping cron calls).
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

DISPOSABLE_URL = os.environ.get("KINDRED_DISPOSABLE_MONGO_URL", "")
DB_NAME = os.environ.get("DB_NAME", "")
if not DISPOSABLE_URL:
    pytest.skip("A disposable MongoDB replica set is required.", allow_module_level=True)
if DISPOSABLE_URL == os.environ.get("PRODUCTION_MONGO_URL"):
    raise RuntimeError("Refusing to run against a production MongoDB URL.")
if not DB_NAME.startswith("kindred_disposable_"):
    raise RuntimeError("Disposable database name must start with kindred_disposable_.")

os.environ["MONGO_URL"] = DISPOSABLE_URL

import event_messaging as em  # noqa: E402
import server  # noqa: E402,F401  (startup wiring imports cleanly)
from invitation_redelivery import ProviderReceipt, ProviderStatus  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
REPLICAS = 4


class SharedProvider:
    def __init__(self):
        self.sent = []

    async def send(self, envelope):
        await asyncio.sleep(0.01)  # a slow provider widens any race window
        self.sent.append(envelope.recipient)
        return ProviderReceipt(status=ProviderStatus.ACCEPTED, provider_message_id=uuid.uuid4().hex)


def _event(event_id, n_guests):
    start = (NOW + timedelta(minutes=45)).isoformat()  # inside the 1h window
    invites = [
        {"id": f"inv-{i}", "email": f"guest{i}@example.invalid", "status": "invited", "rsvp_status": "going"}
        for i in range(n_guests)
    ]
    return {
        "id": event_id,
        "community_id": "synthetic-community",
        "created_by": "synthetic-organizer",
        "title": "Synthetic gathering",
        "timezone": "UTC",
        "publication_state": "published",
        "rsvp_revision": 0,
        "agenda": [
            {
                "id": "session-1",
                "title": "Session One",
                "start_at": start,
                "end_at": (NOW + timedelta(hours=2)).isoformat(),
                "timezone": "UTC",
                "visibility": "published",
                "attendance_requested": True,
            }
        ],
        "event_invites": invites,
        "activity_rsvps": [
            {"activity_id": "session-1", "respondent_id": f"invite:inv-{i}", "status": "coming", "updated_at": NOW.isoformat()}
            for i in range(n_guests)
        ],
    }


async def _replica_cron(provider, now):
    client = AsyncIOMotorClient(DISPOSABLE_URL)
    db = client[DB_NAME]
    try:
        ctx = em.DeliveryContext(
            events=db.events,
            users=db.users,
            preferences=db.notification_preferences,
            opt_outs=db.event_message_opt_outs,
            announcements=db.announcements,
            notifications=db.notification_events,
            outbox=db.event_message_outbox,
            provider=provider,
            now=now,
        )
        await em.plan_due_reminders(
            events_collection=db.events, outbox=db.event_message_outbox, users_collection=db.users, now=now
        )
        return await em.drain_outbox(ctx)
    finally:
        client.close()


@pytest.mark.asyncio
async def test_overlapping_cron_calls_on_several_replicas_send_each_reminder_once():
    client = AsyncIOMotorClient(DISPOSABLE_URL)
    db = client[DB_NAME]
    try:
        await em.ensure_indexes(db)
        event_id = f"k5-{uuid.uuid4().hex[:8]}"
        await db.events.insert_one(_event(event_id, 12))
        provider = SharedProvider()

        results = await asyncio.gather(*(_replica_cron(provider, NOW) for _ in range(REPLICAS)))
        assert sum(r.get("sent", 0) for r in results) == 12
        assert sorted(provider.sent) == sorted(f"guest{i}@example.invalid" for i in range(12))
        rows = await db.event_message_outbox.find({"event_id": event_id}).to_list(100)
        assert len(rows) == 12 and {r["status"] for r in rows} == {"sent"}

        # Later ticks (any replica) find nothing new.
        later = await asyncio.gather(
            *(_replica_cron(provider, NOW + timedelta(minutes=m)) for m in (5, 5, 10))
        )
        assert all(not r for r in later)
        assert len(provider.sent) == 12
    finally:
        await db.events.delete_many({})
        await db.event_message_outbox.delete_many({})
        await db.event_message_opt_outs.delete_many({})
        client.close()


@pytest.mark.asyncio
async def test_unsubscribe_token_is_one_per_address_per_event_under_races():
    client = AsyncIOMotorClient(DISPOSABLE_URL)
    db = client[DB_NAME]
    try:
        await em.ensure_indexes(db)
        tokens = await asyncio.gather(
            *(
                em.unsubscribe_token(db.event_message_opt_outs, "event:race", "a@example.invalid", NOW.isoformat())
                for _ in range(8)
            )
        )
        assert len(set(tokens)) == 1 and tokens[0]
        assert await db.event_message_opt_outs.count_documents({"scope_id": "event:race"}) == 1
    finally:
        await db.event_message_opt_outs.delete_many({})
        client.close()
