from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_capsule_unit")

from memory_privacy import is_memory_owner, visible_memory_query_for_user  # noqa: E402
from reunion_memory_capsule import (  # noqa: E402
    CAPSULE_ACTION_PRIORITY,
    build_reunion_memory_capsule,
    capsule_next_action,
)
from routes import reunion_memories as capsule_routes  # noqa: E402
from routes import timeline as timeline_routes  # noqa: E402
from models import MemoryUpdateRequest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MEMBER = {
    "id": "member-synthetic",
    "community_id": "community-synthetic",
    "full_name": "Synthetic Member",
    "role": "member",
}


def reunion(**overrides):
    event = {
        "id": "reunion-synthetic",
        "community_id": MEMBER["community_id"],
        "event_template": "reunion",
        "title": "Synthetic Reunion",
        "start_at": "2027-08-01T12:00:00-04:00",
        "end_at": "2027-08-02T16:00:00-04:00",
        "timezone": "America/New_York",
        "agenda": [
            {
                "id": "published-activity",
                "title": "Published gathering",
                "start_at": "2027-08-01T18:00:00-04:00",
                "end_at": "2027-08-01T20:00:00-04:00",
                "visibility": "published",
                "venue_name": "Example Hall",
            },
            {
                "id": "draft-activity",
                "title": "Organizer-only draft",
                "visibility": "draft",
                "notes": "Private planning note",
            },
        ],
        "event_invites": [{"id": "private-invitation-credential"}],
        "hidden_from_user_ids": [],
        "memory_capsule_reviewed_by": [],
    }
    event.update(overrides)
    return event


def memory(
    memory_id,
    *,
    creator="other-member",
    creator_name="Community Contributor",
    story="A synthetic family story.",
    capsule_status="published",
):
    return {
        "id": memory_id,
        "community_id": MEMBER["community_id"],
        "event_id": "reunion-synthetic",
        "created_by": creator,
        "created_by_name": creator_name,
        "title": "Internal memory title",
        "description": story,
        "capsule_status": capsule_status,
        "created_at": "2027-08-03T00:00:00Z",
        "tags": ["internal-tag"],
        "ai_summary": "Internal summary",
        "comments": [{"text": "Private comment"}],
    }


def test_capsule_projection_has_strict_allowlist_and_own_draft_only():
    projection = build_reunion_memory_capsule(
        reunion(),
        [
            memory("published"),
            memory(
                "own-draft",
                creator=MEMBER["id"],
                creator_name=MEMBER["full_name"],
                story="My private draft.",
                capsule_status="draft",
            ),
        ],
        MEMBER,
    )
    assert set(projection) == {
        "reunion",
        "itinerary",
        "memories",
        "memory_count",
        "own_contribution",
        "visibility",
        "reviewed",
        "next_action",
    }
    assert [item["id"] for item in projection["itinerary"]] == ["published-activity"]
    assert [item["id"] for item in projection["memories"]] == ["published"]
    assert projection["own_contribution"]["status"] == "draft"
    assert projection["next_action"] == {"code": "finish_memory_draft"}

    encoded = json.dumps(projection)
    for forbidden in [
        "draft-activity",
        "Organizer-only draft",
        "Private planning note",
        "private-invitation-credential",
        "internal-tag",
        "Internal summary",
        "Private comment",
        "community-synthetic",
    ]:
        assert forbidden not in encoded


@pytest.mark.parametrize(
    ("published_count", "own_status", "reviewed", "expected"),
    [
        (0, "", False, "share_first_memory"),
        (0, "draft", False, "finish_memory_draft"),
        (2, "", False, "review_reunion_memories"),
        (2, "published", True, "reunion_capsule_complete"),
    ],
)
def test_deterministic_next_action_priority(
    published_count,
    own_status,
    reviewed,
    expected,
):
    assert CAPSULE_ACTION_PRIORITY == (
        "share_first_memory",
        "finish_memory_draft",
        "review_reunion_memories",
        "reunion_capsule_complete",
    )
    assert capsule_next_action(
        published_count=published_count,
        own_status=own_status,
        reviewed=reviewed,
    ) == {"code": expected}


