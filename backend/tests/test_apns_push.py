"""Unit tests for the APNs (iOS) push transport and platform routing.

Pure unit tests: the HTTP client and Mongo collection are faked, so nothing
touches the network or a database. Async coroutines are driven with
``asyncio.run`` so the file does not depend on any pytest-asyncio configuration.
"""

from __future__ import annotations

import asyncio

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import apns_client
import push_sender
from apns_client import ApnsConfig, ApnsHttp2Client, apns_config, build_apns_client
from push_types import PushOutcome

# --- helpers ---------------------------------------------------------------


def _es256_keypair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


class FakeResponse:
    def __init__(
        self, status_code: int, body: dict | None = None, raise_json: bool = False
    ):
        self.status_code = status_code
        self._body = body or {}
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("response body is not JSON")
        return self._body


class FakeHttp:
    """Records each request and returns queued responses in order."""

    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.requests: list[dict] = []

    async def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0)


class FakeUsers:
    """Minimal async stand-in for the Mongo users collection."""

    def __init__(self, user: dict):
        self.user = user
        self.updates: list[dict] = []

    async def find_one(self, query, projection=None):
        return dict(self.user)

    async def update_one(self, query, update):
        self.updates.append(update)
        # apply $pull for push_tokens / push_devices so assertions can inspect
        pull = update.get("$pull", {})
        if "push_tokens" in pull:
            cond = pull["push_tokens"]
            dead = set(cond.get("$in", [])) if isinstance(cond, dict) else {cond}
            self.user["push_tokens"] = [
                t for t in self.user.get("push_tokens", []) if t not in dead
            ]
        if "push_devices" in pull:
            cond = pull["push_devices"].get("token", {})
            dead = set(cond.get("$in", [])) if isinstance(cond, dict) else set()
            self.user["push_devices"] = [
                d
                for d in self.user.get("push_devices", [])
                if d.get("token") not in dead
            ]


class RecordingClient:
    def __init__(self, outcome=PushOutcome.DELIVERED):
        self.outcome = outcome
        self.tokens: list[str] = []

    async def deliver(self, token, notification):
        self.tokens.append(token)
        return self.outcome


TEMPLATE = "new_gathering"


# --- apns_config -----------------------------------------------------------


def test_apns_config_absent_without_env(monkeypatch):
    for var in (
        "APNS_AUTH_KEY",
        "APNS_KEY_ID",
        "APNS_TEAM_ID",
        "APNS_TOPIC",
        "APNS_ENVIRONMENT",
    ):
        monkeypatch.delenv(var, raising=False)
    assert apns_config() is None
    assert build_apns_client() is None


def test_apns_config_present_and_environment(monkeypatch):
    key, _ = _es256_keypair()
    monkeypatch.setenv("APNS_AUTH_KEY", key)
    monkeypatch.setenv("APNS_KEY_ID", "KID123")
    monkeypatch.setenv("APNS_TEAM_ID", "TEAM99")
    monkeypatch.delenv("APNS_TOPIC", raising=False)
    monkeypatch.delenv("APNS_ENVIRONMENT", raising=False)
    cfg = apns_config()
    assert cfg is not None
    assert cfg.host == apns_client.APNS_PRODUCTION_HOST
    assert cfg.topic == apns_client.DEFAULT_TOPIC
    monkeypatch.setenv("APNS_ENVIRONMENT", "sandbox")
    assert apns_config().host == apns_client.APNS_SANDBOX_HOST


# --- provider token (ES256 JWT) -------------------------------------------


def test_provider_token_signs_es256_and_caches():
    private_pem, public_pem = _es256_keypair()
    cfg = ApnsConfig(
        auth_key=private_pem,
        key_id="KID123",
        team_id="TEAM99",
        topic="com.ubuntumarket.kindred",
        host=apns_client.APNS_PRODUCTION_HOST,
    )
    http = FakeHttp([FakeResponse(200)])
    client = ApnsHttp2Client(config=cfg, http_client=http)

    asyncio.run(client.deliver("devtoken", {"title": "t", "body": "b"}))

    auth = http.requests[0]["headers"]["authorization"]
    assert auth.startswith("bearer ")
    token = auth.split(" ", 1)[1]
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "ES256"
    assert header["kid"] == "KID123"
    claims = jwt.decode(
        token,
        public_pem,
        algorithms=["ES256"],
        options={"verify_exp": False, "verify_aud": False},
    )
    assert claims["iss"] == "TEAM99"
    assert "iat" in claims
    # topic + push-type headers are correct and payload is content-free
    assert http.requests[0]["headers"]["apns-topic"] == "com.ubuntumarket.kindred"
    assert http.requests[0]["json"] == {
        "aps": {"alert": {"title": "t", "body": "b"}, "sound": "default"}
    }

    # a second send within TTL reuses the same provider token (no re-mint)
    http._responses.append(FakeResponse(200))
    asyncio.run(client.deliver("devtoken2", {"title": "t", "body": "b"}))
    assert http.requests[1]["headers"]["authorization"] == auth


# --- outcome mapping -------------------------------------------------------


def _deliver_status(status, body=None):
    private_pem, _ = _es256_keypair()
    cfg = ApnsConfig(
        auth_key=private_pem,
        key_id="K",
        team_id="T",
        topic="com.ubuntumarket.kindred",
        host=apns_client.APNS_PRODUCTION_HOST,
    )
    http = FakeHttp([FakeResponse(status, body)])
    client = ApnsHttp2Client(config=cfg, http_client=http)
    return asyncio.run(client.deliver("tok", {"title": "t", "body": "b"}))


