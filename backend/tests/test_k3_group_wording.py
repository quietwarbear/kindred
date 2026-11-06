"""K3: organizer-chosen group wording.

Covers the server helper (all forms, custom, default), parity with the
frontend helper, storage and organizer-only authorization of the setting,
exposure to every member through the auth payload, and server-generated text
members see with a non-default label. No database: collections are faked.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:1")
os.environ.setdefault("DB_NAME", "kindred_unit_k3")
os.environ.setdefault("JWT_SECRET", "k3-test-only-not-a-secret")

import dependencies  # noqa: E402
import email_service  # noqa: E402
import event_messaging as em  # noqa: E402
import invitation_delivery  # noqa: E402
from attendee_hub import build_attendee_hub  # noqa: E402
from dependencies import build_auth_response, gathering_templates_for, get_current_user  # noqa: E402
from gathering_proposals import member_projection  # noqa: E402
from group_wording import (  # noqa: E402
    MAX_LABEL_LENGTH,
    PRESETS,
    GroupLabelError,
    resolve_group_label,
    validate_group_label,
    wording,
)
from guest_family_access import safe_status_projection  # noqa: E402
from models import AuthResponse  # noqa: E402
from routes import community as community_routes  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
VILLAGE = {"preset": "custom", "singular": "Village", "plural": "Villages"}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [None, "family", 3, {}, {"preset": "nope"}, {"preset": "custom", "singular": "<b>", "plural": "x"}],
)
def test_anything_unreadable_is_family(raw):
    words = wording(raw)
    assert (words.noun, words.Noun, words.nouns, words.Nouns) == ("family", "Family", "families", "Families")
    assert (words.possessive, words.Possessive) == ("family's", "Family's")
    assert resolve_group_label(raw)["preset"] == "family"


@pytest.mark.parametrize("preset", ["community", "congregation", "circle", "team"])
def test_presets_ignore_client_supplied_words(preset):
    label = validate_group_label(preset, "Ignored", "Ignoreds")
    assert label == {"preset": preset, "singular": PRESETS[preset][0], "plural": PRESETS[preset][1]}
    assert wording(label).Nouns == PRESETS[preset][1].capitalize()


def test_custom_label_every_form():
    label = validate_group_label("custom", "  Village ", "Villages")
    assert label == VILLAGE
    words = wording(label)
    assert (words.noun, words.Noun, words.nouns, words.Nouns) == ("village", "Village", "villages", "Villages")
    assert words.possessive == "village's"
    assert wording({"preset": "custom", "singular": "YMCA", "plural": "YMCAs"}).noun == "YMCA"


@pytest.mark.parametrize(
    "singular,plural",
    [
        ("", "crews"),
        ("crew", ""),
        ("a" * (MAX_LABEL_LENGTH + 1), "crews"),
        ("crew2", "crews"),
        ("<script>", "crews"),
        ("crew", "crews!"),
        ("crew\n", "crews\u0000"),
    ],
)
def test_custom_label_rejects(singular, plural):
    with pytest.raises(GroupLabelError):
        validate_group_label("custom", singular, plural)


def test_unicode_letters_hyphens_and_apostrophes_are_fine():
    assert validate_group_label("custom", "ìdílé", "àwọn ìdílé")["plural"] == "àwọn ìdílé"
    assert validate_group_label("custom", "kin-group", "o'hana")["singular"] == "kin-group"


def test_frontend_helper_matches_presets_and_length_cap():
    source = (ROOT / "frontend/src/lib/groupWording.js").read_text()
    js_presets = dict(re.findall(r'(\w+): \{ singular: "(\w+)", plural: "\w+" \}', source))
    assert js_presets == {key: one for key, (one, _) in PRESETS.items()}
    for key, (_, many) in PRESETS.items():
        assert f'{key}: {{ singular: "{PRESETS[key][0]}", plural: "{many}" }}' in source
    assert f"MAX_GROUP_LABEL_LENGTH = {MAX_LABEL_LENGTH};" in source


# ---------------------------------------------------------------------------
# Storage and authorization
# ---------------------------------------------------------------------------


class FakeCommunities:
    def __init__(self, docs):
        self.docs = {doc["id"]: dict(doc) for doc in docs}
        self.updates = []

    async def find_one(self, query, projection=None, **_):
        doc = self.docs.get(query.get("id"))
        return dict(doc) if doc else None

    async def update_one(self, query, update, **_):
        self.updates.append((query, update))
        self.docs[query["id"]].update(update.get("$set", {}))


def _client(monkeypatch, role, community_id="space-1"):
    store = FakeCommunities([
        {"id": "space-1", "name": "Synthetic Space"},
        {"id": "space-2", "name": "Other Space", "group_label": {"preset": "team"}},
    ])
    monkeypatch.setattr(community_routes, "communities_collection", store)
    monkeypatch.setattr(dependencies, "communities_collection", store)
    app = FastAPI()
    app.include_router(community_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": f"user-{role}",
        "community_id": community_id,
        "role": role,
        "email": f"{role}@example.invalid",
    }
    return TestClient(app), store


def test_member_reads_but_cannot_change_the_label(monkeypatch):
    client, store = _client(monkeypatch, "member")
    read = client.get("/api/community/group-label")
    assert read.status_code == 200
    assert read.json()["group_label"] == {"preset": "family", "singular": "family", "plural": "families"}
    assert [p["preset"] for p in read.json()["presets"]] == list(PRESETS)

    denied = client.put("/api/community/group-label", json={"preset": "team"})
    assert denied.status_code == 403
    assert store.updates == []


@pytest.mark.parametrize("role", ["organizer", "host"])
def test_organizers_and_host_store_a_label_on_their_own_space(monkeypatch, role):
    client, store = _client(monkeypatch, role)
    saved = client.put("/api/community/group-label", json={"preset": "custom", "singular": "Village", "plural": "Villages"})
    assert saved.status_code == 200
    assert saved.json()["group_label"] == VILLAGE
    assert store.updates == [({"id": "space-1"}, {"$set": {"group_label": VILLAGE}})]
    assert store.docs["space-2"]["group_label"] == {"preset": "team"}  # other spaces untouched
    assert client.get("/api/community/group-label").json()["group_label"] == VILLAGE


def test_invalid_custom_label_is_refused_and_not_stored(monkeypatch):
    client, store = _client(monkeypatch, "organizer")
    for body in (
        {"preset": "custom", "singular": "crew", "plural": "crews<script>"},
        {"preset": "custom", "singular": "x" * 30, "plural": "crews"},
        {"preset": "tribe"},
    ):
        response = client.put("/api/community/group-label", json=body)
        assert response.status_code == 422, body
    assert store.updates == []


def test_every_member_receives_the_label_through_the_auth_payload():
    user = {"id": "u1", "email": "m@example.invalid", "community_id": "c1", "role": "member"}
    stored = AuthResponse.model_validate(
        build_auth_response(user, {"id": "c1", "name": "Space", "group_label": VILLAGE})
    ).model_dump()
    assert stored["community"]["group_label"] == VILLAGE
    legacy = AuthResponse.model_validate(build_auth_response(user, {"id": "c1", "name": "Space"})).model_dump()
    assert legacy["community"]["group_label"]["preset"] == "family"
    broken = AuthResponse.model_validate(
        build_auth_response(user, {"id": "c1", "name": "Space", "group_label": {"preset": "custom", "singular": "1"}})
    ).model_dump()
    assert broken["community"]["group_label"]["preset"] == "family"


# ---------------------------------------------------------------------------
# Server-generated text members see
# ---------------------------------------------------------------------------


def _capture_email(monkeypatch):
    sent = []

    async def fake_send(to, subject, html):
        sent.append((to, subject, html))
        return True

    monkeypatch.setattr(email_service, "_send_email", fake_send)
    return sent


def test_welcome_email_uses_the_chosen_word(monkeypatch):
    sent = _capture_email(monkeypatch)
    asyncio.run(email_service.send_account_welcome("a@example.invalid", "Ada Example", None, VILLAGE))
    html = sent[0][2]
    assert "your village gathers" in html
    assert "Invite the village" in html
    assert "famil" not in html.replace("font-family", "")


def test_welcome_email_default_is_unchanged(monkeypatch):
    sent = _capture_email(monkeypatch)
    asyncio.run(email_service.send_account_welcome("a@example.invalid", "Ada Example"))
    html = sent[0][2]
    assert "your family gathers" in html
    assert "Invite the family" in html


def _event():
    start = datetime.now(timezone.utc) + timedelta(days=2)
    return {
        "id": "evt-1",
        "community_id": "c1",
        "title": "Summer Gathering",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(days=2)).isoformat(),
        "location": "The Commons",
        "timezone": "UTC",
        "agenda": [
            {
                "id": "a1",
                "title": "Opening circle",
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(hours=1)).isoformat(),
                "visibility": "published",
            }
        ],
        "event_invites": [],
        "rsvp_records": [],
    }


def test_attendee_hub_story_prompt_uses_the_chosen_word():
    user = {"id": "u1", "community_id": "c1", "role": "member", "email": "m@example.invalid"}
    hub = build_attendee_hub(_event(), user, has_memory=False, group_noun=wording(VILLAGE).noun)
    assert hub["memory_prompt"]["question"] == "What is one village story you want everyone to remember?"
    default = build_attendee_hub(_event(), user, has_memory=False)
    assert "family story" in default["memory_prompt"]["question"]


def test_proposal_fallback_name_uses_the_chosen_word():
    view = member_projection(
        {"public_reference": "p1", "state": "submitted"},
        viewer_id="organizer",
        responses=[],
        eligible_user_ids=set(),
        organizer=True,
        group_noun="congregation",
    )
    assert view["proposer_display_name"] == "Former congregation member"


def test_gathering_templates_fill_the_word_and_leave_the_catalog_alone():
    templates = gathering_templates_for(wording({"preset": "community"}))
    reunion = next(t for t in templates if t["id"] == "reunion")
    meal = next(t for t in templates if t["id"] == "holiday_meal")
    assert reunion["description"].startswith("Community-wide gathering")
    assert "community recipe" in meal["defaults"]["recipe_prompt"]
    default = gathering_templates_for(wording(None))
    assert next(t for t in default if t["id"] == "reunion")["description"].startswith("Family-wide gathering")
    assert "{noun}" not in repr(default) and "{Noun}" not in repr(default)
    # The shared constant keeps its tokens for the next community.
    assert "{Noun}" in dependencies.GATHERING_TEMPLATES[0]["description"]


def test_guest_access_status_carries_the_target_space_word():
    view = safe_status_projection({"status": "approved"}, "Synthetic Space", VILLAGE)
    assert view["group_label"] == VILLAGE
    assert "group_label" not in safe_status_projection({"status": "pending"})


def test_invitation_reminder_and_k5_texts_never_contradict_a_custom_word():
    """Invitations (incl. K2 import/webhook sends) and K5 messages carry no
    group word at all, so a non-default label can never be contradicted."""
    event = _event()
    activity = event["agenda"][0]
    texts = [
        invitation_delivery._invitation_subject(event),
        invitation_delivery._invitation_html(event, "https://example.invalid/rsvp#t"),
        invitation_delivery._reminder_subject(event),
        invitation_delivery._reminder_html(event, "https://example.invalid/rsvp#t"),
        *em.announcement_email(
            announcement={"title": "Parking update", "body": "Use the north lot."},
            event=event,
            sender_name="The Organizer",
            app_url="https://example.invalid",
            unsubscribe_url="https://example.invalid/u",
        ),
        *em.reminder_email(
            event=event,
            activity=activity,
            offset_minutes=60,
            start_utc=datetime.fromisoformat(activity["start_at"]),
            sender_name="The Organizer",
            app_url="https://example.invalid",
            unsubscribe_url="https://example.invalid/u",
        ),
    ]
    from routes.events import _event_invite_message

    texts.append(_event_invite_message(event, "https://example.invalid/rsvp#t"))
    for text in texts:
        assert "famil" not in str(text).replace("font-family", "").lower(), text
