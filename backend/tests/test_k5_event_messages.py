"""K5: targeted announcements and scheduled activity reminders.

- Audiences: everyone invited, one local day, or one activity ("coming" only);
  hidden, declined and revoked people are never included.
- Delivery: in-app visibility follows the audience; email goes from the
  verified address under the organizer's chosen name with the organizer's
  Reply-To; push uses a content-free template. Unverified sender -> no email.
- Opt-outs: member preferences and the per-event email opt-out link.
- Scheduling: reminder offsets are absolute durations, read in each
  activity's own time zone, with a bounded late window.
- No double sends: planning and sending twice, or concurrently, delivers once.
- Authorization: organizers of the event's community only; cron needs its key.
"""

from __future__ import annotations

import asyncio
import os
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_k5_event_messages_unit")

import dependencies  # noqa: E402
import event_messaging as em  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from invitation_redelivery import DeliveryEnvelope, ProviderReceipt, ProviderStatus  # noqa: E402
from invitation_redelivery_provider import (  # noqa: E402
    ResendInvitationDeliveryProvider,
    compose_from_header,
    safe_reply_to,
)
from routes import communications  # noqa: E402
from routes import event_messages as routes  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


ORGANIZER = {
    "id": "organizer-1",
    "community_id": "community-1",
    "role": "organizer",
    "full_name": "Synthetic Organizer",
    "email": "organizer@example.invalid",
}
COMING = {**ORGANIZER, "id": "member-coming", "role": "member", "full_name": "Coming Member", "email": "coming@example.invalid"}
ABSENT = {**ORGANIZER, "id": "member-absent", "role": "member", "full_name": "Absent Member", "email": "absent@example.invalid"}
HIDDEN = {**ORGANIZER, "id": "member-hidden", "role": "member", "full_name": "Hidden Member", "email": "hidden@example.invalid"}
OTHER_ORGANIZER = {**ORGANIZER, "id": "organizer-2", "community_id": "community-2", "email": "o2@example.invalid"}


def activity(activity_id, title, start, end, tz="UTC", **extra):
    return {
        "id": activity_id,
        "title": title,
        "start_at": start,
        "end_at": end,
        "timezone": tz,
        "visibility": "published",
        "attendance_requested": True,
        **extra,
    }


def rsvp(activity_id, respondent_id, status="coming"):
    return {"activity_id": activity_id, "respondent_id": respondent_id, "status": status, "updated_at": iso(timedelta())}


def make_event(**overrides):
    base = {
        "id": "event-1",
        "community_id": "community-1",
        "created_by": ORGANIZER["id"],
        "created_by_name": ORGANIZER["full_name"],
        "title": "Synthetic Multiday Gathering",
        "timezone": "UTC",
        "publication_state": "published",
        "hidden_from_user_ids": [HIDDEN["id"]],
        "agenda": [
            activity("day-1", "Opening Workshop", iso(timedelta(hours=23, minutes=30)), iso(timedelta(hours=26)),
                     virtual_link="https://meet.example.invalid/opening"),
            activity("day-2", "Second Day Session", iso(timedelta(days=2)), iso(timedelta(days=2, hours=2))),
        ],
        "event_invites": [
            {"id": "inv-member", "member_id": COMING["id"], "email": COMING["email"], "status": "invited", "rsvp_status": "going"},
            {"id": "inv-guest", "email": "guest@example.invalid", "status": "invited", "rsvp_status": "pending"},
            {"id": "inv-declined", "email": "declined@example.invalid", "status": "invited", "rsvp_status": "not-going"},
            {"id": "inv-revoked", "email": "revoked@example.invalid", "status": "revoked", "rsvp_status": "pending"},
            {"id": "inv-hidden", "member_id": HIDDEN["id"], "email": HIDDEN["email"], "status": "invited", "rsvp_status": "pending"},
        ],
        "activity_rsvps": [
            rsvp("day-1", COMING["id"]),
            rsvp("day-1", "invite:inv-guest"),
            rsvp("day-1", "invite:inv-revoked"),
            rsvp("day-1", HIDDEN["id"]),
            rsvp("day-2", "invite:inv-guest", "not-coming"),
            rsvp("day-2", ABSENT["id"], "maybe"),
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# In-memory stand-ins for the Motor collections.
# ---------------------------------------------------------------------------


def _get(doc, key):
    value = doc
    for part in key.split("."):
        if isinstance(value, list):
            value = [item.get(part) for item in value if isinstance(item, dict)]
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _cmp(value, expected):
    values = value if isinstance(value, list) else [value]
    if isinstance(expected, dict):
        for op, arg in expected.items():
            if op == "$in" and not any(v in arg for v in values):
                return False
            if op == "$nin" and any(v in arg for v in values):
                return False
            if op == "$ne" and arg in values:
                return False
            if op == "$exists" and (value is not None) != arg:
                return False
            if op == "$lt" and not (value is not None and value < arg):
                return False
        return True
    return expected in values


def _matches(doc, query):
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in expected):
                return False
        elif key == "$and":
            if not all(_matches(doc, sub) for sub in expected):
                return False
        elif not _cmp(_get(doc, key), expected):
            return False
    return True


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count
        self.modified_count = matched_count


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda d: d.get(key, ""), reverse=direction < 0)
        return self

    async def to_list(self, _length):
        return deepcopy(self.docs)


