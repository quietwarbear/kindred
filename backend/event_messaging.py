"""K5: targeted announcements and scheduled activity reminders.

Who gets a message
- ``everyone``: every active invitee of the event who has not declined, plus
  anyone marked "coming" for one of its activities.
- ``day``: people marked "coming" for any published activity on that local day
  (the day is read in each activity's own time zone).
- ``activity``: people marked "coming" for that one activity.
People an event is hidden from (surprise gatherings) are never included.

How it is delivered
- In-app: the announcement is visible only to its member recipients (and to
  organizers); reminders add a per-recipient in-app notification.
- Email: through the reviewed Resend provider, always from the configured
  verified address. The organizer's chosen name is only the display name and
  the organizer's email is the Reply-To. If the configured sender's domain is
  not the verified domain, email is unavailable and nothing is sent.
- Push: the content-free allowlisted templates in ``push_sender``.
Opt-outs are checked at send time: a member's ``announcement_notifications`` /
``reminder_notifications`` preference, and a per-event email opt-out that any
recipient (account or not) can set from the link in the email footer.

No double sends
Every message to every recipient is one row in ``event_message_outbox`` with a
deterministic ``dedupe_key`` under a unique index, so planning the same
reminder twice (two cron calls, two Railway replicas) inserts it once. Sending
claims a row with an atomic ``queued -> sending`` update, so exactly one worker
sends it. A worker that dies mid-send leaves the row in ``sending``; it is not
retried, because a missed message can be re-sent by hand but a duplicate
cannot be unsent. Resend also receives a per-row idempotency key.

Scheduling
There is no in-process scheduler. ``POST /api/event-messages/cron`` (see
``routes/event_messages.py``) is called by an external cron every few minutes.
A reminder at offset ``N`` minutes is due from ``start - N`` until two hours
later (never past the start), so a missed cron tick still sends and a deploy
never sends a pile of stale "starts in 24 hours" mail.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from invitation_redelivery import DeliveryEnvelope, ProviderStatus
from itinerary import (
    canonical_activity_responses,
    local_day_key,
    parse_local_datetime,
    published_activities,
)
from organizer_command_center import invitation_is_active

DEFAULT_REMINDER_OFFSETS_MINUTES = [1440, 60]
MIN_REMINDER_OFFSET_MINUTES = 5
MAX_REMINDER_OFFSET_MINUTES = 14 * 1440
MAX_REMINDER_OFFSETS = 4
REMINDER_LATE_GRACE = timedelta(hours=2)
STUCK_SENDING_AFTER = timedelta(minutes=15)

AUDIENCES = ("everyone", "day", "activity")
CHANNELS = ("email", "push")
DECLINED_OVERALL = {"not-going", "declined"}
MAX_SENDER_NAME_LENGTH = 64

KIND_ANNOUNCEMENT = "announcement"
KIND_REMINDER = "activity_reminder"

PREFERENCE_FOR_KIND = {
    KIND_ANNOUNCEMENT: "announcement_notifications",
    KIND_REMINDER: "reminder_notifications",
}
PUSH_TEMPLATE_FOR_KIND = {
    KIND_ANNOUNCEMENT: "announcement",
    KIND_REMINDER: "gathering_reminder",
}


async def ensure_indexes(database) -> None:
    """Indexes K5 relies on for correctness, not just speed."""
    from pymongo import ASCENDING

    await database.event_message_outbox.create_index(
        [("dedupe_key", ASCENDING)], name="event_message_once", unique=True
    )
    await database.event_message_outbox.create_index(
        [("status", ASCENDING), ("created_at", ASCENDING)], name="event_message_queue"
    )
    await database.event_message_outbox.create_index(
        [("announcement_id", ASCENDING)], name="event_message_by_announcement", sparse=True
    )
    await database.event_message_opt_outs.create_index(
        [("token", ASCENDING)], name="event_message_opt_out_token", unique=True
    )
    await database.event_message_opt_outs.create_index(
        [("scope_id", ASCENDING), ("email", ASCENDING)],
        name="event_message_opt_out_once",
        unique=True,
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def normalize_offsets(value: Any) -> list[int]:
    """Validate organizer reminder offsets (minutes before start).

    Returns unique offsets, largest first. Raises ``ValueError`` for anything
    that is not a whole number of minutes in range, or for too many offsets.
    """
    if value is None:
        return list(DEFAULT_REMINDER_OFFSETS_MINUTES)
    if not isinstance(value, (list, tuple)):
        raise ValueError("invalid_reminder_offsets")
    offsets: set[int] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("invalid_reminder_offsets")
        if int(item) != item:
            raise ValueError("invalid_reminder_offsets")
        minutes = int(item)
        if not MIN_REMINDER_OFFSET_MINUTES <= minutes <= MAX_REMINDER_OFFSET_MINUTES:
            raise ValueError("invalid_reminder_offsets")
        offsets.add(minutes)
    if len(offsets) > MAX_REMINDER_OFFSETS:
        raise ValueError("too_many_reminder_offsets")
    return sorted(offsets, reverse=True)


def clean_sender_name(value: Any) -> str:
    cleaned = "".join(
        ch for ch in str(value or "") if ch.isprintable() and ch not in '"<>@\\'
    )
    return " ".join(cleaned.split())[:MAX_SENDER_NAME_LENGTH].strip()


def messaging_settings(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("messaging") or {}
    try:
        default_offsets = normalize_offsets(raw.get("default_reminder_offsets_minutes"))
    except ValueError:
        default_offsets = list(DEFAULT_REMINDER_OFFSETS_MINUTES)
    overrides: dict[str, list[int]] = {}
    for activity_id, offsets in (raw.get("activity_reminder_offsets_minutes") or {}).items():
        try:
            overrides[str(activity_id)] = normalize_offsets(offsets or [])
        except ValueError:
            continue
    return {
        "sender_name": clean_sender_name(raw.get("sender_name")),
        "reply_to_user_id": str(raw.get("reply_to_user_id") or ""),
        "reminders_enabled": raw.get("reminders_enabled", True) is not False,
        "default_reminder_offsets_minutes": default_offsets,
        "activity_reminder_offsets_minutes": overrides,
    }


def activity_offsets(event: dict[str, Any], activity: dict[str, Any]) -> list[int]:
    settings = messaging_settings(event)
    if not settings["reminders_enabled"]:
        return []
    overrides = settings["activity_reminder_offsets_minutes"]
    activity_id = str(activity.get("id") or "")
    if activity_id in overrides:
        return overrides[activity_id]
    return settings["default_reminder_offsets_minutes"]


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def activity_timezone(activity: dict[str, Any], event: dict[str, Any]) -> str:
    return activity.get("timezone") or event.get("timezone") or "UTC"


def activity_start_utc(activity: dict[str, Any], event: dict[str, Any]) -> datetime | None:
    start = parse_local_datetime(
        str(activity.get("start_at") or ""), activity_timezone(activity, event)
    )
    return start.astimezone(timezone.utc) if start else None


def due_reminders(
    event: dict[str, Any], now: datetime
) -> list[tuple[dict[str, Any], int, datetime]]:
    """Return ``(activity, offset_minutes, start_utc)`` reminders due at ``now``.

    Offsets are absolute durations, so "24 hours before" across a daylight
    saving change is 24 real hours, not the same wall-clock time a day earlier.
    """
    if event.get("publication_state") == "organizer_draft":
        return []
    due: list[tuple[dict[str, Any], int, datetime]] = []
    for activity in published_activities(event):
        start = activity_start_utc(activity, event)
        if start is None or now >= start:
            continue
        for offset in activity_offsets(event, activity):
            due_at = start - timedelta(minutes=offset)
            if due_at <= now < min(due_at + REMINDER_LATE_GRACE, start):
                due.append((activity, offset, start))
    return due


def upcoming_schedule(
    event: dict[str, Any], now: datetime, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Every future reminder send time, soonest first, for the organizer UI."""
    rows = []
    if event.get("publication_state") == "organizer_draft":
        return rows
    for activity in published_activities(event):
        start = activity_start_utc(activity, event)
        if start is None or now >= start:
            continue
        for offset in activity_offsets(event, activity):
            due_at = start - timedelta(minutes=offset)
            if due_at + REMINDER_LATE_GRACE <= now:
                continue
            rows.append(
                {
                    "activity_id": activity.get("id", ""),
                    "activity_title": activity.get("title", ""),
                    "offset_minutes": offset,
                    "send_at": max(due_at, now).isoformat(),
                    "start_at": start.isoformat(),
                }
            )
    rows.sort(key=lambda row: row["send_at"])
    return rows[:limit]


