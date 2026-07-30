"""Synthetic signed-webhook recovery tests for invitation redelivery."""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import logging
import sys
import types
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from svix.webhooks import Webhook
from starlette.requests import Request

from invitation_redelivery import (
    ProviderStatus,
    RedeliveryFailure,
    SafeErrorCode,
)
from invitation_redelivery_store import record_provider_delivery_event
from invitation_redelivery_webhook import (
    MAX_WEBHOOK_BODY_BYTES,
    VerifiedDeliveryEvent,
    validate_webhook_secret,
    verify_resend_delivery_event,
)

WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"synthetic-resend-webhook-secret").decode(
    "ascii"
)
EVENT_TIME = datetime.now(timezone.utc)
SENSITIVE_VALUES = (
    "private.guest@example.invalid",
    "synthetic-invitation-credential",
    "Synthetic Private Gathering",
    "Synthetic private invitation body",
)


def signed_event(
    event_type: str,
    *,
    event_id: str = "evt_synthetic_0001",
    provider_message_id: str = "provider_message_0001",
):
    payload = {
        "type": event_type,
        "created_at": EVENT_TIME.isoformat(),
        "data": {
            "email_id": provider_message_id,
            "to": [SENSITIVE_VALUES[0]],
            "subject": SENSITIVE_VALUES[2],
            "html": (
                f"{SENSITIVE_VALUES[3]} "
                f"https://heykindred.org/rsvp#{SENSITIVE_VALUES[1]}"
            ),
        },
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return raw_body, {
        "svix-id": event_id,
        "svix-timestamp": str(int(EVENT_TIME.timestamp())),
        "svix-signature": Webhook(WEBHOOK_SECRET).sign(
            event_id,
            EVENT_TIME,
            raw_body.decode("utf-8"),
        ),
    }


def test_verified_event_discards_all_provider_payload_and_redacts_repr():
    raw_body, headers = signed_event("email.delivered")
    event = verify_resend_delivery_event(
        raw_body=raw_body,
        headers=headers,
        signing_secret=WEBHOOK_SECRET,
    )

    assert event is not None
    assert event.provider_status == ProviderStatus.DELIVERED
    rendered = repr(event) + json.dumps(event.__dict__, sort_keys=True)
    for value in SENSITIVE_VALUES:
        assert value not in rendered


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        ("email.delivered", ProviderStatus.DELIVERED),
        ("email.bounced", ProviderStatus.FAILED),
        ("email.failed", ProviderStatus.FAILED),
        ("email.suppressed", ProviderStatus.FAILED),
        ("email.complained", ProviderStatus.FAILED),
    ],
)
def test_only_safe_terminal_status_is_derived(event_type, expected):
    raw_body, headers = signed_event(event_type)
    event = verify_resend_delivery_event(
        raw_body=raw_body,
        headers=headers,
        signing_secret=WEBHOOK_SECRET,
    )
    assert event is not None
    assert event.provider_status == expected


def test_invalid_signature_fails_with_sanitized_error():
    raw_body, headers = signed_event("email.delivered")
    headers["svix-signature"] = "v1,invalid"
    with pytest.raises(RedeliveryFailure) as caught:
        verify_resend_delivery_event(
            raw_body=raw_body,
            headers=headers,
            signing_secret=WEBHOOK_SECRET,
        )
    assert caught.value.code == SafeErrorCode.PROVIDER_AMBIGUOUS
    for value in SENSITIVE_VALUES:
        assert value not in str(caught.value)


def test_unsupported_signed_event_is_ignored():
    raw_body, headers = signed_event("email.sent")
    assert (
        verify_resend_delivery_event(
            raw_body=raw_body,
            headers=headers,
            signing_secret=WEBHOOK_SECRET,
        )
        is None
    )


def test_oversized_payload_fails_closed_before_parsing():
    with pytest.raises(RedeliveryFailure) as caught:
        verify_resend_delivery_event(
            raw_body=b"x" * (MAX_WEBHOOK_BODY_BYTES + 1),
            headers={},
            signing_secret=WEBHOOK_SECRET,
        )
    assert caught.value.code == SafeErrorCode.PROVIDER_AMBIGUOUS


@pytest.mark.parametrize(
    "unsafe_secret",
    (
        "",
        "whsec_short",
        "whsec_not-valid-base64-material",
        "synthetic-resend-webhook-secret",
    ),
)
def test_webhook_secret_preflight_rejects_malformed_material(unsafe_secret):
    with pytest.raises(RedeliveryFailure) as caught:
        validate_webhook_secret(unsafe_secret)
    assert caught.value.code == SafeErrorCode.CONFIGURATION_UNAVAILABLE


class _Transaction:
    def __init__(self, lock):
        self._lock = lock

    async def __aenter__(self):
        await self._lock.acquire()

    async def __aexit__(self, exc_type, exc, traceback):
        self._lock.release()


class _Session:
    def __init__(self, lock):
        self._lock = lock

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    def start_transaction(self):
        return _Transaction(self._lock)


class _Client:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def start_session(self):
        return _Session(self._lock)


