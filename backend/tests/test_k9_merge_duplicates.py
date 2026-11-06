"""K9 second half: review possible duplicates and merge them.

- Possible duplicates: active invitations sharing a normalized email or name
  (or one account holding two invitations). "Not the same person" is
  remembered per pair.
- Merge keeps one invitation and folds the other in: event and activity
  answers move to the kept person (newest wins on overlap), an account link
  moves with them (so potluck, volunteer and memory contributions, which are
  keyed by account, follow), and the merged invitation is retired with
  ``merged_into``. Its old link opens the kept invitation; a later import of
  its email lands on the kept invitation.
- Two invitations linked to two different accounts are refused.
"""

from __future__ import annotations

import os
from copy import deepcopy

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_k9_merge_unit")

from duplicate_merge import (  # noqa: E402
    REASON_SAME_EMAIL,
    REASON_SAME_NAME,
    MergeError,
    dismiss_pair,
    merge_invitations,
    pair_key,
    possible_duplicates,
    resolve_merged_invite,
)
from event_privacy import serialize_event_for_user  # noqa: E402
from itinerary import activity_summaries  # noqa: E402
from organizer_command_center import canonical_response_summary  # noqa: E402
from registrant_import import Registrant, apply_registrants  # noqa: E402
from routes import public as public_routes  # noqa: E402
from routes import registrants as registrant_routes  # noqa: E402

NOW = "2026-11-10T00:00:00+00:00"


def invite(invite_id, name, email, created="2026-11-01T00:00:00+00:00", **extra):
    return {
        "id": invite_id,
        "invitee_name": name,
        "email": email,
        "invite_source": "guest",
        "rsvp_status": "pending",
        "guests": 0,
        "created_at": created,
        **extra,
    }


def answer(respondent, status, activity="a1", at="2026-11-02T00:00:00+00:00", **extra):
    return {"activity_id": activity, "respondent_id": respondent, "status": status,
            "party_size": 1, "updated_at": at, **extra}


def event(**overrides):
    base = {
        "id": "event-1",
        "community_id": "c-1",
        "timezone": "UTC",
        "agenda": [
            {"id": "a1", "title": "Opening", "start_at": "2026-12-01T10:00", "end_at": "2026-12-01T11:00", "visibility": "published"},
            {"id": "a2", "title": "Meal", "start_at": "2026-12-01T18:00", "end_at": "2026-12-01T20:00", "visibility": "published"},
        ],
        "event_invites": [
            invite("inv-old", "Ada  Guest", "ada@work.invalid"),
            invite("inv-new", "ada guest", "ada@home.invalid", created="2026-11-05T00:00:00+00:00"),
            invite("inv-other", "Bea Guest", "bea@example.invalid"),
        ],
        "rsvp_records": [],
        "activity_rsvps": [],
        "potluck_items": [],
        "volunteer_slots": [],
    }
    base.update(overrides)
    return base


def merge(doc, keep="inv-old", drop="inv-new"):
    updates, report = merge_invitations(doc, keep_invite_id=keep, merge_invite_id=drop, actor_id="org-1", now=NOW)
    merged = {**deepcopy(doc), **updates}
    return merged, report


def by_id(doc, invite_id):
    return next(i for i in doc["event_invites"] if i["id"] == invite_id)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_same_name_different_email_is_a_possible_duplicate():
    pairs = possible_duplicates(event())
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["reason"] == REASON_SAME_NAME
    assert [p["invite_id"] for p in pair["people"]] == ["inv-old", "inv-new"]
    assert pair["suggested_keep_invite_id"] == "inv-old"
    assert pair["pair_key"] == pair_key("inv-new", "inv-old")


def test_same_email_and_same_account_are_flagged_first():
    doc = event(
        event_invites=[
            invite("i1", "Ada", "ada@x.invalid"),
            invite("i2", "Ada Q.", "ADA@x.invalid"),
            invite("i3", "Cy", "cy@x.invalid", member_id="m-1"),
            invite("i4", "Cyrus", "cyrus@x.invalid", member_id="m-1"),
            invite("i5", "Zed", "z1@x.invalid"),
            invite("i6", "zed", "z2@x.invalid"),
        ]
    )
    reasons = [pair["reason"] for pair in possible_duplicates(doc)]
    assert reasons == [REASON_SAME_EMAIL, REASON_SAME_EMAIL, REASON_SAME_NAME]


