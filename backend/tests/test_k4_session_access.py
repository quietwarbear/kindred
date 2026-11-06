"""K4 per-activity access and choices, and K8 automatic response close.

- An activity's virtual link reaches only people who answered "coming" for that
  activity, plus organizers and the event's planning team. Everyone else gets
  "Link shared with registered attendees."
- Organizers can offer choices per activity (e.g. "In person" / "Remote"),
  stored with the response and counted for organizers.
- An activity stops taking responses at its RSVP deadline, or at its end when
  no deadline is set.
"""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_k4_session_access_unit")

from attendee_hub import _response_open, build_attendee_hub  # noqa: E402
from event_privacy import (  # noqa: E402
    serialize_event_for_guest,
    serialize_event_for_user,
)
from itinerary import (  # noqa: E402
    VIRTUAL_LINK_WITHHELD_NOTICE,
    activity_choice_summaries,
    activity_response_open,
    effective_response_choice,
    normalize_activity,
    normalize_response_choices,
    resolve_response_choice,
)
from models import ActivityRSVPRequest, AgendaItemRequest  # noqa: E402
from reunion_memory_capsule import build_reunion_memory_capsule  # noqa: E402
from reunion_recap import build_recap_projection  # noqa: E402
from routes import events as event_routes  # noqa: E402
from routes import public as public_routes  # noqa: E402

LINK = "https://meet.example.invalid/session-a"
NOW = datetime.now(timezone.utc)


def iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


MEMBER = {
    "id": "member-1",
    "community_id": "community-1",
    "role": "member",
    "full_name": "Synthetic Member",
    "email": "member@example.invalid",
}
ORGANIZER = {**MEMBER, "id": "organizer-1", "role": "organizer", "full_name": "Organizer"}
HOST = {**MEMBER, "id": "host-1", "role": "host", "full_name": "Host"}
PLANNER = {**MEMBER, "id": "planner-1", "full_name": "Planning Team Member"}
GUEST_INVITE = {
    "id": "guest-token-1",
    "invitee_name": "Synthetic Guest",
    "invite_source": "guest",
    "rsvp_status": "going",
}


def session(activity_id="session-a", **overrides):
    base = {
        "id": activity_id,
        "title": f"Session {activity_id}",
        "start_at": iso(timedelta(days=10)),
        "end_at": iso(timedelta(days=10, hours=2)),
        "timezone": "UTC",
        "visibility": "published",
        "attendance_requested": True,
        "virtual_link": LINK,
        "response_choices": ["In person", "Remote"],
    }
    base.update(overrides)
    return base


def event(**overrides):
    base = {
        "id": "event-1",
        "community_id": "community-1",
        "event_template": "reunion",
        "title": "Synthetic Multiday Gathering",
        "start_at": iso(timedelta(days=9)),
        "end_at": iso(timedelta(days=12)),
        "timezone": "UTC",
        "created_by": HOST["id"],
        "agenda": [session(), session("session-b", virtual_link="")],
        "activity_rsvps": [],
        "rsvp_records": [],
        "event_invites": [dict(GUEST_INVITE)],
        "planning_team_member_ids": [PLANNER["id"]],
        "potluck_items": [],
        "volunteer_slots": [],
    }
    base.update(overrides)
    return base


def response(respondent_id, status, activity_id="session-a", choice="", **extra):
    return {
        "activity_id": activity_id,
        "respondent_id": respondent_id,
        "status": status,
        "choice": choice,
        "party_size": 1,
        "updated_at": "2026-11-01T00:00:00+00:00",
        **extra,
    }


def hub_activity(event_doc, user, activity_id="session-a"):
    hub = build_attendee_hub(event_doc, user, has_memory=False)
    return next(a for a in hub["itinerary"]["activities"] if a["id"] == activity_id)


def member_activity(event_doc, user, activity_id="session-a"):
    view = serialize_event_for_user(event_doc, user)
    return next(a for a in view["agenda"] if a["id"] == activity_id)


def guest_activity(event_doc, invite=GUEST_INVITE, activity_id="session-a"):
    view = serialize_event_for_guest(event_doc, invite)
    return next(a for a in view["gathering"]["activities"] if a["id"] == activity_id)


# ---------------------------------------------------------------------------
# Link visibility by response state
# ---------------------------------------------------------------------------

