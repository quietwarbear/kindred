"""Signature scheme for the per-event inbound registrant webhook.

The contract is documented for integrators in ``docs/REGISTRANT_WEBHOOK.md``:

    X-Kindred-Timestamp: <unix seconds>
    X-Kindred-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>

A request is accepted only if the signature matches the event's current secret,
the timestamp is within ``SIGNATURE_TOLERANCE_SECONDS`` of now, and the exact
signature has not been seen before (replay guard, enforced by the caller with a
unique index on ``replay_digest``).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

SIGNATURE_HEADER = "X-Kindred-Signature"
TIMESTAMP_HEADER = "X-Kindred-Timestamp"
SIGNATURE_PREFIX = "sha256="
SIGNATURE_TOLERANCE_SECONDS = 300
MAX_WEBHOOK_BODY_BYTES = 16_384
SECRET_PREFIX = "kwhsec_"


def generate_hook_id() -> str:
    """Opaque public identifier for the webhook URL (not the event id)."""
    return secrets.token_urlsafe(18)


def generate_secret() -> str:
    return SECRET_PREFIX + secrets.token_urlsafe(32)


def compute_signature(secret: str, timestamp: str, raw_body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + raw_body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


def replay_digest(hook_id: str, signature: str) -> str:
    return hashlib.sha256(f"{hook_id}:{signature.strip()}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SignatureCheck:
    ok: bool
    code: str = ""


def verify_signature(
    *,
    secret: str,
    timestamp: str,
    signature: str,
    raw_body: bytes,
    now: float | None = None,
) -> SignatureCheck:
    """Constant-time check of signature and freshness. Never raises."""
    timestamp = str(timestamp or "").strip()
    signature = str(signature or "").strip()
    if not secret or not timestamp or not signature:
        return SignatureCheck(False, "missing_signature")
    if not timestamp.isdigit():
        return SignatureCheck(False, "invalid_timestamp")
    current = time.time() if now is None else now
    if abs(current - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return SignatureCheck(False, "stale_timestamp")
    expected = compute_signature(secret, timestamp, raw_body)
    # Accept several comma-separated candidates so a sender can sign with the
    # old and new secret across a rotation if it wants to.
    candidates = [part.strip() for part in signature.split(",") if part.strip()]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        return SignatureCheck(False, "invalid_signature")
    return SignatureCheck(True)


def public_hook_view(hook: dict[str, Any] | None) -> dict[str, Any]:
    """What the organizer sees about their webhook (secret included: they own it)."""
    if not hook:
        return {"configured": False}
    return {
        "configured": True,
        "path": f"/api/inbound/registrants/{hook['hook_id']}",
        "secret": hook["secret"],
        "created_at": hook.get("created_at", ""),
        "rotated_at": hook.get("rotated_at", ""),
        "last_received_at": hook.get("last_received_at", ""),
    }
