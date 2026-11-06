"""K6 per-activity materials: a supply list and PDF/image files per activity.

- The supply list and files reach only people who answered "coming" for that
  activity, plus organizers and the event's planning team. Everyone else sees
  "Materials shared with registered attendees." That's the same rule as the
  K4 virtual link.
- Uploads are typed by their own bytes (PDF, PNG, JPEG, GIF, WebP only),
  capped at 5 MB and 10 per activity, and get a safe download name.
- Downloads answer 404 for "no such file" and "not for you" alike.
- Removing an activity or an event removes its stored files.
"""

from __future__ import annotations

import base64
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_k6_materials_unit")

import activity_materials  # noqa: E402
from activity_materials import (  # noqa: E402
    MAX_MATERIAL_BYTES,
    MAX_MATERIALS_PER_ACTIVITY,
    content_disposition,
    safe_material_name,
    sniff_material_type,
    validate_material_upload,
)
from attendee_hub import build_attendee_hub  # noqa: E402
from event_privacy import (  # noqa: E402
    serialize_event_for_guest,
    serialize_event_for_user,
)
from itinerary import MATERIALS_WITHHELD_NOTICE, normalize_activity  # noqa: E402
from models import ActivityMaterialUploadRequest, AgendaItemRequest  # noqa: E402
from routes import events as event_routes  # noqa: E402
from routes import public as public_routes  # noqa: E402

NOW = datetime.now(timezone.utc)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SUPPLIES = "Bring a folding chair and a dish to share."


def iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


def data_url(raw: bytes, mime: str = "application/octet-stream") -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


MEMBER = {
    "id": "member-1",
    "community_id": "community-1",
    "role": "member",
    "full_name": "Synthetic Member",
    "email": "member@example.invalid",
}
ORGANIZER = {**MEMBER, "id": "organizer-1", "role": "organizer", "full_name": "Organizer"}
PLANNER = {**MEMBER, "id": "planner-1", "full_name": "Planning Team Member"}
GUEST_INVITE = {
    "id": "guest-token-1",
    "invitee_name": "Synthetic Guest",
    "invite_source": "guest",
    "rsvp_status": "going",
}
MATERIAL = {
    "id": "material-1",
    "activity_id": "session-a",
    "name": "map.pdf",
    "mime_type": "application/pdf",
    "size": len(PDF),
    "uploaded_by": ORGANIZER["id"],
    "created_at": "2026-11-01T00:00:00+00:00",
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
        "supply_list": SUPPLIES,
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
        "created_by": ORGANIZER["id"],
        "agenda": [session(), session("session-b", supply_list="")],
        "activity_materials": [dict(MATERIAL)],
        "activity_rsvps": [],
        "rsvp_records": [],
        "event_invites": [dict(GUEST_INVITE)],
        "planning_team_member_ids": [PLANNER["id"]],
        "potluck_items": [],
        "volunteer_slots": [],
    }
    base.update(overrides)
    return base


def response(respondent_id, status, activity_id="session-a"):
    return {
        "activity_id": activity_id,
        "respondent_id": respondent_id,
        "status": status,
        "choice": "",
        "party_size": 1,
        "updated_at": "2026-11-01T00:00:00+00:00",
    }


def member_activity(event_doc, user, activity_id="session-a"):
    view = serialize_event_for_user(event_doc, user)
    return next(a for a in view["agenda"] if a["id"] == activity_id)


def guest_activity(event_doc, activity_id="session-a"):
    view = serialize_event_for_guest(event_doc, GUEST_INVITE)
    return next(a for a in view["gathering"]["activities"] if a["id"] == activity_id)


def hub_activity(event_doc, user, activity_id="session-a"):
    hub = build_attendee_hub(event_doc, user, has_memory=False)
    return next(a for a in hub["itinerary"]["activities"] if a["id"] == activity_id)


def assert_withheld(activity):
    assert activity["supply_list"] == ""
    assert activity["materials"] == []
    assert activity["materials_withheld"] is True
    assert activity["materials_notice"] == MATERIALS_WITHHELD_NOTICE


def assert_shared(activity):
    assert activity["supply_list"] == SUPPLIES
    assert [m["id"] for m in activity["materials"]] == ["material-1"]
    assert activity["materials_withheld"] is False


# ---------------------------------------------------------------------------
# Who sees the supply list and files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["", "maybe", "not-coming"])
def test_member_not_coming_sees_notice_not_materials(status):
    rows = [response(MEMBER["id"], status)] if status else []
    doc = event(activity_rsvps=rows)
    assert_withheld(member_activity(doc, MEMBER))
    assert_withheld(hub_activity(doc, MEMBER))


