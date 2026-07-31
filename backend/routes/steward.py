"""Ubuntu AI Guide — the community steward's briefing.

GET /api/steward/briefing aggregates DETERMINISTIC signals about a community
(who's new, who's gone quiet, a memory worth resurfacing, recent gatherings) and
asks ai_steward to phrase them warmly. The facts are computed here from real data;
the LLM only supplies wording, so the steward never invents people or events.

Read-only and side-effect-free: it suggests, it does not act. Available to any
member; nothing here exposes sensitive payloads (only names + public titles).
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from ai_steward import generate_steward_notes
from ai_gathering import generate_community_history
from db import (
    events_collection,
    memories_collection,
    threads_collection,
    users_collection,
)
from dependencies import get_community_for_user, get_current_user, now_iso
from memory_privacy import visible_memory_query_for_user

router = APIRouter(prefix="/api")


def _parse(iso: str):
    try:
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


@router.get("/steward/briefing")
async def steward_briefing(current_user: dict[str, Any] = Depends(get_current_user)):
    community = await get_community_for_user(current_user)
    community_id = current_user["community_id"]
    now = datetime.now(timezone.utc)

    members = await users_collection.find(
        {"community_id": community_id},
        {"_id": 0, "id": 1, "full_name": 1, "created_at": 1},
    ).to_list(1000)

    # --- Newest member (welcome candidate): joined within the last 21 days ---
    dated = [m for m in members if m.get("created_at")]
    dated.sort(key=lambda m: m["created_at"], reverse=True)
    newest = None
    if dated:
        top_dt = _parse(dated[0]["created_at"])
        if top_dt and now - top_dt <= timedelta(days=21):
            newest = dated[0]

    # --- Contributors vs. quiet members (deterministic) ---
    memory_query = await visible_memory_query_for_user(current_user)
    mem_authors = await memories_collection.distinct("created_by", memory_query)
    thr_authors = await threads_collection.distinct(
        "created_by", {"community_id": community_id}
    )
    contributors = {a for a in (mem_authors + thr_authors) if a}

    quiet = []
    for m in members:
        if m["id"] in contributors:
            continue
        if newest and m["id"] == newest["id"]:
            continue
        joined = _parse(m.get("created_at", ""))
        if joined and now - joined < timedelta(days=14):
            continue  # too new to count as 'quiet'
        quiet.append({"id": m["id"], "name": m.get("full_name", "")})
    quiet = quiet[:4]

    # --- A memory or story worth resurfacing (oldest with a title) ---
    rediscover = None
    oldest_mem = (
        await memories_collection.find(
            await visible_memory_query_for_user(
                current_user,
                title={"$nin": ["", None]},
            ),
            {"_id": 0, "id": 1, "title": 1},
        )
        .sort("created_at", 1)
        .to_list(1)
    )
    if oldest_mem:
        rediscover = {
            "type": "memory",
            "id": oldest_mem[0]["id"],
            "title": oldest_mem[0].get("title", ""),
        }
    else:
        oldest_thr = (
            await threads_collection.find(
                {"community_id": community_id, "title": {"$nin": ["", None]}},
                {"_id": 0, "id": 1, "title": 1},
            )
            .sort("created_at", 1)
            .to_list(1)
        )
        if oldest_thr:
            rediscover = {
                "type": "thread",
                "id": oldest_thr[0]["id"],
                "title": oldest_thr[0].get("title", ""),
            }

    # --- Recent gathering titles (context for the suggestion) ---
    recent_events = (
        await events_collection.find(
            {
                "community_id": community_id,
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            {"_id": 0, "title": 1},
        )
        .sort("start_at", -1)
        .to_list(5)
    )
    recent_gatherings = [e.get("title", "") for e in recent_events if e.get("title")]

    # --- Warm wording from the steward (graceful fallback if no key) ---
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gpt-4o-mini")
    notes = await generate_steward_notes(
        api_key,
        model,
        {
            "community_name": community.get("name", ""),
            "community_type": community.get("community_type", "community"),
            "new_member_name": newest.get("full_name", "") if newest else "",
            "quiet_member_names": [q["name"] for q in quiet],
            "rediscover_title": rediscover["title"] if rediscover else "",
            "recent_gatherings": recent_gatherings,
        },
    )

    return {
        "community_name": community.get("name", ""),
        "generated_at": now_iso(),
        "ai_enabled": bool(api_key),
        "welcome": (
            {
                "member_id": newest["id"],
                "member_name": newest.get("full_name", ""),
                "message": notes["welcome_message"],
            }
            if newest and notes["welcome_message"]
            else None
        ),
        "quiet_members": quiet,
        "rediscover": (
            {**rediscover, "note": notes["rediscover_note"]} if rediscover else None
        ),
        "suggested_gathering": notes["gathering_idea"],
        "reflection": notes["reflection"],
    }


@router.post("/steward/history")
async def steward_history(current_user: dict[str, Any] = Depends(get_current_user)):
    """Weave the community's archive into a narrated chronicle."""
    community = await get_community_for_user(current_user)
    community_id = current_user["community_id"]
    gatherings = (
        await events_collection.find(
            {
                "community_id": community_id,
                "hidden_from_user_ids": {"$ne": current_user["id"]},
            },
            {"_id": 0, "title": 1},
        )
        .sort("start_at", -1)
        .to_list(20)
    )
    memories = (
        await memories_collection.find(
            await visible_memory_query_for_user(current_user),
            {"_id": 0, "title": 1},
        )
        .sort("created_at", -1)
        .to_list(30)
    )
    threads = (
        await threads_collection.find(
            {"community_id": community_id}, {"_id": 0, "title": 1}
        )
        .sort("created_at", -1)
        .to_list(30)
    )

    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gpt-4o-mini")
    history = await generate_community_history(
        api_key,
        model,
        {
            "community_name": community.get("name", ""),
            "community_type": community.get("community_type", "community"),
            "gatherings": [g.get("title", "") for g in gatherings if g.get("title")],
            "memories": [m.get("title", "") for m in memories if m.get("title")],
            "stories": [t.get("title", "") for t in threads if t.get("title")],
        },
    )
    return {"history": history, "ai_enabled": bool(api_key)}
