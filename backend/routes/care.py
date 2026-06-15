"""Care infrastructure — the Circle of Care.

Answers the Ubuntu question "are we cared for?": meal trains (claimable slots, like the
potluck pattern), check-ins, and milestones. Available to every member; when a circle opens
the community is notified so people can rally. Read/write is community-scoped.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import care_circles_collection, users_collection
from dependencies import ensure_minimum_role, get_current_user, log_notification_event, now_iso
from models import CareCircleCreateRequest, CareClaimRequest, CareSlotAddRequest

router = APIRouter(prefix="/api")

KIND_LABELS = {
    "meal-train": "a meal train",
    "check-in": "a check-in",
    "milestone": "a milestone",
    "support": "support",
}


async def _get_circle(circle_id: str, current_user: dict[str, Any]) -> dict[str, Any]:
    circle = await care_circles_collection.find_one(
        {"id": circle_id, "community_id": current_user["community_id"]}, {"_id": 0}
    )
    if not circle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Care circle not found.")
    return circle


@router.get("/care")
async def list_care(current_user: dict[str, Any] = Depends(get_current_user)):
    circles = await care_circles_collection.find(
        {"community_id": current_user["community_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"circles": circles}


@router.post("/care")
async def create_care(payload: CareCircleCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    for_name = (payload.for_name or "").strip()
    if payload.for_member_id:
        member = await users_collection.find_one(
            {"id": payload.for_member_id, "community_id": current_user["community_id"]}, {"_id": 0, "full_name": 1}
        )
        if member:
            for_name = member.get("full_name", for_name)

    slots = [
        {"id": str(uuid.uuid4()), "label": (s.label or "").strip(), "item": (s.item or "").strip(), "claimed_by": "", "claimed_by_name": ""}
        for s in (payload.slots or []) if (s.label or s.item)
    ]
    doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "kind": payload.kind,
        "title": payload.title.strip(),
        "note": (payload.note or "").strip(),
        "for_member_id": payload.for_member_id,
        "for_name": for_name,
        "milestone_type": (payload.milestone_type or "").strip(),
        "status": "open",
        "slots": slots,
        "created_at": now_iso(),
    }
    await care_circles_collection.insert_one(doc.copy())
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="care-circle",
        title=f"Circle of care: {doc['title']}",
        description=f"{current_user['full_name']} started {KIND_LABELS.get(payload.kind, 'support')}"
        + (f" for {for_name}" if for_name else "") + ".",
        related_id=doc["id"],
        audience_scope="community",
    )
    return doc


@router.post("/care/{circle_id}/slots")
async def add_care_slot(circle_id: str, payload: CareSlotAddRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    circle = await _get_circle(circle_id, current_user)
    slots = circle.get("slots", [])
    slots.append({"id": str(uuid.uuid4()), "label": (payload.label or "").strip(), "item": payload.item.strip(), "claimed_by": "", "claimed_by_name": ""})
    await care_circles_collection.update_one({"id": circle_id}, {"$set": {"slots": slots}})
    circle["slots"] = slots
    return circle


@router.post("/care/{circle_id}/claim")
async def claim_care_slot(circle_id: str, payload: CareClaimRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    circle = await _get_circle(circle_id, current_user)
    slots = circle.get("slots", [])
    found = False
    for s in slots:
        if s.get("id") == payload.slot_id:
            found = True
            if s.get("claimed_by") and s.get("claimed_by") != current_user["id"]:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Someone's already got this one.")
            if s.get("claimed_by") == current_user["id"]:
                s["claimed_by"] = ""
                s["claimed_by_name"] = ""
            else:
                s["claimed_by"] = current_user["id"]
                s["claimed_by_name"] = current_user["full_name"]
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found.")
    await care_circles_collection.update_one({"id": circle_id}, {"$set": {"slots": slots}})
    circle["slots"] = slots
    return circle


@router.post("/care/{circle_id}/close")
async def close_care(circle_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    circle = await _get_circle(circle_id, current_user)
    if circle.get("created_by") != current_user["id"]:
        ensure_minimum_role(current_user, "organizer")
    await care_circles_collection.update_one({"id": circle_id}, {"$set": {"status": "closed"}})
    circle["status"] = "closed"
    return circle