class FakeCollection:
    def __init__(self, docs=None, unique=()):
        self.docs = [deepcopy(d) for d in docs or []]
        self.unique = unique

    def find(self, query=None, projection=None):
        docs = [d for d in self.docs if _matches(d, query)]
        if projection:
            excluded = [k for k, v in projection.items() if v == 0 and k != "_id"]
            docs = [{k: v for k, v in d.items() if k not in excluded} for d in docs]
        return _Cursor(docs)

    async def find_one(self, query, _projection=None, **_kwargs):
        doc = next((d for d in self.docs if _matches(d, query)), None)
        return deepcopy(doc)

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _matches(d, query))

    async def insert_one(self, doc):
        for field in self.unique:
            if any(d.get(field) == doc.get(field) for d in self.docs):
                raise DuplicateKeyError("duplicate")
        self.docs.append(deepcopy(doc))

    async def update_one(self, query, update, upsert=False):
        doc = next((d for d in self.docs if _matches(d, query)), None)
        if doc is None:
            return _Result(0)
        doc.update(deepcopy(update.get("$set", {})))
        for key, value in update.get("$addToSet", {}).items():
            doc.setdefault(key, [])
            if value not in doc[key]:
                doc[key].append(value)
        return _Result(1)

    async def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            if _matches(doc, query):
                await self.update_one({"id": doc.get("id")}, update)
                count += 1
        return _Result(count)

    async def find_one_and_update(self, query, update, sort=None, **_kwargs):
        candidates = [d for d in self.docs if _matches(d, query)]
        if sort:
            key, direction = sort[0]
            candidates.sort(key=lambda d: d.get(key, ""), reverse=direction < 0)
        if not candidates:
            return None
        doc = candidates[0]
        doc.update(deepcopy(update.get("$set", {})))
        return deepcopy(doc)


class FakeProvider:
    def __init__(self):
        self.sent: list[DeliveryEnvelope] = []

    async def send(self, envelope):
        await asyncio.sleep(0)  # yield, so concurrent drains interleave
        self.sent.append(envelope)
        return ProviderReceipt(status=ProviderStatus.ACCEPTED, provider_message_id=f"msg-{len(self.sent):08d}")


class FakePush:
    def __init__(self):
        self.delivered = []

    async def deliver(self, token, notification):
        from push_types import PushOutcome

        self.delivered.append((token, notification))
        return PushOutcome.DELIVERED


def users_docs():
    return [
        {**ORGANIZER, "push_devices": [{"token": "tok-org", "platform": "android"}]},
        {**COMING, "push_devices": [{"token": "tok-coming", "platform": "android"}]},
        {**ABSENT, "push_devices": [{"token": "tok-absent", "platform": "android"}]},
        {**HIDDEN},
        {**OTHER_ORGANIZER},
    ]


@pytest.fixture
def store(monkeypatch):
    state = {
        "events": FakeCollection([make_event()]),
        "users": FakeCollection(users_docs()),
        "prefs": FakeCollection(),
        "opt_outs": FakeCollection(unique=("token",)),
        "announcements": FakeCollection(),
        "notifications": FakeCollection(),
        "outbox": FakeCollection(unique=("dedupe_key",)),
        "provider": FakeProvider(),
        "push": FakePush(),
    }
    monkeypatch.setenv("PUSH_NOTIFICATIONS_ENABLED", "true")

    def ctx(now=None):
        return em.DeliveryContext(
            events=state["events"],
            users=state["users"],
            preferences=state["prefs"],
            opt_outs=state["opt_outs"],
            announcements=state["announcements"],
            notifications=state["notifications"],
            outbox=state["outbox"],
            provider=state["provider"],
            push_client=state["push"],
            push_ready=True,
            app_url="https://app.example.invalid",
            public_api_url="https://api.example.invalid",
            now=now or datetime.now(timezone.utc),
        )

    state["ctx"] = ctx
    return state


