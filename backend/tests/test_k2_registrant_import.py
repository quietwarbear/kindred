"""K2 registrant import: CSV, signed webhook, duplicate flags (K9 first half).

- A CSV of name / email / sessions purchased creates or updates one invitation
  per normalized email and pre-marks the person "coming" for exactly those
  sessions, which unlocks those sessions' links under K4 and no others.
- Re-running the same file changes nothing.
- A per-event signed webhook accepts the same fields as JSON and sends the
  invitation through the shared first-send path. Bad, stale and replayed
  signatures are refused.
- A name that matches an existing invitee under a different email is flagged
  for the organizer instead of becoming a silent duplicate.
- Every organizer route requires an organizer of the event's community.
"""

from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_k2_registrant_import_unit")

import registrant_import as ri  # noqa: E402
from attendee_hub import build_attendee_hub  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from invitation_redelivery import ProviderReceipt, ProviderStatus  # noqa: E402
from registrant_webhook import (  # noqa: E402
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    compute_signature,
    verify_signature,
)
from routes import registrants as routes  # noqa: E402

LINK_A = "https://meet.example.invalid/day-one"
LINK_B = "https://meet.example.invalid/day-two"
NOW = datetime.now(timezone.utc)


def iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


ORGANIZER = {
    "id": "organizer-1",
    "community_id": "community-1",
    "role": "organizer",
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
}
MEMBER = {**ORGANIZER, "id": "member-1", "role": "member", "full_name": "Synthetic Member"}
OTHER_ORGANIZER = {**ORGANIZER, "id": "organizer-2", "community_id": "community-2"}


def session(activity_id, title, link="", **overrides):
    base = {
        "id": activity_id,
        "title": title,
        "start_at": iso(timedelta(days=10)),
        "end_at": iso(timedelta(days=10, hours=2)),
        "timezone": "UTC",
        "visibility": "published",
        "attendance_requested": True,
        "virtual_link": link,
    }
    base.update(overrides)
    return base


def make_event(**overrides):
    base = {
        "id": "event-1",
        "community_id": "community-1",
        "event_template": "reunion",
        "title": "Synthetic Multiday Gathering",
        "start_at": iso(timedelta(days=9)),
        "end_at": iso(timedelta(days=12)),
        "timezone": "UTC",
        "location": "Synthetic venue",
        "publication_state": "published",
        "gathering_format": "in-person",
        "agenda": [
            session("day-1", "Day One Workshop", LINK_A),
            session("day-2", "Day Two Workshop", LINK_B),
            session("closing", "Closing Circle"),
            session("draft", "Unpublished Session", visibility="draft"),
        ],
        "activity_rsvps": [],
        "rsvp_records": [],
        "event_invites": [],
        "potluck_items": [],
        "volunteer_slots": [],
        "rsvp_revision": 0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# A small in-memory stand-in for the Motor collections the routes touch.
# ---------------------------------------------------------------------------


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in expected):
                return False
            continue
        value = doc
        for part in key.split("."):
            if isinstance(value, list):  # Mongo matches any element
                value = [item.get(part) for item in value if isinstance(item, dict)]
                if not isinstance(expected, dict) and expected in value:
                    value = expected
            else:
                value = value.get(part) if isinstance(value, dict) else None
        if isinstance(expected, dict):
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$ne" in expected and value == expected["$ne"]:
                return False
            if "$exists" in expected and (value is not None) != expected["$exists"]:
                return False
        elif value != expected:
            return False
    return True


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction):
        self.docs.sort(key=lambda d: d.get(key, ""), reverse=direction < 0)
        return self

    async def to_list(self, _length):
        return deepcopy(self.docs)


