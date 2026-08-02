"""Shared push-delivery types.

Extracted so the FCM (Android/web) and APNs (iOS) transports can share one
outcome vocabulary without a circular import between ``push_sender`` and
``apns_client``.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol


class PushOutcome(str, Enum):
    DELIVERED = "delivered"
    INVALID = "invalid"  # permanently dead token — prune it
    TRANSIENT = "transient"  # retry later
    FAILED = "failed"  # configuration/auth failure — never prune on this


class PushClient(Protocol):
    async def deliver(
        self, device_token: str, notification: dict[str, str]
    ) -> PushOutcome: ...
