"""Timeline, memories, and threads routes."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import communities_collection, events_collection, memories_collection, threads_collection
from dependencies import get_community_for_user, get_current_user, get_memory_for_user, get_thread_for_user, now_iso, parse_datetime_safe
from models import CommentRequest, MemoryCreateRequest, MemoryPublic, MemoryUpdateRequest, ThreadCreateRequest, ThreadPublic
from ai_tagging import generate_memory_tags

router = APIRouter(prefix="/api")


@router.get("/timeline/archive")
async def timeline_archive(current_user: dict[str, Any] = Depends(get_current_user)):
    community_id = current_user["community_id"]
    events = await events_collection.find({"community_id": community_id}, {"_id": 0}).to_list(300)
    memories = await memories_collection.find({"community_id": community_id}, {"_id": 0}).to_list(300)
    threads = await threads_collection.find({"community_id": community_id}, {"_id": 0}).to_list(300)

    timeline_items = []
    for event in events:
        timeline_items.append(
            {
                "id": event["id"],
                "type": "gathering",
                "title": event["title"],
                "subtitle": event.get("subyard_name") or event.get("event_template"),
                "description": event["description"],
                "occurred_at": event["start_at"],
                "tags": event.get("assigned_roles", []),
            }
        )
    for memory in memories:
        timeline_items.append(
            {
                "id": memory["id"],
                "type": "memory",
                "title": memory["title"],
                "subtitle": memory["event_title"],
                "description": memory.get("ai_summary") or memory["description"],
                "occurred_at": memory["created_at"],
                "tags": memory.get("tags", []),
                "image_data_url": memory.get("image_data_url"),
                "voice_note_data_url": memory.get("voice_note_data_url"),
            }
        )
    for thread in threads:
        timeline_items.append(
            {
                "id": thread["id"],
                "type": "story",
                "title": thread["title"],
                "subtitle": thread.get("elder_name") or thread.get("category"),
                "description": thread["body"],
                "occurred_at": thread["created_at"],
                "tags": [thread.get("category", "story")],
                "voice_note_data_url": thread.get("voice_note_data_url"),
            }
        )

    timeline_items.sort(key=lambda item: parse_datetime_safe(item.get("occurred_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    today = datetime.now(timezone.utc)
    anniversaries = [
        event for event in events
        if (parsed := parse_datetime_safe(event.get("start_at"))) and parsed.month == today.month and parsed.day == today.day
    ]
    return {"timeline_items": timeline_items[:300], "on_this_day": anniversaries[:5]}


@router.get("/timeline/export")
async def timeline_export(
    format: str = "json",
    item_type: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Export timeline data as JSON or CSV."""
    from fastapi.responses import Response as FastResponse
    community_id = current_user["community_id"]
    events = await events_collection.find({"community_id": community_id}, {"_id": 0}).to_list(500)
    memories = await memories_collection.find({"community_id": community_id}, {"_id": 0}).to_list(500)
    threads = await threads_collection.find({"community_id": community_id}, {"_id": 0}).to_list(500)

    rows = []
    if not item_type or item_type == "gathering":
        for e in events:
            rows.append({"type": "gathering", "title": e["title"], "description": e.get("description", ""), "date": e.get("start_at", ""), "location": e.get("location", ""), "tags": ", ".join(e.get("assigned_roles", []))})
    if not item_type or item_type == "memory":
        for m in memories:
            rows.append({"type": "memory", "title": m["title"], "description": m.get("description", ""), "date": m.get("created_at", ""), "location": "", "tags": ", ".join(m.get("tags", []))})
    if not item_type or item_type == "story":
        for t in threads:
            rows.append({"type": "story", "title": t["title"], "description": t.get("body", ""), "date": t.get("created_at", ""), "location": "", "tags": t.get("category", "")})

    rows.sort(key=lambda r: r.get("date", ""), reverse=True)

    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["type", "title", "description", "date", "location", "tags"])
        writer.writeheader()
        writer.writerows(rows)
        return FastResponse(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=kindred_timeline.csv"},
        )

    return {"items": rows, "total": len(rows)}


@router.get("/memories", response_model=list[MemoryPublic])
async def list_memories(current_user: dict[str, Any] = Depends(get_current_user)):
    memories = await memories_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return memories


