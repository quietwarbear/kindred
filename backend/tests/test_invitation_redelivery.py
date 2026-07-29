"""Synthetic privacy and state-machine tests for invitation redelivery."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
import pytest

from invitation_redelivery import (
    InvitationRedeliveryCoordinator,
    InvitationSelection,
    PreflightResult,
    ProviderReceipt,
    ProviderStatus,
    RedeliveryFailure,
    SafeErrorCode,
    SafeOperationReport,
    SensitiveActivationMaterial,
    SensitiveDeliveryTarget,
)
from invitation_redelivery_provider import (
    ResendInvitationDeliveryProvider,
)
from invitation_redelivery_validator import PublicRSVPHeaderValidator

OPERATION_ID = "0123456789abcdef0123456789abcdef"
BOUNDARY = datetime(2026, 7, 28, 19, 4, 14, tzinfo=timezone.utc)
SELECTION = InvitationSelection(
    invite_source="guest",
    expected_count=2,
    created_before=BOUNDARY,
)
SENSITIVE_NEEDLES = (
    "first.guest@example.invalid",
    "second.guest@example.invalid",
    "synthetic-old-credential-one",
    "synthetic-old-credential-two",
    "Synthetic Private Gathering",
    "Synthetic invitation body",
)


class FakeStore:
    def __init__(self):
        self.records = [
            {
                "id": "synthetic-old-credential-one",
                "email": "first.guest@example.invalid",
                "invite_source": "guest",
                "created_at": "2026-07-27T00:00:00+00:00",
                "rsvp_status": "going",
                "event_id": "synthetic-event-one",
                "title": "Synthetic Private Gathering",
                "note": "Synthetic invitation body",
            },
            {
                "id": "synthetic-old-credential-two",
                "email": "second.guest@example.invalid",
                "invite_source": "guest",
                "created_at": "2026-07-27T01:00:00+00:00",
                "rsvp_status": "maybe",
                "event_id": "synthetic-event-two",
                "title": "Synthetic Private Gathering",
                "note": "Synthetic invitation body",
            },
        ]
        self.original = deepcopy(self.records)
        self.operations = {}
        self.lock = threading.Lock()
        self.prepare_calls = 0
        self.activation_calls = 0

    def active_credentials(self):
        return {record["id"] for record in self.records}

    def _report(self, operation):
        targets = operation["targets"]
        selected = len(targets)
        delivered = sum(
            target["status"] == ProviderStatus.DELIVERED for target in targets
        )
        failures = sum(
            target["status"]
            in {
                ProviderStatus.REJECTED,
                ProviderStatus.AMBIGUOUS,
                ProviderStatus.FAILED,
            }
            for target in targets
        )
        status = operation["status"]
        return SafeOperationReport(
            operation_id=operation["id"],
            status=status,
            credentials_selected=selected,
            credentials_rotated=(
                selected
                if status in {"activated", "validation_failed", "completed"}
                else 0
            ),
            replacements_delivered=delivered,
            old_credentials_rejected=operation.get("old_rejected", 0),
            new_credentials_validated=operation.get("new_validated", 0),
            failures=max(failures, operation.get("validation_failures", 0)),
            error_code=operation.get("error_code", ""),
        )

    async def prepare(self, operation_id, selection, credential_factory):
        with self.lock:
            self.prepare_calls += 1
            if operation_id in self.operations:
                operation = self.operations[operation_id]
                if operation["selection"] != selection.safe_document():
                    raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                return self._report(operation)
            selected = [
                record
                for record in self.records
                if record["invite_source"] == selection.invite_source
                and record["created_at"] <= selection.created_before.isoformat()
            ]
            if len(selected) != selection.expected_count:
                raise RedeliveryFailure(SafeErrorCode.SELECTION_MISMATCH)
            targets = []
            for ordinal, record in enumerate(selected, 1):
                replacement = credential_factory()
                targets.append(
                    {
                        "target_id": f"target_{ordinal}",
                        "record": record,
                        "old": record["id"],
                        "new": replacement,
                        "idempotency_key": (
                            "kindred-invitation-redelivery/"
                            f"{operation_id}/target_{ordinal}"
                        ),
                        "status": ProviderStatus.PENDING,
                        "provider_message_id": "",
                    }
                )
            operation = {
                "id": operation_id,
                "selection": selection.safe_document(),
                "status": "prepared",
                "targets": targets,
            }
            self.operations[operation_id] = operation
            return self._report(operation)

    async def delivery_targets(self, operation_id):
        operation = self.operations[operation_id]
        if operation["status"] in {
            "activated",
            "validation_failed",
            "completed",
        }:
            return ()
        return tuple(
            SensitiveDeliveryTarget(
                target_id=target["target_id"],
                recipient=target["record"]["email"],
                replacement_credential=target["new"],
                idempotency_key=target["idempotency_key"],
                provider_message_id=target["provider_message_id"],
                provider_status=target["status"],
            )
            for target in operation["targets"]
            if target["status"] != ProviderStatus.DELIVERED
        )

    async def claim_provider_submission(self, operation_id, target_id):
        with self.lock:
            operation = self.operations[operation_id]
            target = next(
                item for item in operation["targets"] if item["target_id"] == target_id
            )
            if target["status"] not in {
                ProviderStatus.PENDING,
                ProviderStatus.REJECTED,
            }:
                return None
            target["status"] = ProviderStatus.SUBMITTING
            return SensitiveDeliveryTarget(
                target_id=target["target_id"],
                recipient=target["record"]["email"],
                replacement_credential=target["new"],
                idempotency_key=target["idempotency_key"],
                provider_status=ProviderStatus.SUBMITTING,
            )

    async def record_provider_receipt(
        self,
        operation_id,
        target_id,
        receipt,
    ):
        with self.lock:
            operation = self.operations[operation_id]
            target = next(
                item for item in operation["targets"] if item["target_id"] == target_id
            )
            target["status"] = receipt.status
            target["error_code"] = receipt.error_code.value
            if receipt.provider_message_id:
                target["provider_message_id"] = receipt.provider_message_id
            operation["status"] = (
                "activation_ready"
                if all(
                    item["status"] == ProviderStatus.DELIVERED
                    for item in operation["targets"]
                )
                else "awaiting_delivery"
            )
            operation["error_code"] = next(
                (
                    item.get("error_code", "")
                    for item in operation["targets"]
                    if item.get("error_code")
                ),
                "",
            )
            return self._report(operation)

    async def activate_if_ready(self, operation_id):
        with self.lock:
            operation = self.operations[operation_id]
            if operation["status"] in {"activated", "validation_failed"}:
                return SensitiveActivationMaterial(
                    operation_id=operation_id,
                    credential_pairs=tuple(
                        (target["old"], target["new"])
                        for target in operation["targets"]
                    ),
                )
            if operation["status"] == "completed":
                return None
            if not all(
                target["status"] == ProviderStatus.DELIVERED
                for target in operation["targets"]
            ):
                return None
            self.activation_calls += 1
            for target in operation["targets"]:
                record = target["record"]
                record["id"] = target["new"]
            operation["status"] = "activated"
            return SensitiveActivationMaterial(
                operation_id=operation_id,
                credential_pairs=tuple(
                    (target["old"], target["new"]) for target in operation["targets"]
                ),
            )

    async def record_validation(
        self,
        operation_id,
        *,
        old_credentials_rejected,
        new_credentials_validated,
        failures,
    ):
        operation = self.operations[operation_id]
        operation["old_rejected"] = old_credentials_rejected
        operation["new_validated"] = new_credentials_validated
        operation["validation_failures"] = failures
        operation["status"] = "completed" if failures == 0 else "validation_failed"
        operation["error_code"] = (
            "" if failures == 0 else SafeErrorCode.VALIDATION_FAILED.value
        )
        return self._report(operation)

    async def report(self, operation_id):
        if operation_id not in self.operations:
            raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
        return self._report(self.operations[operation_id])


class FakeProvider:
    def __init__(
        self,
        *,
        ready=True,
        send_statuses=None,
        delivery_statuses=None,
    ):
        self.ready = ready
        self.send_statuses = {
            key: list(value) for key, value in (send_statuses or {}).items()
        }
        self.delivery_statuses = {
            key: list(value) for key, value in (delivery_statuses or {}).items()
        }
        self.envelopes = []
        self.send_calls = 0
        self._accepted = {}
        self._lock = threading.Lock()

    async def preflight(self):
        return PreflightResult(
            ready=self.ready,
            error_code=(
                SafeErrorCode.NONE if self.ready else SafeErrorCode.PROVIDER_UNAVAILABLE
            ),
        )

    async def send(self, envelope):
        with self._lock:
            self.envelopes.append(envelope)
            self.send_calls += 1
            scripted = self.send_statuses.get(envelope.target_id, [])
            if scripted:
                receipt = scripted.pop(0)
            elif envelope.idempotency_key in self._accepted:
                receipt = self._accepted[envelope.idempotency_key]
            else:
                receipt = ProviderReceipt(
                    status=ProviderStatus.ACCEPTED,
                    provider_message_id=f"provider_{envelope.target_id}_0001",
                )
            if receipt.status == ProviderStatus.ACCEPTED:
                self._accepted[envelope.idempotency_key] = receipt
            return receipt

    async def delivery_status(
        self,
        provider_message_id,
        *,
        operation_id,
        target_id,
    ):
        scripted = self.delivery_statuses.get(target_id, [])
        if scripted:
            return scripted.pop(0)
        return ProviderReceipt(
            status=ProviderStatus.DELIVERED,
            provider_message_id=provider_message_id,
        )


class FakeValidator:
    def __init__(self, store, *, ready=True, force_failure=False):
        self.store = store
        self.ready = ready
        self.force_failure = force_failure

    async def preflight(self):
        return PreflightResult(
            ready=self.ready,
            error_code=(
                SafeErrorCode.NONE
                if self.ready
                else SafeErrorCode.VALIDATION_UNAVAILABLE
            ),
        )

    async def old_credential_rejected(self, credential):
        return (
            not self.force_failure and credential not in self.store.active_credentials()
        )

    async def new_credential_valid(self, credential):
        return not self.force_failure and credential in self.store.active_credentials()


def run(coroutine):
    return asyncio.run(coroutine)


def coordinator(store, provider, validator=None):
    return InvitationRedeliveryCoordinator(
        store=store,
        provider=provider,
        validator=validator or FakeValidator(store),
        app_url="https://kindred.example.invalid",
    )


def test_successful_two_invitation_rotation_is_private_and_preserves_state(
    caplog,
):
    store = FakeStore()
    provider = FakeProvider()
    before = deepcopy(store.records)
    with caplog.at_level(logging.INFO):
        report = run(
            coordinator(store, provider).execute(
                SELECTION,
                operation_id=OPERATION_ID,
            )
        )

    assert report.to_dict() == {
        "operation_id": OPERATION_ID,
        "status": "completed",
        "credentials_selected": 2,
        "credentials_rotated": 2,
        "replacements_delivered": 2,
        "old_credentials_rejected": 2,
        "new_credentials_validated": 2,
        "failures": 0,
        "error_code": "",
    }
    assert store.active_credentials().isdisjoint({item["id"] for item in before})
    for original, rotated in zip(before, store.records):
        for field in (
            "email",
            "invite_source",
            "created_at",
            "rsvp_status",
            "event_id",
            "title",
            "note",
        ):
            assert rotated[field] == original[field]
    assert len(provider.envelopes) == 2
    for envelope in provider.envelopes:
        marker = 'href="'
        invitation_url = envelope.html_body.split(marker, 1)[1].split(
            '"',
            1,
        )[0]
        parsed = urlsplit(invitation_url)
        assert parsed.path == "/rsvp"
        assert parsed.query == ""
        assert parsed.fragment
        assert parsed.fragment not in parsed.path
        assert parsed.fragment not in parsed.query
        assert repr(envelope).count("<redacted>") == 3

    rendered = caplog.text + json.dumps(report.to_dict(), sort_keys=True)
    for needle in SENSITIVE_NEEDLES:
        assert needle not in rendered
    for record in store.records:
        assert record["id"] not in rendered


@pytest.mark.parametrize(
    ("provider_ready", "validator_ready", "expected_code"),
    (
        (False, True, SafeErrorCode.PROVIDER_UNAVAILABLE.value),
        (True, False, SafeErrorCode.VALIDATION_UNAVAILABLE.value),
    ),
)
def test_preflight_failure_does_not_mutate(
    provider_ready,
    validator_ready,
    expected_code,
):
    store = FakeStore()
    before = deepcopy(store.records)
    provider = FakeProvider(ready=provider_ready)
    validator = FakeValidator(store, ready=validator_ready)
    report = run(
        coordinator(store, provider, validator).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert report.status == "preflight_failed"
    assert report.error_code == expected_code
    assert report.credentials_selected == 0
    assert report.credentials_rotated == 0
    assert report.failures == 1
    assert store.records == before
    assert store.operations == {}
    assert provider.envelopes == []


@pytest.mark.parametrize(
    ("receipt", "expected_code"),
    (
        (
            ProviderReceipt(
                ProviderStatus.REJECTED,
                error_code=SafeErrorCode.PROVIDER_REJECTED,
            ),
            SafeErrorCode.PROVIDER_REJECTED,
        ),
        (
            ProviderReceipt(
                ProviderStatus.AMBIGUOUS,
                error_code=SafeErrorCode.PROVIDER_TIMEOUT,
            ),
            SafeErrorCode.PROVIDER_TIMEOUT,
        ),
        (
            ProviderReceipt(
                ProviderStatus.FAILED,
                error_code=SafeErrorCode.DELIVERY_FAILED,
            ),
            SafeErrorCode.DELIVERY_FAILED,
        ),
    ),
)
def test_rejection_timeout_and_delivery_failure_leave_old_tokens_active(
    receipt,
    expected_code,
):
    store = FakeStore()
    old_credentials = store.active_credentials()
    provider = FakeProvider(
        send_statuses={"target_1": [receipt]},
    )
    report = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert report.status == "awaiting_delivery"
    assert report.credentials_selected == 2
    assert report.credentials_rotated == 0
    assert report.replacements_delivered == 1
    assert report.failures == 1
    assert report.error_code == expected_code.value
    assert store.active_credentials() == old_credentials
    assert store.activation_calls == 0
    target = store.operations[OPERATION_ID]["targets"][0]
    assert target["status"] == receipt.status
    assert receipt.error_code == expected_code


def test_ambiguous_acceptance_retry_fails_closed_without_duplicate_delivery():
    store = FakeStore()
    old_credentials = store.active_credentials()
    provider = FakeProvider(
        send_statuses={
            "target_1": [
                ProviderReceipt(
                    ProviderStatus.AMBIGUOUS,
                    error_code=SafeErrorCode.PROVIDER_TIMEOUT,
                ),
            ]
        }
    )
    first = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert first.credentials_rotated == 0
    assert store.active_credentials() == old_credentials

    second = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert second.status == "awaiting_delivery"
    assert second.credentials_rotated == 0
    assert second.replacements_delivered == 1
    assert store.prepare_calls == 2
    target_one_sends = [
        item for item in provider.envelopes if item.target_id == "target_1"
    ]
    assert len(target_one_sends) == 1


def test_partial_failure_is_recoverable_and_does_not_duplicate_accepted_send():
    store = FakeStore()
    provider = FakeProvider(
        send_statuses={
            "target_2": [
                ProviderReceipt(
                    ProviderStatus.REJECTED,
                    error_code=SafeErrorCode.PROVIDER_REJECTED,
                ),
                ProviderReceipt(
                    ProviderStatus.ACCEPTED,
                    provider_message_id="provider_target_2_0001",
                ),
            ]
        }
    )
    first = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert first.replacements_delivered == 1
    assert first.credentials_rotated == 0

    second = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert second.status == "completed"
    assert second.credentials_rotated == 2
    target_one_sends = [
        item for item in provider.envelopes if item.target_id == "target_1"
    ]
    assert len(target_one_sends) == 1


def test_accepted_delivery_is_polled_without_resubmission():
    store = FakeStore()
    provider = FakeProvider(
        delivery_statuses={
            "target_1": [
                ProviderReceipt(
                    ProviderStatus.ACCEPTED,
                    provider_message_id="provider_target_1_0001",
                ),
                ProviderReceipt(
                    ProviderStatus.DELIVERED,
                    provider_message_id="provider_target_1_0001",
                ),
            ]
        }
    )
    first = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert first.credentials_rotated == 0
    assert first.replacements_delivered == 1

    second = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert second.status == "completed"
    target_one_sends = [
        item for item in provider.envelopes if item.target_id == "target_1"
    ]
    assert len(target_one_sends) == 1


def test_interrupted_submission_is_not_automatically_replayed():
    store = FakeStore()
    run(store.prepare(OPERATION_ID, SELECTION, lambda: "synthetic-new"))
    claimed = run(store.claim_provider_submission(OPERATION_ID, "target_1"))
    assert claimed is not None
    provider = FakeProvider()

    report = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )

    assert report.status == "awaiting_delivery"
    assert report.credentials_rotated == 0
    assert report.replacements_delivered == 1
    assert not any(envelope.target_id == "target_1" for envelope in provider.envelopes)


def test_completed_retry_and_concurrent_execution_are_idempotent():
    store = FakeStore()
    provider = FakeProvider()
    flow = coordinator(store, provider)

    async def concurrent_run():
        return await asyncio.gather(
            flow.execute(SELECTION, operation_id=OPERATION_ID),
            flow.execute(SELECTION, operation_id=OPERATION_ID),
        )

    reports = run(concurrent_run())
    final = run(flow.execute(SELECTION, operation_id=OPERATION_ID))
    assert final.status == "completed"
    assert final.credentials_rotated == 2
    assert store.activation_calls == 1
    assert all(report.credentials_selected == 2 for report in reports)
    assert len(store.active_credentials()) == 2
    assert len(set(store.active_credentials())) == 2
    for key in {envelope.idempotency_key for envelope in provider.envelopes}:
        matching = [
            envelope
            for envelope in provider.envelopes
            if envelope.idempotency_key == key
        ]
        assert len(matching) == 1


def test_header_validator_uses_only_stable_path_and_authorization_header():
    observed = []

    def handler(request):
        observed.append(request)
        auth = request.headers.get("Authorization", "")
        if not auth:
            return httpx.Response(401)
        if auth == "Bearer synthetic-old":
            return httpx.Response(404)
        if auth == "Bearer synthetic-new":
            return httpx.Response(200, json={"rsvp_status": "pending"})
        return httpx.Response(404)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )
    validator = PublicRSVPHeaderValidator(
        api_base_url="https://api.kindred.example.invalid",
        client=client,
    )

    async def campaign():
        assert (await validator.preflight()).ready
        assert await validator.old_credential_rejected("synthetic-old")
        assert await validator.new_credential_valid("synthetic-new")
        await client.aclose()

    run(campaign())
    assert len(observed) == 3
    for request in observed:
        assert request.url.path == "/api/public/rsvp"
        assert request.url.query == b""
        assert request.url.fragment == ""
        assert "synthetic-old" not in str(request.url)
        assert "synthetic-new" not in str(request.url)


def test_resend_adapter_logs_only_safe_categories(caplog):
    observed_payloads = []

    def handler(request):
        if request.url.path == "/domains":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "name": "heykindred.org",
                            "status": "verified",
                        }
                    ]
                },
            )
        if request.url.path == "/emails" and request.method == "POST":
            observed_payloads.append(json.loads(request.content))
            return httpx.Response(
                201,
                json={"id": "provider_message_000001"},
            )
        if request.url.path == "/emails/provider_message_000001":
            return httpx.Response(
                200,
                json={"last_event": "delivered"},
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="https://api.resend.com",
        transport=httpx.MockTransport(handler),
    )
    provider = ResendInvitationDeliveryProvider(
        api_key="synthetic-provider-key",
        from_address="Kindred <noreply@heykindred.org>",
        client=client,
    )
    store = FakeStore()
    with caplog.at_level(logging.INFO):
        report = run(
            coordinator(store, provider).execute(
                SELECTION,
                operation_id=OPERATION_ID,
            )
        )
    run(client.aclose())
    assert report.status == "completed"
    assert len(observed_payloads) == 2
    assert all("to" in payload for payload in observed_payloads)
    rendered = caplog.text + json.dumps(report.to_dict(), sort_keys=True)
    for needle in SENSITIVE_NEEDLES:
        assert needle not in rendered
    for record in store.records:
        assert record["id"] not in rendered
