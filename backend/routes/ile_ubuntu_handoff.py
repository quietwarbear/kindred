"""X2 routes: send an event's attendees to Ile Ubuntu. See ile_ubuntu_handoff.py.

Organizer-only:
  GET    /api/events/{id}/ile-ubuntu-handoff             setup, mapping, last send
  PUT    /api/events/{id}/ile-ubuntu-handoff             {connection_key?, course_map}
  DELETE /api/events/{id}/ile-ubuntu-handoff/connection  forget the key
  POST   /api/events/{id}/ile-ubuntu-handoff/send        {dry_run}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from db import events_collection, ile_ubuntu_handoff_connections_collection, users_collection
from dependencies import ensure_minimum_role, get_current_user, get_event_for_user, now_iso
from ile_ubuntu_handoff import (
    MAX_ATTENDEES,
    HandoffError,
    call_ile_ubuntu,
    clean_course_map,
    event_has_ended,
    handoff_attendees,
    handoff_configured,
    valid_key_shape,
)
from organizer_command_center import _normalized_email

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class HandoffSetupRequest(BaseModel):
    connection_key: str | None = Field(default=None, max_length=200)
    course_map: dict[str, str] = Field(default_factory=dict)


class HandoffSendRequest(BaseModel):
    dry_run: bool = False


def _http(error: HandoffError) -> HTTPException:
    return HTTPException(status_code=error.status, detail={"code": error.code, "message": error.message})


async def _organizer_event(event_id: str, current_user: dict[str, Any]) -> dict[str, Any]:
    ensure_minimum_role(current_user, "organizer")
    return await get_event_for_user(event_id, current_user)


async def _connection(event_id: str) -> dict[str, Any] | None:
    return await ile_ubuntu_handoff_connections_collection.find_one({"event_id": event_id}, {"_id": 0})


def _activities(event: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": str(a["id"]), "title": str(a.get("title") or ""), "start_at": str(a.get("start_at") or "")}
        for a in sorted(event.get("agenda", []), key=lambda a: str(a.get("start_at") or "9999"))
        if a.get("id") and a.get("visibility") != "archived"
    ]


async def _state(event: dict[str, Any], connection: dict[str, Any] | None) -> dict[str, Any]:
    state = {
        "configured": handoff_configured(),
        "event_ended": event_has_ended(event),
        "connected": bool(connection and connection.get("connection_key")),
        "key_last4": (connection or {}).get("key_last4", ""),
        "teacher_name": (connection or {}).get("teacher_name", ""),
        "course_map": clean_course_map(event, event.get("ile_ubuntu_course_map")),
        "activities": _activities(event),
        "courses": [],
        "courses_error": "",
        "last_send": event.get("ile_ubuntu_handoff_last") or None,
    }
    if state["configured"] and state["connected"]:
        try:
            reply = await call_ile_ubuntu("courses", {"connection_key": connection["connection_key"]})
            state["courses"] = [
                {"id": str(c.get("id")), "title": str(c.get("title") or "")}
                for c in reply.get("courses", [])
                if c.get("id")
            ]
            state["teacher_name"] = str(reply.get("teacher_name") or state["teacher_name"])
        except HandoffError as exc:
            state["courses_error"] = exc.message
    return state


@router.get("/events/{event_id}/ile-ubuntu-handoff")
async def get_handoff(event_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    event = await _organizer_event(event_id, current_user)
    return await _state(event, await _connection(event_id))


@router.put("/events/{event_id}/ile-ubuntu-handoff")
async def save_handoff(
    event_id: str,
    payload: HandoffSetupRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_event(event_id, current_user)
    connection = await _connection(event_id)
    key = (payload.connection_key or "").strip()
    if key:
        if not valid_key_shape(key):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "connection_key_invalid", "message": "That doesn't look like an Ile Ubuntu connection key."},
            )
        try:
            reply = await call_ile_ubuntu("courses", {"connection_key": key})
        except HandoffError as exc:
            raise _http(exc) from exc
        connection = {
            "event_id": event_id,
            "community_id": current_user["community_id"],
            "connection_key": key,
            "key_last4": key[-4:],
            "teacher_name": str(reply.get("teacher_name") or ""),
            "updated_at": now_iso(),
            "updated_by": current_user["id"],
        }
        await ile_ubuntu_handoff_connections_collection.update_one(
            {"event_id": event_id}, {"$set": connection}, upsert=True
        )
    course_map = clean_course_map(event, payload.course_map)
    await events_collection.update_one(
        {"id": event_id, "community_id": current_user["community_id"]},
        {"$set": {"ile_ubuntu_course_map": course_map}},
    )
    event["ile_ubuntu_course_map"] = course_map
    return await _state(event, connection)


@router.delete("/events/{event_id}/ile-ubuntu-handoff/connection")
async def forget_connection(event_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    event = await _organizer_event(event_id, current_user)
    await ile_ubuntu_handoff_connections_collection.delete_one({"event_id": event_id})
    return await _state(event, None)


@router.post("/events/{event_id}/ile-ubuntu-handoff/send")
async def send_to_ile_ubuntu(
    event_id: str,
    payload: HandoffSendRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_event(event_id, current_user)
    connection = await _connection(event_id)
    if not connection or not connection.get("connection_key"):
        raise _http(HandoffError(409, "not_connected", "Add the connection key from Ile Ubuntu first."))
    if not payload.dry_run and not event_has_ended(event):
        raise _http(HandoffError(409, "event_not_ended", "You can send attendees once the event has ended."))
    course_map = clean_course_map(event, event.get("ile_ubuntu_course_map"))
    if not course_map:
        raise _http(HandoffError(409, "no_mapping", "Choose an Ile Ubuntu course for at least one activity."))

    members = await users_collection.find(
        {"community_id": current_user["community_id"]},
        {"_id": 0, "id": 1, "email": 1, "email_normalized": 1, "full_name": 1},
    ).to_list(5000)
    members_by_id = {m["id"]: m for m in members if m.get("id")}
    member_ids_by_email = {
        _normalized_email(m.get("email_normalized") or m.get("email")): m["id"]
        for m in members
        if m.get("id") and _normalized_email(m.get("email_normalized") or m.get("email"))
    }
    attendees, local_counts = handoff_attendees(
        event, course_map, members_by_id=members_by_id, member_ids_by_email=member_ids_by_email
    )
    if len(attendees) > MAX_ATTENDEES:
        raise _http(HandoffError(413, "too_many", f"Send at most {MAX_ATTENDEES} people at a time."))
    if not attendees:
        return {"dry_run": payload.dry_run, "local": local_counts, "report": None}
    try:
        report = await call_ile_ubuntu(
            "import",
            {
                "connection_key": connection["connection_key"],
                "event_ref": event_id,
                "dry_run": payload.dry_run,
                "attendees": attendees,
            },
        )
    except HandoffError as exc:
        raise _http(exc) from exc
    counts = report.get("counts") or {}
    if not payload.dry_run:
        last = {
            "sent_at": now_iso(),
            "sent_by": current_user["id"],
            "counts": {k: int(v) for k, v in counts.items() if isinstance(v, int)},
            "welcome_emails": int(report.get("welcome_emails") or 0),
            "local": local_counts,
        }
        await events_collection.update_one(
            {"id": event_id, "community_id": current_user["community_id"]},
            {"$set": {"ile_ubuntu_handoff_last": last}},
        )
    # Counts only: no names or emails in the log.
    logger.info("ile ubuntu handoff event=%s dry_run=%s local=%s counts=%s", event_id, payload.dry_run, local_counts, counts)
    return {"dry_run": payload.dry_run, "local": local_counts, "report": report}