WITHHELD = {
    "virtual_link": "",
    "virtual_link_withheld": True,
    "virtual_link_notice": VIRTUAL_LINK_WITHHELD_NOTICE,
}
VISIBLE = {
    "virtual_link": LINK,
    "virtual_link_withheld": False,
    "virtual_link_notice": "",
}


def _link_fields(activity):
    return {key: activity[key] for key in VISIBLE}


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, WITHHELD),
        ("maybe", WITHHELD),
        ("not-coming", WITHHELD),
        ("coming", VISIBLE),
    ],
)
def test_member_sees_link_only_after_answering_coming(status, expected):
    rows = [response(MEMBER["id"], status)] if status else []
    doc = event(activity_rsvps=rows)
    assert _link_fields(hub_activity(doc, MEMBER)) == expected
    assert _link_fields(member_activity(doc, MEMBER)) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, WITHHELD),
        ("maybe", WITHHELD),
        ("not-coming", WITHHELD),
        ("coming", VISIBLE),
    ],
)
def test_guest_sees_link_only_after_answering_coming(status, expected):
    rows = [response("invite:guest-token-1", status)] if status else []
    doc = event(activity_rsvps=rows)
    assert _link_fields(guest_activity(doc)) == expected


def test_coming_for_one_session_does_not_unlock_another_session():
    doc = event(
        agenda=[session(), session("session-c", virtual_link="https://meet.example.invalid/c")],
        activity_rsvps=[response(MEMBER["id"], "coming", "session-a")],
    )
    assert hub_activity(doc, MEMBER, "session-a")["virtual_link"] == LINK
    other = hub_activity(doc, MEMBER, "session-c")
    assert other["virtual_link"] == ""
    assert other["virtual_link_notice"] == VIRTUAL_LINK_WITHHELD_NOTICE


def test_changing_from_coming_to_not_coming_withdraws_the_link():
    doc = event(
        activity_rsvps=[
            response(MEMBER["id"], "coming", updated_at="2026-11-01T00:00:00+00:00"),
            response(
                f"invite:{MEMBER['id']}-alias",
                "not-coming",
                updated_at="2026-11-02T00:00:00+00:00",
            ),
        ],
        event_invites=[
            dict(GUEST_INVITE),
            {"id": f"{MEMBER['id']}-alias", "member_id": MEMBER["id"], "invite_source": "member"},
        ],
    )
    activity = hub_activity(doc, MEMBER)
    assert activity["my_response"] == "not-coming"
    assert activity["virtual_link"] == ""


@pytest.mark.parametrize("user", [ORGANIZER, HOST, PLANNER])
def test_organizers_and_planning_team_always_see_links(user):
    doc = event()
    assert hub_activity(doc, user)["virtual_link"] == LINK
    assert member_activity(doc, user)["virtual_link"] == LINK


def test_planning_team_membership_is_per_event():
    doc = event(planning_team_member_ids=[])
    assert hub_activity(doc, PLANNER)["virtual_link"] == ""


def test_activity_without_a_link_shows_no_notice():
    doc = event()
    for activity in (
        hub_activity(doc, MEMBER, "session-b"),
        member_activity(doc, MEMBER, "session-b"),
        guest_activity(doc, activity_id="session-b"),
    ):
        assert activity["virtual_link"] == ""
        assert activity["virtual_link_withheld"] is False
        assert activity["virtual_link_notice"] == ""


def test_organizer_guest_preview_shows_what_an_unanswered_guest_sees():
    preview_invite = {"id": "organizer-preview-only", "invitee_name": "Invited guest"}
    assert _link_fields(guest_activity(event(), preview_invite)) == WITHHELD


def test_link_never_leaks_anywhere_in_a_withheld_payload():
    doc = event()
    assert LINK not in repr(build_attendee_hub(doc, MEMBER, has_memory=False))
    assert LINK not in repr(serialize_event_for_user(doc, MEMBER))
    assert LINK not in repr(serialize_event_for_guest(doc, GUEST_INVITE))


def test_recap_capsule_and_invitation_text_carry_no_activity_link():
    doc = event(activity_rsvps=[response(MEMBER["id"], "maybe")])
    recap = build_recap_projection(
        doc,
        None,
        [],
        MEMBER,
        organizer_preview=False,
        next_gathering_started=False,
    )
    capsule = build_reunion_memory_capsule(doc, [], MEMBER)
    message = event_routes._event_invite_message(doc, "https://heykindred.org/rsvp#x")
    for payload in (recap, capsule, message):
        assert LINK not in repr(payload)