def event_doc(store):
    return store["events"].docs[0]


async def run_cron(store, now):
    planned = await em.plan_due_reminders(
        events_collection=store["events"], outbox=store["outbox"], users_collection=store["users"], now=now
    )
    processed = await em.drain_outbox(store["ctx"](now))
    return planned, processed


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_offsets_default_to_24h_and_1h_and_are_validated():
    assert em.normalize_offsets(None) == [1440, 60]
    assert em.normalize_offsets([60, 1440, 60]) == [1440, 60]
    assert em.normalize_offsets([]) == []
    for bad in ([1], [15 * 1440], ["60"], [True], [1.5], [60, 120, 180, 240, 300]):
        with pytest.raises(ValueError):
            em.normalize_offsets(bad)


def test_activity_override_and_event_switch():
    event = make_event(messaging={"activity_reminder_offsets_minutes": {"day-2": []}})
    day1, day2 = event["agenda"]
    assert em.activity_offsets(event, day1) == [1440, 60]
    assert em.activity_offsets(event, day2) == []
    event["messaging"]["reminders_enabled"] = False
    assert em.activity_offsets(event, day1) == []


# ---------------------------------------------------------------------------
# Targeting
# ---------------------------------------------------------------------------


def keys(recipients):
    return sorted(r["key"] for r in recipients)


def test_activity_audience_is_only_people_marked_coming():
    recipients = em.resolve_event_audience(make_event(), audience="activity", activity_id="day-1")
    # Not the hidden member, not the revoked invite.
    assert keys(recipients) == ["email:guest@example.invalid", f"member:{COMING['id']}"]
    assert em.resolve_event_audience(make_event(), audience="activity", activity_id="day-2") == []


def test_everyone_skips_declined_revoked_and_hidden():
    recipients = em.resolve_event_audience(make_event(), audience="everyone")
    assert keys(recipients) == ["email:guest@example.invalid", f"member:{COMING['id']}"]


def test_day_audience_reads_the_day_in_each_activity_time_zone():
    event = make_event(
        agenda=[
            # 23:30 in Los Angeles on Jun 1 is Jun 2 in UTC; it belongs to Jun 1.
            activity("late", "Late Session", "2031-06-01T23:30:00", "2031-06-02T00:30:00", "America/Los_Angeles"),
            activity("lagos", "Morning Session", "2031-06-02T08:00:00", "2031-06-02T09:00:00", "Africa/Lagos"),
        ],
        activity_rsvps=[rsvp("late", COMING["id"]), rsvp("lagos", "invite:inv-guest")],
    )
    assert [d["day"] for d in em.event_days(event)] == ["2031-06-01", "2031-06-02"]
    assert keys(em.resolve_event_audience(event, audience="day", day="2031-06-01")) == [f"member:{COMING['id']}"]
    assert keys(em.resolve_event_audience(event, audience="day", day="2031-06-02")) == ["email:guest@example.invalid"]
    with pytest.raises(ValueError, match="unknown_day"):
        em.resolve_event_audience(event, audience="day", day="2031-06-03")


def test_unknown_or_unpublished_activity_is_refused():
    event = make_event()
    event["agenda"][1]["visibility"] = "draft"
    with pytest.raises(ValueError, match="unknown_activity"):
        em.resolve_event_audience(event, audience="activity", activity_id="day-2")
    with pytest.raises(ValueError, match="invalid_audience"):
        em.resolve_event_audience(event, audience="all")


@pytest.mark.asyncio
async def test_hydrate_fills_member_email_and_drops_foreign_members(store):
    recipients = await em.hydrate_recipients(
        [
            {"key": f"member:{ABSENT['id']}", "member_id": ABSENT["id"], "email": ""},
            {"key": "member:stranger", "member_id": "stranger", "email": "s@example.invalid"},
            {"key": "member:nobody", "member_id": "nobody", "email": ""},
        ],
        store["users"],
        "community-1",
    )
    assert sorted((r["key"], r["email"]) for r in recipients) == [
        ("email:s@example.invalid", "s@example.invalid"),
        (f"member:{ABSENT['id']}", ABSENT["email"]),
    ]