def test_member_coming_sees_supply_list_and_files():
    doc = event(activity_rsvps=[response(MEMBER["id"], "coming")])
    assert_shared(member_activity(doc, MEMBER))
    assert_shared(hub_activity(doc, MEMBER))


def test_coming_to_one_activity_does_not_unlock_another():
    doc = event(
        activity_rsvps=[response(MEMBER["id"], "coming", activity_id="session-b")],
        activity_materials=[dict(MATERIAL)],
    )
    assert_withheld(member_activity(doc, MEMBER, "session-a"))


def test_organizer_and_planning_team_always_see_materials():
    doc = event()
    organizer_view = member_activity(doc, ORGANIZER)
    assert organizer_view["supply_list"] == SUPPLIES
    assert [m["id"] for m in organizer_view["materials"]] == ["material-1"]
    assert_shared(member_activity(doc, PLANNER))


def test_activity_without_materials_shows_no_notice():
    activity = member_activity(event(), MEMBER, "session-b")
    assert activity["materials_withheld"] is False
    assert activity["materials_notice"] == ""


def test_guest_follows_their_own_answer():
    assert_withheld(guest_activity(event()))
    doc = event(activity_rsvps=[response("invite:guest-token-1", "coming")])
    assert_shared(guest_activity(doc))


def test_raw_material_records_never_reach_members_or_guests():
    doc = event(activity_rsvps=[response(MEMBER["id"], "coming")])
    assert "activity_materials" not in serialize_event_for_user(doc, MEMBER)
    assert "activity_materials" not in serialize_event_for_user(doc, ORGANIZER)
    guest = serialize_event_for_guest(doc, GUEST_INVITE)
    assert "activity_materials" not in guest
    assert "uploaded_by" not in str(guest)


def test_draft_activity_materials_stay_hidden_from_members():
    doc = event(agenda=[session(visibility="draft")])
    assert serialize_event_for_user(doc, MEMBER)["agenda"] == []


# ---------------------------------------------------------------------------
# Supply list storage
# ---------------------------------------------------------------------------


def test_supply_list_is_normalized_and_capped():
    activity = normalize_activity({"supply_list": "  x" * 3000}, activity_id="a")
    assert len(activity["supply_list"]) == 4000
    assert normalize_activity({}, activity_id="a")["supply_list"] == ""


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, mime",
    [
        (PDF, "application/pdf"),
        (PNG, "image/png"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 8, "image/jpeg"),
        (b"GIF89a" + b"\x00" * 8, "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
    ],
)
def test_allowed_types_are_recognized_by_their_bytes(raw, mime):
    assert sniff_material_type(raw) == mime


def test_type_comes_from_bytes_not_the_claimed_name_or_mime():
    html = b"<html><script>alert(1)</script></html>"
    with pytest.raises(HTTPException) as exc:
        validate_material_upload("map.pdf", data_url(html, "application/pdf"))
    assert exc.value.status_code == 415
    _data, mime, name = validate_material_upload("photo.html", data_url(PNG, "text/html"))
    assert mime == "image/png" and name == "photo.png"


def test_upload_is_capped_at_five_megabytes():
    with pytest.raises(HTTPException) as exc:
        validate_material_upload("big.pdf", data_url(PDF + b"0" * MAX_MATERIAL_BYTES))
    assert exc.value.status_code == 413


@pytest.mark.parametrize("bad", ["", "data:application/pdf,%PDF-plain", "not base64 !!"])
def test_unreadable_uploads_are_rejected(bad):
    with pytest.raises(HTTPException) as exc:
        validate_material_upload("x.pdf", bad)
    assert exc.value.status_code == 400


def test_download_names_are_safe():
    assert safe_material_name("../../etc/passwd", "application/pdf") == "passwd.pdf"
    assert safe_material_name('C:\\Users\\a\\"map".PDF', "application/pdf") == "map.pdf"
    assert safe_material_name("", "image/png") == "material.png"
    assert len(safe_material_name("a" * 500, "image/png")) <= 120
    header = content_disposition("Plan d'accès.pdf")
    assert header.startswith('attachment; filename="Plan d\'accs.pdf"')
    assert "filename*=UTF-8''Plan%20d%27acc%C3%A8s.pdf" in header


# ---------------------------------------------------------------------------
# Routes, against small in-memory collections
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, matched):
        self.matched_count = matched
        self.modified_count = matched


