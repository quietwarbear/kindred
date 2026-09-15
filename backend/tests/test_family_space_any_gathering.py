"""A family that starts with any gathering type can open its family space."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from family_space_activation import PROVISIONAL, build_family_space_readiness  # noqa: E402

NOW = datetime(2027, 8, 8, tzinfo=timezone.utc)
COMMUNITY = {
    "id": "synthetic-community",
    "name": "Synthetic planning space",
    "owner_user_id": "synthetic-host",
    "lifecycle_state": PROVISIONAL,
    "lifecycle_revision": 0,
}
MEMBERS = [
    {"id": "synthetic-host", "role": "host", "email": "host@example.invalid"},
    {"id": "synthetic-member", "role": "member", "email": "member@example.invalid"},
]


def ready_event(template: str) -> dict:
    return {
        "id": "synthetic-gathering",
        "community_id": "synthetic-community",
        "event_template": template,
        "created_at": "2027-08-03T00:00:00+00:00",
        "event_invites": [
            {"id": "i1", "invite_source": "guest", "opened_at": "2027-08-04T00:00:00+00:00", "rsvp_status": "going"},
            {"id": "i2", "invite_source": "guest", "delivery_verified_at": "2027-08-04T00:00:00+00:00", "rsvp_status": "some"},
            {"id": "i3", "invite_source": "member", "member_id": "synthetic-member", "rsvp_status": "maybe"},
        ],
        "rsvp_records": [],
        "potluck_items": [],
        "volunteer_slots": [],
    }


def test_activation_context_does_not_filter_to_reunions():
    source = (BACKEND / "routes/family_space.py").read_text()
    context = source.split("async def _activation_context", 1)[1].split(
        "\ndef _activation_result", 1
    )[0]
    assert '"event_template"' not in context


@pytest.mark.parametrize(
    "template", ["holiday_meal", "birthday", "wedding", "holiday", "custom"]
)
def test_non_reunion_gathering_meets_the_same_readiness_bar(template):
    reunion = build_family_space_readiness(
        COMMUNITY, [ready_event("reunion")], MEMBERS, [], now=NOW
    )
    other = build_family_space_readiness(
        COMMUNITY, [ready_event(template)], MEMBERS, [], now=NOW
    )
    assert reunion["ready"] is True
    assert other == reunion
    assert other["next_action"] == {"code": "activate_family_space"}
