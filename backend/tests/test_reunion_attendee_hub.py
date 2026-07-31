from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_attendee_hub_unit")

from attendee_hub import (  # noqa: E402
    ATTENDEE_ACTION_PRIORITY,
    build_attendee_hub,
    next_attendee_action,
)
from event_privacy import serialize_event_for_user  # noqa: E402
from models import PotluckClaimRequest  # noqa: E402
from routes import attendee as attendee_routes  # noqa: E402
from routes import events as event_routes  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MEMBER = {
    "id": "member-1",
    "community_id": "community-1",
    "role": "member",
    "full_name": "Synthetic Member",
    "email": "member@example.invalid",
}


def reunion(**overrides):
    event = {
        "id": "reunion-1",
        "community_id": "community-1",
        "event_template": "reunion",
        "title": "Synthetic Family Reunion",
        "description": "Published reunion description",
        "start_at": "2027-07-20T12:00:00-04:00",
        "end_at": "2027-07-21T17:00:00-04:00",
        "timezone": "America/New_York",
        "location": "Example Hall",
        "gathering_format": "hybrid",
        "zoom_link": "https://meet.example.invalid/published",
        "agenda": [
            {
                "id": "published",
                "title": "Welcome dinner",
                "description": "Published description",
                "start_at": "2027-07-20T18:00:00-04:00",
                "end_at": "2027-07-20T20:00:00-04:00",
                "timezone": "America/New_York",
                "visibility": "published",
                "attendance_requested": True,
                "venue_name": "Example Hall",
            },
            {
                "id": "draft-secret",
                "title": "Private planning activity",
                "description": "organizer-only activity notes",
                "start_at": "2027-07-21T09:00:00-04:00",
                "end_at": "2027-07-21T10:00:00-04:00",
                "visibility": "draft",
            },
        ],
        "event_invites": [
            {
                "id": "member-invite-secret",
                "member_id": MEMBER["id"],
                "email": MEMBER["email"],
                "note": "private invite note",
            }
        ],
        "rsvp_records": [
            {
                "user_id": MEMBER["id"],
                "user_name": MEMBER["full_name"],
                "status": "going",
                "guests": 1,
                "updated_at": "2027-01-02T00:00:00Z",
            },
            {
                "user_id": "other-member",
                "user_name": "Other Private Name",
                "status": "maybe",
                "updated_at": "2027-01-02T00:00:00Z",
            },
        ],
        "activity_rsvps": [
            {
                "activity_id": "published",
                "respondent_id": MEMBER["id"],
                "display_name": MEMBER["full_name"],
                "status": "coming",
                "party_size": 2,
            },
            {
                "activity_id": "published",
                "respondent_id": "other-member",
                "display_name": "Other Private Name",
                "status": "maybe",
                "party_size": 1,
            },
        ],
        "potluck_items": [
            {
                "id": "dish-mine",
                "item_name": "Greens",
                "assigned_to_id": MEMBER["id"],
                "assigned_to": MEMBER["full_name"],
            },
            {
                "id": "dish-other",
                "item_name": "Dessert",
                "assigned_to_id": "other-member",
                "assigned_to": "Other Private Name",
            },
            {"id": "dish-open", "item_name": "Ice", "assigned_to": ""},
        ],
        "volunteer_slots": [
            {
                "id": "slot-1",
                "title": "Welcome table",
                "needed_count": 2,
                "assigned_member_ids": ["other-member"],
                "assigned_members": ["Other Private Name"],
            }
        ],
        "planning_checklist": [{"title": "Private planning task"}],
        "planning_team_member_ids": ["organizer-private-id"],
        "event_role_assignments": [
            {"role_name": "treasurer", "assignees": ["Private Treasurer"]}
        ],
        "travel_coordination_notes": "Private travel notes",
        "suggested_contribution": 500,
        "hidden_from_user_ids": [],
        "attendee_hub_reviewed_by": [],
    }
    event.update(overrides)
    return event


