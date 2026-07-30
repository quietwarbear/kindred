"""Verified, privacy-safe Resend delivery events for invitation redelivery."""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from svix.webhooks import Webhook, WebhookVerificationError

from invitation_redelivery import (
    ProviderStatus,
    RedeliveryFailure,
    SafeErrorCode,
)

MAX_WEBHOOK_BODY_BYTES = 64 * 1024
SAFE_PROVIDER_REFERENCE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
SAFE_WEBHOOK_EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
RESEND_EVENT_STATUS = {
    "email.delivered": ProviderStatus.DELIVERED,
    "email.complained": ProviderStatus.FAILED,
    "email.bounced": ProviderStatus.FAILED,
    "email.failed": ProviderStatus.FAILED,
    "email.suppressed": ProviderStatus.FAILED,
}


@dataclass(frozen=True, repr=False)
class VerifiedDeliveryEvent:
    """The only provider fields allowed beyond signature verification."""

    event_id: str
    provider_message_id: str
    provider_status: ProviderStatus
    occurred_at: str

    def __repr__(self) -> str:
        return (
            "VerifiedDeliveryEvent("
            f"provider_status={self.provider_status.value!r}, "
            "event_id=<redacted>, provider_message_id=<redacted>)"
        )


def validate_webhook_secret(secret: str) -> str:
    """Validate webhook signing material without exposing it."""

    clean = str(secret or "").strip()
    if not clean.startswith("whsec_") or len(clean) < 16:
        raise RedeliveryFailure(SafeErrorCode.CONFIGURATION_UNAVAILABLE)
    try:
        encoded = clean.removeprefix("whsec_")
        decoded = base64.b64decode(
            encoded + ("=" * (-len(encoded) % 4)),
            validate=True,
        )
        if len(decoded) < 16:
            raise ValueError("webhook signing material is too short")
        Webhook(clean)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise RedeliveryFailure(SafeErrorCode.CONFIGURATION_UNAVAILABLE) from exc
    return clean


def _normalized_timestamp(value: object) -> str:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS) from exc
    if parsed.tzinfo is None:
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS)
    return parsed.astimezone(timezone.utc).isoformat()


def verify_resend_delivery_event(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    signing_secret: str,
) -> VerifiedDeliveryEvent | None:
    """Verify a raw webhook and discard every non-operational field."""

    if not raw_body or len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS)
    event_id = str(headers.get("svix-id") or "").strip()
    if not SAFE_WEBHOOK_EVENT_ID.fullmatch(event_id):
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS)
    verification_headers = {
        "svix-id": event_id,
        "svix-timestamp": str(headers.get("svix-timestamp") or ""),
        "svix-signature": str(headers.get("svix-signature") or ""),
    }
    try:
        payload = Webhook(validate_webhook_secret(signing_secret)).verify(
            raw_body,
            verification_headers,
        )
    except (WebhookVerificationError, ValueError, TypeError) as exc:
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS) from exc
    except RedeliveryFailure:
        raise
    except Exception as exc:
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS) from exc

    if not isinstance(payload, dict):
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS)
    event_type = str(payload.get("type") or "").strip().lower()
    provider_status = RESEND_EVENT_STATUS.get(event_type)
    if provider_status is None:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS)
    provider_message_id = str(data.get("email_id") or "").strip()
    if not SAFE_PROVIDER_REFERENCE.fullmatch(provider_message_id):
        raise RedeliveryFailure(SafeErrorCode.PROVIDER_AMBIGUOUS)
    return VerifiedDeliveryEvent(
        event_id=event_id,
        provider_message_id=provider_message_id,
        provider_status=provider_status,
        occurred_at=_normalized_timestamp(payload.get("created_at")),
    )
