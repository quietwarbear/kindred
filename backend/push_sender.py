"""Disabled-by-default server push notifications (FCM HTTP v1).

Device tokens are already collected at ``/auth/push-token`` but were never used.
This module adds the missing send path WITHOUT introducing a new dependency: it
mints a Google OAuth2 access token from a service account with PyJWT and posts to
FCM HTTP v1 over httpx (both already vendored).

Privacy and safety:
- Notifications carry only an ALLOWLISTED categorical template — a fixed title
  and body with no name, email, event title, or other customer content.
- Nothing here logs or reports a device token, recipient, or message body; only
  aggregate categorical counts leave this module.
- It sends nothing unless ``PUSH_NOTIFICATIONS_ENABLED`` is "true" AND a service
  account is configured; every other path is inert.
- Tokens FCM reports as permanently invalid are pruned from the user.

This is a draft capability: inert until an owner configures it, and it must pass
an independent adversarial review before activation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Protocol

import httpx
import jwt

from dependencies import now_iso

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
ACCESS_TOKEN_TTL_SECONDS = 3600

# Allowlisted, content-free notification templates. No customer content ever.
PUSH_TEMPLATES: dict[str, dict[str, str]] = {
    "new_gathering": {
        "title": "New gathering",
        "body": "A new gathering was shared in your circle.",
    },
    "rsvp_received": {
        "title": "New RSVP",
        "body": "Someone responded to one of your gatherings.",
    },
    "gathering_reminder": {
        "title": "Gathering reminder",
        "body": "You have an upcoming gathering.",
    },
    "gathering_revealed": {
        "title": "A gathering was revealed",
        "body": "A surprise gathering was just revealed to your circle.",
    },
}


class PushOutcome(str, Enum):
    DELIVERED = "delivered"
    INVALID = "invalid"  # permanently dead token — prune it
    TRANSIENT = "transient"  # retry later
    FAILED = "failed"  # configuration/auth failure


class PushClient(Protocol):
    async def deliver(
        self, device_token: str, notification: dict[str, str]
    ) -> PushOutcome: ...


def push_enabled() -> bool:
    """Push is off unless explicitly enabled by deployment configuration."""
    return os.environ.get("PUSH_NOTIFICATIONS_ENABLED", "").lower() == "true"


def _service_account() -> dict[str, str] | None:
    raw = os.environ.get("FCM_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
    else:
        data = {
            "project_id": os.environ.get("FCM_PROJECT_ID", "").strip(),
            "client_email": os.environ.get("FCM_CLIENT_EMAIL", "").strip(),
            "private_key": os.environ.get("FCM_PRIVATE_KEY", "")
            .strip()
            .replace("\\n", "\n"),
        }
    if not (
        data.get("project_id") and data.get("client_email") and data.get("private_key")
    ):
        return None
    return data


@dataclass(frozen=True)
class PushSendReport:
    status: str
    error_code: str = ""
    delivered: int = 0
    invalid: int = 0
    transient: int = 0
    failed: int = 0

    def safe_document(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error_code": self.error_code,
            "counts": {
                "delivered": self.delivered,
                "invalid": self.invalid,
                "transient": self.transient,
                "failed": self.failed,
            },
        }


class FcmHttpV1Client:
    """Minimal FCM HTTP v1 client. Never logs tokens, bodies, or credentials."""

    def __init__(
        self,
        *,
        service_account: dict[str, str],
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._sa = service_account
        self._http = http_client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._access_token = ""
        self._access_expiry = datetime(1970, 1, 1, tzinfo=timezone.utc)

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if self._http is not None:
            return await self._http.request(method, url, **kwargs)
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            return await client.request(method, url, **kwargs)

    def _signed_assertion(self) -> str:
        now = self._clock()
        claims = {
            "iss": self._sa["client_email"],
            "scope": FCM_SCOPE,
            "aud": GOOGLE_TOKEN_URI,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)).timestamp()),
        }
        return jwt.encode(claims, self._sa["private_key"], algorithm="RS256")

    async def _ensure_access_token(self) -> str:
        if self._access_token and self._clock() < self._access_expiry:
            return self._access_token
        response = await self._request(
            "POST",
            GOOGLE_TOKEN_URI,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": self._signed_assertion(),
            },
        )
        if response.status_code != 200:
            raise PermissionError("fcm_token_unavailable")
        token = str(response.json().get("access_token") or "")
        if not token:
            raise PermissionError("fcm_token_unavailable")
        self._access_token = token
        self._access_expiry = self._clock() + timedelta(
            seconds=ACCESS_TOKEN_TTL_SECONDS - 60
        )
        return token

    async def deliver(
        self, device_token: str, notification: dict[str, str]
    ) -> PushOutcome:
        try:
            access_token = await self._ensure_access_token()
        except PermissionError:
            return PushOutcome.FAILED
        except (httpx.TimeoutException, httpx.NetworkError):
            return PushOutcome.TRANSIENT
        url = FCM_SEND_URL.format(project_id=self._sa["project_id"])
        message = {
            "message": {
                "token": device_token,
                "notification": {
                    "title": notification["title"],
                    "body": notification["body"],
                },
            }
        }
        try:
            response = await self._request(
                "POST",
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                json=message,
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return PushOutcome.TRANSIENT
        except Exception:
            return PushOutcome.FAILED
        if response.status_code == 200:
            return PushOutcome.DELIVERED
        if response.status_code == 404:
            return PushOutcome.INVALID  # UNREGISTERED token → prune
        if response.status_code == 401:
            # Expired/rejected access token; force a fresh mint next send.
            self._access_token = ""
            return PushOutcome.FAILED
        # 400 INVALID_ARGUMENT is usually a malformed request (not a dead token)
        # and 403 is a sender-id mismatch — never prune the user's tokens on
        # these; a bad payload would otherwise wipe every token at once.
        if response.status_code in (400, 403):
            return PushOutcome.FAILED
        return PushOutcome.TRANSIENT  # 429/5xx


def build_push_client() -> PushClient | None:
    """Construct the FCM client only when a service account is configured."""
    service_account = _service_account()
    if service_account is None:
        return None
    return FcmHttpV1Client(service_account=service_account)


async def send_push_to_user(
    *,
    users_collection,
    user_id: str,
    template_code: str,
    client: PushClient,
    now_fn: Callable[[], str] = now_iso,
) -> PushSendReport:
    """Send one allowlisted template to a user's devices; prune dead tokens."""
    notification = PUSH_TEMPLATES.get(template_code)
    if notification is None:
        return PushSendReport(status="unavailable", error_code="unknown_template")
    user = await users_collection.find_one(
        {"id": user_id}, {"_id": 0, "push_tokens": 1}
    )
    tokens = list(dict.fromkeys((user or {}).get("push_tokens", []) or []))
    if not tokens:
        return PushSendReport(status="processed")

    delivered = invalid = transient = failed = 0
    dead: list[str] = []
    for token in tokens:
        outcome = await client.deliver(token, notification)
        if outcome == PushOutcome.DELIVERED:
            delivered += 1
        elif outcome == PushOutcome.INVALID:
            invalid += 1
            dead.append(token)
        elif outcome == PushOutcome.TRANSIENT:
            transient += 1
        else:
            failed += 1
    if dead:
        await users_collection.update_one(
            {"id": user_id}, {"$pull": {"push_tokens": {"$in": dead}}}
        )
    return PushSendReport(
        status="processed",
        delivered=delivered,
        invalid=invalid,
        transient=transient,
        failed=failed,
    )


async def maybe_notify(
    *,
    users_collection,
    user_id: str,
    template_code: str,
    client_factory: Callable[[], PushClient | None] = build_push_client,
) -> None:
    """Best-effort, fully gated trigger. Never raises into the caller's path."""
    if not push_enabled() or not user_id:
        return
    try:
        client = client_factory()
        if client is None:
            return
        await send_push_to_user(
            users_collection=users_collection,
            user_id=user_id,
            template_code=template_code,
            client=client,
        )
    except Exception:
        # Push is a side channel; a failure here must never affect the request.
        return