def test_today_attendee_actions_use_the_gated_hub():
    from routes import today as today_routes

    # Today builds its attendee actions from build_attendee_hub, so the same
    # projection (and therefore the same link rule) applies there.
    assert today_routes.build_attendee_hub is build_attendee_hub


# ---------------------------------------------------------------------------
# Organizer-defined choices
# ---------------------------------------------------------------------------


def test_choices_are_trimmed_deduplicated_and_bounded():
    assert normalize_response_choices(
        ["  In   person ", "Remote", "remote", "", None, *[f"Option {i}" for i in range(10)]]
    ) == ["In person", "Remote", "Option 0", "Option 1", "Option 2", "Option 3"]
    assert normalize_response_choices("In person") == []
    assert len(normalize_response_choices(["x" * 200])[0]) == 60


def test_choices_survive_activity_normalization_and_legacy_rows_default_empty():
    payload = AgendaItemRequest(title="Session", response_choices=["In person", "Remote"])
    assert normalize_activity(payload.model_dump(), activity_id="a")["response_choices"] == [
        "In person",
        "Remote",
    ]
    assert normalize_activity({"title": "Legacy"}, activity_id="b")["response_choices"] == []


def test_choice_validation_and_not_coming_never_carries_a_choice():
    activity = session()
    assert resolve_response_choice(activity, "coming", "remote") == "Remote"
    assert resolve_response_choice(activity, "maybe", "In person") == "In person"
    assert resolve_response_choice(activity, "not-coming", "Remote") == ""
    assert resolve_response_choice(activity, "coming", "") == ""
    with pytest.raises(ValueError):
        resolve_response_choice(activity, "coming", "Balcony")
    # Omitted choice keeps a still-offered previous one, drops a removed one.
    assert effective_response_choice(activity, "coming", None, "Remote") == "Remote"
    assert effective_response_choice(activity, "coming", None, "Balcony") == ""
    assert effective_response_choice(activity, "coming", "", "Remote") == ""


def test_choice_counts_for_organizers():
    doc = event(
        activity_rsvps=[
            response("a", "coming", choice="In person", party_size=3),
            response("b", "coming", choice="Remote"),
            response("c", "maybe", choice="Remote"),
            response("d", "coming", choice=""),
            response("e", "not-coming", choice="Remote"),
            response("f", "coming", choice="Removed option"),
        ]
    )
    summary = activity_choice_summaries(doc)["session-a"]
    assert summary["choices"]["In person"] == {"coming": 1, "maybe": 0, "party_size": 3}
    assert summary["choices"]["Remote"] == {"coming": 1, "maybe": 1, "party_size": 1}
    assert summary["unspecified"] == {"coming": 2, "maybe": 0, "party_size": 2}
    assert "session-b" in activity_choice_summaries(doc)
    assert "session-x" not in activity_choice_summaries(doc)


def test_attendees_see_their_own_choice_and_the_options():
    doc = event(
        activity_rsvps=[
            response(MEMBER["id"], "coming", choice="Remote"),
            response("invite:guest-token-1", "maybe", choice="In person"),
        ]
    )
    hub = hub_activity(doc, MEMBER)
    assert hub["response_choices"] == ["In person", "Remote"]
    assert hub["my_choice"] == "Remote"
    view = serialize_event_for_user(doc, MEMBER)
    assert view["my_activity_choices"] == {"session-a": "Remote"}
    guest = guest_activity(doc)
    assert guest["my_choice"] == "In person"
    assert guest["response_choices"] == ["In person", "Remote"]


def test_member_view_counts_are_aggregate_only():
    doc = event(activity_rsvps=[response("someone-else", "coming", choice="Remote")])
    view = serialize_event_for_user(doc, MEMBER)
    assert view["activity_choice_summaries"]["session-a"]["choices"]["Remote"]["coming"] == 1
    assert "someone-else" not in repr(view)


def test_rsvp_request_choice_defaults_to_keep_existing():
    assert ActivityRSVPRequest(activity_id="a", status="coming").choice is None
    with pytest.raises(ValidationError):
        ActivityRSVPRequest(activity_id="a", status="coming", choice="x" * 121)


