"""Real MongoDB Release 6 authorization, concurrency, and preservation campaign.

Run only against a disposable MongoDB replica set:

KINDRED_DISPOSABLE_MONGO_URL=... MONGO_URL=... DB_NAME=kindred_disposable_... pytest ...
"""

from __future__ import annotations

import asyncio
import os
from copy import deepcopy

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

DISPOSABLE_URL = os.environ.get("KINDRED_DISPOSABLE_MONGO_URL")
if not DISPOSABLE_URL:
    pytest.skip(
        "A disposable MongoDB replica set is required.", allow_module_level=True
    )
if os.environ.get("MONGO_URL") != DISPOSABLE_URL:
    raise RuntimeError("Refusing to run against a non-disposable MongoDB URL.")
if not os.environ.get("DB_NAME", "").startswith("kindred_disposable_"):
    raise RuntimeError("Disposable database name must start with kindred_disposable_.")

from db import (  # noqa: E402
    communities_collection,
    events_collection,
    memories_collection,
    subscriptions_collection,
    users_collection,
)
from dependencies import get_current_user  # noqa: E402
from models import FamilySpaceActivationRequest  # noqa: E402
from routes.family_space import activate_family_space  # noqa: E402
from server import app  # noqa: E402

COMMUNITY_ID = "synthetic-release6-community"
OTHER_COMMUNITY_ID = "synthetic-release6-other-community"
EVENT_ID = "synthetic-release6-reunion"
INVITATION_IDS = [
    "synthetic-release6-invite-one",
    "synthetic-release6-invite-two",
    "synthetic-release6-invite-three",
]
HOST = {
    "id": "synthetic-release6-host",
    "community_id": COMMUNITY_ID,
    "community_ids": [COMMUNITY_ID],
    "full_name": "Synthetic Host",
    "email": "host@example.invalid",
    "role": "host",
}
ORGANIZER = {
    "id": "synthetic-release6-organizer",
    "community_id": COMMUNITY_ID,
    "community_ids": [COMMUNITY_ID],
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
    "role": "organizer",
}
MEMBER = {
    "id": "synthetic-release6-member",
    "community_id": COMMUNITY_ID,
    "community_ids": [COMMUNITY_ID],
    "full_name": "Synthetic Member",
    "email": "member@example.invalid",
    "role": "member",
}
PLATFORM_ADMIN = {
    **MEMBER,
    "id": "synthetic-release6-platform-admin",
    "email": "platform@example.invalid",
    "is_platform_admin": True,
}
OUTSIDER = {
    "id": "synthetic-release6-outsider",
    "community_id": OTHER_COMMUNITY_ID,
    "community_ids": [OTHER_COMMUNITY_ID],
    "full_name": "Synthetic Outsider",
    "email": "outsider@example.invalid",
    "role": "host",
}


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


