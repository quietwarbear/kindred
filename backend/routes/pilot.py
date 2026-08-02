"""Platform-admin pilot consent & cohort management.

Records which communities are in the pilot cohort and whether each organizer has
explicitly consented. Every response is categorical/opaque; recording consent
here enables no delivery, provider call, or send — it is bookkeeping for a
consent conversation that happens out of band.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from db import communities_collection
from dependencies import get_current_user, is_platform_admin_user, now_iso
from models import PilotCohortActionRequest
from pilot_cohort import (
    PilotTransitionError,
    apply_pilot_action,
    pilot_cohort_summary,
    public_pilot_record,
)

router = APIRouter(prefix="/api/pilot", tags=["Pilot cohort"])


def _require_admin(current_user: dict[str, Any]) -> None:
    # Re-derive admin authority server-side (get_current_user returns the raw
    # user doc without is_platform_admin); never trust a stored/payload flag.
    if not is_platform_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pilot cohort management is restricted to platform admins.",
        )


@router.get("/cohort")
async def get_pilot_cohort(current_user: dict[str, Any] = Depends(get_current_user)):
    """Content-free cohort summary for the admin (counts + enrolled communities)."""
    _require_admin(current_user)
    communities = await communities_collection.find(
        {}, {"_id": 0, "id": 1, "name": 1, "pilot": 1}
    ).to_list(5000)
    return pilot_cohort_summary(communities)


@router.post("/cohort/{community_id}/action")
async def pilot_cohort_action(
    community_id: str,
    payload: PilotCohortActionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Apply one pilot lifecycle action to a community. Fails closed."""
    _require_admin(current_user)

    community = await communities_collection.find_one(
        {"id": community_id}, {"_id": 0, "id": 1, "pilot": 1}
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found."
        )

    # Recording consent requires an explicit confirmation from the admin that the
    # organizer actually agreed — it must never be inferred.
    if payload.action == "record_consent" and not payload.consent_confirmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "consent_confirmation_required"},
        )

    raw_status = (community.get("pilot") or {}).get("status")
    try:
        new_status = apply_pilot_action(raw_status, payload.action)
    except PilotTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code},
        ) from exc

    now = now_iso()
    pilot = dict(community.get("pilot") or {})
    pilot["status"] = new_status
    pilot["updated_at"] = now
    pilot["updated_by"] = current_user["id"]
    if payload.cohort_label.strip():
        pilot["cohort_label"] = payload.cohort_label.strip()
    if payload.action == "enroll":
        # A fresh enrollment starts clean — prior consent/withdrawal must not
        # linger, so `consented` never reports stale "ever consented" state.
        for stale in ("consented_at", "consent_by", "withdrawn_at"):
            pilot.pop(stale, None)
    if payload.action == "record_consent":
        pilot["consented_at"] = now
        pilot["consent_by"] = current_user["id"]
    if payload.action == "withdraw":
        pilot["withdrawn_at"] = now

    # Optimistic-concurrency guard: only write if the status is still what we
    # read, so two concurrent admin actions can't clobber each other.
    guard = {"id": community_id}
    guard["pilot.status"] = raw_status if raw_status else {"$exists": False}
    result = await communities_collection.update_one(guard, {"$set": {"pilot": pilot}})
    if getattr(result, "matched_count", 1) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "concurrent_pilot_conflict"},
        )
    return {"community_id": community_id, "pilot": public_pilot_record(pilot)}
