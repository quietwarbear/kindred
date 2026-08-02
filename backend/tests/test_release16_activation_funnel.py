"""Release 16 — monotonic activation funnel counts (synthetic, content-free)."""

import os
from datetime import datetime, timezone

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_release16_unit")

from holiday_pilot import build_holiday_pilot_readiness

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def _event(**overrides):
    event = {
        "id": "synthetic-holiday",
        "community_id": "synthetic-family",
        "title": "Synthetic holiday dinner",
        "start_at": "2026-11-26T16:00:00-08:00",
        "end_at": "2026-11-26T20:00:00-08:00",
        "rsvp_deadline": "2026-11-19T18:00:00-08:00",
        "timezone": "America/Los_Angeles",
        "location": "Synthetic home",
        "event_template": "holiday_meal",
        "publication_state": "published",
        "max_attendees": 12,
        "event_invites": [],
    }
    event.update(overrides)
    return event


def test_funnel_counts_are_monotonic_prepared_reached_seen_responded():
    # An invite delivered by email + opened but never manually shared used to
    # make "opened" exceed "shared"; the reached/seen supersets fix that.
    event = _event(
        event_invites=[
            {  # delivered + opened, not shared, not responded
                "id": "a",
                "rsvp_status": "pending",
                "delivered_at": "x",
                "opened_at": "x",
            },
            {  # only shared
                "id": "b",
                "rsvp_status": "pending",
                "shared_at": "x",
            },
            {  # opened + responded
                "id": "c",
                "rsvp_status": "going",
                "opened_at": "x",
            },
            {  # nothing yet
                "id": "d",
                "rsvp_status": "pending",
            },
        ]
    )
    c = build_holiday_pilot_readiness(event, now=NOW)["aggregate_counts"]
    prepared = c["active_invitations"]
    reached = c["invitations_reached"]
    seen = c["invitations_seen"]
    responded = c["responses_received"]

    assert prepared == 4
    assert reached == 3  # a, b, c have evidence; d has none
    assert seen == 2  # a (opened), c (opened/responded)
    assert responded == 1  # c
    # The funnel stages must never invert.
    assert prepared >= reached >= seen >= responded


def test_funnel_counts_are_content_free():
    event = _event(
        title="Private Dinner",
        event_invites=[
            {
                "id": "cred-x",
                "email": "guest@example.invalid",
                "invitee_name": "Guest X",
                "rsvp_status": "pending",
                "opened_at": "x",
            }
        ],
    )
    readiness = build_holiday_pilot_readiness(event, now=NOW)
    serialized = repr(readiness).lower()
    for prohibited in ("guest x", "guest@example.invalid", "cred-x", "private dinner"):
        assert prohibited not in serialized
    assert readiness["aggregate_counts"]["invitations_reached"] == 1
    assert readiness["aggregate_counts"]["invitations_seen"] == 1
