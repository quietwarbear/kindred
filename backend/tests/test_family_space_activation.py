"""Focused Release 6 lifecycle, readiness, naming, and route regressions."""

from __future__ import annotations

import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_family_activation_unit")
os.environ.setdefault("JWT_SECRET", "synthetic-family-activation-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from family_space_activation import (  # noqa: E402
    ACTIVE,
    LEGACY_UNCHANGED,
    PROVISIONAL,
    FamilySpaceNameError,
    build_family_space_readiness,
    community_lifecycle_state,
    normalize_family_space_name,
    public_community_display_name,
)
from models import FamilySpaceActivationRequest  # noqa: E402
from routes import family_space as routes  # noqa: E402

NOW = datetime(2027, 8, 8, tzinfo=timezone.utc)


def community(**overrides):
    return {
        "id": "synthetic-community",
        "name": "Synthetic Reunion planning space",
        "owner_user_id": "synthetic-host",
        "lifecycle_state": PROVISIONAL,
        "lifecycle_revision": 0,
        **overrides,
    }


def members():
    return [
        {
            "id": "synthetic-host",
            "role": "host",
            "email": "host@example.invalid",
        },
        {
            "id": "synthetic-member",
            "role": "member",
            "email": "member@example.invalid",
        },
    ]


def ready_event(**overrides):
    return {
        "id": "synthetic-reunion",
        "community_id": "synthetic-community",
        "event_template": "reunion",
        "created_at": "2027-08-03T00:00:00+00:00",
        "event_invites": [
            {
                "id": "synthetic-invite-1",
                "invite_source": "guest",
                "opened_at": "2027-08-04T00:00:00+00:00",
                "rsvp_status": "going",
            },
            {
                "id": "synthetic-invite-2",
                "invite_source": "guest",
                "delivery_verified_at": "2027-08-04T00:00:00+00:00",
                "rsvp_status": "some",
            },
            {
                "id": "synthetic-invite-3",
                "invite_source": "member",
                "member_id": "synthetic-member",
                "rsvp_status": "maybe",
            },
        ],
        "rsvp_records": [],
        "potluck_items": [],
        "volunteer_slots": [],
        **overrides,
    }


def test_lifecycle_is_explicit_and_never_inferred_from_display_name():
    assert (
        community_lifecycle_state({"name": "Anything planning space"})
        == LEGACY_UNCHANGED
    )
    assert (
        community_lifecycle_state({"name": "Active", "lifecycle_state": PROVISIONAL})
        == PROVISIONAL
    )
    assert (
        community_lifecycle_state({"name": "Planning", "lifecycle_state": ACTIVE})
        == ACTIVE
    )
    assert public_community_display_name(community()) == ""
    assert public_community_display_name({"name": "Legacy Family"}) == "Legacy Family"
    assert (
        public_community_display_name(
            community(name="Enduring", lifecycle_state=ACTIVE)
        )
        == "Enduring"
    )


def test_ready_report_is_aggregate_only_and_has_exactly_one_action():
    report = build_family_space_readiness(
        community(), [ready_event()], members(), [], now=NOW
    )
    assert report == {
        "lifecycle_state": "provisional",
        "lifecycle_revision": 0,
        "readiness_status": "ready",
        "ready": True,
        "aggregate_counts": {
            "reunions": 1,
            "verified_invitations": 3,
            "accepted_responses": 2,
            "non_host_participants": 3,
        },
        "unmet_condition_codes": [],
        "elapsed_day_bucket": "2_7",
        "next_action": {"code": "activate_family_space"},
    }
    serialized = str(report)
    for forbidden in (
        "synthetic-reunion",
        "synthetic-invite",
        "example.invalid",
        "planning space",
        "event_title",
        "credential",
    ):
        assert forbidden not in serialized


def test_copied_or_queued_invitations_are_not_delivery_evidence():
    event = ready_event(
        event_invites=[
            {
                "id": f"synthetic-{index}",
                "rsvp_status": "pending",
                "link_copied_at": "2027-08-04T00:00:00+00:00",
                "delivery_status": "queued",
                "email_ready": True,
            }
            for index in range(4)
        ]
    )
    report = build_family_space_readiness(community(), [event], members(), [], now=NOW)
    assert report["aggregate_counts"]["verified_invitations"] == 0
    assert report["ready"] is False
    assert report["next_action"] == {"code": "collect_verified_invitation_evidence"}


def test_action_priority_and_optional_published_memory_participation():
    no_reunion = build_family_space_readiness(community(), [], members(), [], now=NOW)
    assert no_reunion["next_action"] == {"code": "create_reunion"}

    insufficient_accepts = ready_event(
        event_invites=[
            {"id": "one", "opened_at": "x", "rsvp_status": "maybe"},
            {"id": "two", "opened_at": "x", "rsvp_status": "maybe"},
            {"id": "three", "opened_at": "x", "rsvp_status": "maybe"},
        ]
    )
    report = build_family_space_readiness(
        community(), [insufficient_accepts], members(), [], now=NOW
    )
    assert report["next_action"] == {"code": "receive_more_accepted_responses"}

    no_participant = ready_event(
        event_invites=[
            {
                "id": "host-one",
                "invite_source": "member",
                "member_id": "synthetic-host",
                "opened_at": "x",
                "rsvp_status": "going",
            },
            {
                "id": "host-two",
                "invite_source": "member",
                "member_id": "synthetic-host-two",
                "delivery_verified_at": "x",
                "rsvp_status": "some",
            },
            {
                "id": "host-three",
                "invite_source": "member",
                "member_id": "synthetic-host-three",
                "opened_at": "x",
                "rsvp_status": "maybe",
            },
        ]
    )
    host_members = members() + [
        {"id": "synthetic-host-two", "role": "host", "email": "host2@example.invalid"},
        {
            "id": "synthetic-host-three",
            "role": "host",
            "email": "host3@example.invalid",
        },
    ]
    report = build_family_space_readiness(
        community(), [no_participant], host_members, [], now=NOW
    )
    assert report["next_action"] == {"code": "invite_non_host_participation"}
    memory = {
        "event_id": no_participant["id"],
        "created_by": "synthetic-member",
        "capsule_status": "published",
    }
    with_memory = build_family_space_readiness(
        community(), [no_participant], host_members, [memory], now=NOW
    )
    assert with_memory["ready"] is True


