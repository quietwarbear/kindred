"""Weekly community digest routes.

Reuses the community-overview aggregation and the Resend email pipeline
(email_service) to send each member a warm weekly summary of their community.

Endpoints
- POST /api/digest/preview   (any member)      -> digest data + rendered HTML, no send
- POST /api/digest/send      (organizer+)       -> send to every member of the caller's community
- POST /api/digest/run-all   (platform admin)   -> send to every community; this is what a
                                                    scheduler should hit weekly (see SCHEDULING note)

SCHEDULING: there is intentionally no in-process cron here. Trigger /api/digest/run-all
weekly from an external scheduler (Railway cron, GitHub Actions, or an uptime pinger)
authenticated as the platform admin. Keeping the trigger external avoids a background
loop competing with the request workers and keeps sends idempotent per call.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import (
    communities_collection,
    events_collection,
    memories_collection,
    payments_collection,
    threads_collection,
    users_collection,
)
from dependencies import ensure_minimum_role, get_current_user
from email_service import build_digest_body, send_community_digest

router = APIRouter(prefix="/api")


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

    member_count = await users_collection.count_documents({"community_id": community_id})

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    new_members = await users_collection.count_documents(
        {"community_id": community_id, "created_at": {"$gte": week_ago}}
    )

    upcoming = await events_collection.find(
        {"community_id": community_id}, {"_id": 0, "title": 1, "start_at": 1, "location": 1}
    ).sort("start_at", 1).to_list(5)
    upcoming_events = [
        {"title": e.get("title", ""), "when": _fmt_when(e.get("start_at", "")), "location": e.get("location", "")}
        for e in upcoming
    ]

    memories = await memories_collection.find(
        {"community_id": community_id, "created_at": {"$gte": week_ago}}, {"_id": 0, "title": 1}
    ).sort("created_at", -1).to_list(4)
    threads = await threads_collection.find(
        {"community_id": community_id, "created_at": {"$gte": week_ago}}, {"_id": 0, "title": 1, "category": 1}
    ).sort("created_at", -1).to_list(4)

    funds_agg = await payments_collection.aggregate([
        {"$match": {"community_id": community_id, "payment_status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    funds_raised = round(funds_agg[0]["total"], 2) if funds_agg else 0.0

    return {
        "community_id": community_id,
        "community_name": community.get("name", "your community"),
        "member_count": member_count,
        "new_members": new_members,
        "upcoming_events": upcoming_events,
        "recent_memories": memories,
        "recent_threads": threads,
        "funds_raised": funds_raised,
    }


async def _send_to_members(community_id: str) -> dict:
    """Build the digest and send it to every member with an email address."""
    digest = await _build_digest(community_id)
    if not digest:
        return {"community_id": community_id, "sent": 0, "skipped": 0, "found": False}

    members = await users_collection.find(
        {"community_id": community_id}, {"_id": 0, "email": 1}
    ).to_list(2000)

    sent = 0
    skipped = 0
    for member in members:
        email = (member.get("email") or "").strip()
        if not email:
            skipped += 1
            continue
        ok = await send_community_digest(email, digest)
        sent += 1 if ok else 0
        skipped += 0 if ok else 1

    return {
        "community_id": community_id,
        "community_name": digest["community_name"],
        "sent": sent,
        "skipped": skipped,
        "found": True,
    }


@router.post("/digest/preview")
async def digest_preview(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return the digest data and rendered HTML for the caller's community (no send)."""
    digest = await _build_digest(current_user["community_id"])
    if not digest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found.")
    return {"digest": digest, "html_body": build_digest_body(digest)}


@router.post("/digest/send")
async def digest_send(current_user: dict[str, Any] = Depends(get_current_user)):
    """Send this week's digest to every member of the caller's community (organizer+)."""
    ensure_minimum_role(current_user, "organizer")
    return await _send_to_members(current_user["community_id"])


@router.post("/digest/run-all")
async def digest_run_all(current_user: dict[str, Any] = Depends(get_current_user)):
    """Send the weekly digest to every community. Platform-admin only; called by a scheduler."""
    if not current_user.get("is_platform_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin only.")

    communities = await communities_collection.find({}, {"_id": 0, "id": 1}).to_list(5000)
    results = [await _send_to_members(c["id"]) for c in communities if c.get("id")]
    return {
        "communities": len(results),
        "total_sent": sum(r["sent"] for r in results),
        "total_skipped": sum(r["skipped"] for r in results),
        "results": results,
    }