def test_attendee_projection_is_strict_and_contains_exactly_one_action():
    hub = build_attendee_hub(reunion(), MEMBER, has_memory=False)
    assert hub["gathering"]["title"] == "Synthetic Family Reunion"
    assert [item["id"] for item in hub["itinerary"]["activities"]] == ["published"]
    assert hub["rsvp"]["my_status"] == "going"
    assert hub["itinerary"]["activities"][0]["my_response"] == "coming"
    assert hub["itinerary"]["activities"][0]["attendance"]["coming"] == 1
    assert hub["contributions"]["own_commitments"]["count"] == 1
    assert hub["next_action"] == {"code": "review_itinerary"}
    assert list(hub["next_action"]) == ["code"]

    encoded = json.dumps(hub)
    for forbidden in [
        "member-invite-secret",
        "private invite note",
        "Other Private Name",
        "organizer-only activity notes",
        "Private planning task",
        "organizer-private-id",
        "Private Treasurer",
        "Private travel notes",
        "assigned_to_id",
        "assigned_members",
        "hidden_from_user_ids",
    ]:
        assert forbidden not in encoded


def test_member_event_projection_also_removes_drafts_planning_and_named_commitments():
    view = serialize_event_for_user(reunion(), MEMBER)
    assert [item["id"] for item in view["agenda"]] == ["published"]
    assert view["potluck_items"][0]["is_mine"] is True
    assert view["volunteer_slots"][0]["filled_count"] == 1
    encoded = json.dumps(view)
    for forbidden in [
        "draft-secret",
        "Other Private Name",
        "event_invites",
        "planning_checklist",
        "planning_team_member_ids",
        "travel_coordination_notes",
        "suggested_contribution",
        "attendee_hub_reviewed_by",
    ]:
        assert forbidden not in encoded


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {
                "overall_status": "",
                "activities": [],
                "contributions": {
                    "potluck": [],
                    "volunteer": [],
                    "own_commitments": {"count": 0},
                },
                "itinerary_reviewed": False,
                "has_memory": False,
            },
            "respond_to_reunion",
        ),
        (
            {
                "overall_status": "going",
                "activities": [
                    {
                        "attendance_requested": True,
                        "response_open": True,
                        "my_response": "no-response",
                    }
                ],
                "contributions": {
                    "potluck": [{"claimed": False}],
                    "volunteer": [],
                    "own_commitments": {"count": 0},
                },
                "itinerary_reviewed": False,
                "has_memory": False,
            },
            "complete_activity_responses",
        ),
        (
            {
                "overall_status": "going",
                "activities": [],
                "contributions": {
                    "potluck": [{"claimed": False}],
                    "volunteer": [],
                    "own_commitments": {"count": 0},
                },
                "itinerary_reviewed": False,
                "has_memory": False,
            },
            "choose_contribution",
        ),
        (
            {
                "overall_status": "going",
                "activities": [{"attendance_requested": False}],
                "contributions": {
                    "potluck": [],
                    "volunteer": [],
                    "own_commitments": {"count": 0},
                },
                "itinerary_reviewed": False,
                "has_memory": False,
            },
            "review_itinerary",
        ),
        (
            {
                "overall_status": "going",
                "activities": [],
                "contributions": {
                    "potluck": [],
                    "volunteer": [],
                    "own_commitments": {"count": 0},
                },
                "itinerary_reviewed": True,
                "has_memory": False,
            },
            "share_a_memory",
        ),
        (
            {
                "overall_status": "going",
                "activities": [],
                "contributions": {
                    "potluck": [],
                    "volunteer": [],
                    "own_commitments": {"count": 0},
                },
                "itinerary_reviewed": True,
                "has_memory": True,
            },
            "reunion_plan_complete",
        ),
    ],
)
def test_stable_attendee_action_priority(kwargs, expected):
    assert next_attendee_action(**kwargs) == {"code": expected}
    assert ATTENDEE_ACTION_PRIORITY == (
        "respond_to_reunion",
        "complete_activity_responses",
        "choose_contribution",
        "review_itinerary",
        "share_a_memory",
        "reunion_plan_complete",
    )