@router.post("/memories", response_model=MemoryPublic)
async def create_memory(payload: MemoryCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    event_title = ""
    if payload.event_id:
        event_doc = await events_collection.find_one({"id": payload.event_id, "community_id": current_user["community_id"]}, {"_id": 0})
        if event_doc:
            event_title = event_doc.get("title", "")

    # Get community info for AI tagging
    community_doc = await get_community_for_user(current_user)
    
    ai_tags = []
    ai_summary = ""
    if payload.description.strip():
        api_key = os.environ.get("OPENAI_API_KEY", "")
        model = os.environ.get("GEMINI_MODEL", "gpt-4o-mini")
        tag_result = await generate_memory_tags(
            api_key=api_key,
            model=model,
            community_name=community_doc.get("name", ""),
            community_type=community_doc.get("community_type", "community"),
            title=payload.title,
            description=payload.description,
            event_title=event_title,
            special_focus="",
            image_data_url=payload.image_data_url,
        )
        ai_tags = tag_result.get("tags", [])
        ai_summary = tag_result.get("summary", "")
        ai_sentiment = tag_result.get("sentiment", "neutral")
        ai_mood = tag_result.get("mood", "warm")
    else:
        ai_sentiment = "neutral"
        ai_mood = "warm"

    memory_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "event_id": payload.event_id,
        "event_title": event_title,
        "category": payload.category,
        "image_data_url": payload.image_data_url,
        "voice_note_data_url": payload.voice_note_data_url,
        "tags": list(set(payload.tags + ai_tags)),
        "ai_summary": ai_summary,
        "sentiment": ai_sentiment,
        "mood": ai_mood,
        "comments": [],
        "created_at": now_iso(),
    }
    await memories_collection.insert_one(memory_doc.copy())
    return memory_doc


@router.put("/memories/{memory_id}", response_model=MemoryPublic)
async def update_memory(memory_id: str, payload: MemoryUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    memory_doc = await get_memory_for_user(memory_id, current_user)
    updates = {}
    if payload.title.strip():
        updates["title"] = payload.title.strip()
    if payload.description is not None and payload.description != "":
        updates["description"] = payload.description.strip()
    if updates:
        await memories_collection.update_one({"id": memory_id}, {"$set": updates})
        memory_doc.update(updates)
    return memory_doc


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    await get_memory_for_user(memory_id, current_user)
    await memories_collection.delete_one({"id": memory_id})
    return {"ok": True}


@router.post("/memories/{memory_id}/comments", response_model=MemoryPublic)
async def add_memory_comment(memory_id: str, payload: CommentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    memory_doc = await get_memory_for_user(memory_id, current_user)
    comments = memory_doc.get("comments", [])
    comments.append({"id": str(uuid.uuid4()), "author_name": current_user["full_name"], "text": payload.text.strip(), "created_at": now_iso()})
    await memories_collection.update_one({"id": memory_id}, {"$set": {"comments": comments}})
    memory_doc["comments"] = comments
    return memory_doc


@router.get("/threads", response_model=list[ThreadPublic])
async def list_threads(current_user: dict[str, Any] = Depends(get_current_user)):
    threads = await threads_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return threads


@router.post("/threads", response_model=ThreadPublic)
async def create_thread(payload: ThreadCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    thread_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "title": payload.title.strip(),
        "body": payload.body.strip(),
        "category": payload.category,
        "elder_name": payload.elder_name.strip() if hasattr(payload, "elder_name") and payload.elder_name else "",
        "voice_note_data_url": payload.voice_note_data_url if hasattr(payload, "voice_note_data_url") else "",
        "tags": payload.tags,
        "comments": [],
        "created_at": now_iso(),
    }
    await threads_collection.insert_one(thread_doc.copy())
    return thread_doc


@router.post("/threads/{thread_id}/comments", response_model=ThreadPublic)
async def add_thread_comment(thread_id: str, payload: CommentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    thread_doc = await get_thread_for_user(thread_id, current_user)
    comments = thread_doc.get("comments", [])
    comments.append({"id": str(uuid.uuid4()), "author_name": current_user["full_name"], "text": payload.text.strip(), "created_at": now_iso()})
    await threads_collection.update_one({"id": thread_id}, {"$set": {"comments": comments}})
    thread_doc["comments"] = comments
    return thread_doc



@router.post("/memories/batch-retag")
async def batch_retag(current_user: dict[str, Any] = Depends(get_current_user)):
    """Re-tag all memories in the community using improved AI analysis."""
    from ai_tagging import batch_retag_memories

    community_doc = await get_community_for_user(current_user)
    memories = await memories_collection.find(
        {"community_id": current_user["community_id"]}, {"_id": 0}
    ).to_list(200)

    if not memories:
        return {"updated": 0, "results": []}

    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gpt-4o-mini")

    results = await batch_retag_memories(
        api_key=api_key,
        model=model,
        memories=memories,
        community_name=community_doc.get("name", ""),
        community_type=community_doc.get("community_type", "community"),
    )

    updated = 0
    for r in results:
        mid = r.pop("memory_id")
        await memories_collection.update_one(
            {"id": mid},
            {"$set": {"tags": r["tags"], "ai_summary": r["summary"], "sentiment": r.get("sentiment", "neutral"), "mood": r.get("mood", "warm")}},
        )
        updated += 1

    return {"updated": updated, "results": results}