# ---------------------------------------------------------------------------
# K8 automatic close
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, True),
        (
            {"start_at": iso(timedelta(hours=-3)), "end_at": iso(timedelta(hours=-1))},
            False,
        ),
        (
            {"start_at": iso(timedelta(hours=-1)), "end_at": iso(timedelta(hours=1))},
            True,
        ),
        ({"rsvp_deadline": iso(timedelta(hours=-1))}, False),
        (
            {
                "start_at": iso(timedelta(hours=-3)),
                "end_at": iso(timedelta(hours=-1)),
                "rsvp_deadline": iso(timedelta(hours=5)),
            },
            True,
        ),
        ({"rsvp_deadline": "not-a-date"}, False),
        ({"end_at": ""}, True),
    ],
    ids=[
        "future",
        "ended-no-deadline",
        "in-progress",
        "deadline-passed",
        "deadline-overrides-end",
        "invalid-deadline-fails-closed",
        "legacy-no-end",
    ],
)
def test_response_window_closes_at_deadline_or_end(overrides, expected):
    activity = session(**overrides)
    doc = event(agenda=[activity])
    assert _response_open(activity, doc) is expected
    assert activity_response_open(activity, "UTC") is expected
    assert hub_activity(doc, MEMBER)["response_open"] is expected
    assert member_activity(doc, MEMBER)["response_open"] is expected
    assert guest_activity(doc)["response_open"] is expected


def test_end_time_uses_activity_timezone():
    local = NOW.astimezone(timezone(timedelta(hours=-5)))
    activity = session(
        start_at=(local - timedelta(hours=2)).replace(tzinfo=None).isoformat(),
        end_at=(local + timedelta(minutes=30)).replace(tzinfo=None).isoformat(),
        timezone="America/Bogota",  # UTC-5 all year, no DST
    )
    assert activity_response_open(activity, "UTC") is True
    activity["end_at"] = (local - timedelta(minutes=30)).replace(tzinfo=None).isoformat()
    assert activity_response_open(activity, "UTC") is False


def test_ended_session_drops_out_of_pending_attendee_actions():
    ended = session(start_at=iso(timedelta(hours=-3)), end_at=iso(timedelta(hours=-1)))
    hub = build_attendee_hub(event(agenda=[ended]), MEMBER, has_memory=False)
    assert hub["next_action"]["code"] != "complete_activity_responses"


# ---------------------------------------------------------------------------
# Route behavior (member and guest RSVP writes)
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, matched_count):
        self.matched_count = matched_count


class _EventCollection:
    def __init__(self, doc):
        self.doc = deepcopy(doc)

    async def find_one(self, query, _projection=None):
        if query.get("id") not in (None, self.doc["id"]):
            return None
        return deepcopy(self.doc)

    async def update_one(self, _query, update):
        self.doc.update(deepcopy(update.get("$set", {})))
        self.doc["rsvp_revision"] = int(self.doc.get("rsvp_revision", 0)) + 1
        return _Result(1)


class _NoneCollection:
    async def find_one(self, *_args, **_kwargs):
        return None


@pytest.fixture
def member_route(monkeypatch):
    def install(doc):
        collection = _EventCollection(doc)

        async def event_for_user(_event_id, _user):
            return deepcopy(collection.doc)

        monkeypatch.setattr(event_routes, "events_collection", collection)
        monkeypatch.setattr(event_routes, "get_event_for_user", event_for_user)
        return collection

    return install


async def _member_rsvp(status, choice=None, activity_id="session-a", user=MEMBER):
    return await event_routes.update_activity_rsvp(
        "event-1",
        ActivityRSVPRequest(activity_id=activity_id, status=status, choice=choice),
        user,
    )


@pytest.mark.asyncio
async def test_member_route_stores_choice_and_returns_link_after_coming(member_route):
    collection = member_route(event())
    view = await _member_rsvp("maybe", "Remote")
    assert next(a for a in view["agenda"] if a["id"] == "session-a")["virtual_link"] == ""
    view = await _member_rsvp("coming", "in person")
    activity = next(a for a in view["agenda"] if a["id"] == "session-a")
    assert activity["virtual_link"] == LINK
    assert view["my_activity_choices"] == {"session-a": "In person"}
    rows = [r for r in collection.doc["activity_rsvps"] if r["respondent_id"] == MEMBER["id"]]
    assert len(rows) == 1 and rows[0]["choice"] == "In person"


@pytest.mark.asyncio
async def test_member_route_rejects_unknown_choice(member_route):
    member_route(event())
    with pytest.raises(HTTPException) as exc:
        await _member_rsvp("coming", "Balcony")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_response_choice"