# ---------------------------------------------------------------------------
# Reminder timing across time zones
# ---------------------------------------------------------------------------


def _due(event, now):
    return [(a["id"], offset) for a, offset, _ in em.due_reminders(event, now)]


@pytest.mark.parametrize(
    "tz, local_start, utc_start",
    [
        ("Africa/Lagos", "2031-06-02T09:00:00", datetime(2031, 6, 2, 8, 0, tzinfo=timezone.utc)),
        ("America/Los_Angeles", "2031-06-02T09:00:00", datetime(2031, 6, 2, 16, 0, tzinfo=timezone.utc)),
        ("Asia/Kolkata", "2031-06-02T09:00:00", datetime(2031, 6, 2, 3, 30, tzinfo=timezone.utc)),
    ],
)
def test_offsets_are_measured_from_the_local_start(tz, local_start, utc_start):
    event = make_event(agenda=[activity("a", "Session", local_start, "2031-06-02T23:00:00", tz)])
    day_before = utc_start - timedelta(hours=24)
    assert _due(event, day_before - timedelta(minutes=1)) == []
    assert _due(event, day_before) == [("a", 1440)]
    assert _due(event, day_before + timedelta(hours=1, minutes=59)) == [("a", 1440)]
    assert _due(event, day_before + timedelta(hours=2)) == []  # late window closed
    assert _due(event, utc_start - timedelta(minutes=60)) == [("a", 60)]
    assert _due(event, utc_start - timedelta(minutes=1)) == [("a", 60)]
    assert _due(event, utc_start) == []  # never after it starts


def test_activity_without_its_own_zone_uses_the_event_zone():
    event = make_event(
        timezone="America/New_York",
        agenda=[activity("a", "Session", "2031-06-02T09:00:00", "2031-06-02T10:00:00", tz="")],
    )
    assert _due(event, datetime(2031, 6, 2, 12, 0, tzinfo=timezone.utc)) == [("a", 60)]


def test_24_hours_across_a_daylight_saving_change_is_24_real_hours():
    # US clocks fall back on Nov 2 2031. 18:00 EST = 23:00 UTC.
    event = make_event(agenda=[activity("a", "Session", "2031-11-02T18:00:00", "2031-11-02T20:00:00", "America/New_York")])
    assert _due(event, datetime(2031, 11, 1, 23, 0, tzinfo=timezone.utc)) == [("a", 1440)]
    assert _due(event, datetime(2031, 11, 1, 22, 0, tzinfo=timezone.utc)) == []


def test_drafts_and_unparseable_starts_get_no_reminders():
    event = make_event(agenda=[activity("a", "Session", "not a date", "", "UTC")])
    assert _due(event, NOW) == []
    draft = make_event(publication_state="organizer_draft")
    assert _due(draft, NOW + timedelta(hours=23, minutes=30) - timedelta(minutes=1440)) == []


def test_upcoming_schedule_lists_future_sends_soonest_first():
    rows = em.upcoming_schedule(make_event(), NOW)
    assert [(r["activity_id"], r["offset_minutes"]) for r in rows] == [
        ("day-1", 1440),  # already inside its late window: sends now
        ("day-1", 60),
        ("day-2", 1440),
        ("day-2", 60),
    ]


# ---------------------------------------------------------------------------
# Sending reminders: once, to the right people, honoring opt-outs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cron_sends_the_due_reminder_once_to_people_coming(store):
    planned, processed = await run_cron(store, NOW)
    assert planned["reminders_due"] == 1  # day-1's 24h reminder (starts in 23.5h)
    assert planned["queued"] == 2
    assert processed == {"sent": 2}
    sent = store["provider"].sent
    assert sorted(e.recipient for e in sent) == ["coming@example.invalid", "guest@example.invalid"]
    assert all(e.subject == "Starting in 1 day: Opening Workshop" for e in sent)
    # The session link goes only to these "coming" recipients.
    assert all("https://meet.example.invalid/opening" in e.html_body for e in sent)
    # Push only for the member with a device; in-app only for members.
    assert [t for t, _ in store["push"].delivered] == ["tok-coming"]
    assert store["push"].delivered[0][1]["title"] == "Gathering reminder"
    notes = store["notifications"].docs
    assert [n["recipient_user_ids"] for n in notes] == [[COMING["id"]]]
    assert notes[0]["audience_scope"] == "user"

    again_planned, again_processed = await run_cron(store, NOW + timedelta(minutes=5))
    assert again_planned["queued"] == 0 and again_planned["already_queued"] == 2
    assert again_processed == {}
    assert len(store["provider"].sent) == 2


