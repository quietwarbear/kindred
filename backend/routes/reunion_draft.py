"""Public endpoint: email a reunion draft to the organizer who wrote it.

Unauthenticated by design — the whole point is that the person has not made an
account yet. See draft_rescue.py for the abuse bounds, which are not optional.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from db import reunion_draft_leads_collection
from draft_rescue import (
    clean_field,
    client_ip,
    hash_ip,
    rate_limit_reason,
    valid_email,
)
from email_service import send_reunion_draft_copy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class ReunionDraftEmailRequest(BaseModel):
    email: str = Field(max_length=254)
    gathering_name: str = Field(default="", max_length=120)
    gathering_noun: str = Field(default="gathering", max_length=40)
    organizer_name: str = Field(default="", max_length=100)
    approximate_date: str = Field(default="", max_length=32)
    end_date: str = Field(default="", max_length=32)
    location: str = Field(default="", max_length=160)


@router.post("/reunion/draft/email", status_code=status.HTTP_202_ACCEPTED)
async def email_reunion_draft(payload: ReunionDraftEmailRequest, request: Request):
    email = payload.email.strip().lower()
    if not valid_email(email):
        raise HTTPException(status_code=400, detail="That email address doesn't look right.")

    ip_hash = hash_ip(client_ip(request))
    reason = await rate_limit_reason(reunion_draft_leads_collection, ip_hash, email)
    if reason:
        raise HTTPException(status_code=429, detail=reason)

    draft = {
        "gathering_name": clean_field(payload.gathering_name),
        "gathering_noun": clean_field(payload.gathering_noun, 40),
        "organizer_name": clean_field(payload.organizer_name, 100),
        "approximate_date": clean_field(payload.approximate_date, 32),
        "end_date": clean_field(payload.end_date, 32),
        "location": clean_field(payload.location, 160),
    }

    # Record the lead BEFORE sending, so a send failure still counts against
    # the rate limit and still leaves the abandoned draft visible to us.
    await reunion_draft_leads_collection.insert_one({
        "email": email,
        "ip_hash": ip_hash,
        "draft": draft,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "public_reunion_start",
    })

    sent = await send_reunion_draft_copy(email, draft)
    if not sent:
        logger.warning("Draft copy could not be emailed to %s", email)
    return {"ok": True, "sent": sent}
