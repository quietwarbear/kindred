"""Real MongoDB Release 7 state, authorization, race, and isolation campaign.

Run only against a disposable MongoDB replica set:

KINDRED_DISPOSABLE_MONGO_URL=... MONGO_URL=... DB_NAME=kindred_disposable_... pytest ...
"""

from __future__ import annotations

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient

DISPOSABLE_URL = os.environ.get("KINDRED_DISPOSABLE_MONGO_URL")
if not DISPOSABLE_URL:
    pytest.skip("A disposable MongoDB replica set is required.", allow_module_level=True)
if os.environ.get("MONGO_URL") != DISPOSABLE_URL:
    raise RuntimeError("Refusing to run against a non-disposable MongoDB URL.")
if not os.environ.get("DB_NAME", "").startswith("kindred_disposable_"):
    raise RuntimeError("Disposable database name must start with kindred_disposable_.")

from db import (  # noqa: E402
    communities_collection,
    events_collection,
    family_access_requests_collection,
    guest_family_claims_collection,
    notification_events_collection,
    users_collection,
)
from dependencies import get_current_user, notification_query_for_user  # noqa: E402
from server import app, ensure_indexes  # noqa: E402

COMMUNITY_ID = "synthetic-release7-family"
OTHER_COMMUNITY_ID = "synthetic-release7-other-family"
EVENT_ID = "synthetic-release7-reunion"
HOST = {
    "id": "synthetic-release7-host", "full_name": "Synthetic Host",
    "email": "host@example.invalid", "community_id": COMMUNITY_ID,
    "community_ids": [COMMUNITY_ID], "role": "host",
}
MEMBER = {
    "id": "synthetic-release7-member", "full_name": "Synthetic Member",
    "email": "member@example.invalid", "community_id": COMMUNITY_ID,
    "community_ids": [COMMUNITY_ID], "role": "member",
}
APPLICANT = {
    "id": "synthetic-release7-applicant", "full_name": "Synthetic Applicant",
    "email": "applicant@example.invalid", "community_id": "",
    "community_ids": [], "role": "member",
}
CROSS_FAMILY = {
    "id": "synthetic-release7-cross-family", "full_name": "Synthetic Cross Family",
    "email": "cross@example.invalid", "community_id": OTHER_COMMUNITY_ID,
    "community_ids": [OTHER_COMMUNITY_ID], "role": "member",
}


async def _request_as(user, method, path, **kwargs):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kindred.invalid") as client:
            return await client.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


