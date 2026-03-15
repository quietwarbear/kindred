"""Communications routes: announcements, chat, notifications."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import (
    announcements_collection,
    chat_rooms_collection,
    notification_events_collection,
    notification_preferences_collection,
    subyards_collection,
)
from dependencies import (
    ensure_chat_rooms_for_community,
    ensure_minimum_role,
    get_chat_room_for_user,
    get_community_for_user,
    get_current_user,
    get_notification_preferences_for_user,
    get_subyard_for_user,
    log_notification_event,
    now_iso,
)
from models import (
    AnnouncementCreateRequest,
    ChatMessageCreateRequest,
    CommentRequest,
    CommunicationUnreadSummary,
    NotificationPreferencesUpdateRequest,
)

router = APIRouter(prefix="/api")


@router.get("/announcements")
async def list_announcements(current_user: dict[str, Any] = Depends(get_current_user)):
    prefs = await get_notification_preferences_for_user(current_user)
    base_query = {"community_id": current_user["community_id"]}
    if prefs.get("muted_announcement_scopes"):
        base_query["scope"] = {"$nin": prefs.get("muted_announcement_scopes", [])}
    unread_before_view = await announcements_collection.count_documents({
        **base_query,
        "read_by_ids": {"$ne": current_user["id"]},
    })
    await announcements_collection.update_many(
        base_query,
        {"$addToSet": {"read_by_ids": current_user["id"]}},
    )
    announcements = await announcements_collection.find(base_query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"announcements": announcements, "unread_before_view": unread_before_view}


@router.post("/announcements")
async def create_announcement(payload: AnnouncementCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    subyard_name = ""
    if payload.scope == "subyard":
        if not payload.subyard_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subyard announcements require a subyard.")
        subyard_doc = await get_subyard_for_user(payload.subyard_id, current_user)
        subyard_name = subyard_doc["name"]

    announcement_doc = {
        "id": str(uuid.uuid4()),
        "community_id": current_user["community_id"],
        "scope": payload.scope,
        "subyard_id": payload.subyard_id,
        "subyard_name": subyard_name,
        "title": payload.title.strip(),
        "body": payload.body.strip(),
        "attachments": [item.model_dump() for item in payload.attachments],
        "comments": [],
        "read_by_ids": [current_user["id"]],
        "created_by": current_user["id"],
        "created_by_name": current_user["full_name"],
        "created_at": now_iso(),
    }
    await announcements_collection.insert_one(announcement_doc.copy())
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="announcement",
        title=f"Announcement posted: {announcement_doc['title']}",
        description=announcement_doc["body"],
        related_id=announcement_doc["id"],
        audience_scope=announcement_doc["scope"],
    )
    return announcement_doc


@router.put("/announcements/{announcement_id}")
async def update_announcement(announcement_id: str, payload: AnnouncementCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    doc = await announcements_collection.find_one({"id": announcement_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")
    updates = {"title": payload.title.strip(), "body": payload.body.strip()}
    await announcements_collection.update_one({"id": announcement_id}, {"$set": updates})
    doc.update(updates)
    return doc


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(announcement_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    result = await announcements_collection.delete_one({"id": announcement_id, "community_id": current_user["community_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")
    return {"ok": True}


@router.post("/announcements/{announcement_id}/comments")
async def add_announcement_comment(announcement_id: str, payload: CommentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    announcement_doc = await announcements_collection.find_one({"id": announcement_id, "community_id": current_user["community_id"]}, {"_id": 0})
    if not announcement_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")
    comments = announcement_doc.get("comments", [])
    comments.append({"id": str(uuid.uuid4()), "author_name": current_user["full_name"], "text": payload.text.strip(), "created_at": now_iso()})
    await announcements_collection.update_one(
        {"id": announcement_id},
        {"$set": {"comments": comments}, "$addToSet": {"read_by_ids": current_user["id"]}},
    )
    announcement_doc["comments"] = comments
    announcement_doc["read_by_ids"] = list(set(announcement_doc.get("read_by_ids", []) + [current_user["id"]]))
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="announcement-comment",
        title=f"Comment on announcement: {announcement_doc['title']}",
        description=payload.text.strip(),
        related_id=announcement_id,
        audience_scope=announcement_doc.get("scope", "community"),
    )
    return announcement_doc


@router.get("/chat/rooms")
async def list_chat_rooms(current_user: dict[str, Any] = Depends(get_current_user)):
    community_doc = await get_community_for_user(current_user)
    subyards = await subyards_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).to_list(200)
    await ensure_chat_rooms_for_community(current_user["community_id"], community_doc["name"], subyards)
    prefs = await get_notification_preferences_for_user(current_user)
    rooms = await chat_rooms_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", 1).to_list(200)
    for room in rooms:
        room["is_muted"] = room["id"] in prefs.get("muted_room_ids", [])
        room["unread_count"] = 0 if room["is_muted"] else len([message for message in room.get("messages", []) if current_user["id"] not in message.get("read_by_ids", [])])
    return {"rooms": rooms}


@router.get("/chat/rooms/{room_id}")
async def view_chat_room(room_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    room_doc = await get_chat_room_for_user(room_id, current_user)
    messages = room_doc.get("messages", [])
    changed = False
    for message in messages:
        readers = message.get("read_by_ids", [])
        if current_user["id"] not in readers:
            readers.append(current_user["id"])
            message["read_by_ids"] = readers
            changed = True
    if changed:
        await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": messages}})
    room_doc["messages"] = messages
    room_doc["unread_count"] = 0
    return room_doc


@router.post("/chat/rooms/{room_id}/messages")
async def create_chat_message(room_id: str, payload: ChatMessageCreateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    room_doc = await get_chat_room_for_user(room_id, current_user)
    messages = room_doc.get("messages", [])
    messages.append(
        {
            "id": str(uuid.uuid4()),
            "author_id": current_user["id"],
            "author_name": current_user["full_name"],
            "text": payload.text.strip(),
            "attachments": [item.model_dump() for item in payload.attachments],
            "comments": [],
            "is_pinned": False,
            "read_by_ids": [current_user["id"]],
            "created_at": now_iso(),
        }
    )
    await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": messages}})
    room_doc["messages"] = messages
    room_doc["unread_count"] = len([message for message in messages if current_user["id"] not in message.get("read_by_ids", [])])
    await log_notification_event(
        community_id=current_user["community_id"],
        actor_name=current_user["full_name"],
        event_type="chat-message",
        title=f"New message in {room_doc['name']}",
        description=payload.text.strip(),
        related_id=room_id,
        audience_scope=room_doc.get("room_scope", "community"),
    )
    return room_doc


@router.delete("/chat/rooms/{room_id}/messages/{message_id}")
async def delete_chat_message(room_id: str, message_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    room_doc = await get_chat_room_for_user(room_id, current_user)
    messages = room_doc.get("messages", [])
    msg = next((m for m in messages if m.get("id") == message_id), None)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
    if msg.get("user_id") != current_user["id"]:
        ensure_minimum_role(current_user, "organizer")
    messages = [m for m in messages if m.get("id") != message_id]
    await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": messages}})
    return {"ok": True}


@router.post("/chat/rooms/{room_id}/messages/{message_id}/pin")
async def pin_chat_message(room_id: str, message_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    ensure_minimum_role(current_user, "organizer")
    room_doc = await get_chat_room_for_user(room_id, current_user)
    updated = False
    for message in room_doc.get("messages", []):
        if message.get("id") == message_id:
            message["is_pinned"] = not message.get("is_pinned", False)
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
    await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": room_doc.get("messages", [])}})
    room_doc["unread_count"] = len([message for message in room_doc.get("messages", []) if current_user["id"] not in message.get("read_by_ids", [])])
    return room_doc


@router.post("/chat/rooms/{room_id}/messages/{message_id}/comments")
async def comment_on_chat_message(room_id: str, message_id: str, payload: CommentRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    room_doc = await get_chat_room_for_user(room_id, current_user)
    updated = False
    for message in room_doc.get("messages", []):
        if message.get("id") == message_id:
            comments = message.get("comments", [])
            comments.append({"id": str(uuid.uuid4()), "author_name": current_user["full_name"], "text": payload.text.strip(), "created_at": now_iso()})
            message["comments"] = comments
            readers = message.get("read_by_ids", [])
            if current_user["id"] not in readers:
                readers.append(current_user["id"])
                message["read_by_ids"] = readers
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
    await chat_rooms_collection.update_one({"id": room_id}, {"$set": {"messages": room_doc.get("messages", [])}})
    room_doc["unread_count"] = len([message for message in room_doc.get("messages", []) if current_user["id"] not in message.get("read_by_ids", [])])
    return room_doc


@router.get("/communications/unread-summary", response_model=CommunicationUnreadSummary)
async def communications_unread_summary(current_user: dict[str, Any] = Depends(get_current_user)):
    prefs = await get_notification_preferences_for_user(current_user)
    announcements_unread = await announcements_collection.count_documents({
        "community_id": current_user["community_id"],
        "scope": {"$nin": prefs.get("muted_announcement_scopes", [])},
        "read_by_ids": {"$ne": current_user["id"]},
    })
    rooms = await chat_rooms_collection.find({"community_id": current_user["community_id"]}, {"_id": 0, "messages": 1}).to_list(200)
    chat_unread = 0
    for room in rooms:
        if room.get("id") in prefs.get("muted_room_ids", []):
            continue
        chat_unread += len([message for message in room.get("messages", []) if current_user["id"] not in message.get("read_by_ids", [])])
    return {"announcements_unread": announcements_unread, "chat_unread": chat_unread, "total_unread": announcements_unread + chat_unread}


@router.get("/notifications/history")
async def notification_history(current_user: dict[str, Any] = Depends(get_current_user)):
    items = await notification_events_collection.find({"community_id": current_user["community_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for item in items:
        item["is_read"] = current_user["id"] in item.get("read_by_user_ids", [])
        item.pop("read_by_user_ids", None)
    return {"items": items}


@router.get("/notifications/preferences")
async def notification_preferences(current_user: dict[str, Any] = Depends(get_current_user)):
    return await get_notification_preferences_for_user(current_user)


@router.put("/notifications/preferences")
async def update_notification_preferences(payload: NotificationPreferencesUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    prefs_doc = {
        "user_id": current_user["id"],
        "community_id": current_user["community_id"],
        "reminder_notifications": payload.reminder_notifications,
        "announcement_notifications": payload.announcement_notifications,
        "chat_notifications": payload.chat_notifications,
        "invite_notifications": payload.invite_notifications,
        "rsvp_notifications": payload.rsvp_notifications,
        "muted_room_ids": payload.muted_room_ids,
        "muted_announcement_scopes": payload.muted_announcement_scopes,
        "updated_at": now_iso(),
    }
    await notification_preferences_collection.update_one(
        {"community_id": current_user["community_id"], "user_id": current_user["id"]},
        {"$set": prefs_doc},
        upsert=True,
    )
    return prefs_doc


@router.get("/notifications/unread-count")
async def notification_unread_count(current_user: dict[str, Any] = Depends(get_current_user)):
    count = await notification_events_collection.count_documents({
        "community_id": current_user["community_id"],
        "read_by_user_ids": {"$nin": [current_user["id"]]},
    })
    return {"unread_count": count}


@router.post("/notifications/mark-read")
async def mark_notifications_read(current_user: dict[str, Any] = Depends(get_current_user)):
    result = await notification_events_collection.update_many(
        {
            "community_id": current_user["community_id"],
            "read_by_user_ids": {"$nin": [current_user["id"]]},
        },
        {"$addToSet": {"read_by_user_ids": current_user["id"]}},
    )
    return {"marked_count": result.modified_count}