def test_outcome_mapping():
    assert _deliver_status(200) == PushOutcome.DELIVERED
    assert _deliver_status(410) == PushOutcome.INVALID
    assert _deliver_status(400, {"reason": "BadDeviceToken"}) == PushOutcome.INVALID
    assert (
        _deliver_status(400, {"reason": "DeviceTokenNotForTopic"})
        == PushOutcome.INVALID
    )
    # a non-token 400 (e.g. payload problem) must NOT prune
    assert _deliver_status(400, {"reason": "PayloadTooLarge"}) == PushOutcome.FAILED
    # auth failures never prune
    assert (
        _deliver_status(403, {"reason": "InvalidProviderToken"}) == PushOutcome.FAILED
    )
    # transient
    assert _deliver_status(429, {"reason": "TooManyRequests"}) == PushOutcome.TRANSIENT
    assert _deliver_status(503) == PushOutcome.TRANSIENT


def test_403_resets_provider_token():
    private_pem, _ = _es256_keypair()
    cfg = ApnsConfig(
        auth_key=private_pem,
        key_id="K",
        team_id="T",
        topic="x",
        host=apns_client.APNS_PRODUCTION_HOST,
    )
    http = FakeHttp(
        [FakeResponse(403, {"reason": "ExpiredProviderToken"}), FakeResponse(200)]
    )
    client = ApnsHttp2Client(config=cfg, http_client=http)
    asyncio.run(client.deliver("tok", {"title": "t", "body": "b"}))
    first = http.requests[0]["headers"]["authorization"]
    asyncio.run(client.deliver("tok", {"title": "t", "body": "b"}))
    second = http.requests[1]["headers"]["authorization"]
    assert first != second  # provider token was re-minted after the 403


# --- platform routing in send_push_to_user --------------------------------


def test_routes_ios_to_apns_and_others_to_fcm():
    user = {
        "id": "u1",
        "push_devices": [
            {"token": "ios1", "platform": "ios"},
            {"token": "and1", "platform": "android"},
        ],
        "push_tokens": ["legacy1"],  # untagged legacy → treated as android/FCM
    }
    users = FakeUsers(user)
    fcm = RecordingClient()
    apns = RecordingClient()
    report = asyncio.run(
        push_sender.send_push_to_user(
            users_collection=users,
            user_id="u1",
            template_code=TEMPLATE,
            client=fcm,
            apns_client=apns,
        )
    )
    assert apns.tokens == ["ios1"]
    assert sorted(fcm.tokens) == ["and1", "legacy1"]
    assert report.delivered == 3


def test_ios_device_skipped_when_apns_unconfigured():
    user = {
        "id": "u1",
        "push_devices": [{"token": "ios1", "platform": "ios"}],
        "push_tokens": [],
    }
    users = FakeUsers(user)
    fcm = RecordingClient()
    report = asyncio.run(
        push_sender.send_push_to_user(
            users_collection=users,
            user_id="u1",
            template_code=TEMPLATE,
            client=fcm,
            apns_client=None,
        )
    )
    # no transport for iOS → skipped, never delivered, never pruned
    assert fcm.tokens == []
    assert report.delivered == 0
    assert users.user["push_devices"] == [{"token": "ios1", "platform": "ios"}]


def test_dead_ios_token_pruned_from_both_arrays():
    user = {
        "id": "u1",
        "push_devices": [{"token": "ios1", "platform": "ios"}],
        "push_tokens": ["ios1"],  # simulate a mis-stored duplicate
    }
    users = FakeUsers(user)
    apns = RecordingClient(outcome=PushOutcome.INVALID)
    asyncio.run(
        push_sender.send_push_to_user(
            users_collection=users,
            user_id="u1",
            template_code=TEMPLATE,
            client=RecordingClient(),
            apns_client=apns,
        )
    )
    assert users.user["push_devices"] == []
    assert users.user["push_tokens"] == []


def test_400_with_non_json_body_is_failed_not_pruned():
    private_pem, _ = _es256_keypair()
    cfg = ApnsConfig(
        auth_key=private_pem,
        key_id="K",
        team_id="T",
        topic="x",
        host=apns_client.APNS_PRODUCTION_HOST,
    )
    http = FakeHttp([FakeResponse(400, raise_json=True)])
    client = ApnsHttp2Client(config=cfg, http_client=http)
    outcome = asyncio.run(client.deliver("tok", {"title": "t", "body": "b"}))
    # An unparseable 400 body must not be treated as a dead token.
    assert outcome == PushOutcome.FAILED


def test_all_ios_deploy_delivers_via_apns_and_skips_legacy_android():
    user = {
        "id": "u1",
        "push_devices": [{"token": "ios1", "platform": "ios"}],
        "push_tokens": ["legacy_android"],
    }
    users = FakeUsers(user)
    apns = RecordingClient()
    # No FCM client configured (client=None) — an all-iOS deployment.
    report = asyncio.run(
        push_sender.send_push_to_user(
            users_collection=users,
            user_id="u1",
            template_code=TEMPLATE,
            client=None,
            apns_client=apns,
        )
    )
    assert apns.tokens == ["ios1"]
    assert report.delivered == 1
    # the legacy android token had no transport → skipped, not pruned
    assert users.user["push_tokens"] == ["legacy_android"]


def test_collect_devices_skips_malformed_entry():
    devices = push_sender._collect_devices(
        {
            "push_devices": ["not-a-dict", None, {"token": "good", "platform": "ios"}],
            "push_tokens": ["legacy"],
        }
    )
    assert devices == [("good", "ios"), ("legacy", "android")]


def test_collect_devices_dedupes_and_defaults():
    devices = push_sender._collect_devices(
        {
            "push_devices": [{"token": "a", "platform": "ios"}, {"token": "b"}],
            "push_tokens": ["a", "c"],  # 'a' already seen; 'c' new → android
        }
    )
    assert devices == [("a", "ios"), ("b", "android"), ("c", "android")]