def test_active_and_legacy_reports_are_monotonic_and_safe():
    active = build_family_space_readiness(
        community(lifecycle_state=ACTIVE, lifecycle_revision=1),
        [ready_event()],
        members(),
        [],
        now=NOW,
    )
    assert active["readiness_status"] == "active"
    assert active["next_action"] == {"code": "open_family_home"}
    legacy = build_family_space_readiness(
        {"id": "legacy", "name": "Legacy"}, [], [], [], now=NOW
    )
    assert legacy["lifecycle_state"] == LEGACY_UNCHANGED
    assert legacy["unmet_condition_codes"] == ["explicit_provisional_state_required"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  The   Johnson Family  ", "The Johnson Family"),
        ("Ｆａｍｉｌｙ １２", "Family 12"),
        ("Familia Árvore", "Familia Árvore"),
        ("العائلة", "العائلة"),
    ],
)
def test_name_normalization_supports_safe_unicode(raw, expected):
    assert normalize_family_space_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "!?!",
        "<script>alert(1)</script>",
        "javascript:alert(1)",
        "Family\u0000Name",
        "Family\u200bName",
        "Family\u202eName",
        "A" * 81,
    ],
)
def test_name_validation_rejects_blank_markup_controls_and_invisible_text(raw):
    with pytest.raises(FamilySpaceNameError) as raised:
        normalize_family_space_name(raw)
    if raw:
        assert raw not in str(raised.value)


class FakeCommunities:
    def __init__(self, document):
        self.document = deepcopy(document)

    async def find_one_and_update(self, query, update, **_kwargs):
        if any(self.document.get(key) != value for key, value in query.items()):
            return None
        self.document.update(deepcopy(update["$set"]))
        self.document["lifecycle_revision"] += update["$inc"]["lifecycle_revision"]
        return deepcopy(self.document)

    async def find_one(self, query, _projection=None):
        return (
            deepcopy(self.document)
            if self.document.get("id") == query.get("id")
            else None
        )


@pytest.mark.asyncio
async def test_identical_retry_converges_and_divergent_completed_state_is_immutable(
    monkeypatch,
):
    store = FakeCommunities(community())
    user = {
        "id": "synthetic-organizer",
        "community_id": "synthetic-community",
        "role": "organizer",
    }

    async def context(_user):
        return deepcopy(store.document), {
            "ready": True,
            "unmet_condition_codes": [],
            "readiness_status": "ready",
        }

    monkeypatch.setattr(routes, "_activation_context", context)
    monkeypatch.setattr(routes, "communities_collection", store)
    monkeypatch.setattr(routes, "now_iso", lambda: "2027-08-08T00:00:00+00:00")
    request = FamilySpaceActivationRequest(
        family_space_name="The Synthetic Family",
        expected_revision=0,
        idempotency_key="family-activation-identical-0001",
    )
    first = await routes.activate_family_space(request, user)
    retry = await routes.activate_family_space(request, user)
    assert first == retry
    assert store.document["name"] == "The Synthetic Family"
    assert store.document["lifecycle_state"] == ACTIVE
    assert store.document["lifecycle_revision"] == 1

    with pytest.raises(HTTPException) as divergent:
        await routes.activate_family_space(
            FamilySpaceActivationRequest(
                family_space_name="A Different Family",
                expected_revision=0,
                idempotency_key="family-activation-divergent-0002",
            ),
            user,
        )
    assert divergent.value.status_code == 409
    assert store.document["name"] == "The Synthetic Family"


@pytest.mark.asyncio
async def test_stale_revision_fails_without_mutation(monkeypatch):
    store = FakeCommunities(community(lifecycle_revision=2))
    original = deepcopy(store.document)
    user = {
        "id": "synthetic-host",
        "community_id": "synthetic-community",
        "role": "host",
    }

    async def context(_user):
        return deepcopy(store.document), {
            "ready": True,
            "unmet_condition_codes": [],
            "readiness_status": "ready",
        }

    monkeypatch.setattr(routes, "_activation_context", context)
    monkeypatch.setattr(routes, "communities_collection", store)
    with pytest.raises(HTTPException) as raised:
        await routes.activate_family_space(
            FamilySpaceActivationRequest(
                family_space_name="The Synthetic Family",
                expected_revision=1,
                idempotency_key="family-activation-stale-0001",
            ),
            user,
        )
    assert raised.value.status_code == 409
    assert store.document == original


@pytest.mark.parametrize(
    "user",
    [
        {"id": "member", "community_id": "c", "role": "member"},
        {
            "id": "admin",
            "community_id": "c",
            "role": "member",
            "is_platform_admin": True,
        },
    ],
)
@pytest.mark.asyncio
async def test_member_and_platform_admin_flags_do_not_grant_activation(user):
    with pytest.raises(HTTPException) as raised:
        await routes._activation_context(user)
    assert raised.value.status_code == 403