@pytest.mark.asyncio
async def test_attendee_route_keeps_cross_community_and_hidden_lookups_not_found(
    monkeypatch,
):
    async def not_found(_event_id, _user):
        raise HTTPException(status_code=404, detail="Event not found.")

    monkeypatch.setattr(attendee_routes, "get_event_for_user", not_found)
    with pytest.raises(HTTPException) as exc:
        await attendee_routes._attendee_reunion("reunion-1", MEMBER)
    assert exc.value.status_code == 404


class _UpdateResult:
    def __init__(self, matched_count):
        self.matched_count = matched_count


class _ConcurrentEventCollection:
    def __init__(self, event):
        self.event = deepcopy(event)
        self.lock = asyncio.Lock()

    async def find_one(self, query, _projection):
        if query.get("id") != self.event["id"]:
            return None
        return deepcopy(self.event)

    async def update_one(self, query, update):
        async with self.lock:
            expected = query.get("rsvp_revision")
            current = self.event.get("rsvp_revision")
            matches = (
                (expected == current)
                if not isinstance(expected, dict)
                else "rsvp_revision" not in self.event
            )
            if not matches:
                return _UpdateResult(0)
            self.event.update(deepcopy(update["$set"]))
            self.event["rsvp_revision"] = int(self.event.get("rsvp_revision", 0)) + 1
            return _UpdateResult(1)


@pytest.mark.asyncio
async def test_final_potluck_opening_has_one_winner_and_retry_is_idempotent(
    monkeypatch,
):
    event = reunion(
        potluck_items=[{"id": "last-dish", "item_name": "Ice", "assigned_to": ""}],
        volunteer_slots=[],
        rsvp_revision=0,
    )
    collection = _ConcurrentEventCollection(event)

    async def event_for_user(_event_id, _user):
        return deepcopy(collection.event)

    monkeypatch.setattr(event_routes, "events_collection", collection)
    monkeypatch.setattr(event_routes, "get_event_for_user", event_for_user)
    other = {
        **MEMBER,
        "id": "member-2",
        "full_name": "Second Synthetic Member",
    }
    results = await asyncio.gather(
        event_routes.claim_potluck_item(
            "reunion-1",
            PotluckClaimRequest(item_id="last-dish", idempotency_key="claim:member-1"),
            MEMBER,
        ),
        event_routes.claim_potluck_item(
            "reunion-1",
            PotluckClaimRequest(item_id="last-dish", idempotency_key="claim:member-2"),
            other,
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    loser = next(result for result in results if isinstance(result, HTTPException))
    assert loser.status_code == 409
    winner_id = collection.event["potluck_items"][0]["assigned_to_id"]
    winner = MEMBER if winner_id == MEMBER["id"] else other
    retried = await event_routes.claim_potluck_item(
        "reunion-1",
        PotluckClaimRequest(item_id="last-dish", idempotency_key="claim:retry"),
        winner,
    )
    assert retried["potluck_items"][0]["is_mine"] is True


def test_frontend_route_analytics_public_confirmation_and_provider_boundary():
    page = (ROOT / "frontend/src/components/ReunionAttendeeHubPage.jsx").read_text()
    public_page = (ROOT / "frontend/src/components/PublicRSVPPage.jsx").read_text()
    analytics = (ROOT / "frontend/src/lib/analytics.js").read_text()
    app = (ROOT / "frontend/src/App.js").read_text()
    route = (ROOT / "backend/routes/attendee.py").read_text()
    for event_name in [
        "reunion_hub_viewed",
        "attendee_next_action_viewed",
        "contribution_claimed",
        "contribution_released",
        "memory_prompt_started",
        "memory_prompt_completed",
    ]:
        assert f'"{event_name}"' in analytics
    allowlist = analytics.split("SAFE_REUNION_PROPERTY_KEYS", 1)[1].split("]);", 1)[0]
    for forbidden in ["email", "event_id", "community_id", "title", "token", "story"]:
        assert f'"{forbidden}"' not in allowlist
    assert 'path="/reunion/hub/:eventId"' in app
    assert "data-ph-no-capture" in page
    assert "public-rsvp-confirmation" in public_page
    assert "Revise my response" in public_page
    assert "separate private invitation" in public_page
    assert "generate_memory_tags" not in route
    assert "OPENAI_API_KEY" not in route
    assert "email_service" not in route
    assert "/rsvp/" not in page
