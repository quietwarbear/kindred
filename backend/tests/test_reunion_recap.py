from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_reunion_recap_unit")

from reunion_recap import (  # noqa: E402
    build_recap_projection,
    carry_forward_catalog,
    recap_state,
    reunion_completion,
)
from routes.reunion_recap import (  # noqa: E402
    NextGatheringSelection,
    _new_event_document,
    _next_gathering_preview,
)

MEMBER = {
    "id": "synthetic-member",
    "community_id": "synthetic-family",
    "full_name": "Synthetic Member",
    "role": "member",
}
ORGANIZER = {**MEMBER, "id": "synthetic-organizer", "role": "organizer"}


def reunion(**overrides):
    event = {
        "id": "synthetic-reunion-internal-id",
        "community_id": "synthetic-family",
        "event_template": "reunion",
        "title": "Synthetic Reunion",
        "start_at": "2027-03-13T09:00:00-05:00",
        "end_at": "2027-03-14T16:00:00-04:00",
        "timezone": "America/New_York",
        "gathering_format": "hybrid",
        "max_attendees": 80,
        "agenda": [
            {
                "id": "published-activity-internal-id",
                "title": "Family meal",
                "start_at": "2027-03-14T14:00:00-04:00",
                "end_at": "2027-03-14T18:00:00-04:00",
                "timezone": "America/New_York",
                "visibility": "published",
                "attendance_requested": True,
            },
            {
                "id": "draft-activity-internal-id",
                "title": "Private organizer meeting",
                "start_at": "2027-03-14T19:00:00-04:00",
                "end_at": "2027-03-14T20:00:00-04:00",
                "visibility": "draft",
                "notes": "Private planning note",
            },
        ],
        "event_invites": [
            {
                "id": "private-invitation-credential",
                "email": "private@example.invalid",
                "invitee_name": "Private Guest",
            }
        ],
        "rsvp_records": [
            {
                "user_id": MEMBER["id"],
                "user_name": MEMBER["full_name"],
                "status": "going",
                "guests": 1,
                "updated_at": "2027-03-01T00:00:00Z",
            },
            {
                "user_id": "other-private-member",
                "user_name": "Other Private Person",
                "status": "maybe",
                "updated_at": "2027-03-01T00:00:00Z",
            },
        ],
        "activity_rsvps": [
            {
                "activity_id": "published-activity-internal-id",
                "respondent_id": MEMBER["id"],
                "display_name": MEMBER["full_name"],
                "status": "coming",
            },
            {
                "activity_id": "published-activity-internal-id",
                "respondent_id": "other-private-member",
                "display_name": "Other Private Person",
                "status": "maybe",
            },
        ],
        "potluck_items": [
            {
                "id": "private-potluck-id",
                "item_name": "Dessert",
                "assigned_to_id": "other-private-member",
                "assigned_to": "Other Private Person",
            }
        ],
        "volunteer_slots": [
            {
                "id": "private-volunteer-id",
                "title": "Welcome table",
                "needed_count": 2,
                "assigned_member_ids": ["other-private-member"],
                "assigned_members": ["Other Private Person"],
            }
        ],
        "hidden_from_user_ids": [],
        "travel_coordination_notes": "Private travel details",
        "suggested_contribution": 500,
    }
    event.update(overrides)
    return event


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2027-03-14T21:59:59+00:00", "not_ready"),
        ("2027-03-14T22:00:00+00:00", "ready"),
        ("2027-03-14T22:00:01+00:00", "ready"),
    ],
)
def test_completion_before_at_and_after_final_activity_end(now, expected):
    result = reunion_completion(reunion(), now=datetime.fromisoformat(now))
    assert result["state"] == expected
    assert result["completed_at"] == "2027-03-14T22:00:00+00:00"


@pytest.mark.parametrize(
    "updates",
    [
        {"timezone": "Not/AZone"},
        {"start_at": "not-a-time"},
        {"end_at": "2027-03-14T02:30:00", "agenda": []},
        {"end_at": "2027-11-07T01:30:00", "agenda": []},
        {"end_at": "2027-03-12T16:00:00-05:00", "agenda": []},
        {"end_at": "", "agenda": []},
        {
            "agenda": [
                {
                    "id": "invalid",
                    "title": "Invalid published row",
                    "visibility": "published",
                    "start_at": "2027-03-14T10:00:00-04:00",
                    "end_at": "",
                }
            ]
        },
    ],
)
def test_completion_fails_closed_for_timezone_dst_and_legacy_boundaries(updates):
    assert reunion_completion(reunion(**updates))["state"] == "legacy_conflict"


