"""Community Health — belonging metrics that matter more than likes.

Read-only, community-scoped aggregates computed from existing data: participation
breadth, contribution & volunteer engagement, leadership, and an honest
intergenerational proxy. No new tracking, no per-person sensitive payloads.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from db import (
    events_collection,
    memories_collection,
    payments_collection,
    threads_collection,
    users_collection,
)
from dependencies import get_current_user

router = APIRouter(prefix="/api")


@router.get("/community/health")
async def community_health(current_user: dict[str, Any] = Depends(get_current_user)):
    community_id = current_user["community_id"]
    now = datetime.now(timezone.utc)
    window_iso = (now - timedelta(days=90)).isoformat()

    members = await users_collection.find(
        {"community_id": community_id}, {"_id": 0, "id": 1, "full_name": 1, "role": 1, "created_at": 1}
    ).to_list(2000)
    members_total = len(members)
    member_ids = {m["id"] for m in members}

    memories = await memories_collection.find(
        {"community_id": community_id}, {"_id": 0, "created_by": 1, "created_at": 1}
    ).to_list(3000)
    threads = await threads_collection.find(
        {"community_id": community_id}, {"_id": 0, "created_by": 1, "created_at": 1, "category": 1, "elder_name": 1}
    ).to_list(3000)

    content = memories + threads
    contributors = {d.get("created_by") for d in content if d.get("created_by")}
    recent_contributors = {
        d.get("created_by") for d in content
        if d.get("created_by") and (d.get("created_at") or "") >= window_iso
    }

    events = await events_collection.find(
        {
            "community_id": community_id,
            "hidden_from_user_ids": {"$ne": current_user["id"]},
        },
        {"_id": 0, "rsvp_records": 1, "volunteer_slots": 1},
    ).to_list(3000)
    rsvp_participants = set()
    volunteers = set()
    for event in events:
        for record in event.get("rsvp_records", []):
            uid = record.get("user_id")
            if uid and record.get("status") in ("going", "maybe"):
                rsvp_participants.add(uid)
        for slot in event.get("volunteer_slots", []):
            for name in slot.get("assigned_members", []):
                if name:
                    volunteers.add(name)

    # Active = members who recently created content OR RSVP'd. Public-link RSVPs
    # (user_id "invite:…") aren't members, so intersecting with member_ids drops them.
    active = (recent_contributors | rsvp_participants) & member_ids
    participation_rate = round(100 * len(active) / members_total) if members_total else 0

    paid = await payments_collection.find(
        {"community_id": community_id, "payment_status": "paid"}, {"_id": 0, "amount": 1, "user_id": 1, "user_email": 1}
    ).to_list(3000)
    funds_raised = round(sum(p.get("amount", 0) or 0 for p in paid), 2)
    financial_contributors = len({(p.get("user_id") or p.get("user_email")) for p in paid if (p.get("user_id") or p.get("user_email"))})

    stewards = [m for m in members if (m.get("role") or "member") not in ("member", "")]

    elder_voices = len([t for t in threads if (t.get("elder_name") or "").strip()])
    youth_reflections = len([t for t in threads if t.get("category") == "youth-reflection"])

    return {
        "generated_at": now.isoformat(),
        "members_total": members_total,
        "participation": {"active": len(active), "total": members_total, "rate": participation_rate},
        "contribution": {
            "content_contributors": len(contributors),
            "funds_raised": funds_raised,
            "financial_contributors": financial_contributors,
            "volunteers": len(volunteers),
        },
        "leadership": {
            "stewards": len(stewards),
            "roles": sorted({(m.get("role") or "member") for m in stewards}),
        },
        "intergenerational": {"elder_voices": elder_voices, "youth_reflections": youth_reflections},
        "archive": {"gatherings": len(events), "memories": len(memories), "stories": len(threads)},
    }