class _Cursor:
    def __init__(self, documents):
        self._documents = documents

    async def to_list(self, length):
        return deepcopy(self._documents[:length])


class _Result:
    def __init__(self, matched_count):
        self.matched_count = matched_count


class _Operations:
    def __init__(self, documents):
        self.documents = documents
        self.update_calls = 0

    def find(self, query, projection, session):
        provider_message_id = query["targets.provider_message_id"]
        return _Cursor(
            [
                document
                for document in self.documents
                if any(
                    target.get("provider_message_id") == provider_message_id
                    for target in document.get("targets") or []
                )
            ]
        )

    async def update_one(self, query, update, session):
        for document in self.documents:
            if document["id"] != query["id"]:
                continue
            if document.get("status") != query["status"]:
                continue
            if query["provider_event_ids"]["$ne"] in document.get(
                "provider_event_ids", []
            ):
                continue
            expected_revision = query["provider_event_revision"]
            current_revision = document.get("provider_event_revision")
            if isinstance(expected_revision, dict):
                if current_revision not in expected_revision["$in"]:
                    continue
            elif current_revision != expected_revision:
                continue
            document.update(deepcopy(update["$set"]))
            self.update_calls += 1
            return _Result(1)
        return _Result(0)


def operation_document():
    return {
        "id": "0123456789abcdef0123456789abcdef",
        "status": "awaiting_delivery",
        "error_code": SafeErrorCode.PROVIDER_AMBIGUOUS.value,
        "targets": [
            {
                "target_id": "target_1",
                "provider_message_id": "provider_message_0001",
                "provider_status": ProviderStatus.AMBIGUOUS.value,
                "error_code": SafeErrorCode.PROVIDER_AMBIGUOUS.value,
            },
            {
                "target_id": "target_2",
                "provider_message_id": "provider_message_0002",
                "provider_status": ProviderStatus.ACCEPTED.value,
                "error_code": "",
            },
        ],
    }


def verified_event(event_id, provider_message_id, status):
    return VerifiedDeliveryEvent(
        event_id=event_id,
        provider_message_id=provider_message_id,
        provider_status=status,
        occurred_at=EVENT_TIME.isoformat(),
    )


def run(coroutine):
    return asyncio.run(coroutine)


def request_for(raw_body, headers, *, include_content_length=True):
    encoded_headers = [
        (name.encode("ascii"), value.encode("ascii")) for name, value in headers.items()
    ]
    if include_content_length:
        encoded_headers.append((b"content-length", str(len(raw_body)).encode("ascii")))
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": raw_body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/provider/resend/invitation-delivery",
            "raw_path": b"/api/provider/resend/invitation-delivery",
            "query_string": b"",
            "headers": encoded_headers,
            "client": ("127.0.0.1", 1),
            "server": ("api.example.invalid", 443),
        },
        receive,
    )


def test_route_accepts_verified_event_without_logging_payload(
    monkeypatch,
    caplog,
):
    fake_db = types.ModuleType("db")
    fake_db.client = object()
    fake_db.invitation_redelivery_operations_collection = object()
    monkeypatch.setitem(sys.modules, "db", fake_db)
    sys.modules.pop("routes.resend_webhooks", None)
    route = importlib.import_module("routes.resend_webhooks")
    observed = []

    async def fake_record_provider_delivery_event(**kwargs):
        observed.append(kwargs["event"])
        return "delivered"

    monkeypatch.setattr(
        route,
        "record_provider_delivery_event",
        fake_record_provider_delivery_event,
    )
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    raw_body, headers = signed_event("email.delivered")

    with caplog.at_level(logging.INFO):
        response = run(
            route.invitation_delivery_webhook(request_for(raw_body, headers))
        )

    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "accepted"}
    assert response.headers["cache-control"] == "no-store"
    assert len(observed) == 1
    rendered = caplog.text + repr(observed[0])
    for value in SENSITIVE_VALUES:
        assert value not in rendered
    sys.modules.pop("routes.resend_webhooks", None)


def test_route_rejects_invalid_signature_without_store_call(monkeypatch):
    fake_db = types.ModuleType("db")
    fake_db.client = object()
    fake_db.invitation_redelivery_operations_collection = object()
    monkeypatch.setitem(sys.modules, "db", fake_db)
    sys.modules.pop("routes.resend_webhooks", None)
    route = importlib.import_module("routes.resend_webhooks")
    store_calls = 0

    async def fake_record_provider_delivery_event(**kwargs):
        nonlocal store_calls
        store_calls += 1
        return "delivered"

    monkeypatch.setattr(
        route,
        "record_provider_delivery_event",
        fake_record_provider_delivery_event,
    )
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    raw_body, headers = signed_event("email.delivered")
    headers["svix-signature"] = "v1,invalid"

    response = run(route.invitation_delivery_webhook(request_for(raw_body, headers)))

    assert response.status_code == 400
    assert json.loads(response.body) == {"status": "rejected"}
    assert store_calls == 0
    sys.modules.pop("routes.resend_webhooks", None)


