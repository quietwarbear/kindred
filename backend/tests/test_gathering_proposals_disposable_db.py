"""Real MongoDB Stage 9 authorization, concurrency, conversion, and deletion campaign."""

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
    gathering_proposal_conversions_collection,
    gathering_proposal_responses_collection,
    gathering_proposals_collection,
    notification_events_collection,
    users_collection,
)
from dependencies import get_current_user, notification_query_for_user  # noqa: E402
from server import app, ensure_indexes  # noqa: E402

COMMUNITY_ID = "synthetic-release9-family"
OTHER_COMMUNITY_ID = "synthetic-release9-other"
HOST = {"id": "release9-host", "community_id": COMMUNITY_ID, "community_ids": [COMMUNITY_ID], "full_name": "Synthetic Host", "email": "host@example.invalid", "role": "host", "auth_provider": "apple"}
ORGANIZER = {"id": "release9-organizer", "community_id": COMMUNITY_ID, "community_ids": [COMMUNITY_ID], "full_name": "Synthetic Organizer", "email": "organizer@example.invalid", "role": "organizer", "auth_provider": "apple"}
MEMBER = {"id": "release9-member", "community_id": COMMUNITY_ID, "community_ids": [COMMUNITY_ID], "full_name": "Synthetic Member", "email": "member@example.invalid", "role": "member", "auth_provider": "apple"}
OTHER_MEMBER = {"id": "release9-member-2", "community_id": COMMUNITY_ID, "community_ids": [COMMUNITY_ID], "full_name": "Synthetic Other Member", "email": "other@example.invalid", "role": "member", "auth_provider": "apple"}
SUSPENDED = {"id": "release9-suspended", "community_id": COMMUNITY_ID, "community_ids": [COMMUNITY_ID], "full_name": "Synthetic Suspended", "email": "suspended@example.invalid", "role": "member", "account_status": "suspended", "auth_provider": "apple"}
OUTSIDER = {"id": "release9-outsider", "community_id": OTHER_COMMUNITY_ID, "community_ids": [OTHER_COMMUNITY_ID], "full_name": "Synthetic Outsider", "email": "outsider@example.invalid", "role": "host", "auth_provider": "apple"}
PLATFORM_MEMBER = {**OTHER_MEMBER, "id": "release9-platform-member", "email": "platform@example.invalid", "is_platform_admin": True}
SOLE_OWNER = {"id": "release9-sole-owner", "community_id": "synthetic-release9-sole", "community_ids": ["synthetic-release9-sole"], "full_name": "Synthetic Sole Owner", "email": "sole@example.invalid", "role": "host", "auth_provider": "apple"}


async def request_as(user, method, path, **kwargs):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kindred.invalid") as client:
            return await client.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


def submission(key="release9-proposal-submit-operation-0001", title="Synthetic family picnic"):
    return {
        "working_title": title,
        "gathering_type": "day_trip",
        "broad_date_window": "Early summer",
        "location_suggestion": "Near the family home",
        "organizer_note": "Private synthetic organizer note",
        "idempotency_key": key,
    }