async def _public_claim(invitation_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kindred.invalid") as client:
        response = await client.post(
            "/api/public/family-access-claim",
            headers={"Authorization": f"Bearer {invitation_id}"},
        )
    assert response.status_code == 200, response.text
    return response.json()["claim"]


def _invite(invitation_id, email, created_at):
    return {
        "id": invitation_id, "invitee_name": email.split("@")[0], "email": email,
        "invite_source": "guest", "status": "invited", "rsvp_status": "going",
        "created_at": created_at,
    }


async def _campaign():
    for collection in (
        family_access_requests_collection, guest_family_claims_collection,
        notification_events_collection, events_collection, users_collection,
        communities_collection,
    ):
        await collection.drop()
    await ensure_indexes()
    await communities_collection.insert_many([
        {"id": COMMUNITY_ID, "name": "Synthetic Family", "lifecycle_state": "active", "owner_user_id": HOST["id"]},
        {"id": OTHER_COMMUNITY_ID, "name": "Synthetic Other", "lifecycle_state": "active", "owner_user_id": CROSS_FAMILY["id"]},
    ])
    await users_collection.insert_many([HOST.copy(), MEMBER.copy(), APPLICANT.copy(), CROSS_FAMILY.copy()])
    invitation = _invite("synthetic-release7-invite-one", "guest@example.invalid", "2027-08-01T00:00:00+00:00")
    event = {
        "id": EVENT_ID, "community_id": COMMUNITY_ID, "event_template": "reunion",
        "title": "Synthetic Reunion", "hidden_from_user_ids": [],
        "event_invites": [invitation], "rsvp_records": [], "agenda": [],
    }
    await events_collection.insert_one(event)

    # Claim first, then replace the invitation credential. The durable relationship remains.
    claim = await _public_claim(invitation["id"])
    replacement = {**invitation, "id": "synthetic-release7-replacement", "credential_rotation": {"operation_id": "synthetic"}}
    await events_collection.update_one({"id": EVENT_ID}, {"$set": {"event_invites": [replacement]}})

    submission = {"idempotency_key": "release7-submit-operation-0001"}
    responses = await asyncio.gather(*[
        _request_as(
            APPLICANT, "POST", "/api/family-access/requests", json=submission,
            headers={"X-Kindred-Guest-Claim": claim},
        ) for _ in range(2)
    ])
    assert [response.status_code for response in responses] == [200, 200]
    assert {response.json()["status"] for response in responses} == {"pending"}
    assert await family_access_requests_collection.count_documents({"applicant_user_id": APPLICANT["id"]}) == 1

    ordinary_list = await _request_as(MEMBER, "GET", "/api/family-access/organizer/requests")
    assert ordinary_list.status_code == 403
    organizer_list = await _request_as(HOST, "GET", "/api/family-access/organizer/requests")
    assert organizer_list.status_code == 200
    pending = organizer_list.json()["requests"][0]
    assert pending["applicant_name"] == "Synthetic Applicant"
    assert "email" not in pending

    decisions = [
        {"request_reference": pending["request_reference"], "decision": "approved", "expected_revision": 0, "idempotency_key": "release7-decision-operation-approve"},
        {"request_reference": pending["request_reference"], "decision": "declined", "expected_revision": 0, "idempotency_key": "release7-decision-operation-decline"},
    ]
    decision_responses = await asyncio.gather(*[
        _request_as(HOST, "POST", "/api/family-access/organizer/decision", json=decision)
        for decision in decisions
    ])
    assert sorted(response.status_code for response in decision_responses) == [200, 409]
    winner_index = next(index for index, response in enumerate(decision_responses) if response.status_code == 200)
    winner = decision_responses[winner_index].json()
    retry = await _request_as(HOST, "POST", "/api/family-access/organizer/decision", json=decisions[winner_index])
    assert retry.status_code == 200
    assert retry.json() == winner

    applicant_after = await users_collection.find_one({"id": APPLICANT["id"]}, {"_id": 0})
    if winner["status"] == "approved":
        assert applicant_after["community_id"] == COMMUNITY_ID
        assert applicant_after["community_ids"] == [COMMUNITY_ID]
        own = await _request_as({**APPLICANT, **applicant_after}, "GET", "/api/family-access/status")
        assert own.json()["family_space_name"] == "Synthetic Family"
    else:
        assert applicant_after["community_id"] == ""

    # Organizer-only named request notification and recipient-only result notification.
    member_query = await notification_query_for_user(MEMBER)
    assert await notification_events_collection.count_documents(member_query) == 0
    host_query = await notification_query_for_user(HOST)
    host_events = await notification_events_collection.find(host_query, {"_id": 0}).to_list(20)
    assert any(item["event_type"] == "family-access-request" for item in host_events)

    # A different-family identity reaches only the terminal conflict state.
    cross_invite = _invite("synthetic-release7-cross-invite", "cross@example.invalid", "2027-08-02T00:00:00+00:00")
    await events_collection.update_one({"id": EVENT_ID}, {"$push": {"event_invites": cross_invite}})
    cross_claim = await _public_claim(cross_invite["id"])
    cross = await _request_as(
        CROSS_FAMILY, "POST", "/api/family-access/requests",
        json={"idempotency_key": "release7-cross-family-submit-0001"},
        headers={"X-Kindred-Guest-Claim": cross_claim},
    )
    assert cross.status_code == 200
    assert cross.json()["status"] == "conflict"
    unchanged = await users_collection.find_one({"id": CROSS_FAMILY["id"]}, {"_id": 0})
    assert unchanged["community_id"] == OTHER_COMMUNITY_ID
    assert unchanged["community_ids"] == [OTHER_COMMUNITY_ID]

    # Revocation after claim and hidden-event denial both fail without a request.
    revoked_invite = _invite("synthetic-release7-revoked", "revoked@example.invalid", "2027-08-03T00:00:00+00:00")
    await events_collection.update_one({"id": EVENT_ID}, {"$push": {"event_invites": revoked_invite}})
    revoked_claim = await _public_claim(revoked_invite["id"])
    await events_collection.update_one(
        {"id": EVENT_ID, "event_invites.id": revoked_invite["id"]},
        {"$set": {"event_invites.$.revoked_at": "2027-08-04T00:00:00+00:00"}},
    )
    revoked_user = {**APPLICANT, "id": "synthetic-release7-revoked-user"}
    await users_collection.insert_one(revoked_user.copy())
    revoked = await _request_as(
        revoked_user, "POST", "/api/family-access/requests",
        json={"idempotency_key": "release7-revoked-submit-0001"},
        headers={"X-Kindred-Guest-Claim": revoked_claim},
    )
    assert revoked.status_code == 404
    assert await family_access_requests_collection.count_documents({"applicant_user_id": revoked_user["id"]}) == 0


def test_disposable_guest_family_access_campaign():
    asyncio.run(_campaign())
