"""Disposable-Mongo proof for K2: real indexes, upserts, and the replay guard.

The unit suite uses in-memory collections; this file runs the same routes
against a real MongoDB replica set so the unique indexes, ``find_one_and_update``
upserts and the RSVP compare-and-swap behave as they will in production.
"""

import json
import os
import time
import uuid

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

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from registrant_webhook import SIGNATURE_HEADER, TIMESTAMP_HEADER, compute_signature  # noqa: E402
from routes import registrants  # noqa: E402

ORGANIZER = {
    "id": "synthetic-organizer",
    "community_id": "synthetic-community",
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
    "role": "organizer",
}


def _event(event_id):
    return {
        "id": event_id,
        "community_id": ORGANIZER["community_id"],
        "created_by": ORGANIZER["id"],
        "title": "Synthetic multi-day gathering",
        "start_at": "2031-06-01T09:00:00+00:00",
        "end_at": "2031-06-03T17:00:00+00:00",
        "timezone": "UTC",
        "publication_state": "published",
        "rsvp_revision": 0,
        "event_invites": [],
        "rsvp_records": [],
        "activity_rsvps": [],
        "agenda": [
            {
                "id": "day-1",
                "title": "Day One",
                "start_at": "2031-06-01T09:00:00+00:00",
                "end_at": "2031-06-01T17:00:00+00:00",
                "visibility": "published",
                "attendance_requested": True,
                "virtual_link": "https://meet.example.invalid/one",
            },
            {
                "id": "day-2",
                "title": "Day Two",
                "start_at": "2031-06-02T09:00:00+00:00",
                "end_at": "2031-06-02T17:00:00+00:00",
                "visibility": "published",
                "attendance_requested": True,
            },
        ],
    }


@pytest.fixture(scope="module")
def client():
    # One event loop for the whole module: Motor binds to the first loop it
    # sees, so the app, the index build and the seeding all share it.
    app = FastAPI()
    app.include_router(registrants.router)
    app.dependency_overrides[get_current_user] = lambda: ORGANIZER
    with TestClient(app) as test_client:
        test_client.portal.call(server.ensure_indexes)
        yield test_client


def _seed(client, event_id):
    async def seed():
        await registrants.events_collection.insert_one(_event(event_id))

    client.portal.call(seed)


def _load(client, event_id):
    async def load():
        return await registrants.events_collection.find_one({"id": event_id}, {"_id": 0})

    return client.portal.call(load)


def _signed(client, path, payload, secret, ts=None):
    raw = json.dumps(payload).encode()
    ts = ts or str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: compute_signature(secret, ts, raw),
    }
    return client.post(path, content=raw, headers=headers), raw, headers


def test_csv_import_rerun_and_flag_against_real_mongo(client):
    event_id = f"k2-{uuid.uuid4().hex}"
    _seed(client, event_id)
    csv_text = (
        "Name,Email,Sessions\n"
        "Ada Example,ada@example.invalid,Day One;Day Two\n"
        "Bo Example,bo@example.invalid,Day Two\n"
    )
    first = client.post(f"/api/events/{event_id}/registrants/import", json={"csv_text": csv_text})
    assert first.status_code == 200, first.text
    assert first.json()["counts"]["created"] == 2
    again = client.post(f"/api/events/{event_id}/registrants/import", json={"csv_text": csv_text})
    assert again.json()["counts"]["skipped"] == 2
    event = _load(client, event_id)
    assert len(event["event_invites"]) == 2
    assert len(event["activity_rsvps"]) == 3

    dup = "Name,Email,Sessions\nAda Example,ada.other@example.invalid,Day One\n"
    for _ in range(2):
        flagged = client.post(f"/api/events/{event_id}/registrants/import", json={"csv_text": dup})
        assert flagged.json()["counts"]["flagged"] == 1
    flags = client.get(f"/api/events/{event_id}/registrants/flags").json()["flags"]
    assert len(flags) == 1
    resolved = client.post(
        f"/api/events/{event_id}/registrants/flags/{flags[0]['id']}/resolve",
        json={"action": "apply_to_existing"},
    )
    assert resolved.status_code == 200 and resolved.json()["row"]["status"] in {"updated", "skipped"}
    second = client.post(
        f"/api/events/{event_id}/registrants/flags/{flags[0]['id']}/resolve",
        json={"action": "dismissed"},
    )
    assert second.status_code == 409


def test_webhook_rotation_and_replay_guard_against_real_mongo(client):
    event_id = f"k2-{uuid.uuid4().hex}"
    _seed(client, event_id)
    hook = client.post(f"/api/events/{event_id}/registrants/webhook/rotate").json()
    assert hook["configured"]
    payload = {"name": "Cy Example", "email": "cy@example.invalid", "sessions": ["Day One"]}
    response, raw, headers = _signed(client, hook["path"], payload, hook["secret"])
    assert response.status_code == 200, response.text
    assert response.json()["result"] == "created"
    replay = client.post(hook["path"], content=raw, headers=headers)
    assert replay.status_code == 409

    rotated = client.post(f"/api/events/{event_id}/registrants/webhook/rotate").json()
    assert rotated["path"] == hook["path"] and rotated["secret"] != hook["secret"]
    old, _, _ = _signed(client, hook["path"], payload, hook["secret"], ts=str(int(time.time()) + 1))
    assert old.status_code == 401
    new, _, _ = _signed(client, hook["path"], payload, rotated["secret"], ts=str(int(time.time()) + 2))
    assert new.status_code == 200 and new.json()["result"] == "skipped"
    assert client.get(f"/api/events/{event_id}/registrants/webhook").json()["last_received_at"]