def test_route_stops_oversized_chunked_body_without_store_call(monkeypatch):
    fake_db = types.ModuleType("db")
    fake_db.client = object()
    fake_db.invitation_redelivery_operations_collection = object()
    monkeypatch.setitem(sys.modules, "db", fake_db)
    sys.modules.pop("routes.resend_webhooks", None)
    route = importlib.import_module("routes.resend_webhooks")
    store_calls = 0

    async def fake_record_provider_delivery_event(**kwargs):
        nonlocal store_calls
        store_calls += 1
        return "delivered"

    monkeypatch.setattr(
        route,
        "record_provider_delivery_event",
        fake_record_provider_delivery_event,
    )
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    response = run(
        route.invitation_delivery_webhook(
            request_for(
                b"x" * (MAX_WEBHOOK_BODY_BYTES + 1),
                {},
                include_content_length=False,
            )
        )
    )

    assert response.status_code == 413
    assert store_calls == 0
    sys.modules.pop("routes.resend_webhooks", None)


def test_ambiguous_accepted_operation_recovers_without_provider_submission():
    client = _Client()
    operations = _Operations([operation_document()])

    first = run(
        record_provider_delivery_event(
            client=client,
            operations_collection=operations,
            event=verified_event(
                "evt_synthetic_0001",
                "provider_message_0001",
                ProviderStatus.DELIVERED,
            ),
        )
    )
    second = run(
        record_provider_delivery_event(
            client=client,
            operations_collection=operations,
            event=verified_event(
                "evt_synthetic_0002",
                "provider_message_0002",
                ProviderStatus.DELIVERED,
            ),
        )
    )

    assert (first, second) == ("delivered", "delivered")
    assert operations.documents[0]["status"] == "activation_ready"
    assert operations.update_calls == 2


def test_duplicate_and_concurrent_delivery_events_are_idempotent():
    client = _Client()
    operations = _Operations([operation_document()])
    event = verified_event(
        "evt_synthetic_0001",
        "provider_message_0001",
        ProviderStatus.DELIVERED,
    )

    async def campaign():
        return await asyncio.gather(
            *(
                record_provider_delivery_event(
                    client=client,
                    operations_collection=operations,
                    event=event,
                )
                for _ in range(2)
            )
        )

    assert sorted(run(campaign())) == ["delivered", "duplicate"]
    assert operations.update_calls == 1


def test_out_of_order_failure_cannot_downgrade_delivered_target():
    document = operation_document()
    document["targets"][0]["provider_status"] = ProviderStatus.DELIVERED.value
    document["targets"][0]["error_code"] = ""
    operations = _Operations([document])

    outcome = run(
        record_provider_delivery_event(
            client=_Client(),
            operations_collection=operations,
            event=verified_event(
                "evt_synthetic_0003",
                "provider_message_0001",
                ProviderStatus.FAILED,
            ),
        )
    )

    assert outcome == "ignored"
    assert (
        operations.documents[0]["targets"][0]["provider_status"]
        == ProviderStatus.DELIVERED.value
    )


def test_failure_event_blocks_activation_with_sanitized_code():
    operations = _Operations([operation_document()])
    outcome = run(
        record_provider_delivery_event(
            client=_Client(),
            operations_collection=operations,
            event=verified_event(
                "evt_synthetic_0004",
                "provider_message_0002",
                ProviderStatus.FAILED,
            ),
        )
    )

    assert outcome == "failed"
    assert operations.documents[0]["status"] == "awaiting_delivery"
    assert (
        operations.documents[0]["targets"][1]["error_code"]
        == SafeErrorCode.DELIVERY_FAILED.value
    )


def test_non_unique_or_unknown_provider_reference_is_ignored_without_mutation():
    first = operation_document()
    second = deepcopy(first)
    second["id"] = "fedcba9876543210fedcba9876543210"
    operations = _Operations([first, second])

    outcome = run(
        record_provider_delivery_event(
            client=_Client(),
            operations_collection=operations,
            event=verified_event(
                "evt_synthetic_0005",
                "provider_message_0001",
                ProviderStatus.DELIVERED,
            ),
        )
    )

    assert outcome == "ignored"
    assert operations.update_calls == 0


def test_duplicate_provider_reference_within_operation_is_ignored():
    document = operation_document()
    document["targets"][1]["provider_message_id"] = "provider_message_0001"
    operations = _Operations([document])

    outcome = run(
        record_provider_delivery_event(
            client=_Client(),
            operations_collection=operations,
            event=verified_event(
                "evt_synthetic_0006",
                "provider_message_0001",
                ProviderStatus.DELIVERED,
            ),
        )
    )

    assert outcome == "ignored"
    assert operations.update_calls == 0


def test_terminal_operation_is_immutable():
    document = operation_document()
    document["status"] = "completed"
    before = deepcopy(document)
    operations = _Operations([document])

    outcome = run(
        record_provider_delivery_event(
            client=_Client(),
            operations_collection=operations,
            event=verified_event(
                "evt_synthetic_0007",
                "provider_message_0001",
                ProviderStatus.DELIVERED,
            ),
        )
    )

    assert outcome == "terminal"
    assert operations.documents[0] == before
    assert operations.update_calls == 0
