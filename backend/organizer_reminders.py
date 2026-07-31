"""Fail-closed preflight for ordinary organizer reminders.

The incident redelivery pipeline is intentionally not reused: ordinary
reminders must never rotate invitation credentials. Until a separately
reviewed privacy-safe sender is configured, this module reports an unavailable
state and performs no mutation or provider call.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
REQUIRED_CONFIGURATION = (
    "APP_URL",
    "FROM_EMAIL",
    "PUBLIC_API_BASE_URL",
    "RESEND_API_KEY",
)


@dataclass(frozen=True)
class ProviderAttempt:
    """Sanitized result from a fake or future reviewed provider adapter."""

    status: str
    safe_code: str
    retry_allowed: bool


def classify_provider_attempt(
    *,
    accepted: bool = False,
    rejected: bool = False,
    timed_out: bool = False,
    ambiguous: bool = False,
) -> ProviderAttempt:
    """Classify provider outcomes without preserving payloads or exceptions."""
    if accepted and not any((rejected, timed_out, ambiguous)):
        return ProviderAttempt("accepted", "accepted", False)
    if rejected and not any((accepted, timed_out, ambiguous)):
        return ProviderAttempt("rejected", "provider_rejected", True)
    if timed_out or ambiguous or sum((accepted, rejected, timed_out, ambiguous)) > 1:
        return ProviderAttempt("ambiguous", "provider_acceptance_ambiguous", False)
    return ProviderAttempt("failed", "provider_unavailable", True)


def validate_idempotency_key(value: str) -> str:
    normalized = str(value or "").strip()
    if not IDEMPOTENCY_KEY.fullmatch(normalized):
        raise ValueError("A stable operation idempotency key is required.")
    return normalized


def reminder_preflight(
    *,
    invitation_count: int,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = environment if environment is not None else os.environ
    enabled = env.get("ORGANIZER_REMINDER_DELIVERY_ENABLED") == "true"
    configured = all(
        str(env.get(name) or "").strip() for name in REQUIRED_CONFIGURATION
    )
    if invitation_count <= 0:
        return {
            "available": False,
            "code": "no_missing_responses",
            "recipient_count": 0,
        }
    if not enabled or not configured:
        return {
            "available": False,
            "code": "delivery_unavailable",
            "recipient_count": invitation_count,
        }
    # Configuration alone is not proof of a safe sender. This remains closed
    # until a reviewed ordinary-reminder adapter is added.
    return {
        "available": False,
        "code": "privacy_safe_sender_unavailable",
        "recipient_count": invitation_count,
    }