@pytest.mark.asyncio
async def test_concurrent_cron_calls_send_each_reminder_once(store):
    await asyncio.gather(*(run_cron(store, NOW) for _ in range(4)))
    assert sorted(e.recipient for e in store["provider"].sent) == ["coming@example.invalid", "guest@example.invalid"]
    assert len(store["outbox"].docs) == 2
    assert {d["status"] for d in store["outbox"].docs} == {"sent"}


@pytest.mark.asyncio
async def test_each_offset_and_each_new_start_time_is_its_own_message(store):
    await run_cron(store, NOW)
    start = em.activity_start_utc(event_doc(store)["agenda"][0], event_doc(store))
    await run_cron(store, start - timedelta(minutes=30))  # the 1h reminder
    assert len(store["provider"].sent) == 4
    # The organizer moves the session a day later: its reminders fire again.
    event_doc(store)["agenda"][0]["start_at"] = (start + timedelta(days=1)).isoformat()
    event_doc(store)["agenda"][0]["end_at"] = (start + timedelta(days=1, hours=2)).isoformat()
    await run_cron(store, start + timedelta(minutes=5))
    assert len(store["provider"].sent) == 6


@pytest.mark.asyncio
async def test_a_reminder_planned_before_a_change_is_not_sent_stale(store):
    await em.plan_due_reminders(
        events_collection=store["events"], outbox=store["outbox"], users_collection=store["users"], now=NOW
    )
    rows = event_doc(store)["activity_rsvps"]
    rows[0]["status"] = "not-coming"  # the member changed their answer
    processed = await em.drain_outbox(store["ctx"](NOW))
    assert processed == {"sent": 1, "stale": 1}
    assert [e.recipient for e in store["provider"].sent] == ["guest@example.invalid"]


@pytest.mark.asyncio
async def test_member_reminder_preference_is_respected(store):
    store["prefs"].docs.append({"user_id": COMING["id"], "reminder_notifications": False})
    _, processed = await run_cron(store, NOW)
    assert processed == {"sent": 1, "opted_out": 1}
    assert [e.recipient for e in store["provider"].sent] == ["guest@example.invalid"]
    assert store["push"].delivered == []
    assert store["notifications"].docs == []


@pytest.mark.asyncio
async def test_email_opt_out_link_stops_email_for_that_event_only(store):
    await run_cron(store, NOW)
    guest_email = next(e for e in store["provider"].sent if e.recipient == "guest@example.invalid")
    token = re.search(r"/unsubscribe/([a-f0-9]+)", guest_email.html_body).group(1)

    app = FastAPI()
    app.include_router(routes.router)
    routes_opt_outs = store["opt_outs"]
    import routes.event_messages as module

    module.event_message_opt_outs_collection = routes_opt_outs
    try:
        client = TestClient(app)
        page = client.get(f"/api/public/event-messages/unsubscribe/{token}")
        assert page.status_code == 200 and "Stop these emails" in page.text
        assert not routes_opt_outs.docs[0]["opted_out"]  # GET changes nothing
        done = client.post(f"/api/public/event-messages/unsubscribe/{token}")
        assert done.status_code == 200 and "unsubscribed" in done.text
        assert client.post("/api/public/event-messages/unsubscribe/nope").status_code == 404
    finally:
        import db

        module.event_message_opt_outs_collection = db.event_message_opt_outs_collection

    start = em.activity_start_utc(event_doc(store)["agenda"][0], event_doc(store))
    await run_cron(store, start - timedelta(minutes=30))
    recipients = [e.recipient for e in store["provider"].sent]
    assert recipients.count("guest@example.invalid") == 1  # no second email
    assert recipients.count("coming@example.invalid") == 2
    guest_row = next(d for d in store["outbox"].docs if d["email"] == "guest@example.invalid" and d["offset_minutes"] == 60)
    assert guest_row["results"]["email"] == "opted_out"


# ---------------------------------------------------------------------------
# Sender identity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reminder_uses_the_chosen_name_and_organizer_reply_to(store):
    event_doc(store)["messaging"] = {"sender_name": "The Planning Team", "reply_to_user_id": ""}
    await run_cron(store, NOW)
    envelope = store["provider"].sent[0]
    assert envelope.from_name == "The Planning Team"
    assert envelope.reply_to == ORGANIZER["email"]
    assert "Sent by The Planning Team" in envelope.html_body


