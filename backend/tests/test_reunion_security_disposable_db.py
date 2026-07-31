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
    raise RuntimeError(
        "Refusing to run database incident tests against a non-disposable MongoDB URL."
    )
if not os.environ.get("DB_NAME", "").startswith("kindred_disposable_"):
    raise RuntimeError("Disposable database name must start with kindred_disposable_.")

from db import (  # noqa: E402
    budget_plans_collection,
    communities_collection,
    events_collection,
    invites_collection,
    legacy_table_collection,
    memories_collection,
    notification_events_collection,
    travel_plans_collection,
    users_collection,
)
from dependencies import get_current_user  # noqa: E402
from models import (  # noqa: E402
    AgendaItemRequest,
    EventCreateRequest,
    PotluckClaimRequest,
    RSVPRequest,
)
import routes.events as events_routes  # noqa: E402
import routes.public as public_routes  # noqa: E402
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
    await invites_collection.database.drop_collection(invites_collection.name)
    await users_collection.database.drop_collection(users_collection.name)
    await communities_collection.database.drop_collection(communities_collection.name)
    await notification_events_collection.database.drop_collection(
        notification_events_collection.name
    )
    await memories_collection.database.drop_collection(memories_collection.name)
    await travel_plans_collection.database.drop_collection(travel_plans_collection.name)
    await budget_plans_collection.database.drop_collection(budget_plans_collection.name)
    await legacy_table_collection.database.drop_collection(legacy_table_collection.name)
    await ensure_indexes()
    await communities_collection.insert_one(
        {
            "id": COMMUNITY_ID,
            "name": "Synthetic Community",
        }
    )
    await legacy_table_collection.insert_one(
        {
            "id": "synthetic-legacy-config",
            "community_id": COMMUNITY_ID,
            "base_url": "https://example.invalid",
        }
    )
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
        "event_invites": [
            {
                "id": "synthetic-bearer-credential",
                "member_id": MEMBER["id"],
                "invite_source": "member",
                "invitee_name": MEMBER["full_name"],
                "email": MEMBER["email"],
                "note": "Synthetic private note",
                "share_message": "Synthetic private invitation message",
                "rsvp_status": "going",
            }
        ],
        "rsvp_records": [
            {
                "user_id": MEMBER["id"],
                "user_name": MEMBER["full_name"],
                "status": "going",
                "guests": 1,
                "updated_at": "2027-01-01T00:00:00+00:00",
            }
        ],
        "activity_rsvps": [
            {
                "activity_id": "synthetic-private-activity",
                "respondent_id": MEMBER["id"],
                "display_name": MEMBER["full_name"],
                "status": "coming",
                "party_size": 2,
            }
        ],
        "activity_rsvp_summaries": {},
        "agenda": [
            {
                "id": "synthetic-published-activity",
                "title": "Synthetic Published Activity",
                "description": "Synthetic attendee-visible description",
                "start_at": "2027-07-20T12:00:00-04:00",
                "end_at": "2027-07-20T13:00:00-04:00",
                "timezone": "America/New_York",
                "visibility": "published",
                "attendance_requested": False,
            },
            {
                "id": "synthetic-private-activity",
                "title": "Synthetic Draft Activity",
                "description": "Synthetic organizer-only agenda detail",
                "start_at": "2027-07-20T14:00:00-04:00",
                "end_at": "2027-07-20T15:00:00-04:00",
                "timezone": "America/New_York",
                "visibility": "draft",
                "attendance_requested": True,
            },
        ],
        "potluck_items": [
            {
                "id": "synthetic-open-dish",
                "item_name": "Synthetic Ice",
                "assigned_to": "",
            }
        ],
        "volunteer_slots": [
            {
                "id": "synthetic-volunteer-slot",
                "title": "Synthetic Welcome Table",
                "needed_count": 1,
                "assigned_members": [],
            }
        ],
        "planning_checklist": [{"title": "Synthetic private planning task"}],
        "planning_team_member_ids": [],
        "travel_coordination_notes": "Synthetic private travel detail",
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(sensitive_event.copy())
    hidden_start = datetime.now(timezone.utc) + timedelta(days=7)
    hidden_event = {
        **sensitive_event,
        "id": "synthetic-hidden-event",
        "title": "Synthetic Surprise Gathering",
        "start_at": hidden_start.isoformat(),
        "end_at": (hidden_start + timedelta(hours=2)).isoformat(),
        "hidden_from_user_ids": [MEMBER["id"]],
        "recurrence_frequency": "weekly",
        "event_invites": [
            {
                "id": "synthetic-hidden-invite",
                "member_id": MEMBER["id"],
                "invite_source": "member",
                "invitee_name": MEMBER["full_name"],
                "email": MEMBER["email"],
                "rsvp_status": "pending",
            }
        ],
        "rsvp_records": [
            {
                "user_id": MEMBER["id"],
                "user_name": MEMBER["full_name"],
                "status": "going",
                "guests": 0,
            }
        ],
        "activity_rsvps": [],
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(hidden_event.copy())
    await memories_collection.insert_one(
        {
            "id": "synthetic-hidden-memory",
            "community_id": COMMUNITY_ID,
            "event_id": hidden_event["id"],
            "event_title": hidden_event["title"],
            "title": "Synthetic Surprise Memory",
            "description": "Synthetic hidden-event memory details",
            "created_by": HOST["id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    await travel_plans_collection.insert_one(
        {
            "id": "synthetic-hidden-travel",
            "community_id": COMMUNITY_ID,
            "event_id": hidden_event["id"],
            "title": "Synthetic Surprise Travel",
            "details": "Synthetic hidden travel details",
            "amount_estimate": 100,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    await budget_plans_collection.insert_one(
        {
            "id": "synthetic-hidden-budget",
            "community_id": COMMUNITY_ID,
            "event_id": hidden_event["id"],
            "title": "Synthetic Surprise Budget",
            "target_amount": 500,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kindred.invalid",
    ) as client:
        missing_header = await client.get("/api/public/rsvp")
        secure_view = await client.get(
            "/api/public/rsvp",
            headers={"Authorization": "Bearer synthetic-bearer-credential"},
        )
        secure_submit = await client.post(
            "/api/public/rsvp",
            headers={"Authorization": "Bearer synthetic-bearer-credential"},
            json={"status": "going", "guests": 1, "activity_responses": {}},
        )
        legacy_path = await client.get("/api/public/rsvp/synthetic-bearer-credential")
        hidden_public_view = await client.get(
            "/api/public/rsvp",
            headers={"Authorization": "Bearer synthetic-hidden-invite"},
        )
        hidden_public_submit = await client.post(
            "/api/public/rsvp",
            headers={"Authorization": "Bearer synthetic-hidden-invite"},
            json={"status": "going", "guests": 0, "activity_responses": {}},
        )
    assert missing_header.status_code == 401
    assert secure_view.status_code == 200
    assert secure_view.json()["invitee_name"] == MEMBER["full_name"]
    assert secure_submit.status_code == 200
    assert secure_submit.json()["saved"] is True
    assert legacy_path.status_code == 404
    assert hidden_public_view.status_code == 404
    assert hidden_public_submit.status_code == 404

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kindred.invalid",
    ) as client:
        anonymous_command = await client.get(
            f"/api/events/{sensitive_event['id']}/command-center"
        )
    assert anonymous_command.status_code == 401
    member_command = await _request_as(
        MEMBER,
        "GET",
        f"/api/events/{sensitive_event['id']}/command-center",
    )
    assert member_command.status_code == 403
    platform_admin_member = {
        **MEMBER,
        "id": "synthetic-platform-admin",
        "is_platform_admin": True,
    }
    platform_admin_command = await _request_as(
        platform_admin_member,
        "GET",
        f"/api/events/{sensitive_event['id']}/command-center",
    )
    assert platform_admin_command.status_code == 403
    cross_community_command = await _request_as(
        OUTSIDER,
        "GET",
        f"/api/events/{sensitive_event['id']}/command-center",
    )
    assert cross_community_command.status_code == 404
    hidden_organizer = {**MEMBER, "role": "organizer"}
    hidden_command = await _request_as(
        hidden_organizer,
        "GET",
        f"/api/events/{hidden_event['id']}/command-center",
    )
    assert hidden_command.status_code == 404
    organizer_command = await _request_as(
        HOST,
        "GET",
        f"/api/events/{sensitive_event['id']}/command-center",
    )
    assert organizer_command.status_code == 200
    command_text = str(organizer_command.json())
    assert organizer_command.json()["responses"]["reconciles"] is True
    assert organizer_command.json()["responses"]["total"] == 1
    assert organizer_command.json()["responses"]["missing"] == 0
    assert "synthetic-bearer-credential" not in command_text
    assert MEMBER["email"] not in command_text
    assert MEMBER["full_name"] not in command_text
    organizer_preview = await _request_as(
        HOST,
        "GET",
        f"/api/events/{sensitive_event['id']}/guest-preview",
    )
    assert organizer_preview.status_code == 200
    preview_text = str(organizer_preview.json())
    assert "synthetic-bearer-credential" not in preview_text
    assert MEMBER["email"] not in preview_text
    assert "Synthetic private" not in preview_text

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kindred.invalid",
    ) as client:
        anonymous_hub = await client.get(
            f"/api/events/{sensitive_event['id']}/attendee-hub"
        )
    assert anonymous_hub.status_code == 401
    member_hub = await _request_as(
        MEMBER,
        "GET",
        f"/api/events/{sensitive_event['id']}/attendee-hub",
    )
    assert member_hub.status_code == 200
    hub_payload = member_hub.json()
    assert hub_payload["rsvp"]["my_status"] == "going"
    assert [item["id"] for item in hub_payload["itinerary"]["activities"]] == [
        "synthetic-published-activity"
    ]
    assert hub_payload["next_action"]["code"] == "choose_contribution"
    hub_text = str(hub_payload)
    for private_value in (
        "synthetic-bearer-credential",
        MEMBER["email"],
        "Synthetic organizer-only agenda detail",
        "Synthetic private planning task",
        "Synthetic private travel detail",
    ):
        assert private_value not in hub_text
    hidden_hub = await _request_as(
        MEMBER,
        "GET",
        f"/api/events/{hidden_event['id']}/attendee-hub",
    )
    assert hidden_hub.status_code == 404
    cross_community_hub = await _request_as(
        OUTSIDER,
        "GET",
        f"/api/events/{sensitive_event['id']}/attendee-hub",
    )
    assert cross_community_hub.status_code == 404

    second_member = {
        "id": "synthetic-member-2",
        "community_id": COMMUNITY_ID,
        "full_name": "Synthetic Second Member",
        "email": "member-2@example.invalid",
        "role": "member",
    }
    await users_collection.insert_one(second_member.copy())
    final_opening_results = await asyncio.gather(
        events_routes.claim_potluck_item(
            sensitive_event["id"],
            PotluckClaimRequest(
                item_id="synthetic-open-dish",
                idempotency_key="synthetic-claim-member-1",
            ),
            MEMBER,
        ),
        events_routes.claim_potluck_item(
            sensitive_event["id"],
            PotluckClaimRequest(
                item_id="synthetic-open-dish",
                idempotency_key="synthetic-claim-member-2",
            ),
            second_member,
        ),
        return_exceptions=True,
    )
    assert (
        sum(not isinstance(result, Exception) for result in final_opening_results) == 1
    )
    losing_claim = next(
        result for result in final_opening_results if isinstance(result, HTTPException)
    )
    assert losing_claim.status_code == 409
    claimed_event = await events_collection.find_one(
        {"id": sensitive_event["id"]},
        {"_id": 0},
    )
    winning_member_id = claimed_event["potluck_items"][0]["assigned_to_id"]
    winning_member = MEMBER if winning_member_id == MEMBER["id"] else second_member
    retry_claim = await events_routes.claim_potluck_item(
        sensitive_event["id"],
        PotluckClaimRequest(
            item_id="synthetic-open-dish",
            idempotency_key="synthetic-claim-retry",
        ),
        winning_member,
    )
    assert retry_claim["potluck_items"][0]["is_mine"] is True

    memory_path = f"/api/events/{sensitive_event['id']}/attendee-hub/memory"
    memory_retries = await asyncio.gather(
        _request_as(
            MEMBER,
            "POST",
            memory_path,
            json={"story": "A synthetic attendee story."},
        ),
        _request_as(
            MEMBER,
            "POST",
            memory_path,
            json={"story": "A synthetic attendee story."},
        ),
    )
    assert [response.status_code for response in memory_retries] == [200, 200]
    assert (
        await memories_collection.count_documents(
            {
                "community_id": COMMUNITY_ID,
                "event_id": sensitive_event["id"],
                "created_by": MEMBER["id"],
                "source": "reunion_attendee_prompt",
            }
        )
        == 1
    )
    attendee_memory = await memories_collection.find_one(
        {
            "event_id": sensitive_event["id"],
            "created_by": MEMBER["id"],
            "source": "reunion_attendee_prompt",
        },
        {"_id": 0},
    )
    assert attendee_memory["tags"] == []
    assert attendee_memory["ai_summary"] == ""

    planner = {
        "id": "synthetic-planner",
        "community_id": COMMUNITY_ID,
        "full_name": "Synthetic Planner",
        "email": "planner@example.invalid",
        "email_normalized": "planner@example.invalid",
        "role": "organizer",
    }
    ordinary_planning_candidate = {
        "id": "synthetic-ordinary-planning-candidate",
        "community_id": COMMUNITY_ID,
        "full_name": "Synthetic Ordinary Member",
        "email": "ordinary@example.com",
        "email_normalized": "ordinary@example.com",
        "role": "member",
    }
    await users_collection.insert_many(
        [planner.copy(), ordinary_planning_candidate.copy()]
    )
    ordinary_member_assignment = await _request_as(
        HOST,
        "POST",
        f"/api/events/{sensitive_event['id']}/planning-team/invitations",
        json={
            "email": ordinary_planning_candidate["email"].upper(),
            "idempotency_key": "planner-member-attempt-0001",
        },
    )
    assert ordinary_member_assignment.status_code == 409
    assert (await users_collection.find_one({"id": ordinary_planning_candidate["id"]}))[
        "role"
    ] == "member"

    invitation_path = f"/api/events/{sensitive_event['id']}/planning-team/invitations"
    concurrent_invites = await asyncio.gather(
        _request_as(
            HOST,
            "POST",
            invitation_path,
            json={
                "email": "NEW.PLANNER@example.com",
                "idempotency_key": "planner-invite-concurrent-0001",
            },
        ),
        _request_as(
            HOST,
            "POST",
            invitation_path,
            json={
                "email": "new.planner@EXAMPLE.COM",
                "idempotency_key": "planner-invite-concurrent-0002",
            },
        ),
    )
    assert [response.status_code for response in concurrent_invites] == [200, 200]
    assert (
        await invites_collection.count_documents(
            {
                "planning_event_id": sensitive_event["id"],
                "email_normalized": "new.planner@example.com",
                "status": "pending",
            }
        )
        == 1
    )
    idempotent_retry = await _request_as(
        HOST,
        "POST",
        invitation_path,
        json={
            "email": "new.planner@example.com",
            "idempotency_key": "planner-invite-concurrent-0001",
        },
    )
    assert idempotent_retry.status_code == 200
    planning_team_view = await _request_as(
        HOST,
        "GET",
        f"/api/events/{sensitive_event['id']}/planning-team",
    )
    assert planning_team_view.status_code == 200
    pending_invitation = planning_team_view.json()["pending_invitations"][0]
    assert pending_invitation["email"] == "new.planner@example.com"
    assert "code" not in str(planning_team_view.json())
    revoke_invitation = await _request_as(
        HOST,
        "DELETE",
        (
            f"/api/events/{sensitive_event['id']}/planning-team/invitations/"
            f"{pending_invitation['id']}"
        ),
    )
    assert revoke_invitation.status_code == 200
    assert (
        await invites_collection.count_documents(
            {
                "planning_event_id": sensitive_event["id"],
                "status": "pending",
            }
        )
        == 0
    )

    assignment_path = f"/api/events/{sensitive_event['id']}/planning-team/assignments"
    concurrent_assignments = await asyncio.gather(
        _request_as(
            HOST,
            "POST",
            assignment_path,
            json={
                "member_id": planner["id"],
                "idempotency_key": "planner-assignment-concurrent-0001",
            },
        ),
        _request_as(
            HOST,
            "POST",
            assignment_path,
            json={
                "member_id": planner["id"],
                "idempotency_key": "planner-assignment-concurrent-0002",
            },
        ),
    )
    assert [response.status_code for response in concurrent_assignments] == [200, 200]
    assigned_event = await events_collection.find_one({"id": sensitive_event["id"]})
    assert assigned_event["planning_team_member_ids"] == [planner["id"]]
    revoke_assignment = await _request_as(
        HOST,
        "DELETE",
        (
            f"/api/events/{sensitive_event['id']}/planning-team/assignments/"
            f"{planner['id']}"
        ),
    )
    assert revoke_assignment.status_code == 200
    assigned_event = await events_collection.find_one({"id": sensitive_event["id"]})
    assert assigned_event.get("planning_team_member_ids", []) == []
    hidden_assignment = await _request_as(
        hidden_organizer,
        "POST",
        f"/api/events/{hidden_event['id']}/planning-team/assignments",
        json={
            "member_id": planner["id"],
            "idempotency_key": "planner-hidden-attempt-0001",
        },
    )
    assert hidden_assignment.status_code == 404
    cross_community_assignment = await _request_as(
        OUTSIDER,
        "POST",
        assignment_path,
        json={
            "member_id": planner["id"],
            "idempotency_key": "planner-cross-community-0001",
        },
    )
    assert cross_community_assignment.status_code == 404

    before_reminder = await events_collection.find_one({"id": sensitive_event["id"]})
    reminder_preflight = await _request_as(
        HOST,
        "POST",
        f"/api/events/{sensitive_event['id']}/reminders/preflight",
        json={"idempotency_key": "reminder-preflight-no-mutation-0001"},
    )
    assert reminder_preflight.status_code == 200
    assert reminder_preflight.json()["available"] is False
    after_reminder = await events_collection.find_one({"id": sensitive_event["id"]})
    assert before_reminder == after_reminder

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
        organizer_event = next(
            event for event in organizer_events if event["id"] == sensitive_event["id"]
        )
        assert (
            organizer_event["event_invites"][0]["id"] == "synthetic-bearer-credential"
        )
        assert organizer_event["rsvp_records"][0]["user_id"] == MEMBER["id"]

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
    assert hidden_event["title"] not in str(member_timeline.json())

    member_events = await _request_as(MEMBER, "GET", "/api/events")
    assert hidden_event["title"] not in str(member_events.json())
    hidden_detail = await _request_as(
        MEMBER,
        "GET",
        f"/api/events/{hidden_event['id']}",
    )
    assert hidden_detail.status_code == 404
    for export_path in (
        "/api/timeline/export",
        "/api/timeline/export?format=csv",
    ):
        exported = await _request_as(MEMBER, "GET", export_path)
        assert exported.status_code == 200
        assert hidden_event["title"] not in exported.text
    reminders = await _request_as(MEMBER, "GET", "/api/gatherings/reminders")
    assert reminders.status_code == 200
    assert hidden_event["title"] not in str(reminders.json())
    kinship = await _request_as(
        MEMBER,
        "GET",
        f"/api/kinship/person/{MEMBER['id']}",
    )
    assert kinship.status_code == 200
    assert hidden_event["title"] not in str(kinship.json()["gatherings"])
    digest = await _request_as(MEMBER, "POST", "/api/digest/preview")
    assert digest.status_code == 200
    assert hidden_event["title"] not in str(digest.json())
    assert "Synthetic Surprise Memory" not in str(digest.json())
    assert "_hidden_from" not in str(digest.json())
    assert "_event_id" not in str(digest.json())
    health = await _request_as(MEMBER, "GET", "/api/community/health")
    assert health.status_code == 200
    assert health.json()["archive"]["gatherings"] == 1
    hidden_memory = await _request_as(
        MEMBER,
        "POST",
        "/api/memories",
        json={
            "title": "Synthetic private-association check",
            "event_id": hidden_event["id"],
        },
    )
    assert hidden_memory.status_code == 200
    assert hidden_memory.json()["event_title"] == ""
    for path in (
        "/api/memories",
        "/api/memory/search?q=Surprise",
        "/api/community/overview",
        "/api/courtyard/home",
        "/api/travel-plans",
        "/api/budget-plans",
        "/api/funds-travel/overview",
    ):
        response = await _request_as(MEMBER, "GET", path)
        assert response.status_code == 200
        serialized = str(response.json())
        assert "Synthetic Surprise Memory" not in serialized
        assert "Synthetic Surprise Travel" not in serialized
        assert "Synthetic Surprise Budget" not in serialized
        assert hidden_event["title"] not in serialized
    overview = await _request_as(MEMBER, "GET", "/api/community/overview")
    assert overview.json()["stats"]["events"] == 1
    legacy_member = await _request_as(
        MEMBER,
        "POST",
        "/api/legacy-table/sync-preview",
    )
    assert legacy_member.status_code == 403
    legacy_host = await _request_as(
        HOST,
        "POST",
        "/api/legacy-table/sync-preview",
    )
    assert legacy_host.status_code == 200
    assert legacy_host.json()["preview_counts"]["events"] == 2

    race_event = {
        **sensitive_event,
        "id": "synthetic-hide-write-race",
        "title": "Synthetic Race Gathering",
        "event_invites": [
            {
                "id": "synthetic-race-public",
                "member_id": MEMBER["id"],
                "invite_source": "member",
                "invitee_name": MEMBER["full_name"],
                "email": MEMBER["email"],
                "rsvp_status": "pending",
            }
        ],
        "rsvp_records": [],
        "activity_rsvps": [],
        "agenda": [
            {
                "id": "synthetic-race-activity",
                "title": "Synthetic Race Activity",
                "start_at": (hidden_start + timedelta(hours=1)).isoformat(),
                "end_at": (hidden_start + timedelta(hours=2)).isoformat(),
                "timezone": "UTC",
                "visibility": "published",
                "attendance_requested": True,
            }
        ],
        "hidden_from_user_ids": [],
        "rsvp_revision": 0,
    }
    await events_collection.insert_one(race_event.copy())
    original_compare_and_swap = events_routes.compare_and_swap_event

    async def hide_before_compare(collection, query, mutate):
        await events_collection.update_one(
            {"id": race_event["id"]},
            {"$set": {"hidden_from_user_ids": [MEMBER["id"]]}},
        )
        return await original_compare_and_swap(collection, query, mutate)

    events_routes.compare_and_swap_event = hide_before_compare
    try:
        raced_overall = await _request_as(
            MEMBER,
            "POST",
            f"/api/events/{race_event['id']}/rsvp",
            json={"status": "going", "guests": 0},
        )
    finally:
        events_routes.compare_and_swap_event = original_compare_and_swap
    assert raced_overall.status_code == 404
    raced_doc = await events_collection.find_one(
        {"id": race_event["id"]},
        {"_id": 0},
    )
    assert raced_doc["rsvp_records"] == []

    await events_collection.update_one(
        {"id": race_event["id"]},
        {"$set": {"hidden_from_user_ids": []}},
    )
    events_routes.compare_and_swap_event = hide_before_compare
    try:
        raced_activity = await _request_as(
            MEMBER,
            "POST",
            f"/api/events/{race_event['id']}/activity-rsvp",
            json={
                "activity_id": "synthetic-race-activity",
                "status": "coming",
                "party_size": 1,
            },
        )
    finally:
        events_routes.compare_and_swap_event = original_compare_and_swap
    assert raced_activity.status_code == 404
    raced_doc = await events_collection.find_one(
        {"id": race_event["id"]},
        {"_id": 0},
    )
    assert raced_doc["activity_rsvps"] == []

    await events_collection.update_one(
        {"id": race_event["id"]},
        {"$set": {"hidden_from_user_ids": []}},
    )
    events_routes.compare_and_swap_event = hide_before_compare
    try:
        raced_contribution = await _request_as(
            MEMBER,
            "POST",
            f"/api/events/{race_event['id']}/potluck-claim",
            json={
                "item_id": "synthetic-open-dish",
                "idempotency_key": "synthetic-hidden-contribution-race",
            },
        )
    finally:
        events_routes.compare_and_swap_event = original_compare_and_swap
    assert raced_contribution.status_code == 404
    raced_doc = await events_collection.find_one(
        {"id": race_event["id"]},
        {"_id": 0},
    )
    assert raced_doc["potluck_items"][0].get("assigned_to_id", "") == ""

    await events_collection.update_one(
        {"id": race_event["id"]},
        {"$set": {"hidden_from_user_ids": []}},
    )
    original_public_compare = public_routes.compare_and_swap_event
    public_routes.compare_and_swap_event = hide_before_compare
    try:
        with pytest.raises(HTTPException) as hidden_public_race:
            await public_rsvp_submit(
                "synthetic-race-public",
                PublicRSVPRequest(
                    status="going",
                    guests=0,
                    activity_responses={},
                ),
            )
    finally:
        public_routes.compare_and_swap_event = original_public_compare
    assert hidden_public_race.value.status_code == 404
    raced_doc = await events_collection.find_one(
        {"id": race_event["id"]},
        {"_id": 0},
    )
    assert raced_doc["rsvp_records"] == []

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

    await notification_events_collection.insert_many(
        [
            {
                "id": "synthetic-organizer-rsvp-notification",
                "community_id": COMMUNITY_ID,
                "event_type": "event-rsvp",
                "title": "RSVP updated",
                "description": f"{MEMBER['full_name']} is attending.",
                "audience_scope": "organizer",
                "read_by_user_ids": [],
                "created_at": "2099-01-02T00:00:00+00:00",
            },
            {
                "id": "synthetic-community-notification",
                "community_id": COMMUNITY_ID,
                "event_type": "event-create",
                "title": "Community gathering",
                "description": "A gathering was created.",
                "audience_scope": "community",
                "read_by_user_ids": [],
                "created_at": "2099-01-01T00:00:00+00:00",
            },
            {
                "id": "synthetic-legacy-rsvp-notification",
                "community_id": COMMUNITY_ID,
                "event_type": "rsvp-update",
                "title": "Legacy RSVP updated",
                "description": f"{MEMBER['full_name']} is attending.",
                "audience_scope": "event",
                "read_by_user_ids": [],
                "created_at": "2099-01-03T00:00:00+00:00",
            },
            {
                "id": "synthetic-hidden-invite-notification",
                "community_id": COMMUNITY_ID,
                "event_type": "event-invite",
                "title": f"Invites prepared for {hidden_event['title']}",
                "description": "Synthetic hidden invitation details.",
                "related_id": hidden_event["id"],
                "audience_scope": "event",
                "read_by_user_ids": [],
                "created_at": "2099-01-04T00:00:00+00:00",
            },
            {
                "id": "synthetic-hidden-reminder-notification",
                "community_id": COMMUNITY_ID,
                "event_type": "reminder-send",
                "title": f"Reminders prepared for {hidden_event['title']}",
                "description": "Synthetic hidden reminder details.",
                "related_id": hidden_event["id"],
                "audience_scope": "event",
                "read_by_user_ids": [],
                "created_at": "2099-01-05T00:00:00+00:00",
            },
        ]
    )
    for path in ("/api/activity-feed", "/api/notifications/history"):
        host_feed = await _request_as(HOST, "GET", path)
        member_feed = await _request_as(MEMBER, "GET", path)
        outsider_feed = await _request_as(OUTSIDER, "GET", path)
        assert host_feed.status_code == 200
        assert member_feed.status_code == 200
        assert outsider_feed.status_code == 200
        assert "synthetic-organizer-rsvp-notification" in str(host_feed.json())
        assert "synthetic-legacy-rsvp-notification" in str(host_feed.json())
        assert "synthetic-organizer-rsvp-notification" not in str(member_feed.json())
        assert "synthetic-legacy-rsvp-notification" not in str(member_feed.json())
        assert "synthetic-hidden-invite-notification" not in str(member_feed.json())
        assert "synthetic-hidden-reminder-notification" not in str(member_feed.json())
        assert hidden_event["title"] not in str(member_feed.json())
        assert MEMBER["full_name"] not in str(member_feed.json())
        assert "synthetic-organizer-rsvp-notification" not in str(outsider_feed.json())
        assert "synthetic-community-notification" in str(member_feed.json())

    host_unread = await _request_as(HOST, "GET", "/api/notifications/unread-count")
    member_unread = await _request_as(MEMBER, "GET", "/api/notifications/unread-count")
    assert host_unread.json()["unread_count"] == 5
    assert member_unread.json()["unread_count"] == 1
    marked = await _request_as(MEMBER, "POST", "/api/notifications/mark-read")
    assert marked.json()["marked_count"] == 1
    organizer_only = await notification_events_collection.find_one(
        {"id": "synthetic-organizer-rsvp-notification"},
        {"_id": 0},
    )
    assert MEMBER["id"] not in organizer_only["read_by_user_ids"]
    legacy_named = await notification_events_collection.find_one(
        {"id": "synthetic-legacy-rsvp-notification"},
        {"_id": 0},
    )
    assert MEMBER["id"] not in legacy_named["read_by_user_ids"]
    for notification_id in (
        "synthetic-hidden-invite-notification",
        "synthetic-hidden-reminder-notification",
    ):
        hidden_notification = await notification_events_collection.find_one(
            {"id": notification_id},
            {"_id": 0},
        )
        assert MEMBER["id"] not in hidden_notification["read_by_user_ids"]

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
    await asyncio.gather(
        *[
            public_rsvp_submit(
                f"synthetic-concurrent-{index:02d}",
                PublicRSVPRequest(
                    status="going",
                    guests=index % 3,
                    activity_responses={"synthetic-activity": "coming"},
                ),
            )
            for index in range(invite_count)
        ]
    )
    persisted = await events_collection.find_one(
        {"id": concurrency_event["id"]},
        {"_id": 0},
    )
    assert len(persisted["rsvp_records"]) == invite_count
    assert len(persisted["activity_rsvps"]) == invite_count
    assert all(
        invite["rsvp_status"] == "going" for invite in persisted["event_invites"]
    )
    assert persisted["rsvp_revision"] == invite_count

    await users_collection.update_one(
        {"id": MEMBER["id"]},
        {"$set": {"email": "MeMbEr@Example.Invalid"}},
    )
    legacy_member_event = {
        **sensitive_event,
        "id": "synthetic-legacy-member-event",
        "event_invites": [
            {
                "id": "synthetic-legacy-member-invite",
                "invite_source": "member",
                "invitee_name": MEMBER["full_name"],
                "email": MEMBER["email"],
                "rsvp_status": "pending",
            }
        ],
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
    assert await users_collection.count_documents({"id": MEMBER["id"]}) == 1

    guest_identity_event = {
        **sensitive_event,
        "id": "synthetic-guest-identity-event",
        "event_invites": [
            {
                "id": "synthetic-guest-identity-invite",
                "invite_source": "guest",
                "invitee_name": "Synthetic Unrelated Guest",
                "email": MEMBER["email"],
                "rsvp_status": "pending",
            }
        ],
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
    assert (
        await events_collection.count_documents(
            {
                "community_id": COMMUNITY_ID,
                "created_by": HOST["id"],
                "client_request_id": "synthetic-idempotency-key",
            }
        )
        == 1
    )

    indexes = {index["name"]: index async for index in events_collection.list_indexes()}
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

    inherited_timezone_event = {
        **sensitive_event,
        "id": "synthetic-inherited-timezone-event",
        "start_at": "2027-11-08T09:00:00",
        "end_at": "2027-11-08T18:00:00",
        "timezone": "UTC",
        "event_invites": [],
        "rsvp_records": [],
        "agenda": [
            {
                "id": "synthetic-inherited-timezone-activity",
                "title": "Inherited local time",
                "start_at": "2027-11-07T01:30:00",
                "end_at": "2027-11-07T03:30:00",
                "timezone": "",
                "visibility": "published",
            }
        ],
    }
    await events_collection.insert_one(inherited_timezone_event.copy())
    ambiguous_timezone_update = await _request_as(
        HOST,
        "PUT",
        f"/api/events/{inherited_timezone_event['id']}",
        json={"timezone": "America/New_York"},
    )
    assert ambiguous_timezone_update.status_code == 422
    assert ambiguous_timezone_update.json()["detail"]["code"] == (
        "invalid_inherited_itinerary_timezone"
    )
    unchanged = await events_collection.find_one(
        {"id": inherited_timezone_event["id"]},
        {"_id": 0, "timezone": 1},
    )
    assert unchanged["timezone"] == "UTC"

    await events_collection.update_one(
        {"id": inherited_timezone_event["id"]},
        {
            "$set": {
                "agenda.0.start_at": "2027-03-14T02:30:00",
                "agenda.0.end_at": "2027-03-14T04:30:00",
            }
        },
    )
    nonexistent_timezone_update = await _request_as(
        HOST,
        "PUT",
        f"/api/events/{inherited_timezone_event['id']}",
        json={"timezone": "America/New_York"},
    )
    assert nonexistent_timezone_update.status_code == 422

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
        item
        for item in timezone_override.json()["agenda"]
        if item["title"] == "Synthetic Timezone Override"
    )
    assert timezone_activity["timezone"] == "Pacific/Honolulu"

    deadline_event = await events_collection.find_one(
        {"id": deadline_event["id"]},
        {"_id": 0},
    )
    deadline_event["event_invites"] = [
        {
            "id": "synthetic-future-deadline-invite",
            "invite_source": "guest",
            "invitee_name": "Synthetic Future Guest",
            "email": "future@example.invalid",
            "rsvp_status": "pending",
        }
    ]
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
        "event_invites": [
            {
                "id": "synthetic-expired-invite",
                "invite_source": "guest",
                "invitee_name": "Synthetic Guest",
                "email": "expired@example.invalid",
                "rsvp_status": "pending",
            }
        ],
        "rsvp_records": [],
        "agenda": [
            {
                **activity,
                "rsvp_deadline": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).isoformat(),
            }
        ],
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
        "event_invites": [
            {
                "id": "synthetic-invalid-stored-deadline-invite",
                "invite_source": "guest",
                "invitee_name": "Synthetic Guest",
                "email": "invalid-deadline@example.invalid",
                "rsvp_status": "pending",
            }
        ],
        "agenda": [
            {
                **activity,
                "rsvp_deadline": "not-a-date",
            }
        ],
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
