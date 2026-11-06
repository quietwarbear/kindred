"""K2 registrant import routes: CSV upload, signed inbound webhook, duplicate flags.

Organizer routes (every one needs an organizer or host of the event's community):
- POST /api/events/{event_id}/registrants/import          CSV text -> report
- GET  /api/events/{event_id}/registrants/flags           possible duplicates
- POST /api/events/{event_id}/registrants/flags/{id}/resolve
- GET  /api/events/{event_id}/duplicates                  K9 existing duplicates
- POST /api/events/{event_id}/duplicates/merge
- POST /api/events/{event_id}/duplicates/{pair_key}/dismiss
- GET  /api/events/{event_id}/registrants/webhook         URL + secret
- POST /api/events/{event_id}/registrants/webhook/rotate  create or rotate secret

Public, signed (see docs/REGISTRANT_WEBHOOK.md):
- POST /api/inbound/registrants/{hook_id}

Sends go through ``invitation_delivery.send_first_invitations`` — the same
gated, fail-closed path as the organizer's "Email invitations" button.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from starlette.responses import JSONResponse

from db import (
    events_collection,
    invitation_delivery_outbox_collection,
    registrant_hook_deliveries_collection,
    registrant_hooks_collection,
    registrant_import_flags_collection,
    users_collection,
)
from dependencies import ensure_minimum_role, get_current_user, get_event_for_user, now_iso
from invitation_delivery import (
    build_invitation_delivery_provider,
    first_send_enabled,
    send_first_invitations,
)
from registrant_import import (
    FLAG_APPLY_TO_EXISTING,
    FLAG_CREATE_SEPARATE,
    FLAG_DISMISSED,
    FLAG_PENDING,
    MAX_CSV_BYTES,
    ROW_FLAGGED,
    CSVImportError,
    ImportOutcome,
    Registrant,
    _clean_name,
    apply_registrants,
    importable_activities,
    normalize_import_email,
    parse_registrant_csv,
    split_session_refs,
    valid_email,
)
from registrant_webhook import (
    MAX_WEBHOOK_BODY_BYTES,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    generate_hook_id,
    generate_secret,
    public_hook_view,
    replay_digest,
    verify_signature,
)
from duplicate_merge import MergeError, dismiss_pair, merge_invitations, possible_duplicates
from rsvp_integrity import RSVPWriteConflict, compare_and_swap_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Registrant import"])


class RegistrantCSVImportRequest(BaseModel):
    csv_text: str = Field(default="", max_length=MAX_CSV_BYTES)
    send_invitations: bool = False


class DuplicateMergeRequest(BaseModel):
    keep_invite_id: str = Field(min_length=1, max_length=128)
    merge_invite_id: str = Field(min_length=1, max_length=128)


class RegistrantFlagResolveRequest(BaseModel):
    action: Literal["create_separate", "apply_to_existing", "dismissed"]
    send_invitation: bool = False


def _app_url() -> str:
    return os.environ.get("APP_URL", "https://www.heykindred.org").rstrip("/")


def _share_message(event: dict[str, Any], rsvp_link: str) -> str:
    # Imported lazily: routes.events is large and imports this router's peers.
    from routes.events import _event_invite_message

    return _event_invite_message(event, rsvp_link)


async def _organizer_event(event_id: str, user: dict[str, Any]) -> dict[str, Any]:
    ensure_minimum_role(user, "organizer")
    event = await get_event_for_user(event_id, user)
    return event


def _block_draft(event: dict[str, Any]) -> None:
    if event.get("publication_state") == "organizer_draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "organizer_draft_import_blocked",
                "message": "Finish the private organizer review before importing registrants.",
            },
        )


async def _members_by_email(community_id: str, emails: list[str]) -> dict[str, dict[str, Any]]:
    if not emails:
        return {}
    members = await users_collection.find(
        {
            "community_id": community_id,
            "$or": [{"email_normalized": {"$in": emails}}, {"email": {"$in": emails}}],
        },
        {"_id": 0, "id": 1, "email": 1, "full_name": 1},
    ).to_list(len(emails) * 2 + 10)
    return {normalize_import_email(m.get("email")): m for m in members if m.get("id")}


async def _flags_by_email(event_id: str) -> dict[str, dict[str, Any]]:
    flags = await registrant_import_flags_collection.find(
        {"event_id": event_id}, {"_id": 0}
    ).to_list(10_000)
    return {flag["email"]: flag for flag in flags if flag.get("email")}


async def run_registrant_import(
    *,
    event_id: str,
    community_id: str,
    registrants: list[Registrant],
    source: str,
    flag_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], ImportOutcome]:
    """Apply registrants atomically to one event and record any new flags."""
    members = await _members_by_email(community_id, [r.email for r in registrants])
    flags = await _flags_by_email(event_id)
    flags.update(flag_overrides or {})
    holder: dict[str, ImportOutcome] = {}

    def mutate(current_event: dict[str, Any]) -> dict[str, Any]:
        _block_draft(current_event)
        outcome = apply_registrants(
            current_event,
            registrants,
            flags_by_email=flags,
            members_by_email=members,
            source=source,
            share_message_for=_share_message,
            app_url=_app_url(),
            now=now_iso(),
        )
        holder["outcome"] = outcome
        return outcome.updates

    try:
        event = await compare_and_swap_event(
            events_collection, {"id": event_id, "community_id": community_id}, mutate
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "rsvp_write_conflict", "message": str(exc)},
        ) from exc
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    outcome = holder["outcome"]
    for flag in outcome.new_flags:
        await registrant_import_flags_collection.update_one(
            {"event_id": event_id, "email": flag["email"]},
            {
                "$set": {**flag, "updated_at": now_iso()},
                "$setOnInsert": {
                    "id": uuid.uuid4().hex,
                    "event_id": event_id,
                    "community_id": community_id,
                    "status": FLAG_PENDING,
                    "created_at": now_iso(),
                },
            },
            upsert=True,
        )
    return event, outcome


async def _deliver(event: dict[str, Any], invite_ids: list[str]) -> dict[str, Any]:
    """Send invitations through the shared first-send path; content-free result."""
    empty = {"submitted": 0, "rejected": 0, "ambiguous": 0, "failed": 0, "skipped": 0}
    if not invite_ids:
        return {"status": "not_requested", "error_code": "", "counts": empty}
    if not first_send_enabled():
        return {"status": "unavailable", "error_code": "delivery_disabled", "counts": empty}
    provider = build_invitation_delivery_provider()
    if provider is None:
        return {"status": "unavailable", "error_code": "provider_unconfigured", "counts": empty}
    report = await send_first_invitations(
        event=event,
        invite_ids=invite_ids,
        provider=provider,
        events_collection=events_collection,
        outbox_collection=invitation_delivery_outbox_collection,
        app_url=_app_url(),
    )
    return report.safe_document()


def _sendable_invite_ids(outcome: ImportOutcome) -> list[str]:
    ids: list[str] = []
    for row in outcome.rows:
        invite_id = row.get("invite_id")
        if invite_id and row["status"] != ROW_FLAGGED and invite_id not in ids:
            ids.append(str(invite_id))
    return ids


def _report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row.get("row", 0))
    counts = {"created": 0, "updated": 0, "skipped": 0, "flagged": 0, "error": 0}
    for row in ordered:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"counts": counts, "rows": ordered}


def _flag_view(flag: dict[str, Any], titles: dict[str, str]) -> dict[str, Any]:
    return {
        "id": flag.get("id"),
        "status": flag.get("status"),
        "source": flag.get("source"),
        "row": flag.get("row"),
        "name": flag.get("name", ""),
        "email": flag.get("email", ""),
        "sessions": [titles.get(i, i) for i in flag.get("activity_ids") or []],
        "matched_invite_id": flag.get("matched_invite_id"),
        "matched_name": flag.get("matched_name", ""),
        "matched_email": flag.get("matched_email", ""),
        "created_at": flag.get("created_at", ""),
        "resolved_at": flag.get("resolved_at", ""),
    }


def _activity_titles(event: dict[str, Any]) -> dict[str, str]:
    return {str(a["id"]): str(a.get("title") or "") for a in importable_activities(event)}


# ---------------------------------------------------------------------------
# Organizer: CSV import
# ---------------------------------------------------------------------------


@router.post("/events/{event_id}/registrants/import")
async def import_registrants_csv(
    event_id: str,
    payload: RegistrantCSVImportRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_event(event_id, current_user)
    _block_draft(event)
    try:
        parsed = parse_registrant_csv(payload.csv_text)
    except CSVImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    event, outcome = await run_registrant_import(
        event_id=event_id,
        community_id=current_user["community_id"],
        registrants=parsed.registrants,
        source="csv",
    )
    delivery = (
        await _deliver(event, _sendable_invite_ids(outcome))
        if payload.send_invitations
        else {"status": "not_requested", "error_code": "", "counts": {}}
    )
    return {
        **_report([*parsed.row_results, *outcome.rows]),
        "delivery": delivery,
        "pending_flags": await registrant_import_flags_collection.count_documents(
            {"event_id": event_id, "status": FLAG_PENDING}
        ),
    }


# ---------------------------------------------------------------------------
# Organizer: possible duplicates (K9, first half)
# ---------------------------------------------------------------------------


@router.get("/events/{event_id}/registrants/flags")
async def list_registrant_flags(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_event(event_id, current_user)
    flags = await registrant_import_flags_collection.find(
        {"event_id": event_id, "community_id": current_user["community_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    titles = _activity_titles(event)
    return {"flags": [_flag_view(flag, titles) for flag in flags]}


@router.post("/events/{event_id}/registrants/flags/{flag_id}/resolve")
async def resolve_registrant_flag(
    event_id: str,
    flag_id: str,
    payload: RegistrantFlagResolveRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_event(event_id, current_user)
    flag = await registrant_import_flags_collection.find_one(
        {"id": flag_id, "event_id": event_id, "community_id": current_user["community_id"]},
        {"_id": 0},
    )
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found.")
    if flag.get("status") != FLAG_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "flag_already_resolved", "message": "This was already reviewed."},
        )
    if payload.action != FLAG_DISMISSED:
        _block_draft(event)
    claimed = await registrant_import_flags_collection.find_one_and_update(
        {"id": flag_id, "status": FLAG_PENDING},
        {
            "$set": {
                "status": payload.action,
                "resolved_at": now_iso(),
                "resolved_by": current_user["id"],
            }
        },
    )
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "flag_already_resolved", "message": "This was already reviewed."},
        )
    result: dict[str, Any] = {"status": payload.action, "row": None, "delivery": None}
    if payload.action in {FLAG_CREATE_SEPARATE, FLAG_APPLY_TO_EXISTING}:
        registrant = Registrant(
            row=int(flag.get("row") or 0),
            email=flag["email"],
            name=flag.get("name", ""),
            session_refs=list(flag.get("activity_ids") or []),
        )
        try:
            event, outcome = await run_registrant_import(
                event_id=event_id,
                community_id=current_user["community_id"],
                registrants=[registrant],
                source=str(flag.get("source") or "csv"),
                flag_overrides={flag["email"]: {**flag, "status": payload.action}},
            )
        except Exception:
            # Nothing was applied: put the flag back so the organizer can retry.
            await registrant_import_flags_collection.update_one(
                {"id": flag_id, "status": payload.action},
                {"$set": {"status": FLAG_PENDING, "resolved_at": "", "resolved_by": ""}},
            )
            raise
        result["row"] = outcome.rows[0] if outcome.rows else None
        if payload.send_invitation and payload.action == FLAG_CREATE_SEPARATE:
            result["delivery"] = await _deliver(event, _sendable_invite_ids(outcome))
    elif payload.action != FLAG_DISMISSED:  # pragma: no cover - guarded by Literal
        raise HTTPException(status_code=422, detail="Unknown action.")
    return result


# ---------------------------------------------------------------------------
# Organizer: webhook URL and secret
# ---------------------------------------------------------------------------


@router.get("/events/{event_id}/registrants/webhook")
async def get_registrant_webhook(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    await _organizer_event(event_id, current_user)
    hook = await registrant_hooks_collection.find_one(
        {"event_id": event_id, "community_id": current_user["community_id"]}, {"_id": 0}
    )
    return public_hook_view(hook)


@router.post("/events/{event_id}/registrants/webhook/rotate")
async def rotate_registrant_webhook(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Create the event's webhook, or replace its secret. The old secret stops working."""
    event = await _organizer_event(event_id, current_user)
    _block_draft(event)
    now = now_iso()
    hook = await registrant_hooks_collection.find_one_and_update(
        {"event_id": event_id, "community_id": current_user["community_id"]},
        {
            "$set": {"secret": generate_secret(), "rotated_at": now, "rotated_by": current_user["id"]},
            "$setOnInsert": {
                "id": uuid.uuid4().hex,
                "hook_id": generate_hook_id(),
                "event_id": event_id,
                "community_id": current_user["community_id"],
                "created_at": now,
                "created_by": current_user["id"],
            },
        },
        upsert=True,
        return_document=True,
        projection={"_id": 0},
    )
    return public_hook_view(hook)


