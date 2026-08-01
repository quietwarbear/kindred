"""Real MongoDB authorization, priority, isolation, and read-purity campaign for Today."""

from __future__ import annotations

import asyncio
import copy
import os

import pytest
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
    budget_plans_collection,
    communities_collection,
    events_collection,
    family_access_requests_collection,
    gathering_proposal_conversions_collection,
    gathering_proposal_responses_collection,
    gathering_proposals_collection,
    invites_collection,
    memories_collection,
    notification_events_collection,
    reunion_recaps_collection,
    travel_plans_collection,
    users_collection,
)
from dependencies import get_current_user  # noqa: E402
from server import app, ensure_indexes  # noqa: E402

COMMUNITY = "today-family"
OTHER_COMMUNITY = "today-other-family"
PROVISIONAL_COMMUNITY = "today-provisional-family"
LEGACY_COMMUNITY = "today-legacy-family"
HOST = {
    "id": "today-host",
    "community_id": COMMUNITY,
    "community_ids": [COMMUNITY],
    "full_name": "Synthetic Host",
    "email": "host@example.invalid",
    "role": "host",
    "auth_provider": "apple",
}
MEMBER = {
    "id": "today-member",
    "community_id": COMMUNITY,
    "community_ids": [COMMUNITY],
    "full_name": "Synthetic Member",
    "email": "member@example.invalid",
    "role": "member",
    "auth_provider": "apple",
}
SECOND_MEMBER = {
    "id": "today-member-2",
    "community_id": COMMUNITY,
    "community_ids": [COMMUNITY],
    "full_name": "Synthetic Member Two",
    "email": "member2@example.invalid",
    "role": "member",
    "auth_provider": "apple",
}
SUSPENDED = {
    "id": "today-suspended",
    "community_id": COMMUNITY,
    "community_ids": [COMMUNITY],
    "full_name": "Suspended",
    "email": "suspended@example.invalid",
    "role": "member",
    "account_status": "suspended",
    "auth_provider": "apple",
}
OUTSIDER = {
    "id": "today-outsider",
    "community_id": OTHER_COMMUNITY,
    "community_ids": [OTHER_COMMUNITY],
    "full_name": "Outsider",
    "email": "outside@example.invalid",
    "role": "host",
    "auth_provider": "apple",
}
PROVISIONAL_HOST = {
    "id": "today-provisional-host",
    "community_id": PROVISIONAL_COMMUNITY,
    "community_ids": [PROVISIONAL_COMMUNITY],
    "full_name": "Provisional Host",
    "email": "provisional@example.invalid",
    "role": "host",
    "auth_provider": "apple",
}
PROVISIONAL_MEMBER = {
    "id": "today-provisional-member",
    "community_id": PROVISIONAL_COMMUNITY,
    "community_ids": [PROVISIONAL_COMMUNITY],
    "full_name": "Provisional Member",
    "email": "provisional-member@example.invalid",
    "role": "member",
    "auth_provider": "apple",
}
LEGACY_MEMBER = {
    "id": "today-legacy",
    "community_id": LEGACY_COMMUNITY,
    "community_ids": [LEGACY_COMMUNITY],
    "full_name": "Legacy Member",
    "email": "legacy@example.invalid",
    "role": "member",
    "auth_provider": "apple",
}


async def request_as(user, method, path, **kwargs):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://kindred.invalid"
        ) as api:
            return await api.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


def future_reunion():
    return {
        "id": "today-active-reunion",
        "community_id": COMMUNITY,
        "created_by": HOST["id"],
        "created_by_name": HOST["full_name"],
        "title": "Private synthetic reunion title",
        "description": "Private synthetic description",
        "start_at": "2030-06-01T10:00:00+00:00",
        "end_at": "2030-06-01T18:00:00+00:00",
        "timezone": "UTC",
        "location": "Private synthetic location",
        "event_template": "reunion",
        "gathering_format": "in-person",
        "hidden_from_user_ids": [],
        "event_invites": [],
        "rsvp_records": [],
        "rsvp_revision": 0,
        "activity_rsvps": [],
        "attendee_hub_reviewed_by": [],
        "agenda": [
            {
                "id": "today-activity",
                "title": "Private activity",
                "visibility": "published",
                "start_at": "2030-06-01T11:00:00+00:00",
                "end_at": "2030-06-01T12:00:00+00:00",
                "timezone": "UTC",
                "attendance_requested": True,
            }
        ],
        "potluck_items": [
            {
                "id": "today-potluck",
                "item_name": "Private dish",
                "assigned_to": "",
                "assigned_to_id": "",
            }
        ],
        "volunteer_slots": [],
        "event_role_assignments": [
            {"id": "today-role", "role_name": "Host", "assignees": [HOST["id"]]}
        ],
        "planning_checklist": [],
        "created_at": "2026-07-31T00:00:00+00:00",
    }


