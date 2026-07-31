"""Organizer-only family-space readiness and monotonic activation routes."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from db import (
    communities_collection,
    events_collection,
    memories_collection,
    users_collection,
)
from dependencies import (
    ensure_minimum_role,
    get_community_for_user,
    get_current_user,
    now_iso,
)
from family_space_activation import (
    ACTIVE,
    PROVISIONAL,
    FamilySpaceNameError,
    build_family_space_readiness,
    community_lifecycle_state,
    normalize_family_space_name,
)
from models import FamilySpaceActivationRequest

router = APIRouter(prefix="/api")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


async def _activation_context(
    current_user: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure_minimum_role(current_user, "organizer")
    community = await get_community_for_user(current_user)
    community_id = current_user["community_id"]
    events = await events_collection.find(
        {
            "community_id": community_id,
            "event_template": "reunion",
            "hidden_from_user_ids": {"$ne": current_user["id"]},
        },
        {"_id": 0},
    ).to_list(200)
    members = await users_collection.find(
        {"community_id": community_id},
        {"_id": 0, "id": 1, "role": 1, "email": 1, "email_normalized": 1},
    ).to_list(1000)
    event_ids = [event["id"] for event in events if event.get("id")]
    memories = (
        await memories_collection.find(
            {
                "community_id": community_id,
                "event_id": {"$in": event_ids},
                "capsule_status": {"$ne": "draft"},
            },
            {"_id": 0, "event_id": 1, "created_by": 1, "capsule_status": 1},
        ).to_list(1000)
        if event_ids
        else []
    )
    return community, build_family_space_readiness(community, events, members, memories)


def _activation_result(community: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "activated",
        "lifecycle_state": ACTIVE,
        "lifecycle_revision": int(community.get("lifecycle_revision", 1) or 1),
        "next_action": {"code": "open_family_home"},
    }


@router.get("/family-space/activation")
async def family_space_activation_readiness(
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _community, readiness = await _activation_context(current_user)
    return readiness


@router.post("/family-space/activation")
async def activate_family_space(
    payload: FamilySpaceActivationRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    community, readiness = await _activation_context(current_user)
    try:
        normalized_name = normalize_family_space_name(payload.family_space_name)
    except FamilySpaceNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": exc.code,
                "message": "Choose a family-space name using visible letters or numbers.",
            },
        ) from exc
    if not _IDEMPOTENCY_KEY.fullmatch(payload.idempotency_key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_idempotency_key",
                "message": "This activation request cannot be safely retried.",
            },
        )
    if payload.expected_revision < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_expected_revision",
                "message": "The family-space revision is invalid.",
            },
        )

    operation_hash = _hash(payload.idempotency_key)
    payload_hash = _hash(
        json.dumps(
            {"family_space_name": normalized_name},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    lifecycle = community_lifecycle_state(community)
    if lifecycle == ACTIVE:
        if (
            community.get("activation_operation_hash") == operation_hash
            and community.get("activation_payload_hash") == payload_hash
        ):
            return _activation_result(community)
        raise _conflict(
            "family_space_already_active",
            "This family space has already been activated.",
        )
    if lifecycle != PROVISIONAL:
        raise _conflict(
            "explicit_provisional_state_required",
            "This community is not eligible for family-space activation.",
        )
    if not readiness["ready"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "family_space_not_ready",
                "message": "More verified reunion participation is required.",
                "unmet_condition_codes": readiness["unmet_condition_codes"],
            },
        )

    activated = await communities_collection.find_one_and_update(
        {
            "id": current_user["community_id"],
            "owner_user_id": community.get("owner_user_id"),
            "lifecycle_state": PROVISIONAL,
            "lifecycle_revision": payload.expected_revision,
        },
        {
            "$set": {
                "name": normalized_name,
                "lifecycle_state": ACTIVE,
                "activated_at": now_iso(),
                "activated_by_user_id": current_user["id"],
                "activation_operation_hash": operation_hash,
                "activation_payload_hash": payload_hash,
            },
            "$inc": {"lifecycle_revision": 1},
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if activated:
        return _activation_result(activated)

    current = await communities_collection.find_one(
        {"id": current_user["community_id"]}, {"_id": 0}
    )
    if (
        current
        and community_lifecycle_state(current) == ACTIVE
        and current.get("activation_operation_hash") == operation_hash
        and current.get("activation_payload_hash") == payload_hash
    ):
        return _activation_result(current)
    raise _conflict(
        "family_space_activation_conflict",
        "The family space changed. Refresh before trying again.",
    )