# ---------------------------------------------------------------------------
# Public: signed inbound webhook
# ---------------------------------------------------------------------------


def _invitation_state(delivery: dict[str, Any]) -> str:
    """One word for the sender: sent, already_sent, not_sent, or why not."""
    if delivery["status"] != "processed":
        return delivery["error_code"] or delivery["status"]
    counts = delivery["counts"]
    if counts.get("submitted"):
        return "sent"
    if counts.get("skipped"):
        return "already_sent"
    return "not_sent"


def _reply(status_code: int, body: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=body, status_code=status_code, headers={"Cache-Control": "no-store"})


async def _read_limited_body(request: Request) -> bytes | None:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_WEBHOOK_BODY_BYTES:
            return None
        body.extend(chunk)
    return bytes(body)


def registrant_from_payload(data: Any) -> tuple[Registrant | None, str]:
    """Validate one webhook payload. Returns (registrant, error message)."""
    if not isinstance(data, dict):
        return None, "The body must be a JSON object."
    email = normalize_import_email(data.get("email"))
    if not valid_email(email):
        return None, "A valid email is required."
    name = _clean_name(data.get("name")) or _clean_name(
        f"{data.get('first_name') or ''} {data.get('last_name') or ''}"
    )
    sessions = data.get("sessions", [])
    if not isinstance(sessions, (list, str)) or (
        isinstance(sessions, list) and not all(isinstance(s, str) for s in sessions)
    ):
        return None, "sessions must be a list of session titles or ids."
    return Registrant(row=1, email=email, name=name, session_refs=split_session_refs(sessions)), ""


