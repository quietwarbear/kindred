"""Synthetic privacy and state-machine tests for invitation redelivery."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import subprocess
import sys
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

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
    CredentialVault,
    normalize_application_url,
    selection_fingerprint,
)
from invitation_redelivery_provider import (
    ResendInvitationDeliveryProvider,
)
from invitation_redelivery_validator import PublicRSVPHeaderValidator

OPERATION_ID = "0123456789abcdef0123456789abcdef"
SYNTHETIC_PROVIDER_KEY = "synthetic-provider-key"  # pragma: allowlist secret
WEBHOOK_SECRET = "whsec_" + base64.b64encode(  # pragma: allowlist secret
    b"synthetic-resend-webhook-secret"
).decode("ascii")
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
        self.preflight_calls = 0
        self.preflight_ready = True

    async def preflight(self):
        self.preflight_calls += 1
        return PreflightResult(
            ready=self.preflight_ready,
            error_code=(
                SafeErrorCode.NONE
                if self.preflight_ready
                else SafeErrorCode.TRANSACTION_REQUIRED
            ),
        )

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
            fingerprint = selection_fingerprint(selection)
            if operation_id in self.operations:
                operation = self.operations[operation_id]
                if operation["selection"] != selection.safe_document():
                    raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                return self._report(operation)
            if any(
                operation["selection_fingerprint"] == fingerprint
                for operation in self.operations.values()
            ):
                raise RedeliveryFailure(SafeErrorCode.INCIDENT_ALREADY_CLAIMED)
            selected = [
                record
                for record in self.records
                if record["invite_source"] == selection.invite_source
                and record["created_at"] <= selection.created_before.isoformat()
                and not record.get("credential_rotation")
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
                "selection_fingerprint": fingerprint,
                "status": "prepared",
                "targets": targets,
                "validation_revision": 0,
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

    def record_webhook(self, operation_id, target_id, status):
        with self.lock:
            operation = self.operations[operation_id]
            target = next(
                item for item in operation["targets"] if item["target_id"] == target_id
            )
            if status == ProviderStatus.DELIVERED:
                target["status"] = ProviderStatus.DELIVERED
                target["error_code"] = ""
            elif target["status"] != ProviderStatus.DELIVERED:
                target["status"] = ProviderStatus.FAILED
                target["error_code"] = SafeErrorCode.DELIVERY_FAILED.value
            operation["status"] = (
                "activation_ready"
                if all(
                    item["status"] == ProviderStatus.DELIVERED
                    for item in operation["targets"]
                )
                else "awaiting_delivery"
            )

    async def activate_if_ready(self, operation_id):
        with self.lock:
            operation = self.operations[operation_id]
            if operation["status"] in {"activated", "validation_failed"}:
                return SensitiveActivationMaterial(
                    operation_id=operation_id,
                    validation_revision=operation["validation_revision"],
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
                record["credential_rotation"] = {
                    "operation_id": operation_id,
                    "selection_fingerprint": operation["selection_fingerprint"],
                }
            operation["status"] = "activated"
            return SensitiveActivationMaterial(
                operation_id=operation_id,
                validation_revision=operation["validation_revision"],
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
        expected_validation_revision,
    ):
        with self.lock:
            operation = self.operations[operation_id]
            if operation["status"] == "completed":
                return self._report(operation)
            current_revision = operation["validation_revision"]
            complete = (
                failures == 0
                and old_credentials_rejected == len(operation["targets"])
                and new_credentials_validated == len(operation["targets"])
            )
            if current_revision > expected_validation_revision and not complete:
                return self._report(operation)
            operation["old_rejected"] = old_credentials_rejected
            operation["new_validated"] = new_credentials_validated
            operation["validation_failures"] = failures
            operation["validation_revision"] = current_revision + 1
            operation["status"] = "completed" if complete else "activated"
            operation["error_code"] = (
                "" if complete else SafeErrorCode.VALIDATION_FAILED.value
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
    ):
        self.ready = ready
        self.send_statuses = {
            key: list(value) for key, value in (send_statuses or {}).items()
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
                    status=ProviderStatus.DELIVERED,
                    provider_message_id=f"provider_{envelope.target_id}_0001",
                )
            if receipt.status in {
                ProviderStatus.ACCEPTED,
                ProviderStatus.DELIVERED,
            }:
                self._accepted[envelope.idempotency_key] = receipt
            return receipt


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
    ("provider_ready", "validator_ready", "store_ready", "expected_code"),
    (
        (False, True, True, SafeErrorCode.PROVIDER_UNAVAILABLE.value),
        (True, False, True, SafeErrorCode.VALIDATION_UNAVAILABLE.value),
        (True, True, False, SafeErrorCode.TRANSACTION_REQUIRED.value),
    ),
)
def test_preflight_failure_does_not_mutate(
    provider_ready,
    validator_ready,
    store_ready,
    expected_code,
):
    store = FakeStore()
    before = deepcopy(store.records)
    provider = FakeProvider(ready=provider_ready)
    validator = FakeValidator(store, ready=validator_ready)
    store.preflight_ready = store_ready
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
    ("component", "expected_code"),
    (
        ("provider", SafeErrorCode.PROVIDER_UNAVAILABLE.value),
        ("validator", SafeErrorCode.VALIDATION_UNAVAILABLE.value),
        ("store", SafeErrorCode.TRANSACTION_REQUIRED.value),
    ),
)
def test_preflight_exception_is_sanitized_and_does_not_mutate(
    component,
    expected_code,
    caplog,
):
    store = FakeStore()
    before = deepcopy(store.records)
    provider = FakeProvider()
    validator = FakeValidator(store)

    async def unsafe_preflight():
        raise RuntimeError("synthetic-private-preflight-payload")

    setattr(
        {"provider": provider, "validator": validator, "store": store}[component],
        "preflight",
        unsafe_preflight,
    )
    with caplog.at_level(logging.INFO):
        report = run(
            coordinator(store, provider, validator).execute(
                SELECTION,
                operation_id=OPERATION_ID,
            )
        )

    assert report.status == "preflight_failed"
    assert report.error_code == expected_code
    assert report.failures == 1
    assert store.records == before
    assert store.operations == {}
    assert provider.send_calls == 0
    assert "synthetic-private-preflight-payload" not in caplog.text


@pytest.mark.parametrize(
    "app_url",
    (
        "",
        "http://kindred.example.invalid",
        "https://user@kindred.example.invalid",
        "https://kindred.example.invalid/path",
        "https://kindred.example.invalid?query=unsafe",
        "https://kindred.example.invalid#fragment",
        "https://kindred.example.invalid:unsafe",
        "https://kindred.example.invalid\\@unsafe.example",
        "https://kindred.example.invalid/\nunsafe",
        "https://localhost",
        "https://kindred.localhost",
        "https://127.0.0.1",
        "https://[::1]",
        "https://single-label",
        "https://unsafe_host.example",
        "not-a-url",
    ),
)
def test_app_url_validation_precedes_every_mutation(app_url):
    store = FakeStore()
    before = deepcopy(store.records)
    provider = FakeProvider()

    with pytest.raises(RedeliveryFailure) as captured:
        InvitationRedeliveryCoordinator(
            store=store,
            provider=provider,
            validator=FakeValidator(store),
            app_url=app_url,
        )

    assert captured.value.code == SafeErrorCode.CONFIGURATION_UNAVAILABLE
    assert store.records == before
    assert store.operations == {}
    assert store.preflight_calls == 0
    assert provider.send_calls == 0


def test_application_url_normalization_and_invalid_vault_are_preflight_only():
    assert (
        normalize_application_url("  https://kindred.example.invalid/  ")
        == "https://kindred.example.invalid"
    )
    with pytest.raises(RedeliveryFailure) as captured:
        CredentialVault("not-a-fernet-key")
    assert captured.value.code == SafeErrorCode.CONFIGURATION_UNAVAILABLE


def _run_cli(arguments, *, environment=None):
    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "run_invitation_redelivery.py"
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }
    if environment:
        env.update(environment)
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_requires_an_explicit_operation_id():
    result = _run_cli(
        [
            "--invite-source",
            "guest",
            "--expected-count",
            "2",
            "--created-before",
            "2026-07-28T19:04:14Z",
            "--expected-commit",
            "a" * 40,
        ]
    )
    assert result.returncode == 2
    assert "--operation-id" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "unsafe_operation_id",
    ("", "short", "../unsafe", "g" * 32, "a" * 33),
)
def test_cli_rejects_malformed_operation_id_before_environment_or_database(
    unsafe_operation_id,
):
    result = _run_cli(
        [
            "--operation-id",
            unsafe_operation_id,
            "--invite-source",
            "guest",
            "--expected-count",
            "2",
            "--created-before",
            "2026-07-28T19:04:14Z",
            "--expected-commit",
            "a" * 40,
        ]
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "preflight_failed"
    assert report["error_code"] == SafeErrorCode.OPERATION_MISMATCH.value
    assert report["credentials_selected"] == 0
    assert report["credentials_rotated"] == 0
    assert "operation_id" not in report


@pytest.mark.parametrize(
    "missing_name",
    (
        "MONGO_URL",
        "DB_NAME",
        "RESEND_API_KEY",
        "FROM_EMAIL",
        "RESEND_VERIFIED_DOMAIN",
        "RESEND_WEBHOOK_SECRET",
        "PUBLIC_API_BASE_URL",
        "APP_URL",
        "INVITATION_REDELIVERY_RECOVERY_KEY",
    ),
)
def test_cli_required_environment_failure_precedes_database_import(missing_name):
    commit = "a" * 40
    environment = {
        "RAILWAY_GIT_COMMIT_SHA": commit,
        "MONGO_URL": "mongodb://127.0.0.1:1",
        "DB_NAME": "kindred_disposable_cli_preflight",
        "RESEND_API_KEY": "synthetic-provider-key",  # pragma: allowlist secret
        "FROM_EMAIL": "noreply@example.invalid",
        "RESEND_VERIFIED_DOMAIN": "example.invalid",
        "RESEND_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "PUBLIC_API_BASE_URL": "https://api.example.invalid",
        "APP_URL": "https://kindred.example.invalid",
        "INVITATION_REDELIVERY_RECOVERY_KEY": Fernet.generate_key().decode(),
    }
    environment.pop(missing_name)
    result = _run_cli(
        [
            "--operation-id",
            OPERATION_ID,
            "--invite-source",
            "guest",
            "--expected-count",
            "2",
            "--created-before",
            "2026-07-28T19:04:14Z",
            "--expected-commit",
            commit,
        ],
        environment=environment,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "preflight_failed"
    assert report["error_code"] == SafeErrorCode.CONFIGURATION_UNAVAILABLE.value
    assert report["credentials_selected"] == 0
    assert report["credentials_rotated"] == 0


def test_cli_rejects_invalid_webhook_secret_before_database_import():
    commit = "a" * 40
    result = _run_cli(
        [
            "--operation-id",
            OPERATION_ID,
            "--invite-source",
            "guest",
            "--expected-count",
            "2",
            "--created-before",
            "2026-07-28T19:04:14Z",
            "--expected-commit",
            commit,
        ],
        environment={
            "RAILWAY_GIT_COMMIT_SHA": commit,
            "MONGO_URL": "mongodb://127.0.0.1:1",
            "DB_NAME": "kindred_disposable_cli_preflight",
            "RESEND_API_KEY": SYNTHETIC_PROVIDER_KEY,
            "FROM_EMAIL": "noreply@example.invalid",
            "RESEND_VERIFIED_DOMAIN": "example.invalid",
            "RESEND_WEBHOOK_SECRET": "invalid",  # pragma: allowlist secret
            "PUBLIC_API_BASE_URL": "https://api.example.invalid",
            "APP_URL": "https://kindred.example.invalid",
            "INVITATION_REDELIVERY_RECOVERY_KEY": Fernet.generate_key().decode(),
        },
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "preflight_failed"
    assert report["error_code"] == SafeErrorCode.CONFIGURATION_UNAVAILABLE.value
    assert report["credentials_selected"] == 0


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
                    ProviderStatus.DELIVERED,
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


def test_accepted_delivery_waits_for_signed_webhook_without_resubmission():
    store = FakeStore()
    provider = FakeProvider(
        send_statuses={
            "target_1": [
                ProviderReceipt(
                    ProviderStatus.ACCEPTED,
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
    assert second.status == "awaiting_delivery"
    assert second.credentials_rotated == 0
    target_one_sends = [
        item for item in provider.envelopes if item.target_id == "target_1"
    ]
    assert len(target_one_sends) == 1

    store.record_webhook(
        OPERATION_ID,
        "target_1",
        ProviderStatus.DELIVERED,
    )
    final = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    assert final.status == "completed"
    assert (
        len([item for item in provider.envelopes if item.target_id == "target_1"]) == 1
    )


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


def test_different_operation_id_cannot_repeat_completed_rotation():
    store = FakeStore()
    provider = FakeProvider()
    flow = coordinator(store, provider)

    first = run(flow.execute(SELECTION, operation_id=OPERATION_ID))
    active_after_first = store.active_credentials()
    second = run(
        flow.execute(
            SELECTION,
            operation_id="11111111111111111111111111111111",
        )
    )

    assert first.status == "completed"
    assert second.status == "blocked"
    assert second.error_code == SafeErrorCode.INCIDENT_ALREADY_CLAIMED.value
    assert store.active_credentials() == active_after_first
    assert provider.send_calls == 2
    assert len(store.operations) == 1


def test_crash_after_activation_recovers_only_through_original_operation_id():
    store = FakeStore()
    replacements = iter(("synthetic-new-one", "synthetic-new-two"))
    run(store.prepare(OPERATION_ID, SELECTION, lambda: next(replacements)))
    for target in run(store.delivery_targets(OPERATION_ID)):
        claimed = run(
            store.claim_provider_submission(
                OPERATION_ID,
                target.target_id,
            )
        )
        assert claimed is not None
        run(
            store.record_provider_receipt(
                OPERATION_ID,
                target.target_id,
                ProviderReceipt(
                    ProviderStatus.DELIVERED,
                    provider_message_id=f"provider_{target.target_id}_0001",
                ),
            )
        )
    activation = run(store.activate_if_ready(OPERATION_ID))
    assert activation is not None
    assert all(record.get("credential_rotation") for record in store.records)

    provider = FakeProvider()
    recovered = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    rejected_new_operation = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id="22222222222222222222222222222222",
        )
    )

    assert recovered.status == "completed"
    assert rejected_new_operation.status == "blocked"
    assert (
        rejected_new_operation.error_code
        == SafeErrorCode.INCIDENT_ALREADY_CLAIMED.value
    )
    assert provider.send_calls == 0
    assert store.activation_calls == 1


def test_concurrent_distinct_operations_claim_population_once():
    store = FakeStore()
    provider = FakeProvider()

    async def concurrent_run():
        return await asyncio.gather(
            coordinator(store, provider).execute(
                SELECTION,
                operation_id="33333333333333333333333333333333",
            ),
            coordinator(store, provider).execute(
                SELECTION,
                operation_id="44444444444444444444444444444444",
            ),
        )

    reports = run(concurrent_run())
    assert sorted(report.status for report in reports) == ["blocked", "completed"]
    assert provider.send_calls == 2
    assert len(store.operations) == 1
    assert store.activation_calls == 1


def test_rotation_marker_prevents_replacement_from_becoming_newly_eligible():
    store = FakeStore()
    provider = FakeProvider()
    first = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    changed_selection = InvitationSelection(
        invite_source="guest",
        expected_count=2,
        created_before=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )
    second = run(
        coordinator(store, provider).execute(
            changed_selection,
            operation_id="55555555555555555555555555555555",
        )
    )
    assert first.status == "completed"
    assert second.status == "blocked"
    assert second.error_code == SafeErrorCode.SELECTION_MISMATCH.value
    assert provider.send_calls == 2


def test_transient_validation_failure_preserves_recovery_and_retry_completes():
    store = FakeStore()
    provider = FakeProvider()
    failed = run(
        coordinator(
            store,
            provider,
            FakeValidator(store, force_failure=True),
        ).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    retried = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )

    assert failed.status == "activated"
    assert failed.error_code == SafeErrorCode.VALIDATION_FAILED.value
    assert failed.credentials_rotated == 2
    assert retried.status == "completed"
    assert provider.send_calls == 2


def test_completed_validation_state_is_immutable():
    store = FakeStore()
    provider = FakeProvider()
    completed = run(
        coordinator(store, provider).execute(
            SELECTION,
            operation_id=OPERATION_ID,
        )
    )
    overwritten = run(
        store.record_validation(
            OPERATION_ID,
            old_credentials_rejected=0,
            new_credentials_validated=0,
            failures=2,
            expected_validation_revision=0,
        )
    )
    assert completed.status == "completed"
    assert overwritten.status == "completed"
    assert overwritten.failures == 0


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


class FakeDNSResolver:
    def __init__(self, records=None, error=None):
        self.records = records or {}
        self.error = error
        self.calls = []

    async def resolve(self, name, record_type, *, lifetime):
        self.calls.append((name, record_type, lifetime))
        if self.error is not None:
            raise self.error
        return self.records.get((name, record_type), [])


def verified_resend_dns(domain="heykindred.org"):
    return {
        (f"resend._domainkey.{domain}", "TXT"): ["p=" + ("A" * 216)],
        (f"send.{domain}", "TXT"): ["v=spf1 include:amazonses.com ~all"],
        (f"send.{domain}", "MX"): ["10 feedback-smtp.us-east-1.amazonses.com."],
    }


def restricted_resend_client(response=None):
    observed = []

    def handler(request):
        observed.append(request)
        return (
            response
            if response is not None
            else httpx.Response(
                401,
                json={
                    "name": "restricted_api_key",
                    "message": "synthetic restricted-key response",
                },
            )
        )

    return (
        httpx.AsyncClient(
            base_url="https://api.resend.com",
            transport=httpx.MockTransport(handler),
        ),
        observed,
    )


def test_resend_preflight_accepts_exact_restricted_key_and_dns_configuration():
    client, observed = restricted_resend_client()
    resolver = FakeDNSResolver(verified_resend_dns())
    provider = ResendInvitationDeliveryProvider(
        api_key=SYNTHETIC_PROVIDER_KEY,
        from_address="Kindred <noreply@heykindred.org>",
        verified_domain="heykindred.org",
        client=client,
        resolver=resolver,
    )

    result = run(provider.preflight())
    run(client.aclose())

    assert result.ready
    assert result.error_code == SafeErrorCode.NONE
    assert len(observed) == 1
    assert observed[0].url.path == "/domains"
    assert [call[:2] for call in resolver.calls] == [
        ("resend._domainkey.heykindred.org", "TXT"),
        ("send.heykindred.org", "TXT"),
        ("send.heykindred.org", "MX"),
    ]


@pytest.mark.parametrize(
    ("response", "expected_code"),
    (
        (
            httpx.Response(
                401,
                json={"name": "unexpected_restricted_response"},
            ),
            SafeErrorCode.CONFIGURATION_UNAVAILABLE,
        ),
        (
            httpx.Response(
                401,
                content=b"not-json",
            ),
            SafeErrorCode.CONFIGURATION_UNAVAILABLE,
        ),
        (
            httpx.Response(
                403,
                json={"name": "invalid_api_key"},
            ),
            SafeErrorCode.PROVIDER_UNAVAILABLE,
        ),
    ),
)
def test_resend_preflight_rejects_non_exact_provider_responses(
    response,
    expected_code,
):
    client, observed = restricted_resend_client(response)
    resolver = FakeDNSResolver(verified_resend_dns())
    provider = ResendInvitationDeliveryProvider(
        api_key=SYNTHETIC_PROVIDER_KEY,
        from_address="Kindred <noreply@heykindred.org>",
        verified_domain="heykindred.org",
        client=client,
        resolver=resolver,
    )

    result = run(provider.preflight())
    run(client.aclose())

    assert not result.ready
    assert result.error_code == expected_code
    assert len(observed) == 1
    assert resolver.calls == []


@pytest.mark.parametrize(
    ("from_address", "verified_domain"),
    (
        ("Kindred <noreply@heykindred.org>", ""),
        ("Kindred <noreply@heykindred.org>", "other.example"),
        ("Kindred <noreply@heykindred.org>", "https://heykindred.org"),
        ("Kindred <noreply@localhost>", "localhost"),
        (
            "Kindred <noreply@heykindred.org>\nBcc: unsafe@example.invalid",
            "heykindred.org",
        ),
        (
            "Kindred <noreply@heykindred.org>\r\nBcc: unsafe@example.invalid",
            "heykindred.org",
        ),
    ),
)
def test_resend_preflight_rejects_domain_configuration_before_network(
    from_address,
    verified_domain,
):
    client, observed = restricted_resend_client()
    resolver = FakeDNSResolver(verified_resend_dns())
    provider = ResendInvitationDeliveryProvider(
        api_key=SYNTHETIC_PROVIDER_KEY,
        from_address=from_address,
        verified_domain=verified_domain,
        client=client,
        resolver=resolver,
    )

    result = run(provider.preflight())
    run(client.aclose())

    assert not result.ready
    assert result.error_code == SafeErrorCode.CONFIGURATION_UNAVAILABLE
    assert observed == []
    assert resolver.calls == []


@pytest.mark.parametrize(
    ("record_key", "unsafe_values"),
    (
        (
            ("resend._domainkey.heykindred.org", "TXT"),
            [],
        ),
        (
            ("resend._domainkey.heykindred.org", "TXT"),
            ["p=short"],
        ),
        (
            ("send.heykindred.org", "TXT"),
            ["v=spf1 include:untrusted.example ~all"],
        ),
        (
            ("send.heykindred.org", "MX"),
            ["10 untrusted.example."],
        ),
        (
            ("send.heykindred.org", "MX"),
            ["20 feedback-smtp.us-east-1.amazonses.com."],
        ),
    ),
)
def test_resend_preflight_fails_closed_for_missing_or_wrong_dns(
    record_key,
    unsafe_values,
):
    records = verified_resend_dns()
    records[record_key] = unsafe_values
    client, observed = restricted_resend_client()
    resolver = FakeDNSResolver(records)
    provider = ResendInvitationDeliveryProvider(
        api_key=SYNTHETIC_PROVIDER_KEY,
        from_address="Kindred <noreply@heykindred.org>",
        verified_domain="heykindred.org",
        client=client,
        resolver=resolver,
    )

    result = run(provider.preflight())
    run(client.aclose())

    assert not result.ready
    assert result.error_code == SafeErrorCode.CONFIGURATION_UNAVAILABLE
    assert len(observed) == 1
    assert len(resolver.calls) == 3


def test_resend_preflight_fails_closed_for_dns_unavailability():
    client, observed = restricted_resend_client()
    resolver = FakeDNSResolver(error=OSError("synthetic DNS unavailable"))
    provider = ResendInvitationDeliveryProvider(
        api_key=SYNTHETIC_PROVIDER_KEY,
        from_address="Kindred <noreply@heykindred.org>",
        verified_domain="heykindred.org",
        client=client,
        resolver=resolver,
    )

    result = run(provider.preflight())
    run(client.aclose())

    assert not result.ready
    assert result.error_code == SafeErrorCode.PROVIDER_UNAVAILABLE
    assert len(observed) == 1
    assert len(resolver.calls) == 1


def test_resend_preflight_preserves_full_access_verified_domain_support():
    client, observed = restricted_resend_client(
        httpx.Response(
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
    )
    resolver = FakeDNSResolver(verified_resend_dns())
    provider = ResendInvitationDeliveryProvider(
        api_key=SYNTHETIC_PROVIDER_KEY,
        from_address="Kindred <noreply@heykindred.org>",
        verified_domain="heykindred.org",
        client=client,
        resolver=resolver,
    )

    result = run(provider.preflight())
    run(client.aclose())

    assert result.ready
    assert result.error_code == SafeErrorCode.NONE
    assert len(observed) == 1
    assert len(resolver.calls) == 3


def test_resend_adapter_logs_only_safe_categories(caplog):
    observed_payloads = []
    observed_requests = []

    def handler(request):
        observed_requests.append((request.method, request.url.path))
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
        return httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="https://api.resend.com",
        transport=httpx.MockTransport(handler),
    )
    provider = ResendInvitationDeliveryProvider(
        api_key=SYNTHETIC_PROVIDER_KEY,
        from_address="Kindred <noreply@heykindred.org>",
        verified_domain="heykindred.org",
        client=client,
        resolver=FakeDNSResolver(verified_resend_dns()),
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
    assert report.status == "awaiting_delivery"
    assert report.credentials_rotated == 0
    assert len(observed_payloads) == 2
    assert all("to" in payload for payload in observed_payloads)
    assert not any(
        method == "GET" and path.startswith("/emails/")
        for method, path in observed_requests
    )
    rendered = caplog.text + json.dumps(report.to_dict(), sort_keys=True)
    for needle in SENSITIVE_NEEDLES:
        assert needle not in rendered
    for record in store.records:
        assert record["id"] not in rendered