def test_suggestion_prefers_the_record_with_an_account():
    doc = event(event_invites=[invite("i1", "Ada", "a@x.invalid"), invite("i2", "Ada", "b@x.invalid", created="2026-11-09", member_id="m-1")])
    assert possible_duplicates(doc)[0]["suggested_keep_invite_id"] == "i2"


def test_inactive_merged_and_dismissed_pairs_are_not_raised():
    revoked = event(event_invites=[invite("i1", "Ada", "a@x.invalid"), invite("i2", "Ada", "b@x.invalid", revoked_at=NOW)])
    assert possible_duplicates(revoked) == []
    doc = event()
    key = possible_duplicates(doc)[0]["pair_key"]
    assert possible_duplicates({**doc, **dismiss_pair(doc, key)}) == []
    merged, _ = merge(doc)
    assert possible_duplicates(merged) == []


def test_summary_counts_activity_answers():
    doc = event(activity_rsvps=[answer("invite:inv-new", "coming"), answer("invite:inv-new", "maybe", activity="a2")])
    people = possible_duplicates(doc)[0]["people"]
    assert people[1]["activity_answers"] == 2 and people[0]["activity_answers"] == 0


# ---------------------------------------------------------------------------
# Merge: responses
# ---------------------------------------------------------------------------


def test_answers_move_to_the_kept_person():
    doc = event(
        rsvp_records=[{"user_id": "invite:inv-new", "status": "going", "updated_at": "2026-11-03"}],
        activity_rsvps=[answer("invite:inv-new", "coming"), answer("invite:inv-new", "maybe", activity="a2")],
    )
    merged, report = merge(doc)
    assert {r["respondent_id"] for r in merged["activity_rsvps"]} == {"invite:inv-old"}
    assert merged["rsvp_records"][0]["user_id"] == "invite:inv-old"
    assert report["moved_event_answers"] == 1 and report["moved_activity_answers"] == 2
    assert merged["activity_rsvp_summaries"] == activity_summaries(merged)
    assert merged["activity_rsvp_summaries"]["a1"]["coming"] == 1


def test_newest_answer_wins_where_both_answered():
    doc = event(
        activity_rsvps=[
            answer("invite:inv-old", "not-coming", at="2026-11-02"),
            answer("invite:inv-new", "coming", at="2026-11-06"),
            answer("invite:inv-old", "coming", activity="a2", at="2026-11-08"),
            answer("invite:inv-new", "not-coming", activity="a2", at="2026-11-04"),
        ],
        rsvp_records=[
            {"user_id": "invite:inv-old", "status": "maybe", "updated_at": "2026-11-09"},
            {"user_id": "invite:inv-new", "status": "going", "updated_at": "2026-11-03"},
        ],
    )
    merged, report = merge(doc)
    statuses = {r["activity_id"]: r["status"] for r in merged["activity_rsvps"]}
    assert statuses == {"a1": "coming", "a2": "coming"}
    assert len(merged["activity_rsvps"]) == 2
    assert [r["status"] for r in merged["rsvp_records"]] == ["maybe"]
    assert report["overlapping_answers_resolved"] == 3


def test_other_people_are_untouched():
    doc = event(activity_rsvps=[answer("invite:inv-other", "coming"), answer("invite:inv-new", "maybe")])
    merged, _ = merge(doc)
    assert answer("invite:inv-other", "coming") in merged["activity_rsvps"]


def test_kept_invitation_takes_the_answered_status():
    doc = event()
    by_id(doc, "inv-new").update(rsvp_status="going", guests=2)
    merged, _ = merge(doc)
    kept = by_id(merged, "inv-old")
    assert kept["rsvp_status"] == "going" and kept["guests"] == 2


# ---------------------------------------------------------------------------
# Merge: accounts, contributions, invitations
# ---------------------------------------------------------------------------


def test_account_link_moves_so_contributions_follow():
    doc = event(
        potluck_items=[{"id": "p1", "item_name": "Bread", "assigned_to_id": "m-ada"}],
        activity_rsvps=[answer("m-ada", "coming"), answer("invite:inv-old", "maybe", activity="a2")],
    )
    by_id(doc, "inv-new").update(member_id="m-ada", invite_source="member")
    merged, report = merge(doc)
    kept = by_id(merged, "inv-old")
    assert kept["member_id"] == "m-ada" and kept["invite_source"] == "member"
    assert report["account_linked"] is True
    # The kept guest token's own answers join the account identity too.
    assert {r["respondent_id"] for r in merged["activity_rsvps"]} == {"m-ada"}
    # Potluck is keyed by account and is now that same person's.
    view = serialize_event_for_user(merged, {"id": "m-ada", "role": "member", "community_id": "c-1", "full_name": "Ada"})
    assert view["potluck_items"][0]["is_mine"] is True
    assert view["my_activity_responses"] == {"a1": "coming", "a2": "maybe"}


