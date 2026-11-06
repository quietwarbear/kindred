"""X2: send an event's attendees to Ile Ubuntu.

- Who is sent: registered people marked "coming" for a mapped activity, with
  the courses for those activities. Not coming / maybe / no email / no
  longer registered are left out and counted.
- Requests are signed exactly as Ile Ubuntu verifies them (shared vector).
- The connection key lives in its own collection, never on the event, and is
  only ever shown as its last four characters.
- Organizer-only; sending (not previewing) waits until the event has ended.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_x2_unit")

import ile_ubuntu_handoff as handoff  # noqa: E402
from event_privacy import serialize_event_for_user  # noqa: E402
from routes import ile_ubuntu_handoff as routes  # noqa: E402

NOW = datetime(2026, 12, 10, tzinfo=timezone.utc)
KEY = "kh_" + "k" * 40


def answer(respondent, activity, status, at="2026-11-20T00:00:00+00:00"):
    return {"respondent_id": respondent, "activity_id": activity, "status": status, "updated_at": at}


def event(**overrides):
    base = {
        "id": "event-1",
        "community_id": "c-1",
        "title": "Weekend Gathering",
        "timezone": "UTC",
        "start_at": "2026-12-05T09:00",
        "end_at": "2026-12-06T18:00",
        "agenda": [
            {"id": "a1", "title": "Day One", "start_at": "2026-12-05T09:00", "end_at": "2026-12-05T17:00"},
            {"id": "a2", "title": "Day Two", "start_at": "2026-12-06T09:00", "end_at": "2026-12-06T17:00"},
            {"id": "a3", "title": "Dinner", "start_at": "2026-12-05T18:00", "end_at": "2026-12-05T21:00"},
        ],
        "event_invites": [
            {"id": "inv-ada", "invitee_name": "Ada Guest", "email": "ada@example.invalid", "created_at": "1"},
            {"id": "inv-bea", "invitee_name": "Bea Guest", "email": "bea@example.invalid", "created_at": "1"},
            {"id": "inv-noemail", "invitee_name": "No Email", "email": "", "created_at": "1"},
            {"id": "inv-old", "invitee_name": "Old", "email": "old@example.invalid", "status": "revoked"},
            {"id": "inv-member", "invitee_name": "Cy Member", "email": "cy@example.invalid",
             "member_id": "m-cy", "invite_source": "member", "created_at": "1"},
        ],
        "activity_rsvps": [
            answer("invite:inv-ada", "a1", "coming"),
            answer("invite:inv-ada", "a2", "coming"),
            answer("invite:inv-ada", "a3", "coming"),
            answer("invite:inv-bea", "a1", "maybe"),
            answer("invite:inv-bea", "a2", "coming", at="2026-11-01"),
            answer("invite:inv-bea", "a2", "not-coming", at="2026-11-25"),
            answer("invite:inv-noemail", "a1", "coming"),
            answer("invite:inv-old", "a1", "coming"),
            answer("m-cy", "a2", "coming"),
            answer("m-dee", "a1", "coming"),
        ],
    }
    base.update(overrides)
    return base


MEMBERS = {
    "m-cy": {"id": "m-cy", "email": "cy@example.invalid", "full_name": "Cy Member"},
    "m-dee": {"id": "m-dee", "email": "dee@example.invalid", "full_name": "Dee Member"},
}
MAP = {"a1": "course-day1", "a2": "course-day2"}


# ---------------------------------------------------------------------------
# Who is sent
# ---------------------------------------------------------------------------


def test_only_people_coming_to_mapped_activities_are_sent():
    attendees, counts = handoff.handoff_attendees(event(), MAP, members_by_id=MEMBERS, now=NOW)
    assert attendees == [
        {"name": "Ada Guest", "email": "ada@example.invalid", "course_ids": ["course-day1", "course-day2"]},
        {"name": "Cy Member", "email": "cy@example.invalid", "course_ids": ["course-day2"]},
        {"name": "Dee Member", "email": "dee@example.invalid", "course_ids": ["course-day1"]},
    ]
    # Bea's latest a2 answer is not-coming and a1 is maybe: not sent.
    assert counts == {"people_coming": 5, "no_email": 1, "not_registered": 1, "sending": 3}


def test_unmapped_activities_and_shared_courses():
    attendees, _ = handoff.handoff_attendees(
        event(), {"a1": "course-x", "a3": "course-x"}, members_by_id=MEMBERS, now=NOW
    )
    ada = next(a for a in attendees if a["email"].startswith("ada"))
    assert ada["course_ids"] == ["course-x"]
    assert all(a["email"] != "cy@example.invalid" for a in attendees)  # a2 not mapped


def test_clean_course_map_drops_unknown_activities_and_blanks():
    assert handoff.clean_course_map(event(), {"a1": " c1 ", "zz": "c2", "a2": "", "a3": 5}) == {"a1": "c1"}
    assert handoff.clean_course_map(event(), "nope") == {}


def test_event_has_ended():
    assert handoff.event_has_ended(event(), NOW) is True
    assert handoff.event_has_ended(event(), datetime(2026, 12, 6, 12, tzinfo=timezone.utc)) is False
    no_dates = event(start_at="", end_at="")
    assert handoff.event_has_ended(no_dates, NOW) is True
    assert handoff.event_has_ended(event(start_at="", end_at="", agenda=[]), NOW) is False


# ---------------------------------------------------------------------------
# Signing and the HTTP call
# ---------------------------------------------------------------------------


def test_signature_matches_the_shared_vector():
    # The same vector is asserted in ile_ubuntu backend/tests/test_kindred_handoff.py.
    assert handoff.sign("shared-test-secret", "1700000000", b'{"a":1}') == (
        "v1=b69bcc2b6b3690a8440616579fa827f9c8fe67d9a4458e144a51d646751f8100"
    )


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("ILE_UBUNTU_API_URL", "https://ile.example.invalid/")
    monkeypatch.setenv("ILE_UBUNTU_HANDOFF_SECRET", "s3cret")


@pytest.mark.asyncio
async def test_call_signs_the_exact_body(configured):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = request.content
        seen["ts"] = request.headers["x-handoff-timestamp"]
        seen["sig"] = request.headers["x-handoff-signature"]
        return httpx.Response(200, json={"counts": {"created": 1}})

    reply = await handoff.call_ile_ubuntu("import", {"x": 1}, transport=httpx.MockTransport(handler))
    assert reply == {"counts": {"created": 1}}
    assert seen["url"] == "https://ile.example.invalid/api/kindred-handoff/import"
    assert seen["sig"] == handoff.sign("s3cret", seen["ts"], seen["body"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code, code",
    [(403, "connection_key_invalid"), (401, "handoff_not_configured"), (503, "handoff_not_configured"),
     (429, "ile_ubuntu_busy"), (500, "ile_ubuntu_error")],
)
async def test_ile_ubuntu_errors_become_clear_messages(configured, status_code, code):
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json={"detail": "x"}))
    with pytest.raises(handoff.HandoffError) as exc:
        await handoff.call_ile_ubuntu("courses", {}, transport=transport)
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_unreachable_and_unconfigured(configured, monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(handoff.HandoffError) as exc:
        await handoff.call_ile_ubuntu("courses", {}, transport=httpx.MockTransport(boom))
    assert exc.value.code == "ile_ubuntu_unreachable"
    monkeypatch.delenv("ILE_UBUNTU_HANDOFF_SECRET")
    with pytest.raises(handoff.HandoffError) as exc:
        await handoff.call_ile_ubuntu("courses", {})
    assert exc.value.code == "handoff_not_configured"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, n=1):
        self.matched_count = n
        self.modified_count = n
        self.deleted_count = n


class _Events:
    def __init__(self, doc):
        self.doc = deepcopy(doc)

    async def update_one(self, _query, update, upsert=False):
        self.doc.update(deepcopy(update.get("$set", {})))
        return _Result()


class _Connections:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query, _projection=None):
        doc = self.docs.get(query["event_id"])
        return deepcopy(doc) if doc else None

    async def update_one(self, query, update, upsert=False):
        self.docs.setdefault(query["event_id"], {}).update(deepcopy(update["$set"]))
        return _Result()

    async def delete_one(self, query):
        self.docs.pop(query["event_id"], None)
        return _Result()


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _n):
        return deepcopy(self.docs)


class _Users:
    def find(self, _query, _projection=None):
        return _Cursor(list(MEMBERS.values()))


ORGANIZER = {"id": "org-1", "role": "organizer", "community_id": "c-1"}
MEMBER = {"id": "m-cy", "role": "member", "community_id": "c-1"}


@pytest.fixture
def wired(monkeypatch, configured):
    events = _Events(event())
    connections = _Connections()
    calls = []

    async def event_for_user(_event_id, _user):
        return deepcopy(events.doc)

    async def fake_call(path, payload, **_kw):
        calls.append((path, deepcopy(payload)))
        if payload.get("connection_key") != KEY:
            raise handoff.HandoffError(403, "connection_key_invalid", "bad key")
        if path == "courses":
            return {"teacher_name": "Teacher", "courses": [{"id": "course-day1", "title": "Day One course"}]}
        return {"dry_run": payload["dry_run"], "counts": {"created": 2, "enrolled": 3, "skipped": 0, "errors": 0},
                "welcome_emails": 0 if payload["dry_run"] else 2}

    monkeypatch.setattr(routes, "events_collection", events)
    monkeypatch.setattr(routes, "ile_ubuntu_handoff_connections_collection", connections)
    monkeypatch.setattr(routes, "users_collection", _Users())
    monkeypatch.setattr(routes, "get_event_for_user", event_for_user)
    monkeypatch.setattr(routes, "call_ile_ubuntu", fake_call)
    monkeypatch.setattr(routes, "event_has_ended", lambda _event: True)
    return events, connections, calls


def setup(**kw):
    return routes.HandoffSetupRequest(**kw)


@pytest.mark.asyncio
async def test_routes_are_organizer_only(wired):
    for call in (
        routes.get_handoff("event-1", MEMBER),
        routes.save_handoff("event-1", setup(course_map={}), MEMBER),
        routes.send_to_ile_ubuntu("event-1", routes.HandoffSendRequest(), MEMBER),
        routes.forget_connection("event-1", MEMBER),
    ):
        with pytest.raises(HTTPException) as exc:
            await call
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_connect_map_and_send(wired):
    events, connections, calls = wired
    state = await routes.save_handoff("event-1", setup(connection_key=KEY, course_map=MAP), ORGANIZER)
    assert state["connected"] is True and state["key_last4"] == KEY[-4:]
    assert KEY not in json.dumps(state)
    assert state["courses"] == [{"id": "course-day1", "title": "Day One course"}]
    assert events.doc["ile_ubuntu_course_map"] == MAP
    # The key is stored off the event document.
    assert KEY not in json.dumps(events.doc) and connections.docs["event-1"]["connection_key"] == KEY

    reply = await routes.send_to_ile_ubuntu("event-1", routes.HandoffSendRequest(), ORGANIZER)
    path, payload = calls[-1]
    assert path == "import" and payload["dry_run"] is False and payload["event_ref"] == "event-1"
    assert [a["email"] for a in payload["attendees"]] == ["ada@example.invalid", "cy@example.invalid", "dee@example.invalid"]
    assert reply["local"]["sending"] == 3 and reply["report"]["counts"]["enrolled"] == 3
    assert events.doc["ile_ubuntu_handoff_last"]["counts"]["created"] == 2
    assert events.doc["ile_ubuntu_handoff_last"]["welcome_emails"] == 2


@pytest.mark.asyncio
async def test_preview_does_not_record_a_send(wired):
    events, _connections, _calls = wired
    await routes.save_handoff("event-1", setup(connection_key=KEY, course_map=MAP), ORGANIZER)
    reply = await routes.send_to_ile_ubuntu("event-1", routes.HandoffSendRequest(dry_run=True), ORGANIZER)
    assert reply["dry_run"] is True and "ile_ubuntu_handoff_last" not in events.doc


@pytest.mark.asyncio
async def test_bad_key_is_refused_and_not_stored(wired):
    _events, connections, _calls = wired
    with pytest.raises(HTTPException) as exc:
        await routes.save_handoff("event-1", setup(connection_key="kh_" + "x" * 40, course_map=MAP), ORGANIZER)
    assert exc.value.status_code == 403 and connections.docs == {}
    with pytest.raises(HTTPException) as exc:
        await routes.save_handoff("event-1", setup(connection_key="not-a-key", course_map=MAP), ORGANIZER)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_send_needs_connection_mapping_and_an_ended_event(wired, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await routes.send_to_ile_ubuntu("event-1", routes.HandoffSendRequest(), ORGANIZER)
    assert exc.value.detail["code"] == "not_connected"
    await routes.save_handoff("event-1", setup(connection_key=KEY, course_map={}), ORGANIZER)
    with pytest.raises(HTTPException) as exc:
        await routes.send_to_ile_ubuntu("event-1", routes.HandoffSendRequest(), ORGANIZER)
    assert exc.value.detail["code"] == "no_mapping"
    await routes.save_handoff("event-1", setup(course_map=MAP), ORGANIZER)
    monkeypatch.setattr(routes, "event_has_ended", lambda _event: False)
    with pytest.raises(HTTPException) as exc:
        await routes.send_to_ile_ubuntu("event-1", routes.HandoffSendRequest(), ORGANIZER)
    assert exc.value.detail["code"] == "event_not_ended"
    # A preview is allowed before the event ends.
    assert (await routes.send_to_ile_ubuntu("event-1", routes.HandoffSendRequest(dry_run=True), ORGANIZER))["dry_run"]


@pytest.mark.asyncio
async def test_saving_mapping_keeps_the_key_and_forget_removes_it(wired):
    _events, connections, _calls = wired
    await routes.save_handoff("event-1", setup(connection_key=KEY, course_map=MAP), ORGANIZER)
    state = await routes.save_handoff("event-1", setup(course_map={"a1": "course-day1"}), ORGANIZER)
    assert state["connected"] is True and state["course_map"] == {"a1": "course-day1"}
    state = await routes.forget_connection("event-1", ORGANIZER)
    assert state["connected"] is False and connections.docs == {}


def test_handoff_fields_are_never_shown_to_members():
    doc = event(ile_ubuntu_course_map=MAP, ile_ubuntu_handoff_last={"counts": {}})
    view = serialize_event_for_user(doc, {"id": "m-x", "role": "member", "community_id": "c-1"})
    assert "ile_ubuntu_course_map" not in view and "ile_ubuntu_handoff_last" not in view