class FakeCollection:
    def __init__(self, docs=None, unique=None):
        self.docs = [deepcopy(d) for d in docs or []]
        self.unique = unique

    def find(self, query=None, _projection=None):
        return _Cursor([d for d in self.docs if _matches(d, query or {})])

    async def find_one(self, query, _projection=None, **_kwargs):
        doc = next((d for d in self.docs if _matches(d, query)), None)
        return deepcopy(doc)

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _matches(d, query))

    async def insert_one(self, doc):
        if self.unique and any(d.get(self.unique) == doc.get(self.unique) for d in self.docs):
            raise DuplicateKeyError("duplicate")
        self.docs.append(deepcopy(doc))

    async def delete_one(self, query):
        doc = next((d for d in self.docs if _matches(d, query)), None)
        if doc is not None:
            self.docs.remove(doc)

    def _apply(self, doc, update, inserting):
        for key, value in update.get("$set", {}).items():
            doc[key] = deepcopy(value)
        if inserting:
            for key, value in update.get("$setOnInsert", {}).items():
                doc[key] = deepcopy(value)
        for key, value in update.get("$inc", {}).items():
            doc[key] = int(doc.get(key, 0) or 0) + value

    async def update_one(self, query, update, upsert=False):
        doc = next((d for d in self.docs if _matches(d, query)), None)
        if doc is None:
            if not upsert:
                return _Result(0)
            doc = {k: v for k, v in query.items() if not isinstance(v, dict)}
            self.docs.append(doc)
            self._apply(doc, update, True)
            return _Result(1)
        self._apply(doc, update, False)
        return _Result(1)

    async def find_one_and_update(self, query, update, upsert=False, return_document=False, **_kw):
        doc = next((d for d in self.docs if _matches(d, query)), None)
        before = deepcopy(doc)
        if doc is None:
            if not upsert:
                return None
            doc = {k: v for k, v in query.items() if not isinstance(v, dict)}
            self.docs.append(doc)
            self._apply(doc, update, True)
        else:
            self._apply(doc, update, False)
        return deepcopy(doc) if return_document else before


class FakeProvider:
    def __init__(self):
        self.sent = []

    async def send(self, envelope):
        self.sent.append(envelope.recipient)
        return ProviderReceipt(
            status=ProviderStatus.ACCEPTED,
            provider_message_id=f"msg-{len(self.sent)}",
        )


