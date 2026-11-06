"""K5 routes: event messaging settings, audience preview, cron, unsubscribe.

Announcements themselves are still created at ``POST /api/announcements``
(routes/communications.py); this module owns everything around them.

SCHEDULING: no in-process scheduler. Point an external cron (Railway cron
service, GitHub Actions, or any HTTP pinger) at ``POST /api/event-messages/cron``
every 5 minutes with the header ``X-Event-Messages-Cron-Key:
<EVENT_MESSAGES_CRON_KEY>``. Each call queues the reminders that are due and
sends whatever is queued. Concurrent calls (several replicas, an over-eager
scheduler) are safe: rows are unique per recipient and claimed atomically.
"""

from __future__ import annotations

import hmac
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import HTMLResponse

from db import (
    announcements_collection,
    event_message_opt_outs_collection,
    event_message_outbox_collection,
    events_collection,
    notification_events_collection,
    notification_preferences_collection,
    users_collection,
)
from dependencies import (
    ensure_minimum_role,
    get_current_user,
    get_event_for_user,
    now_iso,
)
from event_messaging import (
    DeliveryContext,
    STUCK_SENDING_AFTER,
    activity_offsets,
    announcement_rows,
    audience_label,
    clean_sender_name,
    community_audience,
    drain_outbox,
    email_flag_enabled,
    enqueue,
    event_days,
    hydrate_recipients,
    messaging_settings,
    normalize_offsets,
    now_utc,
    plan_due_reminders,
    resolve_event_audience,
    sender_domain_verified,
    summarize_rows,
    upcoming_schedule,
)
from invitation_delivery import build_invitation_delivery_provider
from itinerary import published_activities
from models import AnnouncementAudienceRequest, EventMessagingSettingsRequest
from push_sender import build_push_clients, push_enabled

router = APIRouter(prefix="/api")

CRON_HEADER = "X-Event-Messages-Cron-Key"
# A cron call stops claiming new messages after this many seconds; the rest
# go out on the next tick. Keep it under the cron interval and HTTP timeout.
CRON_SEND_BUDGET_SECONDS = 240


def _email_interval_seconds() -> float:
    try:
        per_second = float(os.environ.get("EVENT_MESSAGES_EMAIL_PER_SECOND", "2"))
    except ValueError:
        per_second = 2.0
    return 1.0 / per_second if per_second > 0 else 0.0


def _cron_key() -> str:
    return os.environ.get("EVENT_MESSAGES_CRON_KEY", "")


def _app_url() -> str:
    return os.environ.get("APP_URL", "https://www.heykindred.org").rstrip("/")


def _public_api_url() -> str:
    return os.environ.get(
        "PUBLIC_BACKEND_URL", "https://kindred-production-badd.up.railway.app"
    ).rstrip("/")


def email_provider():
    """The Resend provider, only when enabled AND the sender is verified."""
    if not email_flag_enabled() or not sender_domain_verified():
        return None
    return build_invitation_delivery_provider()


def delivery_context() -> DeliveryContext:
    push_ready = push_enabled()
    fcm, apns = build_push_clients() if push_ready else (None, None)
    return DeliveryContext(
        events=events_collection,
        users=users_collection,
        preferences=notification_preferences_collection,
        opt_outs=event_message_opt_outs_collection,
        announcements=announcements_collection,
        notifications=notification_events_collection,
        outbox=event_message_outbox_collection,
        provider=email_provider(),
        push_client=fcm,
        apns_client=apns,
        push_ready=push_ready,
        app_url=_app_url(),
        public_api_url=_public_api_url(),
        now=now_utc(),
        email_interval_seconds=_email_interval_seconds(),
    )


def delivery_readiness() -> dict[str, Any]:
    return {
        "email": "ready" if email_provider() is not None else (
            "unverified_sender" if email_flag_enabled() and not sender_domain_verified() else "off"
        ),
        "push": "ready" if push_enabled() else "off",
        "scheduler": "configured" if _cron_key() else "not_configured",
    }


async def recipients_for(
    event: dict[str, Any] | None,
    community_id: str,
    *,
    audience: str,
    day: str = "",
    activity_id: str = "",
) -> list[dict[str, str]]:
    if event is None:
        return await community_audience(users_collection, community_id)
    try:
        recipients = resolve_event_audience(
            event, audience=audience, day=day, activity_id=activity_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": str(exc)},
        ) from exc
    return await hydrate_recipients(recipients, users_collection, community_id)