def completed_reunion():
    value = future_reunion()
    value.update(
        {
            "id": "today-completed-reunion",
            "title": "Private completed reunion",
            "start_at": "2025-06-01T10:00:00+00:00",
            "end_at": "2025-06-01T18:00:00+00:00",
            "agenda": [],
            "potluck_items": [],
            "event_role_assignments": [],
        }
    )
    return value


async def code_for(user):
    response = await request_as(user, "GET", "/api/today")
    assert response.status_code == 200, response.text
    return response.json()["primary_action_code"], response.json()


async def campaign():
    collections = (
        users_collection,
        communities_collection,
        events_collection,
        memories_collection,
        reunion_recaps_collection,
        family_access_requests_collection,
        gathering_proposals_collection,
        gathering_proposal_responses_collection,
        gathering_proposal_conversions_collection,
        notification_events_collection,
        invites_collection,
        travel_plans_collection,
        budget_plans_collection,
    )
    for collection in collections:
        await collection.delete_many({})
    await communities_collection.insert_many(
        [
            {
                "id": COMMUNITY,
                "name": "Synthetic Family",
                "lifecycle_state": "active",
                "owner_user_id": HOST["id"],
            },
            {
                "id": OTHER_COMMUNITY,
                "name": "Other",
                "lifecycle_state": "active",
                "owner_user_id": OUTSIDER["id"],
            },
            {
                "id": PROVISIONAL_COMMUNITY,
                "name": "Provisional",
                "lifecycle_state": "provisional",
                "owner_user_id": PROVISIONAL_HOST["id"],
            },
            {
                "id": LEGACY_COMMUNITY,
                "name": "Legacy",
                "owner_user_id": LEGACY_MEMBER["id"],
            },
        ]
    )
    await users_collection.insert_many(
        [
            HOST,
            MEMBER,
            SECOND_MEMBER,
            SUSPENDED,
            OUTSIDER,
            PROVISIONAL_HOST,
            PROVISIONAL_MEMBER,
            LEGACY_MEMBER,
        ]
    )
    await events_collection.insert_many([future_reunion(), completed_reunion()])
    await ensure_indexes()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://kindred.invalid"
    ) as anonymous:
        assert (await anonymous.get("/api/today")).status_code == 401
    assert (await request_as(SUSPENDED, "GET", "/api/today")).status_code == 404
    assert (
        await request_as(PROVISIONAL_MEMBER, "GET", "/api/today")
    ).status_code == 404
    assert (await request_as(LEGACY_MEMBER, "GET", "/api/today")).status_code == 404
    provisional_code, provisional = await code_for(PROVISIONAL_HOST)
    assert provisional_code == "activate_family_space"
    assert provisional["navigation_categories"] == [
        "today",
        "family_activation",
        "gatherings",
    ]

    # Fresh database role beats a stale organizer/platform claim.
    stale_claim = {**MEMBER, "role": "host", "is_platform_admin": True}
    stale_code, stale_projection = await code_for(stale_claim)
    assert stale_projection["viewer_role"] == "member"
    assert stale_code == "complete_reunion_rsvp"

    # Organizer priorities converge in documented order.
    await events_collection.insert_one(
        {
            **future_reunion(),
            "id": "today-private-draft",
            "publication_state": "organizer_draft",
            "created_at": "2026-07-30T00:00:00+00:00",
        }
    )
    assert (await code_for(HOST))[0] == "finish_reunion_draft"
    await events_collection.delete_one({"id": "today-private-draft"})
    assert (await code_for(HOST))[0] == "prepare_first_invitation"

    await events_collection.update_one(
        {"id": "today-active-reunion"},
        {
            "$set": {
                "event_invites": [
                    {
                        "id": "today-member-invite",
                        "member_id": MEMBER["id"],
                        "invite_source": "member",
                        "email": MEMBER["email"],
                        "rsvp_status": "pending",
                        "shared_at": "2026-07-31T01:00:00+00:00",
                    }
                ]
            }
        },
    )
    await family_access_requests_collection.insert_one(
        {
            "id": "today-pending-access",
            "community_id": COMMUNITY,
            "event_id": "today-active-reunion",
            "applicant_user_id": "synthetic-applicant",
            "status": "pending",
            "created_at": "2026-07-31T02:00:00+00:00",
        }
    )
    assert (await code_for(HOST))[0] == "review_family_access_requests"
    await family_access_requests_collection.delete_one({"id": "today-pending-access"})
    assert (await code_for(HOST))[0] == "resolve_rsvp_attention"

    await events_collection.update_one(
        {"id": "today-active-reunion"},
        {
            "$set": {
                "rsvp_records": [
                    {
                        "user_id": MEMBER["id"],
                        "status": "going",
                        "updated_at": "2026-07-31T03:00:00+00:00",
                    }
                ],
                "event_invites.0.rsvp_status": "going",
            }
        },
    )
    assert (await code_for(HOST))[0] == "complete_command_task"
    await events_collection.update_one(
        {"id": "today-active-reunion"},
        {
            "$set": {
                "activity_rsvps": [
                    {
                        "activity_id": "today-activity",
                        "respondent_id": MEMBER["id"],
                        "status": "coming",
                        "updated_at": "2026-07-31T04:00:00+00:00",
                    }
                ],
                "attendee_hub_reviewed_by": [MEMBER["id"]],
                "potluck_items.0.assigned_to": "Another person",
                "potluck_items.0.assigned_to_id": SECOND_MEMBER["id"],
            }
        },
    )
    # With the command center caught up, a recap outranks proposals and fallback.
    await reunion_recaps_collection.insert_one(
        {
            "id": "today-recap",
            "community_id": COMMUNITY,
            "event_id": "today-completed-reunion",
            "state": "ready",
            "message": "Private recap message",
            "revision": 0,
        }
    )
    assert (await code_for(HOST))[0] == "review_recap"
    await reunion_recaps_collection.update_one(
        {"id": "today-recap"}, {"$set": {"state": "published"}}
    )
    await gathering_proposals_collection.insert_one(
        {
            "id": "today-proposal",
            "public_reference": "a" * 32,
            "community_id": COMMUNITY,
            "state": "submitted",
            "created_at": "2026-07-31T05:00:00+00:00",
            "working_title": "Private proposal title",
            "organizer_note": "Private organizer note",
        }
    )
    assert (await code_for(HOST))[0] == "review_gathering_proposal"
    await gathering_proposals_collection.update_one(
        {"id": "today-proposal"}, {"$set": {"state": "published"}}
    )
    converted = {
        **future_reunion(),
        "id": "today-converted-draft",
        "publication_state": "organizer_draft",
        "created_at": "2026-07-31T06:00:00+00:00",
    }
    await events_collection.insert_one(converted)
    await gathering_proposal_conversions_collection.insert_one(
        {
            "id": "today-conversion",
            "proposal_id": "today-proposal",
            "community_id": COMMUNITY,
            "created_event_id": converted["id"],
            "created_at": "2026-07-31T06:00:00+00:00",
        }
    )
    assert (await code_for(HOST))[0] == "continue_converted_draft"

    # A newly approved member confirms explicitly; merely reading Today is pure.
    await family_access_requests_collection.insert_one(
        {
            "id": "today-approved-access",
            "community_id": COMMUNITY,
            "event_id": "today-active-reunion",
            "applicant_user_id": MEMBER["id"],
            "status": "approved",
            "created_at": "2026-07-31T07:00:00+00:00",
        }
    )
    before_request = await family_access_requests_collection.find_one(
        {"id": "today-approved-access"}, {"_id": 0}
    )
    member_code, member_projection = await code_for(MEMBER)
    after_request = await family_access_requests_collection.find_one(
        {"id": "today-approved-access"}, {"_id": 0}
    )
    assert member_code == "confirm_family_access"
    assert before_request == after_request
    assert member_projection["viewer_role"] == "new_member"
    confirm = await request_as(MEMBER, "POST", "/api/family-access/confirm")
    retry_confirm = await request_as(MEMBER, "POST", "/api/family-access/confirm")
    assert confirm.status_code == retry_confirm.status_code == 200

    # Remove the member's existing response state to walk attendee priority order.
    await events_collection.update_one(
        {"id": "today-active-reunion"},
        {
            "$set": {
                "rsvp_records": [],
                "event_invites.0.rsvp_status": "pending",
                "activity_rsvps": [],
                "attendee_hub_reviewed_by": [],
                "potluck_items.0.assigned_to": "",
                "potluck_items.0.assigned_to_id": "",
            }
        },
    )
    assert (await code_for(MEMBER))[0] == "complete_reunion_rsvp"
    await events_collection.update_one(
        {"id": "today-active-reunion"},
        {
            "$set": {
                "rsvp_records": [
                    {
                        "user_id": MEMBER["id"],
                        "status": "going",
                        "updated_at": "2026-07-31T08:00:00+00:00",
                    }
                ],
                "event_invites.0.rsvp_status": "going",
            }
        },
    )
    assert (await code_for(MEMBER))[0] == "complete_activity_responses"
    await events_collection.update_one(
        {"id": "today-active-reunion"},
        {
            "$set": {
                "activity_rsvps": [
                    {
                        "activity_id": "today-activity",
                        "respondent_id": MEMBER["id"],
                        "status": "coming",
                    }
                ]
            }
        },
    )
    assert (await code_for(MEMBER))[0] == "review_updated_itinerary"
    await events_collection.update_one(
        {"id": "today-active-reunion"},
        {"$addToSet": {"attendee_hub_reviewed_by": MEMBER["id"]}},
    )
    assert (await code_for(MEMBER))[0] == "manage_contribution"
    await events_collection.update_one(
        {"id": "today-active-reunion"},
        {
            "$set": {
                "potluck_items.0.assigned_to": "Another person",
                "potluck_items.0.assigned_to_id": SECOND_MEMBER["id"],
            }
        },
    )
    assert (await code_for(MEMBER))[0] == "respond_to_gathering_pulse"
    await gathering_proposal_responses_collection.insert_one(
        {
            "id": "today-response",
            "proposal_id": "today-proposal",
            "community_id": COMMUNITY,
            "user_id": MEMBER["id"],
            "response": "interested",
            "revision": 1,
        }
    )
    await memories_collection.insert_one(
        {
            "id": "today-memory",
            "event_id": "today-active-reunion",
            "community_id": COMMUNITY,
            "created_by": MEMBER["id"],
            "capsule_status": "draft",
            "story": "Private memory text",
        }
    )
    assert (await code_for(MEMBER))[0] == "continue_memory_contribution"
    await memories_collection.update_one(
        {"id": "today-memory"}, {"$set": {"capsule_status": "published"}}
    )
    await notification_events_collection.insert_many(
        [
            {
                "id": "today-recap-notification",
                "community_id": COMMUNITY,
                "event_type": "reunion-recap-published",
                "title": "Private recap title",
                "description": "Private recap notification",
                "related_id": "today-completed-reunion",
                "audience_scope": "user",
                "recipient_user_ids": [MEMBER["id"]],
                "read_by_user_ids": [],
                "created_at": "2026-07-31T09:00:00+00:00",
            },
            {
                "id": "today-hidden-notification",
                "community_id": COMMUNITY,
                "event_type": "event-update",
                "title": "Hidden title",
                "description": "Hidden description",
                "related_id": "today-hidden-event",
                "audience_scope": "community",
                "read_by_user_ids": [],
                "created_at": "2026-07-31T10:00:00+00:00",
            },
        ]
    )
    await events_collection.insert_one(
        {
            **future_reunion(),
            "id": "today-hidden-event",
            "hidden_from_user_ids": [MEMBER["id"], HOST["id"]],
            "title": "Secret hidden reunion",
            "created_at": "2026-07-31T10:00:00+00:00",
        }
    )
    recap_code, recap_projection = await code_for(MEMBER)
    assert recap_code == "view_published_recap"
    serialized = str(recap_projection)
    for forbidden in (
        "today-active-reunion",
        "today-completed-reunion",
        "Private",
        "Synthetic",
        MEMBER["id"],
        HOST["id"],
        "recipient_user_ids",
        "related_id",
        "hidden",
    ):
        assert forbidden not in serialized
    assert len(recap_projection["secondary_actions"]) <= 3
    assert "today-hidden-notification" not in serialized

    # Mark-read is explicit; Today itself did not mark the notification.
    assert (
        await notification_events_collection.count_documents(
            {"id": "today-recap-notification", "read_by_user_ids": MEMBER["id"]}
        )
        == 0
    )
    marked = await request_as(MEMBER, "POST", "/api/notifications/mark-read")
    assert marked.status_code == 200
    assert (
        await notification_events_collection.count_documents(
            {"id": "today-recap-notification", "read_by_user_ids": MEMBER["id"]}
        )
        == 1
    )

    # Dynamic references resolve only for the same freshly authorized account.
    host_code, host_projection = await code_for(HOST)
    assert host_code == "continue_converted_draft"
    reference = host_projection["primary_action"]["action_reference"]
    resolved = await request_as(HOST, "GET", f"/api/today/actions/{reference}")
    assert (
        resolved.status_code == 200
        and resolved.json()["destination"] == "/reunion/command/today-converted-draft"
    )
    assert (
        await request_as(OUTSIDER, "GET", f"/api/today/actions/{reference}")
    ).status_code == 404

    # Concurrent underlying change returns a complete old or new safe projection.
    await gathering_proposal_responses_collection.delete_one({"id": "today-response"})

    async def close_pulse():
        await gathering_proposals_collection.update_one(
            {"id": "today-proposal"}, {"$set": {"state": "expired"}}
        )

    projection_task = asyncio.create_task(request_as(MEMBER, "GET", "/api/today"))
    await asyncio.gather(projection_task, close_pulse())
    concurrent = projection_task.result()
    assert concurrent.status_code == 200
    assert concurrent.json()["primary_action_code"] in {
        "respond_to_gathering_pulse",
        "open_family_home",
    }
    assert "Private proposal title" not in concurrent.text


def test_disposable_family_today_campaign():
    asyncio.run(campaign())