def test_recap_projection_is_allowlisted_and_excludes_names_ids_drafts_and_private_fields():
    event = reunion()
    recap = {
        "state": "published",
        "revision": 3,
        "message": "A private family-facing recap message.",
        "author_user_id": ORGANIZER["id"],
    }
    memories = [
        {"id": "published-memory-id", "capsule_status": "published", "description": "Private story"},
        {"id": "draft-memory-id", "capsule_status": "draft", "description": "Private draft"},
        {"id": "withdrawn-memory-id", "capsule_status": "withdrawn", "description": "Withdrawn story"},
    ]
    projection = build_recap_projection(
        event,
        recap,
        memories,
        MEMBER,
        organizer_preview=False,
        next_gathering_started=False,
        now=datetime(2027, 3, 15, tzinfo=timezone.utc),
    )
    assert projection["state"] == "published"
    assert projection["my_participation"] == {"rsvp_status": "going", "guest_count": 1}
    assert projection["aggregate_participation"]["published_memory_count"] == 1
    assert projection["itinerary"][0]["my_response"] == "coming"
    assert projection["message"] == "A private family-facing recap message."
    assert "id" not in projection["reunion"]
    assert "id" not in projection["itinerary"][0]
    encoded = json.dumps(projection)
    for forbidden in (
        "synthetic-reunion-internal-id",
        "published-activity-internal-id",
        "private-invitation-credential",
        "private@example.invalid",
        "Private Guest",
        "Other Private Person",
        "Private organizer meeting",
        "Private planning note",
        "private-potluck-id",
        "private-volunteer-id",
        "Private travel details",
        "draft-memory-id",
        "withdrawn-memory-id",
        "author_user_id",
    ):
        assert forbidden not in encoded


def test_unpublished_message_is_organizer_preview_only():
    event = reunion()
    recap = {"state": "unpublished", "revision": 2, "message": "Organizer-only preview text"}
    member = build_recap_projection(
        event, recap, [], MEMBER, organizer_preview=False, next_gathering_started=False,
        now=datetime(2027, 3, 15, tzinfo=timezone.utc),
    )
    organizer = build_recap_projection(
        event, recap, [], ORGANIZER, organizer_preview=True, next_gathering_started=False,
        now=datetime(2027, 3, 15, tzinfo=timezone.utc),
    )
    assert "message" not in member
    assert organizer["message"] == "Organizer-only preview text"
    assert recap_state(event, recap, now=datetime(2027, 3, 15, tzinfo=timezone.utc)) == "unpublished"


def test_next_gathering_preview_and_document_use_exact_narrow_allowlist():
    event = reunion()
    catalog = carry_forward_catalog(event)
    encoded_catalog = json.dumps(catalog)
    assert "published-activity-internal-id" not in encoded_catalog
    assert "private-potluck-id" not in encoded_catalog
    assert "private-volunteer-id" not in encoded_catalog
    activity_reference = catalog["itinerary_templates"][0]["selection_reference"]
    contribution_references = [item["selection_reference"] for item in catalog["contribution_categories"]]
    selection = NextGatheringSelection(
        title="Synthetic Next Reunion",
        start_at="2028-11-04T10:00:00-04:00",
        end_at="2028-11-04T18:00:00-04:00",
        timezone="America/New_York",
        itinerary_selection_references=[activity_reference],
        contribution_selection_references=contribution_references,
        carry_gathering_format=True,
        carry_capacity=True,
    )
    preview = _next_gathering_preview(event, selection)
    assert preview["proposal"]["guarantees"] == {
        "zero_invitations": True,
        "zero_responses": True,
        "zero_assignments": True,
        "new_structural_identifiers": True,
    }
    created = _new_event_document(event, ORGANIZER, preview["proposal"], "a" * 64)
    assert created["publication_state"] == "organizer_draft"
    assert created["event_invites"] == []
    assert created["rsvp_records"] == []
    assert created["activity_rsvps"] == []
    assert created["agenda"][0]["id"] != "published-activity-internal-id"
    assert created["agenda"][0]["visibility"] == "draft"
    assert created["potluck_items"][0]["assigned_to"] == ""
    assert created["volunteer_slots"][0]["assigned_members"] == []
    encoded = json.dumps(created)
    for forbidden in (
        "private-invitation-credential",
        "private@example.invalid",
        "Other Private Person",
        "Private travel details",
        "draft-activity-internal-id",
        "published-activity-internal-id",
        "private-potluck-id",
        "private-volunteer-id",
        "synthetic-reunion-internal-id",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize(
    ("start_at", "end_at"),
    [
        ("2028-03-12T02:30:00", "2028-03-12T04:00:00"),
        ("2028-11-05T01:30:00", "2028-11-05T03:00:00"),
        ("2028-11-05T04:00:00-05:00", "2028-11-05T03:00:00-05:00"),
    ],
)
def test_next_gathering_rejects_nonexistent_ambiguous_and_reversed_boundaries(start_at, end_at):
    with pytest.raises(Exception) as captured:
        _next_gathering_preview(
            reunion(),
            NextGatheringSelection(
                title="Invalid next reunion",
                start_at=start_at,
                end_at=end_at,
                timezone="America/New_York",
            ),
        )
    assert getattr(captured.value, "status_code", None) == 422
