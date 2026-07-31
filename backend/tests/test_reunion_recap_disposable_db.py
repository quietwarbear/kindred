"""Real MongoDB Stage 8 transaction, concurrency, isolation, and deletion campaign.

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
    memories_collection,
    next_gathering_operations_collection,
    notification_events_collection,
    reunion_recaps_collection,
    users_collection,
)
from dependencies import get_current_user, notification_query_for_user  # noqa: E402
from server import app, ensure_indexes  # noqa: E402

COMMUNITY_ID = "synthetic-release8-family"
OTHER_COMMUNITY_ID = "synthetic-release8-other"
EVENT_ID = "synthetic-release8-reunion"
HOST = {
    "id": "synthetic-release8-host",
    "full_name": "Synthetic Host",
    "email": "host@example.invalid",
    "community_id": COMMUNITY_ID,
    "community_ids": [COMMUNITY_ID],
    "role": "host",
    "auth_provider": "apple",
}
ORGANIZER = {
    "id": "synthetic-release8-organizer",
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
    "community_id": COMMUNITY_ID,
    "community_ids": [COMMUNITY_ID],
    "role": "organizer",
    "auth_provider": "apple",
}
MEMBER = {
    "id": "synthetic-release8-member",
    "full_name": "Synthetic Member",
    "email": "member@example.invalid",
    "community_id": COMMUNITY_ID,
    "community_ids": [COMMUNITY_ID],
    "role": "member",
    "auth_provider": "apple",
}
HIDDEN_MEMBER = {
    **MEMBER,
    "id": "synthetic-release8-hidden",
    "full_name": "Synthetic Hidden Member",
    "email": "hidden@example.invalid",
}
PLATFORM_ADMIN = {
    **MEMBER,
    "id": "synthetic-release8-platform-admin",
    "full_name": "Synthetic Platform Admin",
    "email": "platform@example.invalid",
    "is_platform_admin": True,
}
OUTSIDER = {
    **HOST,
    "id": "synthetic-release8-outsider",
    "full_name": "Synthetic Outsider",
    "email": "outsider@example.invalid",
    "community_id": OTHER_COMMUNITY_ID,
    "community_ids": [OTHER_COMMUNITY_ID],
}


async def _request_as(user, method, path, **kwargs):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://kindred.invalid"
        ) as client:
            return await client.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


def _event():
    return {
        "id": EVENT_ID,
        "community_id": COMMUNITY_ID,
        "created_by": HOST["id"],
        "created_by_name": HOST["full_name"],
        "event_template": "reunion",
        "title": "Synthetic Completed Reunion",
        "start_at": "2026-06-01T09:00:00-04:00",
        "end_at": "2026-06-02T17:00:00-04:00",
        "timezone": "America/New_York",
        "gathering_format": "hybrid",
        "max_attendees": 75,
        "hidden_from_user_ids": [HIDDEN_MEMBER["id"]],
        "event_invites": [
            {
                "id": "synthetic-private-invitation-credential",
                "email": "private-guest@example.invalid",
                "invitee_name": "Private Guest",
                "rsvp_status": "going",
            }
        ],
        "rsvp_records": [
            {"user_id": MEMBER["id"], "user_name": MEMBER["full_name"], "status": "going", "updated_at": "2026-05-01T00:00:00Z"},
            {"user_id": "other-private-user", "user_name": "Other Private Person", "status": "maybe", "updated_at": "2026-05-01T00:00:00Z"},
        ],
        "activity_rsvps": [
            {"activity_id": "synthetic-source-activity", "respondent_id": MEMBER["id"], "status": "coming"},
            {"activity_id": "synthetic-source-activity", "respondent_id": "other-private-user", "status": "maybe"},
        ],
        "agenda": [
            {
                "id": "synthetic-source-activity",
                "title": "Family dinner",
                "start_at": "2026-06-02T15:00:00-04:00",
                "end_at": "2026-06-02T19:00:00-04:00",
                "timezone": "America/New_York",
                "visibility": "published",
                "attendance_requested": True,
            },
            {"id": "synthetic-private-draft", "title": "Organizer draft", "visibility": "draft", "notes": "Private note"},
        ],
        "potluck_items": [
            {"id": "synthetic-source-potluck", "item_name": "Dessert", "assigned_to_id": "other-private-user", "assigned_to": "Other Private Person"}
        ],
        "volunteer_slots": [
            {"id": "synthetic-source-volunteer", "title": "Welcome table", "needed_count": 2, "assigned_member_ids": ["other-private-user"], "assigned_members": ["Other Private Person"]}
        ],
        "travel_coordination_notes": "Private travel details",
        "suggested_contribution": 900,
        "rsvp_revision": 4,
        "created_at": "2026-05-01T00:00:00Z",
    }


async def _campaign():
    for collection in (
        next_gathering_operations_collection,
        reunion_recaps_collection,
        family_access_requests_collection,
        guest_family_claims_collection,
        notification_events_collection,
        memories_collection,
        events_collection,
        users_collection,
        communities_collection,
    ):
        await collection.drop()
    await ensure_indexes()
    await communities_collection.insert_many([
        {"id": COMMUNITY_ID, "name": "Synthetic Family", "lifecycle_state": "active", "owner_user_id": HOST["id"]},
        {"id": OTHER_COMMUNITY_ID, "name": "Synthetic Other", "lifecycle_state": "active", "owner_user_id": OUTSIDER["id"]},
    ])
    await users_collection.insert_many([HOST, ORGANIZER, MEMBER, HIDDEN_MEMBER, PLATFORM_ADMIN, OUTSIDER])
    source_event = _event()
    await events_collection.insert_one(source_event.copy())
    await memories_collection.insert_many([
        {"id": "synthetic-published-memory", "community_id": COMMUNITY_ID, "event_id": EVENT_ID, "created_by": MEMBER["id"], "capsule_status": "published", "description": "Private published memory"},
        {"id": "synthetic-draft-memory", "community_id": COMMUNITY_ID, "event_id": EVENT_ID, "created_by": MEMBER["id"], "capsule_status": "draft", "description": "Private draft memory"},
        {"id": "synthetic-withdrawn-memory", "community_id": COMMUNITY_ID, "event_id": EVENT_ID, "created_by": MEMBER["id"], "capsule_status": "withdrawn", "description": "Withdrawn memory"},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kindred.invalid") as anonymous:
        anonymous_result = await anonymous.get(f"/api/events/{EVENT_ID}/recap")
    assert anonymous_result.status_code == 401
    unpublished_member = await _request_as(MEMBER, "GET", f"/api/events/{EVENT_ID}/recap")
    assert unpublished_member.status_code == 404
    hidden = await _request_as(HIDDEN_MEMBER, "GET", f"/api/events/{EVENT_ID}/recap")
    outsider = await _request_as(OUTSIDER, "GET", f"/api/events/{EVENT_ID}/recap")
    assert hidden.status_code == outsider.status_code == 404
    platform_preview = await _request_as(PLATFORM_ADMIN, "GET", f"/api/events/{EVENT_ID}/recap/organizer")
    assert platform_preview.status_code == 403

    preview = await _request_as(ORGANIZER, "GET", f"/api/events/{EVENT_ID}/recap/organizer")
    assert preview.status_code == 200
    assert preview.json()["state"] == "ready"
    assert preview.json()["completion"]["state"] == "ready"

    edit_payload = {
        "message": "A synthetic private family message.",
        "expected_revision": 0,
        "idempotency_key": "release8-recap-message-operation-0001",
    }
    edits = await asyncio.gather(*[
        _request_as(ORGANIZER, "PUT", f"/api/events/{EVENT_ID}/recap/message", json=edit_payload)
        for _ in range(2)
    ])
    assert [response.status_code for response in edits] == [200, 200]
    assert await reunion_recaps_collection.count_documents({"event_id": EVENT_ID}) == 1
    recap_doc = await reunion_recaps_collection.find_one({"event_id": EVENT_ID}, {"_id": 0})
    assert recap_doc["revision"] == 1

    divergent_edit = await _request_as(
        ORGANIZER,
        "PUT",
        f"/api/events/{EVENT_ID}/recap/message",
        json={**edit_payload, "message": "Different private text"},
    )
    assert divergent_edit.status_code == 409

    publish_payload = {"expected_revision": 1, "idempotency_key": "release8-recap-publish-operation-0001"}
    published = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/recap/publish", json=publish_payload)
    retry_publish = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/recap/publish", json=publish_payload)
    assert published.status_code == retry_publish.status_code == 200
    assert published.json()["state"] == retry_publish.json()["state"] == "published"
    assert await notification_events_collection.count_documents({"event_type": "reunion-recap-published"}) == 1
    await notification_events_collection.delete_many({"event_type": "reunion-recap-published"})
    recovered_publish = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/recap/publish", json=publish_payload)
    assert recovered_publish.status_code == 200
    assert await notification_events_collection.count_documents({"event_type": "reunion-recap-published"}) == 1

    member_recap = await _request_as(MEMBER, "GET", f"/api/events/{EVENT_ID}/recap")
    assert member_recap.status_code == 200
    member_body = member_recap.json()
    assert member_body["message"] == edit_payload["message"]
    assert member_body["aggregate_participation"]["published_memory_count"] == 1
    serialized = str(member_body)
    for forbidden in (
        EVENT_ID,
        "synthetic-source-activity",
        "synthetic-private-invitation-credential",
        "private-guest@example.invalid",
        "Other Private Person",
        "Private travel details",
        "synthetic-draft-memory",
        "synthetic-withdrawn-memory",
        "synthetic-release8-family",
    ):
        assert forbidden not in serialized

    member_notifications = await notification_events_collection.count_documents(await notification_query_for_user(MEMBER))
    hidden_notifications = await notification_events_collection.count_documents(await notification_query_for_user(HIDDEN_MEMBER))
    assert member_notifications == 1
    assert hidden_notifications == 0

    unpublish_payload = {"expected_revision": 2, "idempotency_key": "release8-recap-unpublish-operation-0001"}
    unpublished = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/recap/unpublish", json=unpublish_payload)
    retry_unpublish = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/recap/unpublish", json=unpublish_payload)
    assert unpublished.status_code == retry_unpublish.status_code == 200
    assert unpublished.json()["state"] == "unpublished"
    assert (await _request_as(MEMBER, "GET", f"/api/events/{EVENT_ID}/recap")).status_code == 404
    assert await notification_events_collection.count_documents({"event_type": "reunion-recap-published"}) == 0
    await notification_events_collection.insert_one({
        "id": "synthetic-release8-crash-window-notification",
        "community_id": COMMUNITY_ID,
        "related_id": EVENT_ID,
        "event_type": "reunion-recap-published",
    })
    recovered_unpublish = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/recap/unpublish", json=unpublish_payload)
    assert recovered_unpublish.status_code == 200
    assert await notification_events_collection.count_documents({"event_type": "reunion-recap-published"}) == 0
    republished = await _request_as(
        ORGANIZER,
        "POST",
        f"/api/events/{EVENT_ID}/recap/publish",
        json={"expected_revision": 3, "idempotency_key": "release8-recap-publish-operation-0002"},
    )
    assert republished.status_code == 200
    assert republished.json()["state"] == "published"
    stale_unpublish_retry = await _request_as(
        ORGANIZER, "POST", f"/api/events/{EVENT_ID}/recap/unpublish", json=unpublish_payload
    )
    assert stale_unpublish_retry.status_code == 200
    assert stale_unpublish_retry.json()["state"] == "published"
    assert await notification_events_collection.count_documents({"event_type": "reunion-recap-published"}) == 1

    organizer_body = (await _request_as(ORGANIZER, "GET", f"/api/events/{EVENT_ID}/recap/organizer")).json()
    catalog = organizer_body["carry_forward_catalog"]
    selection = {
        "title": "Synthetic Next Reunion",
        "start_at": "2027-11-06T10:00:00-05:00",
        "end_at": "2027-11-06T18:00:00-05:00",
        "timezone": "America/New_York",
        "itinerary_selection_references": [catalog["itinerary_templates"][0]["selection_reference"]],
        "contribution_selection_references": [item["selection_reference"] for item in catalog["contribution_categories"]],
        "carry_gathering_format": True,
        "carry_capacity": True,
    }
    next_preview = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/next-gathering/preview", json=selection)
    assert next_preview.status_code == 200
    create_payload = {
        **selection,
        "preview_digest": next_preview.json()["preview_digest"],
        "idempotency_key": "release8-next-gathering-operation-0001",
    }
    creations = await asyncio.gather(*[
        _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/next-gathering", json=create_payload)
        for _ in range(2)
    ])
    assert [response.status_code for response in creations] == [200, 200]
    assert creations[0].json() == creations[1].json()
    assert await next_gathering_operations_collection.count_documents({"source_event_id": EVENT_ID}) == 1
    operation = await next_gathering_operations_collection.find_one({"source_event_id": EVENT_ID}, {"_id": 0})
    draft = await events_collection.find_one({"id": operation["created_event_id"]}, {"_id": 0})
    assert draft["publication_state"] == "organizer_draft"
    assert draft["event_invites"] == draft["rsvp_records"] == draft["activity_rsvps"] == []
    assert draft["agenda"][0]["id"] != source_event["agenda"][0]["id"]
    assert draft["potluck_items"][0]["assigned_to"] == ""
    assert draft["volunteer_slots"][0]["assigned_members"] == []
    draft_serialized = str(draft)
    for forbidden in (
        "synthetic-private-invitation-credential",
        "private-guest@example.invalid",
        "Other Private Person",
        "Private travel details",
        "synthetic-source-activity",
        "synthetic-source-potluck",
        "synthetic-source-volunteer",
        EVENT_ID,
    ):
        assert forbidden not in draft_serialized
    member_draft = await _request_as(MEMBER, "GET", f"/api/events/{draft['id']}")
    organizer_draft = await _request_as(ORGANIZER, "GET", f"/api/events/{draft['id']}")
    assert member_draft.status_code == 404
    assert organizer_draft.status_code == 200

    unchanged_source = await events_collection.find_one({"id": EVENT_ID}, {"_id": 0})
    assert unchanged_source["event_invites"] == source_event["event_invites"]
    assert unchanged_source["rsvp_records"] == source_event["rsvp_records"]
    assert unchanged_source["activity_rsvps"] == source_event["activity_rsvps"]
    assert unchanged_source["agenda"] == source_event["agenda"]

    # Distinct explicit operations may create later gatherings, while
    # divergent concurrent selections remain isolated in separate drafts.
    alternate_selection = {
        **selection,
        "title": "Synthetic Alternate Reunion",
        "itinerary_selection_references": [],
        "contribution_selection_references": [],
        "carry_gathering_format": False,
        "carry_capacity": False,
    }
    detailed_selection = {**selection, "title": "Synthetic Detailed Reunion"}
    alternate_preview = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/next-gathering/preview", json=alternate_selection)
    detailed_preview = await _request_as(ORGANIZER, "POST", f"/api/events/{EVENT_ID}/next-gathering/preview", json=detailed_selection)
    divergent = await asyncio.gather(
        _request_as(
            ORGANIZER, "POST", f"/api/events/{EVENT_ID}/next-gathering",
            json={**alternate_selection, "preview_digest": alternate_preview.json()["preview_digest"], "idempotency_key": "release8-next-gathering-operation-0002"},
        ),
        _request_as(
            ORGANIZER, "POST", f"/api/events/{EVENT_ID}/next-gathering",
            json={**detailed_selection, "preview_digest": detailed_preview.json()["preview_digest"], "idempotency_key": "release8-next-gathering-operation-0003"},
        ),
    )
    assert [response.status_code for response in divergent] == [200, 200]
    assert await next_gathering_operations_collection.count_documents({"source_event_id": EVENT_ID}) == 3
    alternate = await events_collection.find_one({"title": "Synthetic Alternate Reunion"}, {"_id": 0})
    detailed = await events_collection.find_one({"title": "Synthetic Detailed Reunion"}, {"_id": 0})
    assert alternate["agenda"] == alternate["potluck_items"] == alternate["volunteer_slots"] == []
    assert len(detailed["agenda"]) == 1
    assert len(detailed["potluck_items"]) == 1
    assert len(detailed["volunteer_slots"]) == 1

    await guest_family_claims_collection.insert_one({
        "id": "synthetic-delete-claim", "community_id": COMMUNITY_ID,
        "claimed_by_user_id": ORGANIZER["id"], "secret_digest": "synthetic-delete-secret",
    })
    await family_access_requests_collection.insert_one({
        "id": "synthetic-delete-request", "public_reference": "synthetic-delete-public-reference",
        "community_id": COMMUNITY_ID, "applicant_user_id": ORGANIZER["id"],
        "applicant_name": ORGANIZER["full_name"], "relationship_fingerprint": "synthetic-private-relationship",
        "submission_operation_hash": "synthetic-private-submit", "status": "pending", "revision": 0,
    })
    deleted = await _request_as(ORGANIZER, "DELETE", "/api/auth/account", json={"password": ""})
    assert deleted.status_code == 200
    assert await guest_family_claims_collection.count_documents({"claimed_by_user_id": ORGANIZER["id"]}) == 0
    tombstone = await family_access_requests_collection.find_one({"id": "synthetic-delete-request"}, {"_id": 0})
    assert tombstone["status"] == "cancelled"
    assert tombstone["applicant_tombstone"] is True
    assert tombstone["applicant_user_id"].startswith("deleted:")
    assert tombstone["applicant_user_id"] != ORGANIZER["id"]
    for removed in ("applicant_name", "relationship_fingerprint", "submission_operation_hash"):
        assert removed not in tombstone
    retained_recap = await reunion_recaps_collection.find_one({"event_id": EVENT_ID}, {"_id": 0})
    assert retained_recap["message"] == edit_payload["message"]
    assert retained_recap["author_tombstone"] is True
    assert "author_user_id" not in retained_recap
    retained_operation = await next_gathering_operations_collection.find_one({"source_event_id": EVENT_ID}, {"_id": 0})
    assert retained_operation["creator_tombstone"] is True
    assert "created_by_user_id" not in retained_operation
    assert await users_collection.find_one({"id": ORGANIZER["id"]}) is None
    assert await communities_collection.find_one({"id": COMMUNITY_ID}) is not None


def test_disposable_reunion_recap_campaign():
    asyncio.run(_campaign())