@router.post("/inbound/registrants/{hook_id}", include_in_schema=False)
async def inbound_registrant_webhook(hook_id: str, request: Request):
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_WEBHOOK_BODY_BYTES:
        return _reply(413, {"status": "rejected", "code": "payload_too_large"})
    raw_body = await _read_limited_body(request)
    if raw_body is None:
        return _reply(413, {"status": "rejected", "code": "payload_too_large"})

    hook = await registrant_hooks_collection.find_one({"hook_id": hook_id}, {"_id": 0})
    signature = request.headers.get(SIGNATURE_HEADER, "")
    check = verify_signature(
        secret=(hook or {}).get("secret", ""),
        timestamp=request.headers.get(TIMESTAMP_HEADER, ""),
        signature=signature,
        raw_body=raw_body,
    )
    if not hook or not check.ok:
        # Same answer for an unknown hook and a bad signature: no probing.
        logger.info("registrant_webhook status=rejected code=%s", check.code or "unknown_hook")
        return _reply(401, {"status": "rejected", "code": check.code or "invalid_signature"})

    digest = replay_digest(hook_id, signature)
    try:
        await registrant_hook_deliveries_collection.insert_one(
            {
                "replay_digest": digest,
                "hook_id": hook_id,
                "received_at": now_iso(),
                "received_at_dt": datetime.now(timezone.utc),
            }
        )
    except DuplicateKeyError:
        return _reply(409, {"status": "rejected", "code": "replayed"})

    try:
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _reply(400, {"status": "rejected", "code": "invalid_json"})
        registrant, error = registrant_from_payload(data)
        if registrant is None:
            return _reply(422, {"status": "rejected", "code": "invalid_payload", "message": error})
        try:
            event, outcome = await run_registrant_import(
                event_id=hook["event_id"],
                community_id=hook["community_id"],
                registrants=[registrant],
                source="webhook",
            )
        except HTTPException as exc:
            await registrant_hook_deliveries_collection.delete_one({"replay_digest": digest})
            code = exc.detail.get("code") if isinstance(exc.detail, dict) else "unavailable"
            return _reply(exc.status_code, {"status": "rejected", "code": code})
        row = outcome.rows[0]
        if row["status"] == "error":
            return _reply(
                422,
                {"status": "rejected", "code": row.get("code", "invalid"), "message": row["detail"]},
            )
        delivery = await _deliver(event, _sendable_invite_ids(outcome))
        await registrant_hooks_collection.update_one(
            {"hook_id": hook_id}, {"$set": {"last_received_at": now_iso()}}
        )
        return _reply(
            200,
            {
                "status": "accepted",
                "result": row["status"],
                "sessions": row.get("sessions", []),
                "invitation": _invitation_state(delivery),
            },
        )
    except Exception:
        # Let the sender retry the same signed request after a server fault.
        await registrant_hook_deliveries_collection.delete_one({"replay_digest": digest})
        raise