async def campaign():
    for collection in (
        communities_collection, users_collection, events_collection,
        gathering_proposals_collection, gathering_proposal_responses_collection,
        gathering_proposal_conversions_collection, notification_events_collection,
    ):
        await collection.delete_many({})
    await communities_collection.insert_many([
        {"id": COMMUNITY_ID, "name": "Synthetic Family", "lifecycle_state": "active", "owner_user_id": HOST["id"]},
        {"id": OTHER_COMMUNITY_ID, "name": "Synthetic Other", "lifecycle_state": "active", "owner_user_id": OUTSIDER["id"]},
    ])
    await users_collection.insert_many([HOST, ORGANIZER, MEMBER, OTHER_MEMBER, SUSPENDED, OUTSIDER, PLATFORM_MEMBER])
    await ensure_indexes()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kindred.invalid") as anonymous:
        assert (await anonymous.get("/api/gathering-proposals")).status_code == 401

    await communities_collection.update_one({"id": COMMUNITY_ID}, {"$set": {"lifecycle_state": "provisional"}})
    assert (await request_as(MEMBER, "POST", "/api/gathering-proposals", json=submission())).status_code == 404
    await communities_collection.update_one({"id": COMMUNITY_ID}, {"$set": {"lifecycle_state": "active"}})
    assert (await request_as(SUSPENDED, "POST", "/api/gathering-proposals", json=submission())).status_code == 404

    created = await asyncio.gather(*[
        request_as(MEMBER, "POST", "/api/gathering-proposals", json=submission()) for _ in range(2)
    ])
    assert [item.status_code for item in created] == [200, 200]
    assert created[0].json() == created[1].json()
    reference = created[0].json()["proposal_reference"]
    assert await gathering_proposals_collection.count_documents({}) == 1
    assert created[0].json()["state"] == "submitted"
    assert "proposer_display_name" not in created[0].json()

    assert (await request_as(OTHER_MEMBER, "GET", f"/api/gathering-proposals/{reference}")).status_code == 404
    own = await request_as(MEMBER, "GET", "/api/gathering-proposals")
    outsider = await request_as(OUTSIDER, "GET", f"/api/gathering-proposals/{reference}")
    assert own.status_code == 200 and len(own.json()["proposals"]) == 1
    assert outsider.status_code == 404
    assert (await request_as(PLATFORM_MEMBER, "GET", "/api/gathering-proposals/organizer/review")).status_code == 403
    stale_organizer_claim = {**MEMBER, "role": "organizer"}
    assert (await request_as(stale_organizer_claim, "GET", "/api/gathering-proposals/organizer/review")).status_code == 403

    member_notification_count = await notification_events_collection.count_documents(await notification_query_for_user(MEMBER))
    host_notification_count = await notification_events_collection.count_documents(await notification_query_for_user(HOST))
    assert member_notification_count == 0
    assert host_notification_count == 1
    submission_notification = await notification_events_collection.find_one({"event_type": "gathering-proposal-submitted"}, {"_id": 0})
    assert submission_notification["related_id"] == ""
    assert "picnic" not in str(submission_notification).lower()
    assert "private synthetic" not in str(submission_notification).lower()

    organizer_review = await request_as(ORGANIZER, "GET", "/api/gathering-proposals/organizer/review")
    assert organizer_review.status_code == 200
    review = organizer_review.json()["proposals"][0]
    assert review["proposer_display_name"] == MEMBER["full_name"]
    assert review["organizer_note"] == submission()["organizer_note"]

    publish_payload = {"expected_revision": 0, "idempotency_key": "release9-proposal-publish-operation-0001"}
    published = await request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{reference}/publish", json=publish_payload)
    retry_publish = await request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{reference}/publish", json=publish_payload)
    assert published.status_code == retry_publish.status_code == 200
    assert published.json()["state"] == "published"
    pulse_notification = await notification_events_collection.find_one({"event_type": "gathering-proposal-published"}, {"_id": 0})
    assert pulse_notification["related_id"] == ""
    assert SUSPENDED["id"] not in pulse_notification["recipient_user_ids"]
    activity = await request_as(OTHER_MEMBER, "GET", "/api/activity-feed")
    history = await request_as(OTHER_MEMBER, "GET", "/api/notifications/history")
    assert activity.status_code == history.status_code == 200
    for projection in (activity.json()["items"], history.json()["items"]):
        assert projection
        assert all("recipient_user_ids" not in item and "read_by_user_ids" not in item for item in projection)
        assert MEMBER["id"] not in str(projection) and OTHER_MEMBER["id"] not in str(projection)
    unread = await request_as(OTHER_MEMBER, "GET", "/api/notifications/unread-count")
    marked = await request_as(OTHER_MEMBER, "POST", "/api/notifications/mark-read")
    assert unread.status_code == marked.status_code == 200

    public_pulse = await request_as(OTHER_MEMBER, "GET", f"/api/gathering-proposals/{reference}")
    assert public_pulse.status_code == 200
    serialized = str(public_pulse.json())
    for forbidden in (MEMBER["full_name"], MEMBER["id"], OTHER_MEMBER["id"], submission()["organizer_note"]):
        assert forbidden not in serialized

    response_payload = {"response": "interested", "expected_revision": 0, "idempotency_key": "release9-interest-response-operation-0001"}
    response_retries = await asyncio.gather(*[
        request_as(OTHER_MEMBER, "PUT", f"/api/gathering-proposals/{reference}/interest", json=response_payload)
        for _ in range(2)
    ])
    assert [item.status_code for item in response_retries] == [200, 200]
    assert await gathering_proposal_responses_collection.count_documents({"user_id": OTHER_MEMBER["id"]}) == 1
    response_view = response_retries[0].json()
    assert response_view["interest"]["my_response"] == "interested"
    assert response_view["interest"]["aggregate"] == {"interested": 1, "maybe": 0, "not_available": 0, "total": 1}

    divergent = await request_as(
        OTHER_MEMBER, "PUT", f"/api/gathering-proposals/{reference}/interest",
        json={**response_payload, "response": "maybe"},
    )
    assert divergent.status_code == 409
    suspended_response = await request_as(
        SUSPENDED, "PUT", f"/api/gathering-proposals/{reference}/interest",
        json={"response": "maybe", "expected_revision": 0, "idempotency_key": "release9-suspended-response-operation"},
    )
    assert suspended_response.status_code == 404

    conversion_selection = {
        "title": "Synthetic next reunion", "start_at": "2028-06-03T10:00:00-04:00",
        "end_at": "2028-06-03T18:00:00-04:00", "timezone": "America/New_York",
        "location": "Synthetic family center", "gathering_format": "in-person",
        "max_attendees": 80, "organizer_reference": ORGANIZER["id"],
    }
    preview = await request_as(
        ORGANIZER, "POST", f"/api/gathering-proposals/{reference}/conversion-preview", json=conversion_selection
    )
    assert preview.status_code == 200
    convert_base = {
        **conversion_selection, "expected_revision": 1,
        "preview_digest": preview.json()["preview_digest"],
    }
    conversions = await asyncio.gather(
        request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{reference}/convert", json={**convert_base, "idempotency_key": "release9-convert-operation-0001"}),
        request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{reference}/convert", json={**convert_base, "idempotency_key": "release9-convert-operation-0002"}),
    )
    assert [item.status_code for item in conversions] == [200, 200]
    assert conversions[0].json() == conversions[1].json()
    assert await gathering_proposal_conversions_collection.count_documents({}) == 1
    assert await events_collection.count_documents({"publication_state": "organizer_draft"}) == 1
    conversion = await gathering_proposal_conversions_collection.find_one({}, {"_id": 0})
    divergent_conversion = await request_as(
        ORGANIZER, "POST", f"/api/gathering-proposals/{reference}/convert",
        json={**convert_base, "preview_digest": "0" * 64, "idempotency_key": "release9-convert-divergent-operation"},
    )
    assert divergent_conversion.status_code == 409
    draft = await events_collection.find_one({"id": conversion["created_event_id"]}, {"_id": 0})
    assert draft["event_invites"] == draft["rsvp_records"] == draft["activity_rsvps"] == []
    assert draft["agenda"] == draft["potluck_items"] == draft["volunteer_slots"] == []
    draft_serialized = str(draft)
    for forbidden in (
        reference, MEMBER["id"], OTHER_MEMBER["id"], submission()["organizer_note"],
        "Early summer", "interested", "private-proposal",
    ):
        assert forbidden not in draft_serialized
    assert (await request_as(OTHER_MEMBER, "GET", f"/api/events/{draft['id']}")).status_code == 404
    assert (await request_as(ORGANIZER, "GET", f"/api/events/{draft['id']}")).status_code == 200
    timeline_export = await request_as(OTHER_MEMBER, "GET", "/api/timeline/export")
    assert timeline_export.status_code == 200
    assert draft["id"] not in timeline_export.text and submission()["organizer_note"] not in timeline_export.text
    assert await notification_events_collection.count_documents({"event_type": "gathering-proposal-published"}) == 0
    conversion_notification = await notification_events_collection.find_one({"event_type": "gathering-proposal-converted"}, {"_id": 0})
    assert conversion_notification["recipient_user_ids"] == [MEMBER["id"]]
    assert conversion_notification["related_id"] == ""

    closed_response = await request_as(
        OTHER_MEMBER, "PUT", f"/api/gathering-proposals/{reference}/interest",
        json={"response": "maybe", "expected_revision": 1, "idempotency_key": "release9-late-response-operation-0001"},
    )
    assert closed_response.status_code == 404

    # A second proposal exercises concurrent organizer terminal decisions.
    second = await request_as(MEMBER, "POST", "/api/gathering-proposals", json=submission("release9-proposal-submit-operation-0002", "Second synthetic proposal"))
    second_ref = second.json()["proposal_reference"]
    decisions = await asyncio.gather(
        request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{second_ref}/publish", json={"expected_revision": 0, "idempotency_key": "release9-racing-publish-operation"}),
        request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{second_ref}/decline", json={"expected_revision": 0, "idempotency_key": "release9-racing-decline-operation", "reason": "not_a_fit"}),
    )
    assert sorted(item.status_code for item in decisions) == [200, 409]
    second_doc = await gathering_proposals_collection.find_one({"public_reference": second_ref}, {"_id": 0})
    assert second_doc["state"] in {"published", "declined"}
    assert second_doc["revision"] == 1

    race = await request_as(MEMBER, "POST", "/api/gathering-proposals", json=submission("release9-proposal-submit-operation-race", "Withdrawal race proposal"))
    race_ref = race.json()["proposal_reference"]
    withdrawal_race = await asyncio.gather(
        request_as(MEMBER, "POST", f"/api/gathering-proposals/{race_ref}/withdraw", json={"expected_revision": 0, "idempotency_key": "release9-racing-withdraw-operation"}),
        request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{race_ref}/publish", json={"expected_revision": 0, "idempotency_key": "release9-racing-withdraw-publish-operation"}),
    )
    assert sorted(item.status_code for item in withdrawal_race) == [200, 409]
    race_doc = await gathering_proposals_collection.find_one({"public_reference": race_ref}, {"_id": 0})
    assert race_doc["state"] in {"published", "withdrawn"} and race_doc["revision"] == 1

    withdrawn = await request_as(MEMBER, "POST", "/api/gathering-proposals", json=submission("release9-proposal-submit-operation-0003", "Withdrawn synthetic proposal"))
    withdrawn_ref = withdrawn.json()["proposal_reference"]
    withdrawal_payload = {"expected_revision": 0, "idempotency_key": "release9-proposal-withdraw-operation"}
    withdrawal = await request_as(MEMBER, "POST", f"/api/gathering-proposals/{withdrawn_ref}/withdraw", json=withdrawal_payload)
    retry_withdrawal = await request_as(MEMBER, "POST", f"/api/gathering-proposals/{withdrawn_ref}/withdraw", json=withdrawal_payload)
    assert withdrawal.status_code == retry_withdrawal.status_code == 200
    assert withdrawal.json()["state"] == "withdrawn"
    assert (await request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{withdrawn_ref}/publish", json={"expected_revision": 1, "idempotency_key": "release9-publish-withdrawn-operation"})).status_code == 409

    closable = await request_as(MEMBER, "POST", "/api/gathering-proposals", json=submission("release9-proposal-submit-operation-0004", "Closable synthetic proposal"))
    closable_ref = closable.json()["proposal_reference"]
    await request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{closable_ref}/publish", json={"expected_revision": 0, "idempotency_key": "release9-closable-publish-operation"})
    closed = await request_as(ORGANIZER, "POST", f"/api/gathering-proposals/{closable_ref}/close", json={"expected_revision": 1, "idempotency_key": "release9-close-pulse-operation"})
    assert closed.status_code == 200 and closed.json()["state"] == "expired"
    assert (await request_as(OTHER_MEMBER, "GET", f"/api/gathering-proposals/{closable_ref}")).status_code == 404
    assert (await request_as(OTHER_MEMBER, "PUT", f"/api/gathering-proposals/{closable_ref}/interest", json={"response": "maybe", "expected_revision": 0, "idempotency_key": "release9-closed-interest-operation"})).status_code == 404

    # Account deletion removes response identity and private proposer content,
    # while preserving the already-created draft and categorical audit linkage.
    deleted = await request_as(MEMBER, "DELETE", "/api/auth/account", json={})
    assert deleted.status_code == 200
    assert await gathering_proposal_responses_collection.count_documents({"user_id": MEMBER["id"]}) == 0
    assert await users_collection.count_documents({"id": MEMBER["id"]}) == 0
    retained = await gathering_proposals_collection.find_one({"public_reference": reference}, {"_id": 0})
    assert retained.get("proposer_tombstone") is True
    assert "proposer_user_id" not in retained and "proposer_display_name" not in retained
    assert retained["working_title"] == retained["organizer_note"] == retained["location_suggestion"] == ""
    retained_conversion = await gathering_proposal_conversions_collection.find_one({"proposal_id": retained["id"]}, {"_id": 0})
    assert retained_conversion.get("proposer_tombstone") is True
    assert "proposer_user_id" not in retained_conversion
    assert await events_collection.count_documents({"id": draft["id"]}) == 1

    # Sole-owner deletion removes all new Stage 9 collections for that family.
    await communities_collection.insert_one({
        "id": SOLE_OWNER["community_id"], "name": "Synthetic Sole Family",
        "lifecycle_state": "active", "owner_user_id": SOLE_OWNER["id"],
    })
    await users_collection.insert_one(SOLE_OWNER.copy())
    await gathering_proposals_collection.insert_one({
        "id": "release9-sole-proposal", "public_reference": "1" * 32,
        "community_id": SOLE_OWNER["community_id"], "proposer_user_id": SOLE_OWNER["id"],
        "state": "published", "revision": 1,
    })
    await gathering_proposal_responses_collection.insert_one({
        "id": "release9-sole-response", "proposal_id": "release9-sole-proposal",
        "community_id": SOLE_OWNER["community_id"], "user_id": SOLE_OWNER["id"],
        "response": "interested", "revision": 1,
    })
    await gathering_proposal_conversions_collection.insert_one({
        "id": "release9-sole-conversion", "proposal_id": "release9-sole-proposal",
        "community_id": SOLE_OWNER["community_id"], "created_event_id": "release9-sole-event",
    })
    sole_deleted = await request_as(SOLE_OWNER, "DELETE", "/api/auth/account", json={})
    assert sole_deleted.status_code == 200
    for collection in (
        gathering_proposals_collection, gathering_proposal_responses_collection,
        gathering_proposal_conversions_collection,
    ):
        assert await collection.count_documents({"community_id": SOLE_OWNER["community_id"]}) == 0
    assert await communities_collection.count_documents({"id": SOLE_OWNER["community_id"]}) == 0


def test_disposable_gathering_proposal_campaign():
    asyncio.run(campaign())
