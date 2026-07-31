"""Weekly community digest routes.

Reuses the community-overview aggregation and the Resend email pipeline
(email_service) to send each member a warm weekly summary of their community.

Endpoints
- POST /api/digest/preview   (any member)    -> digest data + rendered HTML, no send
- POST /api/digest/send      (organizer+)    -> send NOW to the caller's community (force)
- POST /api/digest/run-all   (platform admin)-> send to every community (idempotent)
- POST /api/digest/cron      (header secret) -> same as run-all; for an external scheduler

SCHEDULING: no in-process cron. Point a weekly external trigger (Railway cron, GitHub
Actions, or a free pinger like cron-job.org) at POST /api/digest/cron with the header
`X-Digest-Cron-Key: <DIGEST_CRON_KEY>`. Sends are made idempotent by a per-community
`last_digest_sent_at` guard (DIGEST_MIN_INTERVAL_DAYS), so an over-eager trigger never
double-sends. Members who unsubscribed (`digest_opt_out`) are skipped.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from db import (
    communities_collection,
    events_collection,
    memories_collection,
    payments_collection,
    threads_collection,
    users_collection,
)
from dependencies import (
    ensure_minimum_role,
    get_current_user,
    hidden_event_ids_for_user,
    now_iso,
)
from email_service import build_digest_body, send_community_digest

router = APIRouter(prefix="/api")

DIGEST_MIN_INTERVAL_DAYS = 6
DIGEST_CRON_KEY = os.environ.get("DIGEST_CRON_KEY", "")
BACKEND_PUBLIC_URL = os.environ.get(
    "PUBLIC_BACKEND_URL", "https://kindred-production-badd.up.railway.app"
).rstrip("/")


def _fmt_when(start_at: str) -> str:
    """Light, dependency-free formatting of a stored ISO datetime for email."""
    if not start_at:
        return ""
    try:
        dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
        return dt.strftime("%a %b %-d, %-I:%M %p")
    except (ValueError, AttributeError):
        return str(start_at)[:16].replace("T", " ")


async def _build_digest(community_id: str) -> dict:
    """Aggregate a single community's week into the digest payload shape."""
    community = await communities_collection.find_one({"id": community_id}, {"_id": 0})
    if not community:
        return {}

    member_count = await users_collection.count_documents(
        {"community_id": community_id}
    )

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    new_members = await users_collection.count_documents(
        {"community_id": community_id, "created_at": {"$gte": week_ago}}
    )

    upcoming = (
        await events_collection.find(
            {"community_id": community_id},
            {
                "_id": 0,
                "title": 1,
                "start_at": 1,
                "location": 1,
                "hidden_from_user_ids": 1,
            },
        )
        .sort("start_at", 1)
        .to_list(15)
    )
    # Keep each event's hidden-from list internally so we can drop surprise gatherings
    # per-recipient in _send_to_members (the digest is built once, sent to many).
    upcoming_events = [
        {
            "title": e.get("title", ""),
            "when": _fmt_when(e.get("start_at", "")),
            "location": e.get("location", ""),
            "_hidden_from": e.get("hidden_from_user_ids") or [],
        }
        for e in upcoming
    ]

    memories = (
        await memories_collection.find(
            {
                "community_id": community_id,
                "created_at": {"$gte": week_ago},
                "capsule_status": {"$ne": "draft"},
            },
            {"_id": 0, "title": 1, "event_id": 1},
        )
        .sort("created_at", -1)
        .to_list(4)
    )
    threads = (
        await threads_collection.find(
            {"community_id": community_id, "created_at": {"$gte": week_ago}},
            {"_id": 0, "title": 1, "category": 1},
        )
        .sort("created_at", -1)
        .to_list(4)
    )

    funds_agg = await payments_collection.aggregate(
        [
            {"$match": {"community_id": community_id, "payment_status": "paid"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
    ).to_list(1)
    funds_raised = round(funds_agg[0]["total"], 2) if funds_agg else 0.0

    return {
        "community_id": community_id,
        "community_name": community.get("name", "your community"),
        "member_count": member_count,
        "new_members": new_members,
        "upcoming_events": upcoming_events,
        "recent_memories": [
            {
                "title": memory.get("title", ""),
                "_event_id": memory.get("event_id", ""),
            }
            for memory in memories
        ],
        "recent_threads": threads,
        "funds_raised": funds_raised,
    }


async def _visible_digest_for_user(digest: dict, user: dict) -> dict:
    """Strip records derived from events concealed from this recipient."""
    hidden_ids = set(await hidden_event_ids_for_user(user))
    return {
        **digest,
        "upcoming_events": [
            {key: value for key, value in event.items() if key != "_hidden_from"}
            for event in digest.get("upcoming_events", [])
            if user["id"] not in (event.get("_hidden_from") or [])
        ],
        "recent_memories": [
            {key: value for key, value in memory.items() if key != "_event_id"}
            for memory in digest.get("recent_memories", [])
            if not memory.get("_event_id") or memory.get("_event_id") not in hidden_ids
        ],
    }


async def _recently_sent(community_id: str) -> bool:
    community = await communities_collection.find_one(
        {"id": community_id}, {"_id": 0, "last_digest_sent_at": 1}
    )
    last = (community or {}).get("last_digest_sent_at")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        return datetime.now(timezone.utc) - last_dt < timedelta(
            days=DIGEST_MIN_INTERVAL_DAYS
        )
    except (ValueError, TypeError):
        return False


async def _send_to_members(community_id: str, force: bool = False) -> dict:
    """Build the digest and send it to every opted-in member with an email address."""
    digest = await _build_digest(community_id)
    if not digest:
        return {"community_id": community_id, "sent": 0, "skipped": 0, "found": False}

    if not force and await _recently_sent(community_id):
        return {
            "community_id": community_id,
            "community_name": digest["community_name"],
            "sent": 0,
            "skipped": 0,
            "opted_out": 0,
            "found": True,
            "throttled": True,
        }

    members = await users_collection.find(
        {"community_id": community_id},
        {
            "_id": 0,
            "id": 1,
            "email": 1,
            "digest_opt_out": 1,
            "digest_unsubscribe_token": 1,
        },
    ).to_list(2000)

    sent = 0
    skipped = 0
    opted_out = 0
    for member in members:
        email = (member.get("email") or "").strip()
        if not email:
            skipped += 1
            continue
        if member.get("digest_opt_out"):
            opted_out += 1
            continue

        token = member.get("digest_unsubscribe_token")
        if not token:
            token = uuid.uuid4().hex
            await users_collection.update_one(
                {"id": member["id"]}, {"$set": {"digest_unsubscribe_token": token}}
            )

        member_digest = {
            **await _visible_digest_for_user(
                digest,
                {"id": member["id"], "community_id": community_id},
            ),
            "unsubscribe_url": f"{BACKEND_PUBLIC_URL}/api/public/digest/unsubscribe/{token}",
        }
        member_digest["upcoming_events"] = member_digest["upcoming_events"][:5]
        ok = await send_community_digest(email, member_digest)
        sent += 1 if ok else 0
        skipped += 0 if ok else 1

    await communities_collection.update_one(
        {"id": community_id}, {"$set": {"last_digest_sent_at": now_iso()}}
    )

    return {
        "community_id": community_id,
        "community_name": digest["community_name"],
        "sent": sent,
        "skipped": skipped,
        "opted_out": opted_out,
        "found": True,
    }


async def _run_all(force: bool = False) -> dict:
    communities = await communities_collection.find({}, {"_id": 0, "id": 1}).to_list(
        5000
    )
    results = [
        await _send_to_members(c["id"], force=force) for c in communities if c.get("id")
    ]
    return {
        "communities": len(results),
        "total_sent": sum(r.get("sent", 0) for r in results),
        "total_skipped": sum(r.get("skipped", 0) for r in results),
        "results": results,
    }


@router.post("/digest/preview")
async def digest_preview(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return the digest data and rendered HTML for the caller's community (no send)."""
    digest = await _build_digest(current_user["community_id"])
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found."
        )
    visible_digest = await _visible_digest_for_user(digest, current_user)
    return {
        "digest": visible_digest,
        "html_body": build_digest_body(visible_digest),
    }


@router.post("/digest/send")
async def digest_send(current_user: dict[str, Any] = Depends(get_current_user)):
    """Send this week's digest NOW to every member of the caller's community (organizer+)."""
    ensure_minimum_role(current_user, "organizer")
    return await _send_to_members(current_user["community_id"], force=True)


@router.post("/digest/run-all")
async def digest_run_all(current_user: dict[str, Any] = Depends(get_current_user)):
    """Send the weekly digest to every community (idempotent). Platform-admin only."""
    if not current_user.get("is_platform_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin only."
        )
    return await _run_all(force=False)


@router.post("/digest/cron")
async def digest_cron(x_digest_cron_key: str = Header(default="")):
    """Weekly scheduler hook. Auth via the X-Digest-Cron-Key header, not a user token."""
    if not DIGEST_CRON_KEY or x_digest_cron_key != DIGEST_CRON_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid cron key."
        )
    return await _run_all(force=False)