# ---------------------------------------------------------------------------
# Organizer: duplicates that already exist (K9, second half)
# ---------------------------------------------------------------------------


@router.get("/events/{event_id}/duplicates")
async def list_possible_duplicates(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    event = await _organizer_event(event_id, current_user)
    return {"pairs": possible_duplicates(event)}


@router.post("/events/{event_id}/duplicates/merge")
async def merge_duplicate_people(
    event_id: str,
    payload: DuplicateMergeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Keep one invitation; move the other's answers, account link and email to it."""
    await _organizer_event(event_id, current_user)
    report: dict[str, Any] = {}

    def mutate(current: dict[str, Any]) -> dict[str, Any]:
        updates, result = merge_invitations(
            current,
            keep_invite_id=payload.keep_invite_id,
            merge_invite_id=payload.merge_invite_id,
            actor_id=current_user.get("id", ""),
            now=now_iso(),
        )
        report.update(result)
        return updates

    try:
        event = await compare_and_swap_event(
            events_collection,
            {"id": event_id, "community_id": current_user["community_id"]},
            mutate,
        )
    except MergeError as exc:
        raise HTTPException(
            status_code=exc.http_status, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "rsvp_write_conflict", "message": str(exc)},
        ) from exc
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    # Import flags that pointed at the merged person now point at the kept one.
    await registrant_import_flags_collection.update_many(
        {"event_id": event_id, "matched_invite_id": payload.merge_invite_id},
        {"$set": {"matched_invite_id": payload.keep_invite_id}},
    )
    logger.info(
        "duplicate_merge event=%s moved_event=%s moved_activity=%s",
        event_id,
        report.get("moved_event_answers"),
        report.get("moved_activity_answers"),
    )
    return {"merge": report, "pairs": possible_duplicates(event)}


@router.post("/events/{event_id}/duplicates/{pair_key}/dismiss")
async def dismiss_possible_duplicate(
    event_id: str,
    pair_key: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """The organizer says these are two different people; don't raise it again."""
    event = await _organizer_event(event_id, current_user)
    if pair_key not in {pair["pair_key"] for pair in possible_duplicates(event)}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pair not found.")
    try:
        event = await compare_and_swap_event(
            events_collection,
            {"id": event_id, "community_id": current_user["community_id"]},
            lambda current: dismiss_pair(current, pair_key),
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "rsvp_write_conflict", "message": str(exc)},
        ) from exc
    return {"pairs": possible_duplicates(event or {})}