def test_two_different_accounts_are_refused():
    doc = event()
    by_id(doc, "inv-old")["member_id"] = "m-1"
    by_id(doc, "inv-new")["member_id"] = "m-2"
    with pytest.raises(MergeError) as exc:
        merge(doc)
    assert exc.value.code == "two_accounts"


@pytest.mark.parametrize(
    "keep, drop, code",
    [("inv-old", "inv-old", "same_invitation"), ("inv-old", "nope", "invitation_not_found")],
)
def test_bad_requests_are_refused(keep, drop, code):
    with pytest.raises(MergeError) as exc:
        merge(event(), keep, drop)
    assert exc.value.code == code


def test_cannot_merge_twice_or_keep_an_inactive_invitation():
    merged, _ = merge(event())
    with pytest.raises(MergeError) as exc:
        merge(merged, "inv-other", "inv-new")
    assert exc.value.code == "already_merged"
    doc = event()
    by_id(doc, "inv-old")["revoked_at"] = NOW
    with pytest.raises(MergeError) as exc:
        merge(doc)
    assert exc.value.code == "keep_inactive"


def test_merged_invitation_is_retired_and_counts_drop_by_one():
    doc = event()
    assert canonical_response_summary(doc)["total"] == 3
    merged, _ = merge(doc)
    retired = by_id(merged, "inv-new")
    assert retired["merged_into"] == "inv-old" and retired["status"] == "superseded"
    assert canonical_response_summary(merged)["total"] == 2
    assert by_id(merged, "inv-old")["alternate_emails"] == ["ada@home.invalid"]
    assert merged["duplicate_merges"][-1]["merged_invite_id"] == "inv-new"


def test_merge_history_is_never_shown_to_members():
    merged, _ = merge(event())
    view = serialize_event_for_user(merged, {"id": "m-x", "role": "member", "community_id": "c-1"})
    assert "duplicate_merges" not in view and "duplicate_dismissals" not in view


def test_old_link_resolves_to_the_kept_invitation():
    merged, _ = merge(event())
    assert resolve_merged_invite(merged, by_id(merged, "inv-new"))["id"] == "inv-old"
    looped = deepcopy(merged)
    by_id(looped, "inv-old")["merged_into"] = "inv-new"
    assert resolve_merged_invite(looped, by_id(looped, "inv-new")) is None


