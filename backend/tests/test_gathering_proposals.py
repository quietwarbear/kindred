from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_gathering_proposals_unit")

from gathering_proposals import (  # noqa: E402
    ProposalValidationError,
    aggregate_interest,
    clean_private_text,
    conversion_preview_value,
    member_projection,
    new_draft_document,
)


def proposal(**overrides):
    value = {
        "id": "private-proposal-database-id",
        "public_reference": "a" * 32,
        "community_id": "private-community-id",
        "proposer_user_id": "member-1",
        "proposer_display_name": "Synthetic Member",
        "working_title": "Summer family picnic",
        "gathering_type": "day_trip",
        "broad_date_window": "Early summer",
        "location_suggestion": "Near the family home",
        "organizer_note": "A private organizer-only note",
        "state": "published",
        "revision": 2,
    }
    value.update(overrides)
    return value


def responses():
    return [
        {"user_id": "member-1", "response": "interested", "revision": 1, "updated_at": "private-time-1"},
        {"user_id": "member-2", "response": "maybe", "revision": 3, "updated_at": "private-time-2"},
        {"user_id": "removed-member", "response": "not_available", "revision": 1},
    ]


def test_private_text_normalizes_and_rejects_controls_and_overflow():
    assert clean_private_text("  Family\t picnic  ", maximum=30, required=True) == "Family picnic"
    with pytest.raises(ProposalValidationError):
        clean_private_text("bad\x00text", maximum=30)
    with pytest.raises(ProposalValidationError):
        clean_private_text("x" * 31, maximum=30)


def test_aggregate_reconciles_only_current_eligible_members():
    aggregate = aggregate_interest(responses(), {"member-1", "member-2"})
    assert aggregate == {"interested": 1, "maybe": 1, "not_available": 0, "total": 2}
    assert aggregate["total"] == sum(aggregate[key] for key in ("interested", "maybe", "not_available"))


def test_member_projection_contains_only_own_response_and_anonymous_totals():
    value = member_projection(
        proposal(), viewer_id="member-1", responses=responses(),
        eligible_user_ids={"member-1", "member-2"},
    )
    assert value["interest"]["my_response"] == "interested"
    assert value["interest"]["my_revision"] == 1
    encoded = json.dumps(value)
    for forbidden in (
        "private-proposal-database-id", "private-community-id", "member-2",
        "removed-member", "private-time-1", "private-time-2", "Synthetic Member",
    ):
        assert forbidden not in encoded


def test_other_member_cannot_see_unpublished_note_or_proposer_identity():
    value = member_projection(
        proposal(state="submitted"), viewer_id="member-2", responses=[],
        eligible_user_ids={"member-1", "member-2"},
    )
    assert "organizer_note" not in value
    assert "proposer_display_name" not in value


def test_organizer_projection_gets_review_fields_but_no_response_roster():
    value = member_projection(
        proposal(), viewer_id="organizer-1", responses=responses(),
        eligible_user_ids={"member-1", "member-2", "organizer-1"}, organizer=True,
    )
    assert value["proposer_display_name"] == "Synthetic Member"
    assert value["organizer_note"] == "A private organizer-only note"
    assert "member-1" not in json.dumps(value)
    assert "member-2" not in json.dumps(value)


def preview(**overrides):
    values = {
        "title": "Next family reunion",
        "start_at": "2028-06-02T10:00:00-04:00",
        "end_at": "2028-06-02T18:00:00-04:00",
        "timezone_name": "America/New_York",
        "location": "Family center",
        "gathering_format": "in-person",
        "max_attendees": 80,
        "organizer_display_name": "Synthetic Organizer",
    }
    values.update(overrides)
    return conversion_preview_value(**values)


def test_conversion_preview_is_exact_and_digest_stable():
    first = preview()
    second = preview()
    assert first == second
    assert len(first["preview_digest"]) == 64
    assert first["proposal"]["guarantees"]["no_proposer_identity"] is True


@pytest.mark.parametrize(
    "updates",
    [
        {"timezone_name": "Not/AZone"},
        {"start_at": "2028-03-12T02:30:00", "end_at": "2028-03-12T04:00:00"},
        {"start_at": "2028-11-05T01:30:00", "end_at": "2028-11-05T03:00:00"},
        {"start_at": "2028-06-02T18:00:00-04:00", "end_at": "2028-06-02T10:00:00-04:00"},
    ],
)
def test_conversion_preview_rejects_timezone_dst_and_reversed_boundaries(updates):
    with pytest.raises(ProposalValidationError):
        preview(**updates)


def test_new_draft_uses_exact_allowlist_and_no_proposal_or_response_identity():
    draft = new_draft_document(
        community_id="synthetic-family", organizer={"id": "organizer-1", "full_name": "Synthetic Organizer"},
        proposal_id="private-proposal-database-id", preview=preview(), timestamp="2028-01-01T00:00:00Z",
    )
    assert draft["publication_state"] == "organizer_draft"
    assert draft["event_invites"] == draft["rsvp_records"] == draft["activity_rsvps"] == []
    assert draft["agenda"] == draft["potluck_items"] == draft["volunteer_slots"] == []
    encoded = json.dumps(draft)
    for forbidden in (
        "private-proposal-database-id", "member-1", "member-2", "private organizer-only note",
        "Early summer", "Near the family home", "interested", "maybe",
    ):
        assert forbidden not in encoded