async def queue_announcement(
    announcement: dict[str, Any],
    recipients: list[dict[str, str]],
    channels: list[str],
) -> dict[str, int]:
    return await enqueue(
        event_message_outbox_collection,
        announcement_rows(announcement, recipients, channels),
    )


async def dispatch_announcement(announcement_id: str) -> None:
    """Background send for one announcement. The cron picks up anything left."""
    try:
        await drain_outbox(
            delivery_context(), limit=5000, extra={"announcement_id": announcement_id}
        )
    except Exception:
        return


async def _organizer_event(event_id: str, user: dict[str, Any]) -> dict[str, Any]:
    ensure_minimum_role(user, "organizer")
    return await get_event_for_user(event_id, user)


async def _reply_to_options(community_id: str) -> list[dict[str, str]]:
    organizers = await users_collection.find(
        {"community_id": community_id, "role": {"$in": ["host", "organizer"]}},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1},
    ).to_list(200)
    return [
        {"id": u["id"], "name": u.get("full_name", ""), "email": u.get("email", "")}
        for u in organizers
        if u.get("id") and u.get("email")
    ]


def _settings_view(event: dict[str, Any], options: list[dict[str, str]]) -> dict[str, Any]:
    settings = messaging_settings(event)
    reply_to_id = settings["reply_to_user_id"] or str(event.get("created_by") or "")
    reply_to = next((o for o in options if o["id"] == reply_to_id), None)
    activities = [
        {
            "id": activity.get("id", ""),
            "title": activity.get("title", ""),
            "start_at": activity.get("start_at", ""),
            "timezone": activity.get("timezone") or event.get("timezone") or "UTC",
            "uses_default": str(activity.get("id")) not in settings["activity_reminder_offsets_minutes"],
            "offsets_minutes": activity_offsets(event, activity),
        }
        for activity in published_activities(event)
    ]
    return {
        "event_id": event["id"],
        "settings": {**settings, "reply_to_user_id": reply_to_id},
        "reply_to": reply_to,
        "reply_to_options": options,
        "default_sender_name": clean_sender_name(event.get("created_by_name") or ""),
        "activities": activities,
        "days": [{"day": d["day"], "activity_count": len(d["activity_ids"])} for d in event_days(event)],
        "upcoming_reminders": upcoming_schedule(event, now_utc()),
        "delivery": delivery_readiness(),
    }


@router.get("/events/{event_id}/messaging")
async def get_event_messaging(
    event_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    event = await _organizer_event(event_id, current_user)
    return _settings_view(event, await _reply_to_options(current_user["community_id"]))


@router.put("/events/{event_id}/messaging")
async def update_event_messaging(
    event_id: str,
    payload: EventMessagingSettingsRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_event(event_id, current_user)
    options = await _reply_to_options(current_user["community_id"])
    reply_to_user_id = payload.reply_to_user_id.strip()
    if reply_to_user_id and reply_to_user_id not in {o["id"] for o in options}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "reply_to_must_be_an_organizer"},
        )
    activity_ids = {str(a.get("id")) for a in event.get("agenda", []) if a.get("id")}
    try:
        default_offsets = normalize_offsets(payload.default_reminder_offsets_minutes)
        overrides = {
            activity_id: normalize_offsets(offsets)
            for activity_id, offsets in payload.activity_reminder_offsets_minutes.items()
            if activity_id in activity_ids
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": str(exc)},
        ) from exc
    messaging = {
        "sender_name": clean_sender_name(payload.sender_name),
        "reply_to_user_id": reply_to_user_id,
        "reminders_enabled": payload.reminders_enabled,
        "default_reminder_offsets_minutes": default_offsets,
        "activity_reminder_offsets_minutes": overrides,
        "updated_at": now_iso(),
        "updated_by": current_user["id"],
    }
    # A distinct field: the RSVP compare-and-swap writes only the fields it
    # changes, so this cannot clobber (or be clobbered by) a concurrent RSVP.
    await events_collection.update_one(
        {"id": event_id, "community_id": current_user["community_id"]},
        {"$set": {"messaging": messaging}},
    )
    event["messaging"] = messaging
    return _settings_view(event, options)


