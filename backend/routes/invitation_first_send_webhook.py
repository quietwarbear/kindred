"""Signed Resend callbacks for the invitation first-send outbox.

This route never triggers a send. It verifies the provider signature, discards
every non-operational field, and confirms delivery of a first-send invitation by
stamping the mapped invitation. It is isolated from the credential-rotation
webhook and uses its own signing secret, so neither path can act on the other's
events.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from db import events_collection, invitation_delivery_outbox_collection
from invitation_delivery import apply_first_send_delivery_event
from invitation_redelivery import RedeliveryFailure
from invitation_redelivery_webhook import (
    MAX_WEBHOOK_BODY_BYTES,
    verify_resend_delivery_event,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provider/resend", tags=["Provider callbacks"])


def _safe_response(status: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        content={"status": status},
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


async def _read_limited_body(request: Request) -> bytes | None:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_WEBHOOK_BODY_BYTES:
            return None
        body.extend(chunk)
    return bytes(body)


@router.post("/invitation-first-send", include_in_schema=False)
async def invitation_first_send_webhook(request: Request):
    """Accept only verified delivery outcomes; never trigger a send."""

    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_WEBHOOK_BODY_BYTES:
        logger.warning(
            "invitation_first_send_webhook status=rejected code=payload_too_large"
        )
        return _safe_response("rejected", 413)

    signing_secret = os.environ.get("INVITATION_FIRST_SEND_WEBHOOK_SECRET", "")
    if not signing_secret:
        logger.error(
            "invitation_first_send_webhook status=unavailable "
            "code=configuration_unavailable"
        )
        return _safe_response("unavailable", 503)

    raw_body = await _read_limited_body(request)
    if raw_body is None:
        logger.warning(
            "invitation_first_send_webhook status=rejected code=payload_too_large"
        )
        return _safe_response("rejected", 413)

    try:
        event = verify_resend_delivery_event(
            raw_body=raw_body,
            headers={
                "svix-id": request.headers.get("svix-id", ""),
                "svix-timestamp": request.headers.get("svix-timestamp", ""),
                "svix-signature": request.headers.get("svix-signature", ""),
            },
            signing_secret=signing_secret,
        )
    except RedeliveryFailure:
        logger.warning(
            "invitation_first_send_webhook status=rejected code=invalid_signature"
        )
        return _safe_response("rejected", 400)

    if event is None:
        logger.info(
            "invitation_first_send_webhook status=ignored code=unsupported_event"
        )
        return _safe_response("accepted", 200)

    result = await apply_first_send_delivery_event(
        events_collection=events_collection,
        outbox_collection=invitation_delivery_outbox_collection,
        event=event,
    )
    if result == "conflict":
        # The invite was under sustained concurrent writes; ask the provider to
        # retry rather than silently dropping a delivery confirmation.
        logger.warning("invitation_first_send_webhook status=unavailable code=conflict")
        return _safe_response("unavailable", 503)
    logger.info("invitation_first_send_webhook status=%s", result)
    return _safe_response("accepted", 200)