def test_from_header_keeps_the_verified_address_whatever_the_name():
    configured = "Kindred <noreply@verified.example>"
    assert compose_from_header(configured, "The Planning Team") == "The Planning Team <noreply@verified.example>"
    spoof = compose_from_header(configured, 'Boss <boss@elsewhere.example>"\r\nBcc: x@y')
    assert spoof.endswith("<noreply@verified.example>")
    assert "@" not in spoof.rsplit("<", 1)[0]  # the name cannot carry an address
    assert "\r" not in spoof and "\n" not in spoof
    assert compose_from_header(configured, "") == configured
    assert safe_reply_to("organizer@example.invalid") == "organizer@example.invalid"
    assert safe_reply_to("a@b.example\r\nBcc: c@d") == ""


@pytest.mark.asyncio
async def test_provider_sends_display_name_and_reply_to():
    calls = []

    class Client:
        async def request(self, method, path, **kwargs):
            calls.append(kwargs["json"])
            return httpx.Response(200, json={"id": "msg_abcdefgh123"})

    provider = ResendInvitationDeliveryProvider(
        api_key="re_test", from_address="Kindred <noreply@verified.example>",
        verified_domain="verified.example", client=Client(),
    )
    base = dict(recipient="p@example.invalid", subject="s", html_body="<p>b</p>", idempotency_key="k" * 20,
                operation_id="op", target_id="t")
    await provider.send(DeliveryEnvelope(**base, from_name="Event Host", reply_to="host@example.invalid"))
    await provider.send(DeliveryEnvelope(**base))
    assert calls[0]["from"] == "Event Host <noreply@verified.example>"
    assert calls[0]["reply_to"] == ["host@example.invalid"]
    assert calls[1]["from"] == "Kindred <noreply@verified.example>"  # unchanged for old callers
    assert "reply_to" not in calls[1]