@router.post("/events/{event_id}/announcements/audience")
async def preview_announcement_audience(
    event_id: str,
    payload: AnnouncementAudienceRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_event(event_id, current_user)
    recipients = await recipients_for(
        event,
        current_user["community_id"],
        audience=payload.audience,
        day=payload.day,
        activity_id=payload.activity_id,
    )
    return {
        "label": audience_label(event, payload.audience, payload.day, payload.activity_id),
        "recipients": len(recipients),
        "with_email": sum(1 for r in recipients if r.get("email")),
        "with_account": sum(1 for r in recipients if r.get("member_id")),
    }


@router.get("/events/{event_id}/announcements")
async def list_event_announcements(
    event_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    await _organizer_event(event_id, current_user)
    announcements = await announcements_collection.find(
        {"community_id": current_user["community_id"], "event_id": event_id},
        {"_id": 0, "recipient_user_ids": 0, "read_by_ids": 0},
    ).sort("created_at", -1).to_list(100)
    for announcement in announcements:
        rows = await event_message_outbox_collection.find(
            {"announcement_id": announcement["id"]},
            {"_id": 0, "status": 1, "results": 1},
        ).to_list(10000)
        announcement["delivery_summary"] = summarize_rows(rows)
    return {"announcements": announcements}


@router.post("/event-messages/cron")
async def event_messages_cron(
    x_event_messages_cron_key: str = Header(default="", alias=CRON_HEADER),
):
    """Scheduler hook. Auth via the cron header, not a user token."""
    key = _cron_key()
    if not key or not hmac.compare_digest(x_event_messages_cron_key.encode(), key.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid cron key.")
    ctx = delivery_context()
    ctx.deadline = time.monotonic() + CRON_SEND_BUDGET_SECONDS
    planned = await plan_due_reminders(
        events_collection=events_collection,
        outbox=event_message_outbox_collection,
        users_collection=users_collection,
        now=ctx.now,
    )
    sent = await drain_outbox(ctx, limit=1000)
    stuck = await event_message_outbox_collection.count_documents(
        {
            "status": "sending",
            "claimed_at": {"$lt": (ctx.now - STUCK_SENDING_AFTER).isoformat()},
        }
    )
    return {"planned": planned, "processed": sent, "stuck_sending": stuck, "delivery": delivery_readiness()}


# ---------------------------------------------------------------------------
# Public one-click email opt-out (token per event + address). GET only shows a
# confirmation; the change is a POST, because mail scanners prefetch links.
# ---------------------------------------------------------------------------


def _page(title: str, message: str, form_action: str = "") -> str:
    from html import escape

    action = (
        f'<form method="post" action="{escape(form_action, quote=True)}" style="margin:0;">'
        '<button type="submit" style="cursor:pointer;border:0;border-radius:999px;'
        'background:#9A3412;color:#fff;font-size:15px;font-weight:600;padding:12px 28px;">'
        "Stop these emails</button></form>"
        if form_action
        else ""
    )
    return (
        '<!doctype html><html><head><meta name="viewport" content="width=device-width,'
        'initial-scale=1"><title>Kindred</title></head><body style="font-family:'
        '-apple-system,Segoe UI,Roboto,sans-serif;background:#f9f5f0;margin:0;padding:32px;">'
        '<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;">'
        f'<h1 style="font-size:22px;color:#2d1810;margin:0 0 12px;">{escape(title)}</h1>'
        f'<p style="color:#5a4a3a;line-height:22px;margin:0 0 20px;">{escape(message)}</p>'
        f"{action}</div></body></html>"
    )


@router.get("/public/event-messages/unsubscribe/{token}", response_class=HTMLResponse)
async def event_messages_unsubscribe_confirm(token: str):
    doc = await event_message_opt_outs_collection.find_one({"token": token}, {"_id": 0, "opted_out": 1})
    if not doc:
        return HTMLResponse(
            _page("Link not recognized", "This link is no longer valid."), status_code=404
        )
    if doc.get("opted_out"):
        return HTMLResponse(
            _page("You're unsubscribed", "You won't get more emails about this event.")
        )
    return HTMLResponse(
        _page(
            "Stop emails about this event?",
            "You'll stop getting announcement and reminder emails about this event. "
            "Anything shared inside the app stays there.",
            f"/api/public/event-messages/unsubscribe/{token}",
        )
    )


@router.post("/public/event-messages/unsubscribe/{token}", response_class=HTMLResponse)
async def event_messages_unsubscribe(token: str):
    result = await event_message_opt_outs_collection.update_one(
        {"token": token}, {"$set": {"opted_out": True, "opted_out_at": now_iso()}}
    )
    if not result.matched_count:
        return HTMLResponse(
            _page("Link not recognized", "This link is no longer valid."), status_code=404
        )
    return HTMLResponse(
        _page("You're unsubscribed", "You won't get more emails about this event.")
    )


# Re-exported for routes/communications.py
__all__ = [
    "dispatch_announcement",
    "queue_announcement",
    "recipients_for",
    "router",
]
