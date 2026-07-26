"""Real-database incident regressions.

Run only against a disposable MongoDB process:

KINDRED_DISPOSABLE_MONGO_URL=... MONGO_URL=... DB_NAME=... pytest ...
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


if not os.environ.get("KINDRED_DISPOSABLE_MONGO_URL"):
    pytest.skip("A disposable MongoDB instance is required.", allow_module_level=True)
if os.environ.get("MONGO_URL") != os.environ.get("KINDRED_DISPOSABLE_MONGO_URL"):
    raise RuntimeError("Refusing to run database incident tests against a non-disposable MongoDB URL.")
if not os.environ.get("DB_NAME", "").startswith("kindred_disposable_"):
    raise RuntimeError("Disposable database name must start with kindred_disposable_.")

from db import (  # noqa: E402
    communities_collection,
    events_collection,
    notification_events_collection,
    users_collection,
)
from dependencies import get_current_user  # noqa: E402
from models import AgendaItemRequest, EventCreateRequest, RSVPRequest  # noqa: E402
from routes.events import create_event, update_rsvp  # noqa: E402
from routes.public import PublicRSVPRequest, public_rsvp_submit  # noqa: E402
from server import app, ensure_indexes  # noqa: E402


COMMUNITY_ID = "synthetic-community"
HOST = {
    "id": "synthetic-host",
    "community_id": COMMUNITY_ID,
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
    "role": "host",
}
MEMBER = {
    "id": "synthetic-member",
    "community_id": COMMUNITY_ID,
    "full_name": "Synthetic Member",
    "email": "member@example.invalid",
    "role": "member",
}
OUTSIDER = {
    "id": "synthetic-outsider",
    "community_id": "synthetic-other-community",
    "full_name": "Synthetic Outsider",
    "email": "outsider@example.invalid",
    "role": "host",
}


def _contains_stage(value, stage):
    if isinstance(value, dict):
        return value.get("stage") == stage or any(
            _contains_stage(item, stage) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_stage(item, stage) for item in value)
    return False


async def _request_as(user, method, path, **kwargs):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://kindred.invalid",
        ) as client:
            return await client.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


async def _run_campaign():
    await events_collection.database.drop_collection(events_collection.name)
    await users_collection.database.drop_collection(users_collection.name)
    await communities_collection.database.drop_collection(communities_collection.name)
    await notification_events_collection.database.drop_collection(
        notification_events_collection.name
    )
    await ensure_indexes()
    await communities_collection.insert_one({
        "id": COMMUNITY_ID,
        "name": "Synthetic Community",
    })
    await users_collection.insert_many([HOST.copy(), MEMBER.copy(), OUTSIDER.copy()])

    sensitive_event = {
        "id": "synthetic-sensitive-event",
        "community_id": COMMUNITY_ID,
        "created_by": HOST["id"],
        "created_by_name": HOST["full_name"],
        "title": "Synthetic Reunion",
        "description": "Disposable authorization fixture",
        "start_at": f"2027-{datetime.now(timezone.utc):%m-%d}T09:00:00",
        "end_at": f"2027-{datetime.now(timezone.utc):%m-%d}T18:00:00",
        "timezone": "America/New_York",
        "location": "Synthetic Venue",
        "event_template": "reunion",
        "gathering_format": "in-person",
        "event_invites": [{
            "id": "synthetic-bearer-credential",
            "member_id": MEMBER["id"],
            "invite_source": "member",
            "invitee_name": MEMBER["full_name"],
            "email": MEMBER["email"],
            "note": "Synthetic private note",
            "share_message": "Synthetic private invitation message",
            "rsvp_status": "going",
        }],
        "rsvp_records": [{
            "user_id": MEMBER["id"],
            "user_name": MEMBER["full_name"],
            "status": "going",
            "guests": 1,
            "updated_at": "2027-01-01T00:00:00+00:00",
        }],
        "activity_rsvps": [{
            "activity_id": "synthetic-private-activity",
            "respondent_id": MEMBER["id"],
            "display_name": MEMBER["full_name"],
            "status": "coming",
            "party_size": 2,
        }],
        "activity_rsvp_summaries": {},
        "agenda": [],
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(sensitive_event.copy())

    for path in ("/api/events", f"/api/events/{sensitive_event['id']}"):
        member_response = await _request_as(MEMBER, "GET", path)
        assert member_response.status_code == 200
        member_events = (
            member_response.json()
            if isinstance(member_response.json(), list)
            else [member_response.json()]
        )
        serialized = str(member_events)
        for event in member_events:
            assert "event_invites" not in event
            assert "rsvp_records" not in event
            assert "activity_rsvps" not in event
            assert "attendees" not in event
            assert event["rsvp_summary"]["going"] == 1
            assert event["my_rsvp_status"] == "going"
        assert "synthetic-bearer-credential" not in serialized
        assert MEMBER["email"] not in serialized
        assert "Synthetic private" not in serialized

        organizer_response = await _request_as(HOST, "GET", path)
        assert organizer_response.status_code == 200
        organizer_events = (
            organizer_response.json()
            if isinstance(organizer_response.json(), list)
            else [organizer_response.json()]
        )
        assert organizer_events[0]["event_invites"][0]["id"] == "synthetic-bearer-credential"
        assert organizer_events[0]["rsvp_records"][0]["user_id"] == MEMBER["id"]

    member_timeline = await _request_as(MEMBER, "GET", "/api/timeline/archive")
    assert member_timeline.status_code == 200
    timeline_serialized = str(member_timeline.json().get("on_this_day", []))
    assert "synthetic-bearer-credential" not in timeline_serialized
    assert MEMBER["email"] not in timeline_serialized
    assert "Synthetic private" not in timeline_serialized
    for event in member_timeline.json().get("on_this_day", []):
        assert "event_invites" not in event
        assert "rsvp_records" not in event
        assert "activity_rsvps" not in event

    outsider_list = await _request_as(OUTSIDER, "GET", "/api/events")
    assert outsider_list.status_code == 200
    assert outsider_list.json() == []
    outsider_detail = await _request_as(
        OUTSIDER,
        "GET",
        f"/api/events/{sensitive_event['id']}",
    )
    assert outsider_detail.status_code == 404

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kindred.invalid",
    ) as client:
        anonymous = await client.get(f"/api/events/{sensitive_event['id']}")
    assert anonymous.status_code == 401

    activity = {
        "id": "synthetic-activity",
        "title": "Synthetic Activity",
        "start_at": "2099-07-18T10:00:00",
        "end_at": "2099-07-18T11:00:00",
        "timezone": "UTC",
        "visibility": "published",
        "attendance_requested": True,
        "rsvp_deadline": "2099-07-01T12:00:00",
    }
    invite_count = 16
    concurrency_event = {
        **sensitive_event,
        "id": "synthetic-concurrency-event",
        "event_invites": [
            {
                "id": f"synthetic-concurrent-{index:02d}",
                "invite_source": "guest",
                "invitee_name": f"Synthetic Guest {index:02d}",
                "email": f"guest-{index:02d}@example.invalid",
                "rsvp_status": "pending",
            }
            for index in range(invite_count)
        ],
        "rsvp_records": [],
        "activity_rsvps": [],
        "agenda": [activity],
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(concurrency_event.copy())
    await asyncio.gather(*[
        public_rsvp_submit(
            f"synthetic-concurrent-{index:02d}",
            PublicRSVPRequest(
                status="going",
                guests=index % 3,
                activity_responses={"synthetic-activity": "coming"},
            ),
        )
        for index in range(invite_count)
    ])
    persisted = await events_collection.find_one(
        {"id": concurrency_event["id"]},
        {"_id": 0},
    )
    assert len(persisted["rsvp_records"]) == invite_count
    assert len(persisted["activity_rsvps"]) == invite_count
    assert all(
        invite["rsvp_status"] == "going"
        for invite in persisted["event_invites"]
    )
    assert persisted["rsvp_revision"] == invite_count

    legacy_member_event = {
        **sensitive_event,
        "id": "synthetic-legacy-member-event",
        "event_invites": [{
            "id": "synthetic-legacy-member-invite",
            "invite_source": "member",
            "invitee_name": MEMBER["full_name"],
            "email": MEMBER["email"],
            "rsvp_status": "pending",
        }],
        "rsvp_records": [],
        "activity_rsvps": [],
        "agenda": [activity],
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(legacy_member_event.copy())
    await public_rsvp_submit(
        "synthetic-legacy-member-invite",
        PublicRSVPRequest(
            status="some",
            guests=0,
            activity_responses={"synthetic-activity": "maybe"},
        ),
    )
    await update_rsvp(
        legacy_member_event["id"],
        RSVPRequest(status="going", guests=1),
        MEMBER,
    )
    reconciled = await events_collection.find_one(
        {"id": legacy_member_event["id"]},
        {"_id": 0},
    )
    assert reconciled["event_invites"][0]["member_id"] == MEMBER["id"]
    assert [record["user_id"] for record in reconciled["rsvp_records"]] == [
        MEMBER["id"]
    ]

    guest_identity_event = {
        **sensitive_event,
        "id": "synthetic-guest-identity-event",
        "event_invites": [{
            "id": "synthetic-guest-identity-invite",
            "invite_source": "guest",
            "invitee_name": "Synthetic Unrelated Guest",
            "email": MEMBER["email"],
            "rsvp_status": "pending",
        }],
        "rsvp_records": [],
        "activity_rsvps": [],
        "agenda": [activity],
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(guest_identity_event.copy())
    await public_rsvp_submit(
        "synthetic-guest-identity-invite",
        PublicRSVPRequest(
            status="going",
            activity_responses={"synthetic-activity": "coming"},
        ),
    )
    guest_persisted = await events_collection.find_one(
        {"id": guest_identity_event["id"]},
        {"_id": 0},
    )
    assert "member_id" not in guest_persisted["event_invites"][0]
    assert guest_persisted["rsvp_records"][0]["user_id"] == (
        "invite:synthetic-guest-identity-invite"
    )

    idempotent_payload = EventCreateRequest(
        title="Synthetic Idempotent Reunion",
        description="Disposable retry fixture",
        start_at="2027-08-01T09:00:00",
        end_at="2027-08-01T18:00:00",
        timezone="UTC",
        location="Synthetic Venue",
        event_template="reunion",
        client_request_id="synthetic-idempotency-key",
    )
    first, retry = await asyncio.gather(
        create_event(idempotent_payload, HOST),
        create_event(idempotent_payload, HOST),
    )
    assert first["id"] == retry["id"]
    assert await events_collection.count_documents({
        "community_id": COMMUNITY_ID,
        "created_by": HOST["id"],
        "client_request_id": "synthetic-idempotency-key",
    }) == 1

    indexes = {
        index["name"]: index
        async for index in events_collection.list_indexes()
    }
    assert indexes["event_invitation_token_lookup"]["unique"] is True
    assert indexes["event_creation_idempotency"]["unique"] is True
    explain = await events_collection.database.command(
        "explain",
        {
            "find": events_collection.name,
            "filter": {"event_invites.id": "synthetic-query-value"},
        },
        verbosity="queryPlanner",
    )
    assert _contains_stage(explain["queryPlanner"]["winningPlan"], "IXSCAN")

    deadline_event = {
        **sensitive_event,
        "id": "synthetic-deadline-event",
        "agenda": [],
        "event_invites": [],
        "rsvp_records": [],
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(deadline_event.copy())
    for deadline in (
        "not-a-date",
        "2027-03-14T02:30:00",
        "2027-11-07T01:30:00",
    ):
        response = await _request_as(
            HOST,
            "POST",
            f"/api/events/{deadline_event['id']}/agenda",
            json=AgendaItemRequest(
                title="Synthetic Deadline Activity",
                start_at="2027-11-08T10:00:00",
                end_at="2027-11-08T11:00:00",
                timezone="America/New_York",
                rsvp_deadline=deadline,
            ).model_dump(),
        )
        assert response.status_code == 422

    explicit_offset = await _request_as(
        HOST,
        "POST",
        f"/api/events/{deadline_event['id']}/agenda",
        json=AgendaItemRequest(
            title="Synthetic Explicit Offset Deadline",
            start_at="2099-11-08T10:00:00",
            end_at="2099-11-08T11:00:00",
            timezone="America/New_York",
            rsvp_deadline="2099-11-07T01:30:00-05:00",
            visibility="published",
        ).model_dump(),
    )
    assert explicit_offset.status_code == 200
    explicit_activity_id = explicit_offset.json()["agenda"][0]["id"]

    timezone_override = await _request_as(
        HOST,
        "POST",
        f"/api/events/{deadline_event['id']}/agenda",
        json=AgendaItemRequest(
            title="Synthetic Timezone Override",
            start_at="2099-07-18T10:00:00",
            end_at="2099-07-18T11:00:00",
            timezone="Pacific/Honolulu",
            rsvp_deadline="2099-07-01T12:00:00",
        ).model_dump(),
    )
    assert timezone_override.status_code == 200
    timezone_activity = next(
        item for item in timezone_override.json()["agenda"]
        if item["title"] == "Synthetic Timezone Override"
    )
    assert timezone_activity["timezone"] == "Pacific/Honolulu"

    deadline_event = await events_collection.find_one(
        {"id": deadline_event["id"]},
        {"_id": 0},
    )
    deadline_event["event_invites"] = [{
        "id": "synthetic-future-deadline-invite",
        "invite_source": "guest",
        "invitee_name": "Synthetic Future Guest",
        "email": "future@example.invalid",
        "rsvp_status": "pending",
    }]
    await events_collection.replace_one(
        {"id": deadline_event["id"]},
        deadline_event,
    )
    future_result = await public_rsvp_submit(
        "synthetic-future-deadline-invite",
        PublicRSVPRequest(
            status="some",
            activity_responses={explicit_activity_id: "coming"},
        ),
    )
    assert future_result["saved"] is True

    expired = {
        **sensitive_event,
        "id": "synthetic-expired-event",
        "event_invites": [{
            "id": "synthetic-expired-invite",
            "invite_source": "guest",
            "invitee_name": "Synthetic Guest",
            "email": "expired@example.invalid",
            "rsvp_status": "pending",
        }],
        "rsvp_records": [],
        "agenda": [{
            **activity,
            "rsvp_deadline": (
                datetime.now(timezone.utc) - timedelta(hours=1)
            ).isoformat(),
        }],
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(expired.copy())
    with pytest.raises(HTTPException) as exc:
        await public_rsvp_submit(
            "synthetic-expired-invite",
            PublicRSVPRequest(
                status="going",
                activity_responses={"synthetic-activity": "coming"},
            ),
        )
    assert exc.value.status_code == 409

    invalid_stored_deadline = {
        **expired,
        "id": "synthetic-invalid-stored-deadline-event",
        "event_invites": [{
            "id": "synthetic-invalid-stored-deadline-invite",
            "invite_source": "guest",
            "invitee_name": "Synthetic Guest",
            "email": "invalid-deadline@example.invalid",
            "rsvp_status": "pending",
        }],
        "agenda": [{
            **activity,
            "rsvp_deadline": "not-a-date",
        }],
    }
    await events_collection.insert_one(invalid_stored_deadline.copy())
    with pytest.raises(HTTPException) as invalid_exc:
        await public_rsvp_submit(
            "synthetic-invalid-stored-deadline-invite",
            PublicRSVPRequest(
                status="going",
                activity_responses={"synthetic-activity": "coming"},
            ),
        )
    assert invalid_exc.value.status_code == 409


def test_real_disposable_database_security_and_concurrency_campaign():
    asyncio.run(_run_campaign())
