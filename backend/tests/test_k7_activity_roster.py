"""K7 organizer view per activity.

- Every registered person (active invitation) appears for every activity, with
  "no-response" until they answer; people who answered without a current
  invitation appear too, marked unregistered.
- Counts, expected turnout (coming party sizes) and possible turnout (coming +
  maybe) per activity.
- People still marked "coming" for an activity that has ended are flagged.
- CSV export, one row per person per activity, safe against spreadsheet
  formulas. Organizer-only.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_k7_roster_unit")

from organizer_command_center import (  # noqa: E402
    CSV_COLUMNS,
    ENDED_STILL_COMING,
    activity_roster,
    activity_roster_csv,
    canonical_response_summary,
)
from routes import organizer as organizer_routes  # noqa: E402

NOW = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)


def iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


def invite(invite_id, name, email, **extra):
    return {
        "id": invite_id,
        "invitee_name": name,
        "email": email,
        "invite_source": "guest",
        "rsvp_status": "pending",
        "created_at": "2026-11-01T00:00:00+00:00",
        **extra,
    }


def answer(respondent_id, status, activity_id="later", party_size=1, at="2026-11-02T00:00:00+00:00", **extra):
    return {
        "activity_id": activity_id,
        "respondent_id": respondent_id,
        "status": status,
        "party_size": party_size,
        "updated_at": at,
        **extra,
    }


def event(**overrides):
    base = {
        "id": "event-1",
        "timezone": "UTC",
        "agenda": [
            {
                "id": "earlier",
                "title": "Opening circle",
                "start_at": iso(timedelta(hours=-4)),
                "end_at": iso(timedelta(hours=-2)),
                "visibility": "published",
            },
            {
                "id": "later",
                "title": "Evening meal",
                "start_at": iso(timedelta(days=1)),
                "end_at": iso(timedelta(days=1, hours=2)),
                "visibility": "published",
                "capacity": 40,
            },
            {"id": "gone", "title": "Removed", "visibility": "archived"},
        ],
        "event_invites": [
            invite("inv-a", "Ada Guest", "ADA@example.invalid"),
            invite("inv-b", "Bea Guest", "bea@example.invalid"),
            invite("inv-m", "Member Person", "member@example.invalid", invite_source="member", member_id="member-1"),
            invite("inv-x", "Revoked Person", "x@example.invalid", revoked_at="2026-11-03T00:00:00+00:00"),
        ],
        "activity_rsvps": [],
        "rsvp_records": [],
    }
    base.update(overrides)
    return base


def roster_activity(roster, activity_id):
    return next(a for a in roster["activities"] if a["id"] == activity_id)


def person(activity, name):
    return next(p for p in activity["people"] if p["name"] == name)


# ---------------------------------------------------------------------------
# Roster contents
# ---------------------------------------------------------------------------


def test_every_registered_person_appears_for_every_activity():
    roster = activity_roster(event(), now=NOW)
    assert roster["registered"] == 3  # the revoked invitation does not count
    assert [a["id"] for a in roster["activities"]] == ["earlier", "later"]  # archived dropped
    later = roster_activity(roster, "later")
    assert {p["name"] for p in later["people"]} == {"Ada Guest", "Bea Guest", "Member Person"}
    assert later["counts"] == {"coming": 0, "maybe": 0, "not-coming": 0, "no-response": 3}


def test_answers_counts_and_turnout():
    doc = event(
        activity_rsvps=[
            answer("invite:inv-a", "coming", party_size=3, choice="In person"),
            answer("invite:inv-b", "maybe", party_size=2),
            answer("member-1", "not-coming", party_size=4),
        ]
    )
    later = roster_activity(activity_roster(doc, now=NOW), "later")
    assert later["counts"] == {"coming": 1, "maybe": 1, "not-coming": 1, "no-response": 0}
    assert later["expected_turnout"] == 3
    assert later["possible_turnout"] == 5
    ada = person(later, "Ada Guest")
    assert ada["choice"] == "In person" and ada["party_size"] == 3
    assert person(later, "Member Person")["party_size"] == 0
    assert [p["status"] for p in later["people"]] == ["coming", "maybe", "not-coming"]


def test_latest_answer_wins_and_member_aliases_merge():
    doc = event(
        activity_rsvps=[
            answer("invite:inv-m", "coming", at="2026-11-02T00:00:00+00:00"),
            answer("member-1", "not-coming", at="2026-11-05T00:00:00+00:00"),
        ]
    )
    later = roster_activity(activity_roster(doc, now=NOW), "later")
    members = [p for p in later["people"] if p["name"] == "Member Person"]
    assert len(members) == 1 and members[0]["status"] == "not-coming"


def test_member_matched_by_email_merges_with_their_answers():
    doc = event(
        event_invites=[invite("inv-e", "Email Member", "Member@Example.invalid", invite_source="member")],
        activity_rsvps=[answer("member-9", "coming")],
    )
    roster = activity_roster(doc, member_ids_by_email={"member@example.invalid": "member-9"}, now=NOW)
    later = roster_activity(roster, "later")
    assert len(later["people"]) == 1
    assert later["people"][0]["status"] == "coming" and later["people"][0]["registered"] is True


def test_answers_without_a_current_invitation_show_as_unregistered():
    doc = event(activity_rsvps=[answer("invite:inv-x", "coming", display_name="Revoked Person")])
    later = roster_activity(activity_roster(doc, now=NOW), "later")
    revoked = person(later, "Revoked Person")
    assert revoked["registered"] is False and revoked["status"] == "coming"
    assert later["registered"] == 3


def test_people_still_coming_to_an_ended_activity_are_flagged():
    doc = event(
        activity_rsvps=[
            answer("invite:inv-a", "coming", activity_id="earlier"),
            answer("invite:inv-b", "maybe", activity_id="earlier"),
            answer("invite:inv-a", "coming", activity_id="later"),
        ]
    )
    roster = activity_roster(doc, now=NOW)
    earlier = roster_activity(roster, "earlier")
    assert earlier["ended"] is True and earlier["ended_still_coming"] == 1
    assert person(earlier, "Ada Guest")["flags"] == [ENDED_STILL_COMING]
    assert person(earlier, "Bea Guest")["flags"] == []
    assert person(roster_activity(roster, "later"), "Ada Guest")["flags"] == []
    assert roster["ended_still_coming"] == 1


def test_ended_uses_the_activity_timezone():
    # 10:00 in Los Angeles is 18:00 UTC: ending at 09:30 local has passed.
    activity = {
        "id": "la",
        "title": "Breakfast",
        "start_at": "2026-11-20T08:00",
        "end_at": "2026-11-20T09:30",
        "timezone": "America/Los_Angeles",
        "visibility": "published",
    }
    later_local = {**activity, "id": "la-late", "end_at": "2026-11-20T10:30"}
    roster = activity_roster(event(agenda=[activity, later_local]), now=NOW)
    assert roster_activity(roster, "la")["ended"] is True
    assert roster_activity(roster, "la-late")["ended"] is False


def test_rows_carry_no_emails_or_invitation_tokens():
    roster = activity_roster(event(), now=NOW)
    for activity in roster["activities"]:
        for row in activity["people"]:
            assert "inv-" not in row["row_key"] and "member-1" not in row["row_key"]
            assert "email" not in row
    assert "example.invalid" not in str(roster)
    assert "example.invalid" not in activity_roster_csv(roster)


def test_registered_count_matches_the_command_center():
    doc = event()
    assert activity_roster(doc, now=NOW)["registered"] == canonical_response_summary(doc, now=NOW)["total"]


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def parse(text):
    return list(csv.reader(io.StringIO(text)))


def test_csv_has_one_row_per_person_per_activity():
    doc = event(activity_rsvps=[answer("invite:inv-a", "coming", activity_id="earlier")])
    rows = parse(activity_roster_csv(activity_roster(doc, now=NOW)))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert len(rows) == 1 + 3 * 2
    ada = next(r for r in rows[1:] if r[0] == "Opening circle" and r[3] == "Ada Guest")
    assert ada[2] == "yes" and ada[5] == "coming" and ada[9] == ENDED_STILL_COMING


def test_csv_can_be_limited_to_one_activity():
    rows = parse(activity_roster_csv(activity_roster(event(), now=NOW), "later"))
    assert {r[0] for r in rows[1:]} == {"Evening meal"}


@pytest.mark.parametrize("hostile", ["=HYPERLINK(\"http://x\")", "+1", "-2", "@SUM(A1)", "\tx"])
def test_csv_neutralizes_formulas(hostile):
    doc = event(event_invites=[invite("inv-a", hostile, "a@example.invalid")])
    rows = parse(activity_roster_csv(activity_roster(doc, now=NOW)))
    assert all(r[3] == f"'{hostile}" for r in rows[1:])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.fixture
def routes(monkeypatch):
    def install(doc, role="organizer"):
        async def organizer_reunion(_event_id, user):
            if user.get("role") not in {"host", "organizer"}:
                raise HTTPException(status_code=403, detail="Organizer access required.")
            return doc

        async def context(_event, _user):
            return {"member_ids_by_email": {}}

        monkeypatch.setattr(organizer_routes, "_organizer_reunion", organizer_reunion)
        monkeypatch.setattr(organizer_routes, "_command_center_context", context)

    return install


ORGANIZER = {"id": "org-1", "role": "organizer", "community_id": "c-1"}
MEMBER = {"id": "member-1", "role": "member", "community_id": "c-1"}


@pytest.mark.asyncio
async def test_roster_route_is_organizer_only(routes):
    routes(event())
    with pytest.raises(HTTPException) as exc:
        await organizer_routes.organizer_activity_roster("event-1", MEMBER)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        await organizer_routes.organizer_activity_roster_csv("event-1", "", MEMBER)


@pytest.mark.asyncio
async def test_roster_route_returns_people(routes):
    routes(event())
    roster = await organizer_routes.organizer_activity_roster("event-1", ORGANIZER)
    assert roster["registered"] == 3


@pytest.mark.asyncio
async def test_csv_route_headers_and_bom(routes):
    routes(event())
    reply = await organizer_routes.organizer_activity_roster_csv("event-1", "later", ORGANIZER)
    assert reply.media_type.startswith("text/csv")
    assert reply.headers["content-disposition"] == 'attachment; filename="activity-roster.csv"'
    assert "no-store" in reply.headers["cache-control"]
    text = reply.body.decode("utf-8")
    assert text.startswith("﻿")
    assert parse(text.lstrip("﻿"))[0] == list(CSV_COLUMNS)


@pytest.mark.asyncio
async def test_csv_route_unknown_activity_is_404(routes):
    routes(event())
    with pytest.raises(HTTPException) as exc:
        await organizer_routes.organizer_activity_roster_csv("event-1", "nope", ORGANIZER)
    assert exc.value.status_code == 404
