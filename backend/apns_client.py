"""Disabled-by-default Apple Push Notification service (APNs) transport.

iOS devices registered through ``@capacitor/push-notifications`` return an
**APNs** device token, not an FCM token. The FCM HTTP v1 sender in
``push_sender`` cannot deliver to those tokens, so iOS push requires this
first-party path: token-based JWT (ES256) provider auth over HTTP/2 directly to
``api.push.apple.com``.

Privacy and safety (identical contract to the FCM sender):
- Only an ALLOWLISTED, content-free ``{title, body}`` template is sent — never a
  name, email, gathering title, or any other customer content. The caller in
  ``push_sender`` owns the allowlist; this module just transports it.
- Nothing here logs or returns a device token, recipient, or message body; the
  only thing that leaves is a categorical :class:`PushOutcome`.
- It is inert unless ``PUSH_NOTIFICATIONS_ENABLED`` is "true" (enforced by the
  caller) AND an APNs auth key is configured; every other path returns ``None``.
- Only tokens Apple reports as permanently invalid (410 Unregistered, or 400
  ``BadDeviceToken``/``DeviceTokenNotForTopic``) are marked for pruning; auth or
  config failures never prune, so one bad key can't wipe every device.

Draft capability: inert until an owner configures it, and it must pass an
independent adversarial review before activation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

import httpx
import jwt

from push_types import PushClient, PushOutcome

APNS_PRODUCTION_HOST = "https://api.push.apple.com"
APNS_SANDBOX_HOST = "https://api.sandbox.push.apple.com"
DEFAULT_TOPIC = "com.ubuntumarket.kindred"
# Apple accepts a provider token for up to 60 minutes and rejects one minted
# less than ~20 minutes ago on refresh; 40 minutes stays safely inside both.
PROVIDER_TOKEN_TTL = timedelta(minutes=40)
# 400 reasons that mean the token itself is unusable → safe to prune.
_PRUNABLE_REASONS = frozenset(
    {"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"}
)


@dataclass(frozen=True)
class ApnsConfig:
    auth_key: str
    key_id: str
    team_id: str
    topic: str
    host: str


def apns_config() -> ApnsConfig | None:
    """Build APNs config from env, or ``None`` when not fully configured."""
    auth_key = os.environ.get("APNS_AUTH_KEY", "").strip().replace("\\n", "\n")
    key_id = os.environ.get("APNS_KEY_ID", "").strip()
    team_id = os.environ.get("APNS_TEAM_ID", "").strip()
    topic = os.environ.get("APNS_TOPIC", DEFAULT_TOPIC).strip() or DEFAULT_TOPIC
    environment = os.environ.get("APNS_ENVIRONMENT", "production").strip().lower()
    if not (auth_key and key_id and team_id):
        return None
    host = APNS_SANDBOX_HOST if environment == "sandbox" else APNS_PRODUCTION_HOST
    return ApnsConfig(
        auth_key=auth_key, key_id=key_id, team_id=team_id, topic=topic, host=host
    )


class ApnsHttp2Client:
    """Minimal APNs HTTP/2 client. Never logs tokens, bodies, or credentials."""

    def __init__(
        self,
        *,
        config: ApnsConfig,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._cfg = config
        self._http = http_client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._provider = ""
        self._provider_minted = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def _provider_token(self) -> str:
        now = self._clock()
        if self._provider and (now - self._provider_minted) < PROVIDER_TOKEN_TTL:
            return self._provider
        token = jwt.encode(
            {"iss": self._cfg.team_id, "iat": int(now.timestamp())},
            self._cfg.auth_key,
            algorithm="ES256",
            headers={"kid": self._cfg.key_id},
        )
        self._provider = token
        self._provider_minted = now
        return token

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if self._http is not None:
            return await self._http.request(method, url, **kwargs)
        async with httpx.AsyncClient(http2=True, timeout=httpx.Timeout(15.0)) as client:
            return await client.request(method, url, **kwargs)

    async def deliver(
        self, device_token: str, notification: dict[str, str]
    ) -> PushOutcome:
        try:
            provider = self._provider_token()
        except Exception:
            # Malformed key / signing failure — a configuration problem, not a
            # dead token. Never prune on this.
            return PushOutcome.FAILED
        url = f"{self._cfg.host}/3/device/{device_token}"
        payload = {
            "aps": {
                "alert": {
                    "title": notification["title"],
                    "body": notification["body"],
                },
                "sound": "default",
            }
        }
        headers = {
            "authorization": f"bearer {provider}",
            "apns-topic": self._cfg.topic,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }
        try:
            response = await self._request("POST", url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError):
            return PushOutcome.TRANSIENT
        except Exception:
            return PushOutcome.FAILED
        if response.status_code == 200:
            return PushOutcome.DELIVERED
        if response.status_code == 410:
            return PushOutcome.INVALID  # Unregistered device token → prune
        if response.status_code == 400:
            reason = ""
            try:
                reason = str((response.json() or {}).get("reason") or "")
            except Exception:
                reason = ""
            if reason in _PRUNABLE_REASONS:
                return PushOutcome.INVALID
            return PushOutcome.FAILED  # other 400s are payload/config, not dead tokens
        if response.status_code == 403:
            # InvalidProviderToken / ExpiredProviderToken → force a fresh mint,
            # but do not prune the device.
            self._provider = ""
            return PushOutcome.FAILED
        return PushOutcome.TRANSIENT  # 429 TooManyRequests / 5xx


def build_apns_client() -> PushClient | None:
    """Construct the APNs client only when an auth key is configured."""
    config = apns_config()
    if config is None:
        return None
    return ApnsHttp2Client(config=config)