async def _campaign():
    for collection in (
        communities_collection,
        events_collection,
        memories_collection,
        subscriptions_collection,
        users_collection,
    ):
        await collection.drop()

    community = {
        "id": COMMUNITY_ID,
        "name": "Synthetic Internal Planning Space",
        "community_type": "family reunion",
        "location": "Synthetic City",
        "description": "Synthetic description",
        "motto": "Synthetic motto",
        "owner_user_id": HOST["id"],
        "lifecycle_state": "provisional",
        "lifecycle_revision": 0,
        "modules": ["gatherings", "memory"],
        "provider_metadata": {"opaque": "synthetic-provider-reference"},
        "created_at": "2027-08-01T00:00:00+00:00",
    }
    other_community = {
        "id": OTHER_COMMUNITY_ID,
        "name": "Synthetic Other Family",
        "owner_user_id": OUTSIDER["id"],
        "lifecycle_state": "active",
        "lifecycle_revision": 0,
        "created_at": "2027-08-01T00:00:00+00:00",
    }
    event = {
        "id": EVENT_ID,
        "community_id": COMMUNITY_ID,
        "created_by": HOST["id"],
        "created_by_name": HOST["full_name"],
        "title": "Synthetic Private Reunion",
        "description": "Synthetic private history",
        "event_template": "reunion",
        "start_at": "2027-08-15T09:00:00+00:00",
        "timezone": "UTC",
        "location": "Synthetic Venue",
        "hidden_from_user_ids": [],
        "event_invites": [
            {
                "id": INVITATION_IDS[0],
                "invite_source": "guest",
                "invitee_name": "Synthetic Guest One",
                "email": "guest1@example.invalid",
                "rsvp_status": "going",
                "opened_at": "2027-08-02T00:00:00+00:00",
                "private_credential_marker": "synthetic-credential-one",
            },
            {
                "id": INVITATION_IDS[1],
                "invite_source": "guest",
                "invitee_name": "Synthetic Guest Two",
                "email": "guest2@example.invalid",
                "rsvp_status": "some",
                "delivery_verified_at": "2027-08-02T00:00:00+00:00",
                "private_credential_marker": "synthetic-credential-two",
            },
            {
                "id": INVITATION_IDS[2],
                "invite_source": "member",
                "member_id": MEMBER["id"],
                "invitee_name": MEMBER["full_name"],
                "email": MEMBER["email"],
                "rsvp_status": "maybe",
                "opened_at": "2027-08-02T00:00:00+00:00",
                "private_credential_marker": "synthetic-credential-three",
            },
        ],
        "rsvp_records": [
            {
                "user_id": f"invite:{INVITATION_IDS[0]}",
                "user_name": "Synthetic Guest One",
                "status": "going",
                "updated_at": "2027-08-02T00:00:00+00:00",
            },
            {
                "user_id": f"invite:{INVITATION_IDS[1]}",
                "user_name": "Synthetic Guest Two",
                "status": "some",
                "updated_at": "2027-08-02T00:00:00+00:00",
            },
        ],
        "agenda": [{"id": "synthetic-activity", "title": "Synthetic Activity"}],
        "potluck_items": [],
        "volunteer_slots": [],
        "rsvp_revision": 7,
        "created_at": "2027-08-01T00:00:00+00:00",
    }
    memory = {
        "id": "synthetic-release6-memory",
        "community_id": COMMUNITY_ID,
        "event_id": EVENT_ID,
        "created_by": MEMBER["id"],
        "description": "Synthetic private memory",
        "capsule_status": "published",
    }
    subscription = {
        "id": "synthetic-release6-subscription",
        "community_id": COMMUNITY_ID,
        "status": "synthetic-preserved-state",
        "provider_reference": "synthetic-provider-subscription-reference",
    }
    await communities_collection.insert_many([community, other_community])
    await users_collection.insert_many(
        [HOST, ORGANIZER, MEMBER, PLATFORM_ADMIN, OUTSIDER]
    )
    await events_collection.insert_one(event)
    await memories_collection.insert_one(memory)
    await subscriptions_collection.insert_one(subscription)

    readiness = await _request_as(ORGANIZER, "GET", "/api/family-space/activation")
    assert readiness.status_code == 200
    body = readiness.json()
    assert body["readiness_status"] == "ready"
    assert body["aggregate_counts"] == {
        "reunions": 1,
        "verified_invitations": 3,
        "accepted_responses": 2,
        "non_host_participants": 3,
    }
    serialized = str(body)
    for forbidden in (
        COMMUNITY_ID,
        EVENT_ID,
        "Synthetic Private Reunion",
        "example.invalid",
        "synthetic-credential",
        "provider",
    ):
        assert forbidden not in serialized

    member_denied = await _request_as(MEMBER, "GET", "/api/family-space/activation")
    admin_denied = await _request_as(
        PLATFORM_ADMIN, "GET", "/api/family-space/activation"
    )
    assert member_denied.status_code == 403
    assert admin_denied.status_code == 403
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kindred.invalid",
    ) as anonymous:
        anonymous_denied = await anonymous.get("/api/family-space/activation")
    assert anonymous_denied.status_code == 401

    outsider_report = await _request_as(OUTSIDER, "GET", "/api/family-space/activation")
    assert outsider_report.status_code == 200
    assert outsider_report.json()["lifecycle_state"] == "active"
    assert COMMUNITY_ID not in str(outsider_report.json())

    provisional_public_rsvp = await _request_as(
        OUTSIDER,
        "GET",
        "/api/public/rsvp",
        headers={"Authorization": f"Bearer {INVITATION_IDS[0]}"},
    )
    assert provisional_public_rsvp.status_code == 200
    assert provisional_public_rsvp.json()["community_name"] == ""

    before_event = await events_collection.find_one({"id": EVENT_ID})
    before_users = (
        await users_collection.find({"community_id": COMMUNITY_ID})
        .sort("id", 1)
        .to_list(20)
    )
    before_memory = await memories_collection.find_one({"id": memory["id"]})
    before_subscription = await subscriptions_collection.find_one(
        {"id": subscription["id"]}
    )
    before_community = await communities_collection.find_one({"id": COMMUNITY_ID})

    request = FamilySpaceActivationRequest(
        family_space_name="  The   Synthetic Family  ",
        expected_revision=0,
        idempotency_key="release6-identical-activation-0001",
    )
    identical = await asyncio.gather(
        activate_family_space(request, ORGANIZER),
        activate_family_space(request, ORGANIZER),
    )
    assert identical[0] == identical[1]
    assert identical[0]["lifecycle_state"] == "active"
    assert identical[0]["lifecycle_revision"] == 1

    after_community = await communities_collection.find_one({"id": COMMUNITY_ID})
    assert after_community["name"] == "The Synthetic Family"
    assert after_community["lifecycle_state"] == "active"
    assert after_community["lifecycle_revision"] == 1
    for field in (
        "id",
        "community_type",
        "location",
        "description",
        "motto",
        "owner_user_id",
        "modules",
        "provider_metadata",
        "created_at",
    ):
        assert after_community[field] == before_community[field]
    assert await events_collection.find_one({"id": EVENT_ID}) == before_event
    assert (
        await users_collection.find({"community_id": COMMUNITY_ID})
        .sort("id", 1)
        .to_list(20)
        == before_users
    )
    assert await memories_collection.find_one({"id": memory["id"]}) == before_memory
    assert (
        await subscriptions_collection.find_one({"id": subscription["id"]})
        == before_subscription
    )

    retry = await activate_family_space(request, HOST)
    assert retry == identical[0]
    with pytest.raises(HTTPException) as divergent:
        await activate_family_space(
            FamilySpaceActivationRequest(
                family_space_name="Another Synthetic Family",
                expected_revision=0,
                idempotency_key="release6-divergent-activation-0002",
            ),
            HOST,
        )
    assert divergent.value.status_code == 409
    final = await communities_collection.find_one({"id": COMMUNITY_ID})
    assert final["name"] == "The Synthetic Family"
    assert final["lifecycle_revision"] == 1

    public_rsvp = await _request_as(
        OUTSIDER,
        "GET",
        "/api/public/rsvp",
        headers={"Authorization": f"Bearer {INVITATION_IDS[0]}"},
    )
    assert public_rsvp.status_code == 200
    assert public_rsvp.json()["community_name"] == "The Synthetic Family"

    race_community_id = "synthetic-release6-divergent-race-community"
    race_host = {
        **HOST,
        "id": "synthetic-release6-divergent-race-host",
        "community_id": race_community_id,
        "community_ids": [race_community_id],
        "email": "race-host@example.invalid",
    }
    race_host.pop("_id", None)
    race_community = {
        **deepcopy(community),
        "id": race_community_id,
        "owner_user_id": race_host["id"],
    }
    race_community.pop("_id", None)
    race_event = {
        **deepcopy(event),
        "id": "synthetic-release6-divergent-race-event",
        "community_id": race_community_id,
        "created_by": race_host["id"],
        "rsvp_records": [],
    }
    race_event.pop("_id", None)
    await communities_collection.insert_one(race_community)
    await users_collection.insert_one(race_host)
    await events_collection.insert_one(race_event)
    divergent_requests = [
        FamilySpaceActivationRequest(
            family_space_name="Synthetic Race Family A",
            expected_revision=0,
            idempotency_key="release6-concurrent-divergent-a-0001",
        ),
        FamilySpaceActivationRequest(
            family_space_name="Synthetic Race Family B",
            expected_revision=0,
            idempotency_key="release6-concurrent-divergent-b-0001",
        ),
    ]
    race_results = await asyncio.gather(
        *(activate_family_space(item, race_host) for item in divergent_requests),
        return_exceptions=True,
    )
    assert sum(isinstance(item, dict) for item in race_results) == 1
    conflicts = [item for item in race_results if isinstance(item, HTTPException)]
    assert len(conflicts) == 1
    assert conflicts[0].status_code == 409
    race_winner = await communities_collection.find_one({"id": race_community_id})
    assert race_winner["name"] in {
        "Synthetic Race Family A",
        "Synthetic Race Family B",
    }
    assert race_winner["lifecycle_state"] == "active"
    assert race_winner["lifecycle_revision"] == 1
    winning_request = divergent_requests[0 if race_winner["name"].endswith("A") else 1]
    assert await activate_family_space(winning_request, race_host) == next(
        item for item in race_results if isinstance(item, dict)
    )


def test_release6_family_space_activation_against_disposable_mongodb():
    asyncio.run(_campaign())