@pytest.mark.asyncio
async def test_member_route_keeps_choice_when_older_client_omits_it(member_route):
    collection = member_route(
        event(activity_rsvps=[response(MEMBER["id"], "maybe", choice="Remote")])
    )
    await _member_rsvp("coming")
    assert collection.doc["activity_rsvps"][-1]["choice"] == "Remote"
    await _member_rsvp("not-coming")
    assert collection.doc["activity_rsvps"][-1]["choice"] == ""


@pytest.mark.asyncio
async def test_member_route_refuses_responses_after_activity_ends(member_route):
    ended = session(start_at=iso(timedelta(hours=-3)), end_at=iso(timedelta(hours=-1)))
    member_route(event(agenda=[ended]))
    with pytest.raises(HTTPException) as exc:
        await _member_rsvp("coming", "Remote")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "activity_rsvp_closed"


@pytest.fixture
def guest_route(monkeypatch):
    def install(doc):
        collection = _EventCollection(doc)

        async def find_event_and_invite(token):
            current = deepcopy(collection.doc)
            invite = next(
                (i for i in current["event_invites"] if i.get("id") == token), None
            )
            return current, invite

        async def no_notify(**_kwargs):
            return None

        monkeypatch.setattr(public_routes, "events_collection", collection)
        monkeypatch.setattr(public_routes, "_find_event_and_invite", find_event_and_invite)
        monkeypatch.setattr(public_routes, "communities_collection", _NoneCollection())
        monkeypatch.setattr(public_routes, "users_collection", _NoneCollection())
        monkeypatch.setattr(public_routes, "maybe_notify", no_notify)
        return collection

    return install


async def _guest_rsvp(responses, choices=None):
    payload = public_routes.PublicRSVPRequest(
        status="some",
        activity_responses=responses,
        activity_choices=choices or {},
    )
    return await public_routes._public_rsvp_submit("guest-token-1", payload)


def _guest_session(view, activity_id="session-a"):
    return next(a for a in view["gathering"]["activities"] if a["id"] == activity_id)


@pytest.mark.asyncio
async def test_guest_route_stores_choice_and_reveals_link_only_when_coming(guest_route):
    guest_route(event())
    view = await _guest_rsvp({"session-a": "maybe"}, {"session-a": "Remote"})
    assert _guest_session(view)["virtual_link"] == ""
    assert _guest_session(view)["my_choice"] == "Remote"
    view = await _guest_rsvp({"session-a": "coming"})
    assert _guest_session(view)["virtual_link"] == LINK
    assert _guest_session(view)["my_choice"] == "Remote"


@pytest.mark.asyncio
async def test_guest_route_rejects_unknown_or_orphan_choices(guest_route):
    guest_route(event())
    for responses, choices in (
        ({"session-a": "coming"}, {"session-a": "Balcony"}),
        ({"session-a": "coming"}, {"session-b": "Remote"}),
    ):
        with pytest.raises(HTTPException) as exc:
            await _guest_rsvp(responses, choices)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "invalid_response_choice"


@pytest.mark.asyncio
async def test_guest_route_keeps_closed_answers_and_refuses_changes(guest_route):
    ended = session(start_at=iso(timedelta(hours=-3)), end_at=iso(timedelta(hours=-1)))
    saved = response("invite:guest-token-1", "coming", choice="Remote")
    collection = guest_route(
        event(agenda=[ended, session("session-b", virtual_link="")], activity_rsvps=[saved])
    )
    # The form resubmits every answer: an unchanged closed answer is accepted
    # and kept exactly as saved, while an open activity still updates.
    view = await _guest_rsvp(
        {"session-a": "coming", "session-b": "coming"}, {"session-b": "In person"}
    )
    assert _guest_session(view)["response_open"] is False
    kept = [r for r in collection.doc["activity_rsvps"] if r["activity_id"] == "session-a"]
    assert kept == [saved]
    for responses, choices in (
        ({"session-a": "not-coming"}, None),
        ({"session-a": "coming"}, {"session-a": "In person"}),
        ({"session-a": "maybe"}, None),
    ):
        with pytest.raises(HTTPException) as exc:
            await _guest_rsvp(responses, choices)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "activity_rsvp_closed"


@pytest.mark.asyncio
async def test_guest_route_refuses_a_first_answer_after_the_activity_ended(guest_route):
    ended = session(start_at=iso(timedelta(hours=-3)), end_at=iso(timedelta(hours=-1)))
    guest_route(event(agenda=[ended]))
    with pytest.raises(HTTPException) as exc:
        await _guest_rsvp({"session-a": "coming"})
    assert exc.value.status_code == 409