@pytest.mark.asyncio
async def test_general_memory_query_excludes_capsule_drafts(monkeypatch):
    async def base_query(_user, **extra):
        return {"community_id": MEMBER["community_id"], **extra}

    monkeypatch.setattr("memory_privacy.event_derived_query_for_user", base_query)
    query = await visible_memory_query_for_user(MEMBER, category="story")
    assert {"capsule_status": {"$ne": "draft"}} in query["$and"]

    own_query = await visible_memory_query_for_user(
        MEMBER,
        include_own_capsule_drafts=True,
    )
    assert {"created_by": MEMBER["id"]} in own_query["$and"][1]["$or"]


def test_memory_ownership_is_creator_only():
    own = memory("own", creator=MEMBER["id"])
    other = memory("other")
    assert is_memory_owner(own, MEMBER) is True
    assert is_memory_owner(other, MEMBER) is False
    assert (
        is_memory_owner(
            {"created_by_id": MEMBER["id"]},
            MEMBER,
        )
        is True
    )


@pytest.mark.asyncio
async def test_generic_memory_edit_and_withdraw_reject_other_contributor(monkeypatch):
    async def other_memory(_memory_id, _user):
        return memory("other")

    monkeypatch.setattr(timeline_routes, "get_memory_for_user", other_memory)
    with pytest.raises(HTTPException) as edit_error:
        await timeline_routes.update_memory(
            "other",
            MemoryUpdateRequest(title="Unauthorized edit"),
            MEMBER,
        )
    assert edit_error.value.status_code == 403

    with pytest.raises(HTTPException) as delete_error:
        await timeline_routes.delete_memory("other", MEMBER)
    assert delete_error.value.status_code == 403


@pytest.mark.asyncio
async def test_capsule_authorization_preserves_not_found(monkeypatch):
    async def not_found(_event_id, _user):
        raise HTTPException(status_code=404, detail="Event not found.")

    monkeypatch.setattr(capsule_routes, "get_event_for_user", not_found)
    with pytest.raises(HTTPException) as captured:
        await capsule_routes._authorized_reunion("forged-event", MEMBER)
    assert captured.value.status_code == 404


def test_frontend_route_continuity_analytics_and_provider_boundary():
    page = (ROOT / "frontend/src/components/ReunionMemoryCapsulePage.jsx").read_text()
    hub = (ROOT / "frontend/src/components/ReunionAttendeeHubPage.jsx").read_text()
    public = (ROOT / "frontend/src/components/PublicRSVPPage.jsx").read_text()
    analytics = (ROOT / "frontend/src/lib/analytics.js").read_text()
    app = (ROOT / "frontend/src/App.js").read_text()
    route = (ROOT / "backend/routes/reunion_memories.py").read_text()

    assert 'path="/reunion/memories/:eventId"' in app
    assert "data-ph-no-capture" in page
    assert "capsule_path" in hub
    assert "This RSVP link cannot open or add" in public
    for event_name in [
        "reunion_capsule_viewed",
        "memory_contribution_started",
        "memory_contribution_saved",
        "memory_contribution_withdrawn",
        "reunion_capsule_next_action_viewed",
    ]:
        assert f'"{event_name}"' in analytics
    allowlist = analytics.split("SAFE_REUNION_PROPERTY_KEYS", 1)[1].split("]);", 1)[0]
    for forbidden in [
        "email",
        "event_id",
        "community_id",
        "title",
        "story",
        "memory_id",
        "url",
    ]:
        assert f'"{forbidden}"' not in allowlist
    for provider_marker in [
        "generate_memory_tags",
        "OPENAI_API_KEY",
        "email_service",
        "posthog",
        "requests.",
        "httpx.",
    ]:
        assert provider_marker not in route