def test_email_is_unavailable_unless_enabled_and_the_sender_domain_is_verified(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("INVITATION_FROM_ADDRESS", "Kindred <noreply@verified.example>")
    monkeypatch.setenv("INVITATION_VERIFIED_DOMAIN", "verified.example")
    monkeypatch.delenv("EVENT_MESSAGES_EMAIL_ENABLED", raising=False)
    assert routes.email_provider() is None
    monkeypatch.setenv("EVENT_MESSAGES_EMAIL_ENABLED", "true")
    assert routes.email_provider() is not None
    monkeypatch.setenv("INVITATION_FROM_ADDRESS", "Kindred <noreply@unverified.example>")
    assert routes.email_provider() is None
    assert routes.delivery_readiness()["email"] == "unverified_sender"


@pytest.mark.asyncio
async def test_without_a_provider_nothing_is_emailed_but_push_still_goes(store):
    store["provider"] = None
    ctx = store["ctx"]

    def no_email_ctx(now=None):
        c = ctx(now)
        c.provider = None
        return c

    store["ctx"] = no_email_ctx
    _, processed = await run_cron(store, NOW)
    assert processed == {"sent": 2}
    assert {d["results"]["email"] for d in store["outbox"].docs} == {"unavailable"}
    assert [t for t, _ in store["push"].delivered] == ["tok-coming"]


# ---------------------------------------------------------------------------
# Routes: announcements, settings, cron, authorization
# ---------------------------------------------------------------------------


@pytest.fixture
def client(store, monkeypatch):
    current = {"user": ORGANIZER}
    patch_targets = {
        "events_collection": store["events"],
        "users_collection": store["users"],
        "announcements_collection": store["announcements"],
        "event_message_outbox_collection": store["outbox"],
        "event_message_opt_outs_collection": store["opt_outs"],
        "notification_events_collection": store["notifications"],
        "notification_preferences_collection": store["prefs"],
    }
    for name, value in patch_targets.items():
        monkeypatch.setattr(routes, name, value, raising=False)
    monkeypatch.setattr(communications, "announcements_collection", store["announcements"])
    monkeypatch.setattr(communications, "chat_rooms_collection", FakeCollection())
    monkeypatch.setattr(dependencies, "notification_events_collection", store["notifications"])
    monkeypatch.setattr(dependencies, "notification_preferences_collection", store["prefs"])

    async def event_for_user(event_id, user):
        doc = await store["events"].find_one({"id": event_id, "community_id": user["community_id"]})
        if not doc or user["id"] in (doc.get("hidden_from_user_ids") or []):
            raise HTTPException(status_code=404, detail="Event not found.")
        return doc

    async def hidden_ids(user, **_):
        return [e["id"] for e in store["events"].docs if user["id"] in (e.get("hidden_from_user_ids") or [])]

    monkeypatch.setattr(routes, "get_event_for_user", event_for_user)
    monkeypatch.setattr(communications, "get_event_for_user", event_for_user)
    monkeypatch.setattr(communications, "hidden_event_ids_for_user", hidden_ids)
    monkeypatch.setattr(routes, "delivery_context", lambda: store["ctx"]())
    monkeypatch.setenv("EVENT_MESSAGES_CRON_KEY", "cron-secret-for-tests")

    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(communications.router)
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    test_client = TestClient(app)
    test_client.current = current
    return test_client


def post_announcement(client, **payload):
    body = {"title": "Parking update", "body": "Use the north lot.\n\nSee you there.", **payload}
    return client.post("/api/announcements", json=body)


def test_activity_announcement_reaches_only_its_audience_on_every_channel(client, store):
    response = post_announcement(client, event_id="event-1", audience="activity", activity_id="day-1", channels=["email", "push"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["audience_label"] == "Coming to Opening Workshop"
    assert body["recipient_count"] == 2
    assert "recipient_user_ids" not in body
    sent = store["provider"].sent
    assert sorted(e.recipient for e in sent) == ["coming@example.invalid", "guest@example.invalid"]
    assert sent[0].subject == "Parking update · Synthetic Multiday Gathering"
    assert "Use the north lot." in sent[0].html_body
    assert sent[0].reply_to == ORGANIZER["email"]
    assert [t for t, n in store["push"].delivered] == ["tok-coming"]
    assert store["push"].delivered[0][1] == {"title": "New announcement", "body": "An organizer shared an update with you."}

    # In-app: the recipient sees it, a member outside the audience does not.
    client.current["user"] = COMING
    assert [a["title"] for a in client.get("/api/announcements").json()["announcements"]] == ["Parking update"]
    client.current["user"] = ABSENT
    assert client.get("/api/announcements").json()["announcements"] == []
    assert client.get("/api/communications/unread-summary").json()["announcements_unread"] == 0
    announcement_id = body["id"]
    assert client.post(f"/api/announcements/{announcement_id}/comments", json={"text": "hi"}).status_code == 404
    client.current["user"] = ORGANIZER
    listed = client.get("/api/events/event-1/announcements").json()["announcements"]
    assert listed[0]["delivery_summary"]["email"] == {"accepted": 2}
    assert listed[0]["delivery_summary"]["sent"] == 2


def test_posting_twice_is_two_announcements_but_resending_is_impossible(client, store):
    post_announcement(client, event_id="event-1", audience="everyone", channels=["email"])
    assert len(store["provider"].sent) == 2
    # A cron run afterwards finds nothing left to send for it.
    response = client.post("/api/event-messages/cron", headers={"X-Event-Messages-Cron-Key": "cron-secret-for-tests"})
    assert response.status_code == 200
    announcement_rows = [d for d in store["outbox"].docs if d["kind"] == "announcement"]
    assert {d["status"] for d in announcement_rows} == {"sent"}
    assert len([e for e in store["provider"].sent if e.subject.startswith("Parking update")]) == 2


def test_community_announcement_without_channels_stays_in_app_only(client, store):
    response = post_announcement(client)
    assert response.status_code == 200
    assert store["outbox"].docs == [] and store["provider"].sent == []
    client.current["user"] = ABSENT
    assert len(client.get("/api/announcements").json()["announcements"]) == 1


def test_member_announcement_preference_skips_email_and_push(client, store):
    store["prefs"].docs.append({"user_id": COMING["id"], "announcement_notifications": False})
    post_announcement(client, event_id="event-1", audience="activity", activity_id="day-1", channels=["email", "push"])
    assert [e.recipient for e in store["provider"].sent] == ["guest@example.invalid"]
    assert store["push"].delivered == []


def test_audience_preview_counts(client):
    preview = client.post("/api/events/event-1/announcements/audience", json={"audience": "activity", "activity_id": "day-1"})
    assert preview.json() == {"label": "Coming to Opening Workshop", "recipients": 2, "with_email": 2, "with_account": 1}
    bad = client.post("/api/events/event-1/announcements/audience", json={"audience": "day", "day": "1999-01-01"})
    assert bad.status_code == 422


def test_messaging_settings_round_trip_and_validation(client, store):
    view = client.get("/api/events/event-1/messaging").json()
    assert view["settings"]["default_reminder_offsets_minutes"] == [1440, 60]
    assert view["reply_to"]["email"] == ORGANIZER["email"]
    saved = client.put(
        "/api/events/event-1/messaging",
        json={
            "sender_name": "  The <Planning> Team  ",
            "default_reminder_offsets_minutes": [120],
            "activity_reminder_offsets_minutes": {"day-2": [], "unknown": [60]},
        },
    )
    assert saved.status_code == 200, saved.text
    settings = saved.json()["settings"]
    assert settings["sender_name"] == "The Planning Team"
    assert settings["activity_reminder_offsets_minutes"] == {"day-2": []}
    assert [a["offsets_minutes"] for a in saved.json()["activities"]] == [[120], []]
    assert client.put("/api/events/event-1/messaging", json={"default_reminder_offsets_minutes": [1]}).status_code == 422
    assert client.put("/api/events/event-1/messaging", json={"reply_to_user_id": COMING["id"]}).status_code == 422


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/api/events/event-1/messaging", None),
        ("put", "/api/events/event-1/messaging", {}),
        ("post", "/api/events/event-1/announcements/audience", {"audience": "everyone"}),
        ("get", "/api/events/event-1/announcements", None),
        ("post", "/api/announcements", {"title": "x", "event_id": "event-1", "channels": ["email"]}),
    ],
)
def test_organizer_routes_refuse_members_and_other_communities(client, method, path, body):
    for user, expected in ((COMING, 403), (OTHER_ORGANIZER, 404)):
        client.current["user"] = user
        kwargs = {"json": body} if body is not None else {}
        assert getattr(client, method)(path, **kwargs).status_code == expected


def test_cron_requires_its_key(client, monkeypatch):
    assert client.post("/api/event-messages/cron").status_code == 403
    assert client.post("/api/event-messages/cron", headers={"X-Event-Messages-Cron-Key": "wrong"}).status_code == 403
    monkeypatch.setenv("EVENT_MESSAGES_CRON_KEY", "")
    assert client.post("/api/event-messages/cron", headers={"X-Event-Messages-Cron-Key": ""}).status_code == 403


def test_cron_route_plans_and_sends(client, store):
    response = client.post("/api/event-messages/cron", headers={"X-Event-Messages-Cron-Key": "cron-secret-for-tests"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["planned"]["queued"] == 2 and data["processed"] == {"sent": 2}
    assert data["stuck_sending"] == 0


@pytest.mark.asyncio
async def test_emails_are_paced_and_a_spent_budget_leaves_the_rest_queued(store, monkeypatch):
    await em.plan_due_reminders(
        events_collection=store["events"], outbox=store["outbox"], users_collection=store["users"], now=NOW
    )
    sleeps = []

    async def fake_sleep(seconds):
        if seconds:  # the fake provider's own sleep(0) yields are not pacing
            sleeps.append(seconds)

    monkeypatch.setattr(em.asyncio, "sleep", fake_sleep)
    ctx = store["ctx"](NOW)
    ctx.email_interval_seconds = 0.5
    assert await em.drain_outbox(ctx) == {"sent": 2}
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 0.5  # second email waited

    # A cron call whose time budget is spent claims nothing; rows stay queued.
    store["outbox"].docs.clear()
    await em.plan_due_reminders(
        events_collection=store["events"], outbox=store["outbox"], users_collection=store["users"], now=NOW
    )
    spent = store["ctx"](NOW)
    spent.deadline = em.time.monotonic() - 1
    assert await em.drain_outbox(spent) == {}
    assert {d["status"] for d in store["outbox"].docs} == {"queued"}


def test_email_rate_setting(monkeypatch):
    monkeypatch.delenv("EVENT_MESSAGES_EMAIL_PER_SECOND", raising=False)
    assert routes._email_interval_seconds() == 0.5
    monkeypatch.setenv("EVENT_MESSAGES_EMAIL_PER_SECOND", "10")
    assert routes._email_interval_seconds() == 0.1
    monkeypatch.setenv("EVENT_MESSAGES_EMAIL_PER_SECOND", "nonsense")
    assert routes._email_interval_seconds() == 0.5