@pytest.fixture
def store(monkeypatch):
    events = FakeCollection([make_event()])
    state = {
        "events": events,
        "users": FakeCollection(
            [{"id": "member-1", "community_id": "community-1", "email": "member@example.invalid", "full_name": "Synthetic Member"}]
        ),
        "flags": FakeCollection(),
        "hooks": FakeCollection(),
        "deliveries": FakeCollection(unique="replay_digest"),
        "outbox": FakeCollection(),
        "provider": FakeProvider(),
    }

    async def event_for_user(event_id, user):
        doc = await events.find_one({"id": event_id, "community_id": user["community_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Event not found.")
        return doc

    monkeypatch.setattr(routes, "events_collection", events)
    monkeypatch.setattr(routes, "users_collection", state["users"])
    monkeypatch.setattr(routes, "registrant_import_flags_collection", state["flags"])
    monkeypatch.setattr(routes, "registrant_hooks_collection", state["hooks"])
    monkeypatch.setattr(routes, "registrant_hook_deliveries_collection", state["deliveries"])
    monkeypatch.setattr(routes, "invitation_delivery_outbox_collection", state["outbox"])
    monkeypatch.setattr(routes, "get_event_for_user", event_for_user)
    monkeypatch.setattr(routes, "first_send_enabled", lambda: True)
    monkeypatch.setattr(routes, "build_invitation_delivery_provider", lambda: state["provider"])
    return state


def doc(store):
    return store["events"].docs[0]


def invite_for(store, email):
    return next(i for i in doc(store)["event_invites"] if i["email"] == email)


def marks_for(store, email):
    invite = invite_for(store, email)
    identity = invite.get("member_id") or f"invite:{invite['id']}"
    return {
        row["activity_id"]: row["status"]
        for row in doc(store)["activity_rsvps"]
        if row["respondent_id"] == identity
    }


async def run_csv(text, user=ORGANIZER, send=False):
    return await routes.import_registrants_csv(
        "event-1", routes.RegistrantCSVImportRequest(csv_text=text, send_invitations=send), user
    )


CSV = (
    "Name,Email,Sessions purchased\n"
    "Ada Example,ADA@Example.invalid ,Day One Workshop; Day Two Workshop\n"
    "Bo Example,bo@example.invalid,day one workshop\n"
    "Cy Example,cy@example.invalid,\n"
)


# ---------------------------------------------------------------------------
# Parsing and session matching (pure)
# ---------------------------------------------------------------------------


def test_parser_reads_common_export_headers_and_combines_repeat_emails():
    parsed = ri.parse_registrant_csv(
        "﻿First Name,Last Name,E-mail,Ticket Type\n"
        "Ada,Example,ada@example.invalid,Day One Workshop\n"
        "Ada,Example,ADA@example.invalid,Day Two Workshop\n"
        ",,not-an-email,Day One Workshop\n"
    )
    assert [r.email for r in parsed.registrants] == ["ada@example.invalid"]
    assert parsed.registrants[0].name == "Ada Example"
    assert parsed.registrants[0].session_refs == ["Day One Workshop", "Day Two Workshop"]
    statuses = {r["row"]: (r["status"], r.get("code")) for r in parsed.row_results}
    assert statuses == {3: ("skipped", "merged_with_earlier_row"), 4: ("error", "invalid_email")}


@pytest.mark.parametrize(
    "text, code",
    [
        ("", "csv_empty"),
        ("Name,Email\n", "csv_empty"),
        ("Name,Phone\nAda,555\n", "csv_missing_email_column"),
        ("Email\n" + "x@example.invalid\n" * (ri.MAX_CSV_ROWS + 1), "csv_too_many_rows"),
    ],
)
def test_parser_rejects_unreadable_files(text, code):
    with pytest.raises(ri.CSVImportError) as exc:
        ri.parse_registrant_csv(text)
    assert exc.value.code == code


def test_session_refs_match_id_title_all_and_comma_lists():
    event = make_event()
    assert ri.resolve_session_refs(event, ["day-2", "  CLOSING   circle "]) == (
        ["day-2", "closing"],
        [],
        [],
    )
    assert sorted(ri.resolve_session_refs(event, ["All"])[0]) == ["closing", "day-1", "day-2"]
    assert ri.resolve_session_refs(event, ["Day One Workshop, Day Two Workshop"])[0] == [
        "day-1",
        "day-2",
    ]
    # Unpublished sessions cannot be sold into.
    assert ri.resolve_session_refs(event, ["Unpublished Session"])[1] == ["Unpublished Session"]
    twin = make_event(agenda=[session("a", "Twin"), session("b", "Twin")])
    assert ri.resolve_session_refs(twin, ["Twin"]) == ([], [], ["Twin"])


# ---------------------------------------------------------------------------
# CSV import through the route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_creates_invites_and_marks_exactly_the_purchased_sessions(store):
    report = await run_csv(CSV)
    assert report["counts"] == {"created": 3, "updated": 0, "skipped": 0, "flagged": 0, "error": 0}
    assert [r["row"] for r in report["rows"]] == [2, 3, 4]
    ada = invite_for(store, "ada@example.invalid")
    assert ada["invitee_name"] == "Ada Example"
    assert ada["invite_source"] == "guest" and ada["import_source"] == "csv"
    assert ada["rsvp_status"] == "pending" and ada["share_message"]
    assert marks_for(store, "ada@example.invalid") == {"day-1": "coming", "day-2": "coming"}
    assert marks_for(store, "bo@example.invalid") == {"day-1": "coming"}
    assert marks_for(store, "cy@example.invalid") == {}
    assert doc(store)["activity_rsvp_summaries"]["day-1"]["coming"] == 2


@pytest.mark.asyncio
async def test_rerunning_the_same_file_changes_nothing(store):
    await run_csv(CSV)
    before = deepcopy(doc(store))
    report = await run_csv(CSV)
    assert report["counts"] == {"created": 0, "updated": 0, "skipped": 3, "flagged": 0, "error": 0}
    after = doc(store)
    assert after["event_invites"] == before["event_invites"]
    assert after["activity_rsvps"] == before["activity_rsvps"]


@pytest.mark.asyncio
async def test_rerun_with_changed_sessions_updates_to_exactly_the_new_list(store):
    await run_csv(CSV)
    report = await run_csv("Name,Email,Sessions\nAda Example,ada@example.invalid,Closing Circle\n")
    assert report["counts"]["updated"] == 1
    assert marks_for(store, "ada@example.invalid") == {"closing": "coming"}
    assert len(doc(store)["event_invites"]) == 3


@pytest.mark.asyncio
async def test_import_never_overwrites_an_answer_the_person_gave(store):
    await run_csv(CSV)
    bo = invite_for(store, "bo@example.invalid")
    doc(store)["activity_rsvps"] = [
        r for r in doc(store)["activity_rsvps"] if r["respondent_id"] != f"invite:{bo['id']}"
    ] + [
        {
            "activity_id": "day-1",
            "respondent_id": f"invite:{bo['id']}",
            "status": "not-coming",
            "updated_at": iso(timedelta(0)),
            "via": "public-link",
        }
    ]
    report = await run_csv(CSV)
    bo_row = next(r for r in report["rows"] if r["email"] == "bo@example.invalid")
    assert bo_row["kept_own_answer"] == ["Day One Workshop"]
    assert marks_for(store, "bo@example.invalid") == {"day-1": "not-coming"}


@pytest.mark.asyncio
async def test_imported_marks_unlock_only_the_purchased_session_links(store):
    await run_csv(CSV)
    bo = invite_for(store, "bo@example.invalid")
    # A guest invite becomes a member later; the hub reads the same marks.
    doc(store)["event_invites"][1]["member_id"] = "bo-member"
    for row in doc(store)["activity_rsvps"]:
        if row["respondent_id"] == f"invite:{bo['id']}":
            row["respondent_id"] = "bo-member"
    hub = build_attendee_hub(
        doc(store),
        {"id": "bo-member", "role": "member", "email": "bo@example.invalid", "community_id": "community-1"},
        has_memory=False,
    )
    links = {a["id"]: a["virtual_link"] for a in hub["itinerary"]["activities"]}
    assert links["day-1"] == LINK_A
    assert links["day-2"] == ""


@pytest.mark.asyncio
async def test_existing_community_member_is_linked_by_email(store):
    await run_csv("Name,Email,Sessions\nWhoever,MEMBER@example.invalid,Day Two Workshop\n")
    invite = invite_for(store, "member@example.invalid")
    assert invite["member_id"] == "member-1"
    assert invite["invite_source"] == "member"
    assert invite["invitee_name"] == "Synthetic Member"
    assert marks_for(store, "member@example.invalid") == {"day-2": "coming"}


@pytest.mark.asyncio
async def test_row_errors_carry_row_numbers_and_do_not_block_other_rows(store):
    report = await run_csv(
        "Name,Email,Sessions\n"
        "Ada Example,ada@example.invalid,Day One Workshop\n"
        "Bad Email,nope,Day One Workshop\n"
        "Wrong Session,wrong@example.invalid,Day Nine\n"
    )
    assert report["counts"]["created"] == 1 and report["counts"]["error"] == 2
    errors = {r["row"]: r["code"] for r in report["rows"] if r["status"] == "error"}
    assert errors == {3: "invalid_email", 4: "unknown_session"}
    assert [i["email"] for i in doc(store)["event_invites"]] == ["ada@example.invalid"]


@pytest.mark.asyncio
async def test_import_can_send_through_the_shared_first_send_path(store):
    report = await run_csv(CSV, send=True)
    assert report["delivery"]["status"] == "processed"
    assert report["delivery"]["counts"]["submitted"] == 3
    assert sorted(store["provider"].sent) == [
        "ada@example.invalid",
        "bo@example.invalid",
        "cy@example.invalid",
    ]
    assert {row["kind"] for row in store["outbox"].docs} == {"first_send"}
    report = await run_csv(CSV, send=True)
    assert report["delivery"]["counts"]["submitted"] == 0
    assert report["delivery"]["counts"]["skipped"] == 3


@pytest.mark.asyncio
async def test_import_is_blocked_while_the_event_is_a_private_draft(store):
    doc(store)["publication_state"] = "organizer_draft"
    with pytest.raises(HTTPException) as exc:
        await run_csv(CSV)
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# K9 first half: possible duplicates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_name_different_email_is_flagged_not_duplicated(store):
    await run_csv(CSV)
    report = await run_csv(
        "Name,Email,Sessions\nada  EXAMPLE,ada.personal@example.invalid,Closing Circle\n"
    )
    assert report["counts"]["flagged"] == 1
    row = report["rows"][0]
    assert row["matched_email"] == "ada@example.invalid"
    assert report["pending_flags"] == 1
    assert len(doc(store)["event_invites"]) == 3
    flags = (await routes.list_registrant_flags("event-1", ORGANIZER))["flags"]
    assert flags[0]["status"] == "pending" and flags[0]["sessions"] == ["Closing Circle"]
    # Re-running keeps the single flag rather than piling up copies.
    await run_csv("Name,Email,Sessions\nAda Example,ada.personal@example.invalid,Closing Circle\n")
    assert len(store["flags"].docs) == 1


async def _flag_then_resolve(store, action, send=False):
    await run_csv(CSV)
    await run_csv("Name,Email,Sessions\nAda Example,ada.personal@example.invalid,Closing Circle\n")
    flag_id = store["flags"].docs[0]["id"]
    return await routes.resolve_registrant_flag(
        "event-1",
        flag_id,
        routes.RegistrantFlagResolveRequest(action=action, send_invitation=send),
        ORGANIZER,
    )


@pytest.mark.asyncio
async def test_resolving_as_separate_person_creates_the_invite(store):
    result = await _flag_then_resolve(store, "create_separate", send=True)
    assert result["row"]["status"] == "created"
    assert marks_for(store, "ada.personal@example.invalid") == {"closing": "coming"}
    assert store["provider"].sent == ["ada.personal@example.invalid"]
    report = await run_csv(
        "Name,Email,Sessions\nAda Example,ada.personal@example.invalid,Closing Circle\n"
    )
    assert report["counts"]["skipped"] == 1


@pytest.mark.asyncio
async def test_resolving_as_same_person_applies_sessions_to_the_existing_invitee(store):
    result = await _flag_then_resolve(store, "apply_to_existing")
    assert result["row"]["status"] == "updated"
    assert len(doc(store)["event_invites"]) == 3
    assert marks_for(store, "ada@example.invalid") == {"closing": "coming"}
    report = await run_csv(
        "Name,Email,Sessions\nAda Example,ada.personal@example.invalid,Closing Circle\n"
    )
    assert report["counts"]["skipped"] == 1 and report["counts"]["flagged"] == 0


@pytest.mark.asyncio
async def test_dismissed_flags_stay_dismissed_on_rerun(store):
    await _flag_then_resolve(store, "dismissed")
    report = await run_csv(
        "Name,Email,Sessions\nAda Example,ada.personal@example.invalid,Closing Circle\n"
    )
    assert report["rows"][0]["code"] == "duplicate_dismissed"
    assert len(doc(store)["event_invites"]) == 3


@pytest.mark.asyncio
async def test_a_flag_can_only_be_resolved_once(store):
    await _flag_then_resolve(store, "dismissed")
    with pytest.raises(HTTPException) as exc:
        await routes.resolve_registrant_flag(
            "event-1",
            store["flags"].docs[0]["id"],
            routes.RegistrantFlagResolveRequest(action="create_separate"),
            ORGANIZER,
        )
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    [
        lambda u: run_csv(CSV, user=u),
        lambda u: routes.list_registrant_flags("event-1", u),
        lambda u: routes.resolve_registrant_flag(
            "event-1", "any", routes.RegistrantFlagResolveRequest(action="dismissed"), u
        ),
        lambda u: routes.get_registrant_webhook("event-1", u),
        lambda u: routes.rotate_registrant_webhook("event-1", u),
    ],
)
async def test_organizer_routes_refuse_members_and_other_communities(store, call):
    with pytest.raises(HTTPException) as exc:
        await call(MEMBER)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await call(OTHER_ORGANIZER)
    assert exc.value.status_code == 404
    assert doc(store)["event_invites"] == []


@pytest.mark.asyncio
async def test_flags_are_scoped_to_the_event_and_community(store):
    store["flags"].docs.append(
        {"id": "foreign", "event_id": "event-1", "community_id": "community-2", "status": "pending", "email": "x@example.invalid"}
    )
    assert (await routes.list_registrant_flags("event-1", ORGANIZER))["flags"] == []
    with pytest.raises(HTTPException) as exc:
        await routes.resolve_registrant_flag(
            "event-1", "foreign", routes.RegistrantFlagResolveRequest(action="dismissed"), ORGANIZER
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Webhook: secret management and signed delivery
# ---------------------------------------------------------------------------


def test_signature_check_accepts_valid_and_refuses_tampered_or_stale():
    body = b'{"email":"a@example.invalid"}'
    ts = str(int(time.time()))
    good = compute_signature("secret-1", ts, body)
    assert verify_signature(secret="secret-1", timestamp=ts, signature=good, raw_body=body).ok
    assert verify_signature(secret="secret-2", timestamp=ts, signature=good, raw_body=body).code == "invalid_signature"
    assert verify_signature(secret="secret-1", timestamp=ts, signature=good, raw_body=body + b" ").code == "invalid_signature"
    old = str(int(time.time()) - 600)
    stale = compute_signature("secret-1", old, body)
    assert verify_signature(secret="secret-1", timestamp=old, signature=stale, raw_body=body).code == "stale_timestamp"
    assert verify_signature(secret="secret-1", timestamp="", signature=good, raw_body=body).code == "missing_signature"
    # Signing with both secrets during a rotation is allowed.
    both = compute_signature("old", ts, body) + "," + good
    assert verify_signature(secret="secret-1", timestamp=ts, signature=both, raw_body=body).ok


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: ORGANIZER
    return TestClient(app)


def _signed_post(client, path, payload, secret, *, ts=None, body=None):
    raw = body if body is not None else json.dumps(payload).encode()
    ts = ts or str(int(time.time()))
    return client.post(
        path,
        content=raw,
        headers={
            "Content-Type": "application/json",
            TIMESTAMP_HEADER: ts,
            SIGNATURE_HEADER: compute_signature(secret, ts, raw),
        },
    )


def test_organizer_creates_views_and_rotates_the_webhook_secret(client):
    assert client.get("/api/events/event-1/registrants/webhook").json() == {"configured": False}
    created = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    assert created["configured"] and created["secret"].startswith("kwhsec_")
    assert re.fullmatch(r"/api/inbound/registrants/[A-Za-z0-9_-]+", created["path"])
    assert "event-1" not in created["path"]
    assert client.get("/api/events/event-1/registrants/webhook").json()["secret"] == created["secret"]
    rotated = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    assert rotated["path"] == created["path"]
    assert rotated["secret"] != created["secret"]


def test_signed_webhook_creates_the_invite_marks_sessions_and_sends(client, store):
    hook = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    response = _signed_post(
        client,
        hook["path"],
        {"name": "Dee Example", "email": "Dee@Example.invalid", "sessions": ["Day Two Workshop"]},
        hook["secret"],
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "accepted",
        "result": "created",
        "sessions": ["Day Two Workshop"],
        "invitation": "sent",
    }
    assert invite_for(store, "dee@example.invalid")["import_source"] == "webhook"
    assert marks_for(store, "dee@example.invalid") == {"day-2": "coming"}
    assert store["provider"].sent == ["dee@example.invalid"]
    # A fresh, correctly signed repeat is idempotent and does not re-send.
    again = _signed_post(
        client,
        hook["path"],
        {"name": "Dee Example", "email": "dee@example.invalid", "sessions": "Day Two Workshop"},
        hook["secret"],
        ts=str(int(time.time()) + 1),
    )
    assert again.json()["result"] == "skipped"
    assert again.json()["invitation"] == "already_sent"
    assert store["provider"].sent == ["dee@example.invalid"]


def test_webhook_refuses_bad_signature_old_secret_unknown_hook_and_stale_time(client, store):
    hook = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    payload = {"email": "eve@example.invalid", "sessions": []}
    assert _signed_post(client, hook["path"], payload, "kwhsec_wrong").status_code == 401
    rotated = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    assert _signed_post(client, hook["path"], payload, hook["secret"]).status_code == 401
    assert _signed_post(client, "/api/inbound/registrants/nope", payload, rotated["secret"]).status_code == 401
    stale = str(int(time.time()) - 3600)
    response = _signed_post(client, hook["path"], payload, rotated["secret"], ts=stale)
    assert response.status_code == 401 and response.json()["code"] == "stale_timestamp"
    unsigned = client.post(hook["path"], json=payload)
    assert unsigned.status_code == 401
    assert doc(store)["event_invites"] == []


def test_webhook_refuses_a_replayed_request(client, store):
    hook = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    raw = json.dumps({"email": "fay@example.invalid"}).encode()
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: compute_signature(hook["secret"], ts, raw),
    }
    assert client.post(hook["path"], content=raw, headers=headers).status_code == 200
    replay = client.post(hook["path"], content=raw, headers=headers)
    assert replay.status_code == 409 and replay.json()["code"] == "replayed"
    assert len(doc(store)["event_invites"]) == 1


def test_webhook_validates_the_payload(client):
    hook = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    bad_json = _signed_post(client, hook["path"], None, hook["secret"], body=b"{not json")
    assert bad_json.status_code == 400
    no_email = _signed_post(client, hook["path"], {"name": "Gus"}, hook["secret"])
    assert no_email.status_code == 422
    unknown = _signed_post(
        client, hook["path"], {"email": "gus@example.invalid", "sessions": ["Day Nine"]}, hook["secret"]
    )
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_session"
    too_big = _signed_post(
        client, hook["path"], {"email": "gus@example.invalid", "pad": "x" * 20_000}, hook["secret"]
    )
    assert too_big.status_code == 413


def test_webhook_flags_a_possible_duplicate_and_sends_nothing(client, store):
    hook = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    _signed_post(client, hook["path"], {"name": "Hal Example", "email": "hal@example.invalid"}, hook["secret"])
    response = _signed_post(
        client,
        hook["path"],
        {"name": "Hal Example", "email": "hal.work@example.invalid"},
        hook["secret"],
        ts=str(int(time.time()) + 1),
    )
    assert response.json()["result"] == "flagged"
    assert response.json()["invitation"] == "not_requested"
    assert store["provider"].sent == ["hal@example.invalid"]
    assert store["flags"].docs[0]["source"] == "webhook"


def test_webhook_reports_delivery_off_without_failing(client, store, monkeypatch):
    monkeypatch.setattr(routes, "first_send_enabled", lambda: False)
    hook = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    response = _signed_post(client, hook["path"], {"email": "ivy@example.invalid"}, hook["secret"])
    assert response.status_code == 200
    assert response.json()["invitation"] == "delivery_disabled"
    assert invite_for(store, "ivy@example.invalid")


def test_webhook_for_a_draft_event_is_refused_and_can_be_retried(client, store):
    hook = client.post("/api/events/event-1/registrants/webhook/rotate").json()
    doc(store)["publication_state"] = "organizer_draft"
    raw = json.dumps({"email": "jo@example.invalid"}).encode()
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: compute_signature(hook["secret"], ts, raw),
    }
    assert client.post(hook["path"], content=raw, headers=headers).status_code == 409
    doc(store)["publication_state"] = "published"
    assert client.post(hook["path"], content=raw, headers=headers).status_code == 200


@pytest.mark.asyncio
async def test_a_failed_resolution_leaves_the_flag_pending(store, monkeypatch):
    await run_csv(CSV)
    await run_csv("Name,Email,Sessions\nAda Example,ada.personal@example.invalid,Closing Circle\n")
    flag_id = store["flags"].docs[0]["id"]

    async def conflict(**_kwargs):
        raise HTTPException(status_code=409, detail={"code": "rsvp_write_conflict"})

    monkeypatch.setattr(routes, "run_registrant_import", conflict)
    with pytest.raises(HTTPException):
        await routes.resolve_registrant_flag(
            "event-1", flag_id, routes.RegistrantFlagResolveRequest(action="create_separate"), ORGANIZER
        )
    assert store["flags"].docs[0]["status"] == "pending"