def test_reimporting_the_merged_email_lands_on_the_kept_invitation():
    merged, _ = merge(event())
    outcome = apply_registrants(
        merged,
        [Registrant(row=2, name="Ada Guest", email="ada@home.invalid", session_refs=["a2"])],
        flags_by_email={},
        members_by_email={},
        source="csv",
        share_message_for=lambda *_a, **_k: "",
        app_url="https://app.example.invalid",
        now=NOW,
    )
    assert outcome.rows[0]["status"] in {"updated", "skipped"}
    assert outcome.rows[0]["invite_id"] == "inv-old"
    assert len(merged["event_invites"]) == 3  # nothing new created
    assert any(r["respondent_id"] == "invite:inv-old" and r["activity_id"] == "a2" for r in outcome.updates["activity_rsvps"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, matched):
        self.matched_count = matched
        self.modified_count = matched


class _Events:
    def __init__(self, doc):
        self.doc = deepcopy(doc)

    async def find_one(self, query, _projection=None):
        return deepcopy(self.doc) if query.get("id") == self.doc["id"] else None

    async def update_one(self, _query, update):
        self.doc.update(deepcopy(update.get("$set", {})))
        self.doc["rsvp_revision"] = int(self.doc.get("rsvp_revision", 0)) + 1
        return _Result(1)


class _Flags:
    def __init__(self):
        self.updates = []

    async def update_many(self, query, update):
        self.updates.append((query, update))
        return _Result(0)


ORGANIZER = {"id": "org-1", "role": "organizer", "community_id": "c-1"}
MEMBER = {"id": "m-9", "role": "member", "community_id": "c-1"}


@pytest.fixture
def routes(monkeypatch):
    def install(doc):
        events = _Events(doc)
        flags = _Flags()

        async def event_for_user(_event_id, _user):
            return deepcopy(events.doc)

        monkeypatch.setattr(registrant_routes, "events_collection", events)
        monkeypatch.setattr(registrant_routes, "registrant_import_flags_collection", flags)
        monkeypatch.setattr(registrant_routes, "get_event_for_user", event_for_user)
        return events, flags

    return install


@pytest.mark.asyncio
async def test_routes_are_organizer_only(routes):
    routes(event())
    with pytest.raises(HTTPException) as exc:
        await registrant_routes.list_possible_duplicates("event-1", MEMBER)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        await registrant_routes.merge_duplicate_people(
            "event-1", registrant_routes.DuplicateMergeRequest(keep_invite_id="inv-old", merge_invite_id="inv-new"), MEMBER
        )


@pytest.mark.asyncio
async def test_merge_route_writes_and_repoints_import_flags(routes):
    events, flags = routes(event(activity_rsvps=[answer("invite:inv-new", "coming")]))
    reply = await registrant_routes.merge_duplicate_people(
        "event-1", registrant_routes.DuplicateMergeRequest(keep_invite_id="inv-old", merge_invite_id="inv-new"), ORGANIZER
    )
    assert reply["merge"]["moved_activity_answers"] == 1 and reply["pairs"] == []
    assert by_id(events.doc, "inv-new")["merged_into"] == "inv-old"
    assert flags.updates == [
        ({"event_id": "event-1", "matched_invite_id": "inv-new"}, {"$set": {"matched_invite_id": "inv-old"}})
    ]


@pytest.mark.asyncio
async def test_merge_route_reports_refusals(routes):
    doc = event()
    by_id(doc, "inv-old")["member_id"] = "m-1"
    by_id(doc, "inv-new")["member_id"] = "m-2"
    events, _flags = routes(doc)
    with pytest.raises(HTTPException) as exc:
        await registrant_routes.merge_duplicate_people(
            "event-1", registrant_routes.DuplicateMergeRequest(keep_invite_id="inv-old", merge_invite_id="inv-new"), ORGANIZER
        )
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "two_accounts"
    assert "merged_into" not in by_id(events.doc, "inv-new")


@pytest.mark.asyncio
async def test_dismiss_route(routes):
    events, _ = routes(event())
    key = (await registrant_routes.list_possible_duplicates("event-1", ORGANIZER))["pairs"][0]["pair_key"]
    reply = await registrant_routes.dismiss_possible_duplicate("event-1", key, ORGANIZER)
    assert reply["pairs"] == [] and events.doc["duplicate_dismissals"] == [key]
    with pytest.raises(HTTPException) as exc:
        await registrant_routes.dismiss_possible_duplicate("event-1", "unknown", ORGANIZER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_guest_link_of_a_merged_invitation_answers_on_the_kept_one(monkeypatch):
    merged, _ = merge(event())
    events = _Events(merged)

    async def no_notify(**_kwargs):
        return None

    class _NoneCollection:
        async def find_one(self, *_a, **_k):
            return None

    monkeypatch.setattr(public_routes, "events_collection", events)
    monkeypatch.setattr(public_routes, "communities_collection", _NoneCollection())
    monkeypatch.setattr(public_routes, "users_collection", _NoneCollection())
    monkeypatch.setattr(public_routes, "maybe_notify", no_notify)

    async def find_one(query, _projection=None):
        token = query.get("event_invites.id")
        if token and any(i["id"] == token for i in events.doc["event_invites"]):
            return deepcopy(events.doc)
        return None

    monkeypatch.setattr(events, "find_one", find_one)
    found_event, found_invite = await public_routes._find_event_and_invite("inv-new")
    assert found_invite["id"] == "inv-old"
    await public_routes._public_rsvp_submit(
        "inv-new",
        public_routes.PublicRSVPRequest(status="going", activity_responses={"a1": "coming"}),
    )
    assert by_id(events.doc, "inv-old")["rsvp_status"] == "going"
    assert by_id(events.doc, "inv-new")["rsvp_status"] == "pending"
    assert {r["respondent_id"] for r in events.doc["activity_rsvps"]} == {"invite:inv-old"}