class _EventCollection:
    def __init__(self, doc):
        self.doc = deepcopy(doc)

    async def find_one(self, query, _projection=None):
        return deepcopy(self.doc) if query.get("id") == self.doc["id"] else None

    async def update_one(self, query, update):
        if query.get("id") != self.doc["id"]:
            return _Result(0)
        if "agenda.id" in query and not any(
            a.get("id") == query["agenda.id"] for a in self.doc.get("agenda", [])
        ):
            return _Result(0)
        for key, cond in query.items():
            if key.startswith("activity_materials.") and cond == {"$exists": False}:
                index = int(key.split(".", 1)[1])
                if len(self.doc.get("activity_materials") or []) > index:
                    return _Result(0)
        self.doc.update(deepcopy(update.get("$set", {})))
        for field, value in (update.get("$push") or {}).items():
            self.doc.setdefault(field, []).append(deepcopy(value))
        for field, match in (update.get("$pull") or {}).items():
            self.doc[field] = [
                row
                for row in self.doc.get(field) or []
                if not all(row.get(k) == v for k, v in match.items())
            ]
        return _Result(1)

    async def delete_one(self, _query):
        return _Result(1)


class _FileCollection:
    def __init__(self):
        self.rows = []

    def _match(self, row, query):
        return all(row.get(k) == v for k, v in query.items())

    async def insert_one(self, row):
        self.rows.append(deepcopy(row))

    async def find_one(self, query, _projection=None):
        return next((deepcopy(r) for r in self.rows if self._match(r, query)), None)

    async def delete_one(self, query):
        for index, row in enumerate(self.rows):
            if self._match(row, query):
                del self.rows[index]
                return _Result(1)
        return _Result(0)

    async def delete_many(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not self._match(r, query)]
        return _Result(before - len(self.rows))


@pytest.fixture
def routes(monkeypatch):
    def install(doc):
        events = _EventCollection(doc)
        files = _FileCollection()

        async def event_for_user(_event_id, _user):
            return deepcopy(events.doc)

        async def find_event_and_invite(token):
            current = deepcopy(events.doc)
            invite = next((i for i in current["event_invites"] if i["id"] == token), None)
            return current, invite

        monkeypatch.setattr(event_routes, "events_collection", events)
        monkeypatch.setattr(event_routes, "activity_material_files_collection", files)
        monkeypatch.setattr(event_routes, "get_event_for_user", event_for_user)
        monkeypatch.setattr(public_routes, "_find_event_and_invite", find_event_and_invite)
        return events, files

    return install


async def _upload(name="Site map.pdf", raw=PDF, activity_id="session-a", user=ORGANIZER):
    return await event_routes.add_activity_material(
        "event-1",
        activity_id,
        ActivityMaterialUploadRequest(name=name, data_url=data_url(raw)),
        user,
    )


async def _download(material_id, user=MEMBER):
    return await event_routes.download_activity_material("event-1", material_id, user)


@pytest.mark.asyncio
async def test_organizer_uploads_and_coming_member_downloads(routes):
    events, files = routes(event(activity_materials=[]))
    view = await _upload()
    material = next(a for a in view["agenda"] if a["id"] == "session-a")["materials"][0]
    assert material["name"] == "Site map.pdf" and material["mime_type"] == "application/pdf"
    assert files.rows[0]["data"] == PDF

    events.doc["activity_rsvps"] = [response(MEMBER["id"], "coming")]
    reply = await _download(material["id"])
    assert reply.body == PDF
    assert reply.media_type == "application/pdf"
    assert reply.headers["content-disposition"].startswith("attachment;")
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in reply.headers["cache-control"]


@pytest.mark.asyncio
async def test_member_upload_is_refused(routes):
    routes(event(activity_materials=[]))
    with pytest.raises(HTTPException) as exc:
        await _upload(user=MEMBER)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_upload_to_unknown_activity_is_404(routes):
    routes(event(activity_materials=[]))
    with pytest.raises(HTTPException) as exc:
        await _upload(activity_id="nope")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_per_activity_limit(routes):
    full = [
        {**MATERIAL, "id": f"m-{i}"} for i in range(MAX_MATERIALS_PER_ACTIVITY)
    ]
    _events, files = routes(event(activity_materials=full))
    with pytest.raises(HTTPException) as exc:
        await _upload()
    assert exc.value.status_code == 409
    assert files.rows == []


@pytest.mark.asyncio
async def test_event_wide_limit_rolls_back_the_stored_bytes(routes, monkeypatch):
    monkeypatch.setattr(event_routes, "MAX_MATERIALS_PER_EVENT", 1)
    _events, files = routes(event())  # already holds one file
    with pytest.raises(HTTPException) as exc:
        await _upload(activity_id="session-b")
    assert exc.value.status_code == 409
    assert files.rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "maybe", "not-coming"])
