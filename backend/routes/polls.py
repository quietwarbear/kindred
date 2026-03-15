"""Polls routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import polls_collection
from dependencies import ensure_minimum_role, get_current_user, log_notification_event, now_iso
from models import PollCreateRequest, PollVoteRequest

router = APIRouter(prefix="/api")


@router.get("/polls")
async def list_polls(current_user: dict[str, Any] = Depends(get_current_user)):
    polls = await polls_collection.find(
        {"community_id": current_user["community_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    for poll in polls:
        for option in poll.get("options", []):
            option["vote_count"] = len(option.get("voter_ids", []))
            option["voted_by_me"] = current_user["id"] in option.get("voter_ids", [])
            option.pop("voter_ids", None)
        poll["total_votes"] = sum(o["vote_count"] for o in poll.get("options", []))
    return {"polls": polls}


@router.post("/polls")
async def create_poll(payload: PollCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    poll_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "options": [
            {"id": str(uuid.uuid4()), "text": opt.text.strip(), "voter_ids": []}
            for opt in payload.options
        ],
        "allow_multiple": payload.allow_multiple,
        "is_active": True,
        "closes_at": payload.closes_at,
        "created_at": now_iso(),
    }
    await polls_collection.insert_one(poll_doc.copy())
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="poll-create",
        title=f"New poll: {poll_doc['title']}",
        description=f"{current_user['full_name']} started a vote with {len(payload.options)} options.",
        related_id=poll_doc["id"],
        audience_scope="community",
    )
    for option in poll_doc["options"]:
        option["vote_count"] = 0
        option["voted_by_me"] = False
        option.pop("voter_ids", None)
    poll_doc["total_votes"] = 0
    return poll_doc


@router.post("/polls/{poll_id}/vote")
async def vote_on_poll(poll_id: str, payload: PollVoteRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    poll_doc = await polls_collection.find_one(
        {"id": poll_id, "community_id": current_user["community_id"]}, {"_id": 0}
    )
    if not poll_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found.")
    if not poll_doc.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This poll is closed.")

    options = poll_doc.get("options", [])
    valid_option_ids = {o["id"] for o in options}
    for oid in payload.option_ids:
        if oid not in valid_option_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid option: {oid}")

    if not poll_doc.get("allow_multiple") and len(payload.option_ids) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This poll only allows a single vote.")

    for option in options:
        voter_ids = option.get("voter_ids", [])
        if current_user["id"] in voter_ids:
            voter_ids.remove(current_user["id"])
        option["voter_ids"] = voter_ids

    for option in options:
        if option["id"] in payload.option_ids:
            option["voter_ids"].append(current_user["id"])

    await polls_collection.update_one({"id": poll_id}, {"$set": {"options": options}})

    for option in options:
        option["vote_count"] = len(option.get("voter_ids", []))
        option["voted_by_me"] = current_user["id"] in option.get("voter_ids", [])
        option.pop("voter_ids", None)
    poll_doc["options"] = options
    poll_doc["total_votes"] = sum(o["vote_count"] for o in options)
    return poll_doc


@router.post("/polls/{poll_id}/close")
async def close_poll(poll_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    poll_doc = await polls_collection.find_one(
        {"id": poll_id, "community_id": current_user["community_id"]}, {"_id": 0}
    )
    if not poll_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found.")
    await polls_collection.update_one({"id": poll_id}, {"$set": {"is_active": False}})
    return {"status": "closed"}


@router.delete("/polls/{poll_id}")
async def delete_poll(poll_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    result = await polls_collection.delete_one(
        {"id": poll_id, "community_id": current_user["community_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found.")
    return {"status": "deleted"}