def humanize_minutes(minutes: int) -> str:
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "1 day" if days == 1 else f"{days} days"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "1 hour" if hours == 1 else f"{hours} hours"
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def format_local(dt: datetime, timezone_name: str) -> str:
    try:
        local = dt.astimezone(ZoneInfo(timezone_name or "UTC"))
    except ZoneInfoNotFoundError:
        local = dt.astimezone(timezone.utc)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local.strftime('%a %b')} {local.day} · {hour}:{local.strftime('%M %p')} {local.tzname()}"


# ---------------------------------------------------------------------------
# Audience
# ---------------------------------------------------------------------------


def event_days(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Distinct local days of published activities, for the "one day" picker."""
    days: dict[str, list[str]] = {}
    for activity in published_activities(event):
        key = local_day_key(
            str(activity.get("start_at") or ""), activity_timezone(activity, event)
        )
        if key:
            days.setdefault(key, []).append(str(activity.get("id") or ""))
    return [{"day": key, "activity_ids": ids} for key, ids in sorted(days.items())]


def _coming_respondents(event: dict[str, Any], activity_ids: set[str]) -> list[str]:
    return [
        str(row.get("respondent_id") or "")
        for row in canonical_activity_responses(event)
        if row.get("activity_id") in activity_ids and row.get("status") == "coming"
    ]


def _recipient_key(member_id: str, email: str) -> str:
    if member_id:
        return f"member:{member_id}"
    return f"email:{normalize_email(email)}" if email else ""


def resolve_event_audience(
    event: dict[str, Any],
    *,
    audience: str,
    day: str = "",
    activity_id: str = "",
) -> list[dict[str, str]]:
    """Return recipients ``{key, member_id, email}`` for an event audience.

    Raises ``ValueError`` for an unknown audience, day or activity. ``email``
    may be empty for a member without an invitation row; callers fill it from
    the member's account.
    """
    if audience not in AUDIENCES:
        raise ValueError("invalid_audience")
    hidden = set(event.get("hidden_from_user_ids") or [])
    invites = {
        str(invite.get("id")): invite
        for invite in event.get("event_invites", [])
        if invite.get("id")
    }
    invite_by_member = {
        str(invite.get("member_id")): invite
        for invite in invites.values()
        if invite.get("member_id")
    }

    respondents: list[str] = []
    if audience == "activity":
        known = {str(a.get("id")) for a in published_activities(event)}
        if not activity_id or activity_id not in known:
            raise ValueError("unknown_activity")
        respondents = _coming_respondents(event, {activity_id})
    elif audience == "day":
        match = next((d for d in event_days(event) if d["day"] == day), None)
        if not match:
            raise ValueError("unknown_day")
        respondents = _coming_respondents(event, set(match["activity_ids"]))
    else:
        all_ids = {str(a.get("id")) for a in event.get("agenda", []) if a.get("id")}
        respondents = _coming_respondents(event, all_ids)
        for invite_id, invite in invites.items():
            if str(invite.get("rsvp_status") or "").lower() in DECLINED_OVERALL:
                continue
            respondents.append(
                str(invite.get("member_id") or "") or f"invite:{invite_id}"
            )

    recipients: dict[str, dict[str, str]] = {}
    for respondent_id in respondents:
        if not respondent_id or respondent_id.startswith("legacy-anonymous:"):
            continue
        if respondent_id.startswith("invite:"):
            invite = invites.get(respondent_id.split(":", 1)[1])
            if not invite:
                continue
            member_id = str(invite.get("member_id") or "")
            email = normalize_email(invite.get("email"))
        else:
            member_id = respondent_id
            invite = invite_by_member.get(member_id)
            email = normalize_email((invite or {}).get("email"))
        if invite is not None and not invitation_is_active(invite):
            continue
        if member_id and member_id in hidden:
            continue
        key = _recipient_key(member_id, email)
        if not key:
            continue
        existing = recipients.get(key)
        if existing:
            existing["email"] = existing["email"] or email
            continue
        recipients[key] = {"key": key, "member_id": member_id, "email": email}
    return list(recipients.values())


async def hydrate_recipients(
    recipients: list[dict[str, str]],
    users_collection,
    community_id: str,
) -> list[dict[str, str]]:
    """Fill member emails from accounts; drop member ids from other communities."""
    member_ids = sorted({r["member_id"] for r in recipients if r.get("member_id")})
    users: dict[str, dict[str, Any]] = {}
    if member_ids:
        found = await users_collection.find(
            {"id": {"$in": member_ids}, "community_id": community_id},
            {"_id": 0, "id": 1, "email": 1, "email_verified": 1},
        ).to_list(len(member_ids))
        users = {u["id"]: u for u in found if u.get("id")}
    result: dict[str, dict[str, str]] = {}
    for recipient in recipients:
        member_id = recipient.get("member_id", "")
        email = recipient.get("email", "")
        if member_id and member_id not in users:
            member_id = ""  # not a member of this community: email only
        elif member_id and not email:
            user = users[member_id]
            if user.get("email_verified") is not False:
                email = normalize_email(user.get("email"))
        key = _recipient_key(member_id, email)
        if not key:
            continue
        if key in result:
            result[key]["email"] = result[key]["email"] or email
            continue
        result[key] = {"key": key, "member_id": member_id, "email": email}
    return list(result.values())


async def community_audience(users_collection, community_id: str) -> list[dict[str, str]]:
    users = await users_collection.find(
        {"community_id": community_id},
        {"_id": 0, "id": 1, "email": 1, "email_verified": 1},
    ).to_list(5000)
    recipients = []
    for user in users:
        if not user.get("id"):
            continue
        email = (
            normalize_email(user.get("email"))
            if user.get("email_verified") is not False
            else ""
        )
        recipients.append(
            {"key": f"member:{user['id']}", "member_id": user["id"], "email": email}
        )
    return recipients


def audience_label(event: dict[str, Any] | None, audience: str, day: str, activity_id: str) -> str:
    if not event:
        return "Everyone in the community"
    if audience == "activity":
        activity = next(
            (a for a in event.get("agenda", []) if a.get("id") == activity_id), {}
        )
        return f"Coming to {activity.get('title') or 'one activity'}"
    if audience == "day":
        try:
            label = datetime.fromisoformat(day).strftime("%A, %B ") + str(
                datetime.fromisoformat(day).day
            )
        except ValueError:
            label = day
        return f"Coming on {label}"
    return "Everyone invited"


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------


def announcement_dedupe_key(announcement_id: str, recipient_key: str) -> str:
    return f"ann:{announcement_id}:{recipient_key}"


def reminder_dedupe_key(
    event_id: str, activity_id: str, offset: int, start_utc: datetime, recipient_key: str
) -> str:
    # The start time is part of the key: if the organizer moves the activity,
    # the reminders for the new time are new messages.
    return f"rem:{event_id}:{activity_id}:{offset}:{start_utc.isoformat()}:{recipient_key}"


async def enqueue(outbox, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    queued = duplicates = 0
    for row in rows:
        try:
            await outbox.insert_one(dict(row))
            queued += 1
        except DuplicateKeyError:
            duplicates += 1
    return {"queued": queued, "already_queued": duplicates}


def _outbox_row(
    *,
    kind: str,
    dedupe_key: str,
    community_id: str,
    event_id: str,
    recipient: dict[str, str],
    channels: list[str],
    created_at: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "kind": kind,
        "dedupe_key": dedupe_key,
        "community_id": community_id,
        "event_id": event_id,
        "recipient_key": recipient["key"],
        "member_id": recipient.get("member_id", ""),
        "email": recipient.get("email", ""),
        "channels": list(channels),
        "status": "queued",
        "created_at": created_at,
        **extra,
    }


def announcement_rows(
    announcement: dict[str, Any],
    recipients: list[dict[str, str]],
    channels: list[str],
) -> list[dict[str, Any]]:
    return [
        _outbox_row(
            kind=KIND_ANNOUNCEMENT,
            dedupe_key=announcement_dedupe_key(announcement["id"], r["key"]),
            community_id=announcement["community_id"],
            event_id=announcement.get("event_id", ""),
            recipient=r,
            channels=channels,
            created_at=announcement["created_at"],
            announcement_id=announcement["id"],
        )
        for r in recipients
    ]


async def plan_due_reminders(
    *, events_collection, outbox, users_collection, now: datetime
) -> dict[str, int]:
    """Queue every reminder that is due now. Safe to call concurrently."""
    events = await events_collection.find(
        {
            "agenda.visibility": "published",
            "publication_state": {"$ne": "organizer_draft"},
        },
        {
            "_id": 0,
            "id": 1,
            "community_id": 1,
            "timezone": 1,
            "publication_state": 1,
            "agenda": 1,
            "event_invites": 1,
            "activity_rsvps": 1,
            "hidden_from_user_ids": 1,
            "messaging": 1,
        },
    ).to_list(5000)
    totals = {"events_scanned": len(events), "reminders_due": 0, "queued": 0, "already_queued": 0}
    created_at = now.isoformat()
    for event in events:
        for activity, offset, start in due_reminders(event, now):
            totals["reminders_due"] += 1
            recipients = await hydrate_recipients(
                resolve_event_audience(
                    event, audience="activity", activity_id=str(activity["id"])
                ),
                users_collection,
                event["community_id"],
            )
            rows = [
                _outbox_row(
                    kind=KIND_REMINDER,
                    dedupe_key=reminder_dedupe_key(
                        event["id"], str(activity["id"]), offset, start, r["key"]
                    ),
                    community_id=event["community_id"],
                    event_id=event["id"],
                    recipient=r,
                    channels=list(CHANNELS),
                    created_at=created_at,
                    activity_id=str(activity["id"]),
                    offset_minutes=offset,
                    start_utc=start.isoformat(),
                )
                for r in recipients
            ]
            result = await enqueue(outbox, rows)
            totals["queued"] += result["queued"]
            totals["already_queued"] += result["already_queued"]
    return totals


async def claim_next(outbox, *, now: datetime, extra: dict[str, Any] | None = None):
    """Atomically move one queued row to ``sending``; ``None`` when empty."""
    claim_id = uuid.uuid4().hex
    row = await outbox.find_one_and_update(
        {"status": "queued", **(extra or {})},
        {"$set": {"status": "sending", "claim_id": claim_id, "claimed_at": now.isoformat()}},
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    return row


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def email_flag_enabled() -> bool:
    return os.environ.get("EVENT_MESSAGES_EMAIL_ENABLED", "").lower() == "true"


def sender_domain_verified() -> bool:
    """The configured From address must be on the verified sending domain."""
    _, address = parseaddr(os.environ.get("INVITATION_FROM_ADDRESS", "").strip())
    verified = os.environ.get("INVITATION_VERIFIED_DOMAIN", "").strip().lower()
    if address.count("@") != 1 or not verified:
        return False
    return address.rsplit("@", 1)[1].lower() == verified


def _page(inner: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"></head><body style="font-family:-apple-system,Segoe UI,'
        'Roboto,sans-serif;background:#f9f5f0;margin:0;padding:32px;">'
        '<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:16px;'
        f'padding:32px;">{inner}</div></body></html>'
    )


def _footer(unsubscribe_url: str, sender_name: str) -> str:
    who = html.escape(sender_name or "the organizer")
    link = html.escape(unsubscribe_url, quote=True)
    return (
        '<p style="color:#6b5b4b;font-size:12px;line-height:18px;margin:24px 0 0;">'
        f"Sent by {who} through Kindred. Reply to this email to reach them. "
        f'<a href="{link}" style="color:#6b5b4b;">Stop emails about this event</a>.</p>'
    )


def _paragraphs(text: str) -> str:
    blocks = [b.strip() for b in str(text or "").split("\n\n") if b.strip()]
    return "".join(
        '<p style="color:#3a2a1a;font-size:15px;line-height:22px;margin:0 0 12px;">'
        + html.escape(block).replace("\n", "<br>")
        + "</p>"
        for block in blocks
    )


def announcement_email(
    *,
    announcement: dict[str, Any],
    event: dict[str, Any] | None,
    sender_name: str,
    app_url: str,
    unsubscribe_url: str,
) -> tuple[str, str]:
    title = str(announcement.get("title") or "An update").strip()
    context = str((event or {}).get("title") or "").strip()
    subject = f"{title} · {context}" if context else title
    link = html.escape(f"{app_url.rstrip('/')}/announcements", quote=True)
    inner = (
        '<p style="color:#9A3412;font-size:13px;letter-spacing:.12em;'
        'text-transform:uppercase;margin:0 0 8px;">'
        f"{html.escape(context or 'Announcement')}</p>"
        f'<h1 style="font-size:22px;color:#2d1810;margin:0 0 16px;">{html.escape(title)}</h1>'
        f"{_paragraphs(announcement.get('body', ''))}"
        f'<a href="{link}" style="display:inline-block;margin-top:8px;background:#9A3412;'
        'color:#fff;border-radius:999px;padding:12px 28px;text-decoration:none;'
        'font-weight:600;">Open in Kindred</a>'
        f"{_footer(unsubscribe_url, sender_name)}"
    )
    return subject[:200], _page(inner)


def reminder_email(
    *,
    event: dict[str, Any],
    activity: dict[str, Any],
    offset_minutes: int,
    start_utc: datetime,
    sender_name: str,
    app_url: str,
    unsubscribe_url: str,
) -> tuple[str, str]:
    title = str(activity.get("title") or "Your activity").strip()
    subject = f"Starting in {humanize_minutes(offset_minutes)}: {title}"
    when = format_local(start_utc, activity_timezone(activity, event))
    where_parts = [
        str(activity.get(key) or "").strip()
        for key in ("venue_name", "venue_address", "venue_detail")
    ]
    where = " · ".join(p for p in where_parts if p)
    if activity.get("location_tba") and not where:
        where = "Location to be announced"
    rows = [f'<p style="color:#5a4a3a;margin:0 0 4px;">{html.escape(when)}</p>']
    if where:
        rows.append(f'<p style="color:#5a4a3a;margin:0 0 4px;">{html.escape(where)}</p>')
    # Recipients are re-checked as "coming" right before sending, so the
    # session link may be included (K4: links go to registered attendees).
    virtual_link = str(activity.get("virtual_link") or "").strip()
    if virtual_link.startswith(("https://", "http://")):
        safe = html.escape(virtual_link, quote=True)
        rows.append(
            '<p style="margin:12px 0 0;"><a href="'
            f'{safe}" style="color:#9A3412;font-weight:600;">Join online</a></p>'
        )
    event_link = html.escape(f"{app_url.rstrip('/')}/gatherings", quote=True)
    inner = (
        '<p style="color:#9A3412;font-size:13px;letter-spacing:.12em;'
        'text-transform:uppercase;margin:0 0 8px;">'
        f"{html.escape(str(event.get('title') or 'Reminder'))}</p>"
        f'<h1 style="font-size:22px;color:#2d1810;margin:0 0 12px;">{html.escape(title)}</h1>'
        + "".join(rows)
        + f'<a href="{event_link}" style="display:inline-block;margin-top:20px;background:#9A3412;'
        'color:#fff;border-radius:999px;padding:12px 28px;text-decoration:none;'
        'font-weight:600;">See the schedule</a>'
        + _footer(unsubscribe_url, sender_name)
    )
    return subject[:200], _page(inner)


def opt_out_scope(event_id: str, community_id: str) -> str:
    return f"event:{event_id}" if event_id else f"community:{community_id}"


async def unsubscribe_token(opt_outs, scope_id: str, email: str, now_value: str) -> str:
    query = {"scope_id": scope_id, "email": email}
    existing = await opt_outs.find_one(query, {"_id": 0, "token": 1})
    if existing and existing.get("token"):
        return existing["token"]
    token = uuid.uuid4().hex + uuid.uuid4().hex
    try:
        await opt_outs.insert_one(
            {**query, "token": token, "opted_out": False, "created_at": now_value}
        )
        return token
    except DuplicateKeyError:
        existing = await opt_outs.find_one(query, {"_id": 0, "token": 1})
        return (existing or {}).get("token", "")


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


@dataclass
class DeliveryContext:
    events: Any
    users: Any
    preferences: Any
    opt_outs: Any
    announcements: Any
    notifications: Any
    outbox: Any
    provider: Any = None
    push_client: Any = None
    apns_client: Any = None
    push_ready: bool = False
    app_url: str = "https://www.heykindred.org"
    public_api_url: str = "https://kindred-production-badd.up.railway.app"
    now: datetime = field(default_factory=now_utc)
    # Pace emails to stay under the provider's rate limit (Resend's default
    # is 2 requests per second); 0 sends back to back.
    email_interval_seconds: float = 0.0
    # Stop claiming new rows after this ``time.monotonic()`` value, so a cron
    # call stays short; whatever is left is sent on the next tick.
    deadline: float | None = None
    _last_email_at: float = 0.0
    _events: dict[str, Any] = field(default_factory=dict)
    _announcements: dict[str, Any] = field(default_factory=dict)
    _users: dict[str, Any] = field(default_factory=dict)

    @property
    def email_ready(self) -> bool:
        return self.provider is not None

    async def event(self, event_id: str) -> dict[str, Any] | None:
        if not event_id:
            return None
        if event_id not in self._events:
            self._events[event_id] = await self.events.find_one({"id": event_id}, {"_id": 0})
        return self._events[event_id]

    async def announcement(self, announcement_id: str) -> dict[str, Any] | None:
        if announcement_id not in self._announcements:
            self._announcements[announcement_id] = await self.announcements.find_one(
                {"id": announcement_id}, {"_id": 0}
            )
        return self._announcements[announcement_id]

    async def user(self, user_id: str, community_id: str) -> dict[str, Any] | None:
        if not user_id:
            return None
        cache_key = f"{community_id}:{user_id}"
        if cache_key not in self._users:
            self._users[cache_key] = await self.users.find_one(
                {"id": user_id, "community_id": community_id},
                {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1},
            )
        return self._users[cache_key]


async def sender_identity(
    ctx: DeliveryContext,
    *,
    event: dict[str, Any] | None,
    community_id: str,
    author_id: str = "",
    author_name: str = "",
) -> tuple[str, str]:
    """Return ``(display_name, reply_to_email)`` for a message.

    For an event: the organizer's chosen sender name (default: the event
    creator's name) and the chosen organizer's email (default: the creator).
    For a community announcement: the author.
    """
    if event:
        settings = messaging_settings(event)
        reply_user = await ctx.user(
            settings["reply_to_user_id"] or str(event.get("created_by") or ""),
            community_id,
        )
        creator = await ctx.user(str(event.get("created_by") or ""), community_id)
        name = settings["sender_name"] or clean_sender_name(
            (creator or {}).get("full_name") or event.get("created_by_name") or ""
        )
        return name, normalize_email((reply_user or {}).get("email"))
    author = await ctx.user(author_id, community_id)
    return clean_sender_name(author_name or (author or {}).get("full_name")), normalize_email(
        (author or {}).get("email")
    )


async def _member_opted_out(ctx: DeliveryContext, row: dict[str, Any]) -> bool:
    member_id = row.get("member_id")
    if not member_id:
        return False
    prefs = await ctx.preferences.find_one({"user_id": member_id}, {"_id": 0})
    if not prefs:
        return False
    return prefs.get(PREFERENCE_FOR_KIND[row["kind"]], True) is False


async def _email_opted_out(ctx: DeliveryContext, scope_id: str, email: str) -> bool:
    doc = await ctx.opt_outs.find_one(
        {"scope_id": scope_id, "email": email, "opted_out": True}, {"_id": 0, "token": 1}
    )
    return bool(doc)


def _still_coming(event: dict[str, Any], activity_id: str, recipient_key: str) -> bool:
    try:
        recipients = resolve_event_audience(event, audience="activity", activity_id=activity_id)
    except ValueError:
        return False
    keys = {r["key"] for r in recipients}
    if recipient_key in keys:
        return True
    # A guest who later linked an account is keyed by member now; match on email.
    if recipient_key.startswith("email:"):
        email = recipient_key.split(":", 1)[1]
        return any(r.get("email") == email for r in recipients)
    return False


async def _deliver_push(ctx: DeliveryContext, row: dict[str, Any]) -> str:
    from push_sender import send_push_to_user

    if not row.get("member_id"):
        return "no_account"
    if not ctx.push_ready or (ctx.push_client is None and ctx.apns_client is None):
        return "unavailable"
    try:
        report = await send_push_to_user(
            users_collection=ctx.users,
            user_id=row["member_id"],
            template_code=PUSH_TEMPLATE_FOR_KIND[row["kind"]],
            client=ctx.push_client,
            apns_client=ctx.apns_client,
        )
    except Exception:
        return "failed"
    return "delivered" if report.delivered else "no_device"


async def _deliver_email(
    ctx: DeliveryContext,
    row: dict[str, Any],
    *,
    subject: str,
    html_body: str,
    sender_name: str,
    reply_to: str,
) -> str:
    if not ctx.email_ready:
        return "unavailable"
    if ctx.email_interval_seconds > 0:
        wait = ctx._last_email_at + ctx.email_interval_seconds - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        ctx._last_email_at = time.monotonic()
    digest = hashlib.sha256(row["dedupe_key"].encode()).hexdigest()
    envelope = DeliveryEnvelope(
        recipient=row["email"],
        subject=subject,
        html_body=html_body,
        idempotency_key=f"kem_{digest}",
        operation_id=row["id"],
        target_id=uuid.uuid4().hex,
        from_name=sender_name,
        reply_to=reply_to,
    )
    try:
        receipt = await ctx.provider.send(envelope)
    except Exception:
        return "failed"
    return {
        ProviderStatus.ACCEPTED: "accepted",
        ProviderStatus.REJECTED: "rejected",
        ProviderStatus.AMBIGUOUS: "ambiguous",
    }.get(receipt.status, "failed")


async def deliver_row(ctx: DeliveryContext, row: dict[str, Any]) -> dict[str, Any]:
    """Send one claimed outbox row. Returns the fields to store on it."""
    event = await ctx.event(row.get("event_id", ""))
    community_id = row["community_id"]
    result: dict[str, Any] = {"results": {}}

    if row["kind"] == KIND_ANNOUNCEMENT:
        announcement = await ctx.announcement(row.get("announcement_id", ""))
        if not announcement:
            return {"status": "cancelled", "reason": "announcement_deleted"}
        activity = None
    else:
        if not event:
            return {"status": "stale", "reason": "event_missing"}
        activity = next(
            (
                a
                for a in published_activities(event)
                if str(a.get("id")) == row.get("activity_id")
            ),
            None,
        )
        start = activity_start_utc(activity, event) if activity else None
        if (
            not activity
            or start is None
            or start.isoformat() != row.get("start_utc")
            or ctx.now >= start
            or row.get("offset_minutes") not in activity_offsets(event, activity)
        ):
            return {"status": "stale", "reason": "schedule_changed"}
        if not _still_coming(event, row["activity_id"], row["recipient_key"]):
            return {"status": "stale", "reason": "no_longer_coming"}
        announcement = None

    if await _member_opted_out(ctx, row):
        return {"status": "opted_out", "results": {}}

    if row["kind"] == KIND_REMINDER and row.get("member_id"):
        await ctx.notifications.insert_one(
            {
                "id": uuid.uuid4().hex,
                "community_id": community_id,
                "actor_name": "Kindred",
                "event_type": "activity-reminder",
                "title": f"Starting in {humanize_minutes(row['offset_minutes'])}: {activity.get('title', '')}",
                "description": format_local(start, activity_timezone(activity, event)),
                "related_id": event["id"],
                "audience_scope": "user",
                "recipient_user_ids": [row["member_id"]],
                "read_by_user_ids": [],
                "created_at": ctx.now.isoformat(),
            }
        )
        result["results"]["in_app"] = "delivered"

    if "email" in row.get("channels", []):
        scope_id = opt_out_scope(row.get("event_id", ""), community_id)
        if not row.get("email"):
            result["results"]["email"] = "no_address"
        elif await _email_opted_out(ctx, scope_id, row["email"]):
            result["results"]["email"] = "opted_out"
        elif not ctx.email_ready:
            result["results"]["email"] = "unavailable"
        else:
            sender_name, reply_to = await sender_identity(
                ctx,
                event=event,
                community_id=community_id,
                author_id=(announcement or {}).get("created_by", ""),
                author_name=(announcement or {}).get("created_by_name", ""),
            )
            token = await unsubscribe_token(
                ctx.opt_outs, scope_id, row["email"], ctx.now.isoformat()
            )
            unsubscribe_url = (
                f"{ctx.public_api_url.rstrip('/')}/api/public/event-messages/unsubscribe/{token}"
            )
            if row["kind"] == KIND_ANNOUNCEMENT:
                subject, body = announcement_email(
                    announcement=announcement,
                    event=event,
                    sender_name=sender_name,
                    app_url=ctx.app_url,
                    unsubscribe_url=unsubscribe_url,
                )
            else:
                subject, body = reminder_email(
                    event=event,
                    activity=activity,
                    offset_minutes=row["offset_minutes"],
                    start_utc=start,
                    sender_name=sender_name,
                    app_url=ctx.app_url,
                    unsubscribe_url=unsubscribe_url,
                )
            result["results"]["email"] = await _deliver_email(
                ctx,
                row,
                subject=subject,
                html_body=body,
                sender_name=sender_name,
                reply_to=reply_to,
            )

    if "push" in row.get("channels", []):
        result["results"]["push"] = await _deliver_push(ctx, row)

    result["status"] = "sent"
    return result


async def drain_outbox(
    ctx: DeliveryContext, *, limit: int = 300, extra: dict[str, Any] | None = None
) -> dict[str, int]:
    """Claim and send up to ``limit`` queued rows. Safe to run concurrently."""
    counts: dict[str, int] = {}
    for _ in range(limit):
        if ctx.deadline is not None and time.monotonic() >= ctx.deadline:
            break
        row = await claim_next(ctx.outbox, now=ctx.now, extra=extra)
        if row is None:
            break
        try:
            outcome = await deliver_row(ctx, row)
        except Exception:
            outcome = {"status": "failed", "reason": "internal_error"}
        outcome["finished_at"] = now_utc().isoformat()
        await ctx.outbox.update_one(
            {"id": row["id"], "claim_id": row["claim_id"]}, {"$set": outcome}
        )
        counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1
    return counts


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Content-free delivery counts for one announcement."""
    summary = {
        "recipients": len(rows),
        "pending": 0,
        "sent": 0,
        "opted_out": 0,
        "email": {},
        "push": {},
    }
    for row in rows:
        status = row.get("status")
        if status in {"queued", "sending"}:
            summary["pending"] += 1
        elif status == "sent":
            summary["sent"] += 1
        elif status == "opted_out":
            summary["opted_out"] += 1
        for channel in ("email", "push"):
            value = (row.get("results") or {}).get(channel)
            if value:
                summary[channel][value] = summary[channel].get(value, 0) + 1
    return summary