async def test_download_is_404_unless_coming(routes, status):
    events, files = routes(event(activity_materials=[]))
    view = await _upload()
    material_id = view["agenda"][0]["materials"][0]["id"]
    if status:
        events.doc["activity_rsvps"] = [response(MEMBER["id"], status)]
    with pytest.raises(HTTPException) as exc:
        await _download(material_id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unknown_and_withheld_files_answer_alike(routes):
    routes(event(activity_materials=[]))
    with pytest.raises(HTTPException) as unknown:
        await _download("no-such-file")
    view = await _upload()
    with pytest.raises(HTTPException) as withheld:
        await _download(view["agenda"][0]["materials"][0]["id"])
    assert unknown.value.status_code == withheld.value.status_code == 404
    assert unknown.value.detail == withheld.value.detail


@pytest.mark.asyncio
async def test_draft_activity_file_is_hidden_from_coming_members(routes):
    events, _files = routes(event(activity_materials=[]))
    view = await _upload()
    material_id = view["agenda"][0]["materials"][0]["id"]
    events.doc["activity_rsvps"] = [response(MEMBER["id"], "coming")]
    events.doc["agenda"][0]["visibility"] = "draft"
    with pytest.raises(HTTPException):
        await _download(material_id)
    assert (await _download(material_id, ORGANIZER)).body == PDF


@pytest.mark.asyncio
async def test_planning_team_downloads_without_answering(routes):
    routes(event(activity_materials=[]))
    view = await _upload()
    reply = await _download(view["agenda"][0]["materials"][0]["id"], PLANNER)
    assert reply.body == PDF


@pytest.mark.asyncio
async def test_guest_download_follows_their_answer(routes):
    events, _files = routes(event(activity_materials=[]))
    view = await _upload()
    material_id = view["agenda"][0]["materials"][0]["id"]
    with pytest.raises(HTTPException) as exc:
        await public_routes.secure_public_material_download(
            material_id, authorization="Bearer guest-token-1"
        )
    assert exc.value.status_code == 404
    events.doc["activity_rsvps"] = [response("invite:guest-token-1", "coming")]
    reply = await public_routes.secure_public_material_download(
        material_id, authorization="Bearer guest-token-1"
    )
    assert reply.body == PDF


@pytest.mark.asyncio
async def test_guest_download_needs_a_header_token(routes):
    routes(event())
    with pytest.raises(HTTPException) as exc:
        await public_routes.secure_public_material_download("material-1", authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_organizer_removes_one_file(routes):
    events, files = routes(event(activity_materials=[]))
    view = await _upload()
    material_id = view["agenda"][0]["materials"][0]["id"]
    view = await event_routes.delete_activity_material(
        "event-1", "session-a", material_id, ORGANIZER
    )
    assert view["agenda"][0]["materials"] == []
    assert events.doc["activity_materials"] == [] and files.rows == []


@pytest.mark.asyncio
async def test_removing_an_activity_removes_its_files(routes):
    events, files = routes(event(activity_materials=[]))
    await _upload()
    await _upload(activity_id="session-b")
    await event_routes.delete_agenda_activity("event-1", "session-a", False, ORGANIZER)
    assert [r["activity_id"] for r in files.rows] == ["session-b"]
    assert [m["activity_id"] for m in events.doc["activity_materials"]] == ["session-b"]


@pytest.mark.asyncio
async def test_removing_an_event_removes_its_files(routes, monkeypatch):
    events, files = routes(event(activity_materials=[]))
    await _upload()

    async def delete_event_doc(_query):
        return _Result(1)

    monkeypatch.setattr(events, "delete_one", delete_event_doc)
    await event_routes.delete_event("event-1", ORGANIZER)
    assert files.rows == []


@pytest.mark.asyncio
async def test_older_client_edit_keeps_the_supply_list(routes):
    events, _files = routes(event())
    payload = AgendaItemRequest(
        title="Session session-a",
        start_at=events.doc["agenda"][0]["start_at"],
        end_at=events.doc["agenda"][0]["end_at"],
        timezone="UTC",
        visibility="published",
    )
    await event_routes.update_agenda_activity("event-1", "session-a", payload, ORGANIZER)
    assert events.doc["agenda"][0]["supply_list"] == SUPPLIES
    payload.supply_list = ""
    await event_routes.update_agenda_activity("event-1", "session-a", payload, ORGANIZER)
    edited = next(a for a in events.doc["agenda"] if a["id"] == "session-a")
    assert edited["supply_list"] == ""


def test_module_exports_are_stable():
    assert activity_materials.MAX_MATERIALS_PER_ACTIVITY == 10
