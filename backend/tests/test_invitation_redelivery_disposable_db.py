"""Real transaction tests for the privacy-safe redelivery outbox.

Run only against a disposable MongoDB replica set:

KINDRED_DISPOSABLE_MONGO_URL=... MONGO_URL=... DB_NAME=kindred_disposable_... pytest ...
"""

from __future__ import annotations

import asyncio
import logging
import os
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from motor.motor_asyncio import AsyncIOMotorClient

from invitation_redelivery import (
    CredentialVault,
    InvitationRedeliveryCoordinator,
    InvitationSelection,
    PreflightResult,
    ProviderReceipt,
    ProviderStatus,
    RedeliveryFailure,
    SafeErrorCode,
)
from invitation_redelivery_store import (
    MongoInvitationRedeliveryStore,
    record_provider_delivery_event,
)
from invitation_redelivery_webhook import VerifiedDeliveryEvent

DISPOSABLE_URL = os.environ.get("KINDRED_DISPOSABLE_MONGO_URL")
if not DISPOSABLE_URL:
    pytest.skip(
        "A disposable MongoDB replica set is required.", allow_module_level=True
    )
if os.environ.get("MONGO_URL") != DISPOSABLE_URL:
    raise RuntimeError("Refusing to run against a non-disposable MongoDB URL.")
DB_NAME = os.environ.get("DB_NAME", "")
if not DB_NAME.startswith("kindred_disposable_"):
    raise RuntimeError("Disposable database name must start with kindred_disposable_.")


OPERATION_ID = "abcdef0123456789abcdef0123456789"
SENSITIVE_NEEDLES = (
    "guest.one@example.com",
    "guest.two@example.com",
    "synthetic-old-mongo-one",
    "synthetic-old-mongo-two",
)


class FakeProvider:
    def __init__(self, *, accept_only=False):
        self.send_calls = 0
        self.idempotency_keys = []
        self.accept_only = accept_only

    async def preflight(self):
        return PreflightResult(ready=True)

    async def send(self, envelope):
        self.send_calls += 1
        self.idempotency_keys.append(envelope.idempotency_key)
        await asyncio.sleep(0.02)
        return ProviderReceipt(
            status=(
                ProviderStatus.ACCEPTED
                if self.accept_only
                else ProviderStatus.DELIVERED
            ),
            provider_message_id=f"provider_{envelope.target_id}_0001",
        )


class DatabaseValidator:
    def __init__(self, events):
        self._events = events

    async def preflight(self):
        return PreflightResult(ready=True)

    async def old_credential_rejected(self, credential):
        return await self._events.count_documents({"event_invites.id": credential}) == 0

    async def new_credential_valid(self, credential):
        return await self._events.count_documents({"event_invites.id": credential}) == 1


def test_real_transaction_keeps_staged_secrets_out_of_events(caplog):
    async def campaign():
        client = AsyncIOMotorClient(DISPOSABLE_URL)
        database = client[DB_NAME]
        events = database.events
        operations = database.invitation_redelivery_operations
        await database.drop_collection("events")
        await database.drop_collection("invitation_redelivery_operations")
        await events.create_index("event_invites.id", unique=True, sparse=True)
        await operations.create_index("id", unique=True)
        await operations.create_index(
            "targets.old_credential_digest",
            unique=True,
            sparse=True,
        )
        await operations.create_index(
            "selection_fingerprint",
            unique=True,
            sparse=True,
        )

        originals = [
            {
                "id": "synthetic-event-one",
                "created_at": "2026-07-27T00:00:00+00:00",
                "event_template": "standard",
                "rsvp_revision": 4,
                "event_invites": [
                    {
                        "id": "synthetic-old-mongo-one",
                        "email": "guest.one@example.com",
                        "invite_source": "guest",
                        "created_at": "2026-07-27T00:00:00+00:00",
                        "rsvp_status": "going",
                        "note": "synthetic note one",
                    }
                ],
            },
            {
                "id": "synthetic-event-two",
                "created_at": "malformed-conservative-inclusion",
                "event_template": "reunion",
                "event_invites": [
                    {
                        "id": "synthetic-old-mongo-two",
                        "email": "guest.two@example.com",
                        "invite_source": "guest",
                        "created_at": None,
                        "rsvp_status": "maybe",
                        "note": "synthetic note two",
                    }
                ],
            },
        ]
        await events.insert_many(deepcopy(originals))
        store = MongoInvitationRedeliveryStore(
            client=client,
            events_collection=events,
            operations_collection=operations,
            vault=CredentialVault(Fernet.generate_key().decode("ascii")),
        )
        coordinator = InvitationRedeliveryCoordinator(
            store=store,
            provider=FakeProvider(accept_only=True),
            validator=DatabaseValidator(events),
            app_url="https://synthetic.example",
        )
        selection = InvitationSelection(
            invite_source="guest",
            expected_count=2,
            created_before=datetime(
                2026,
                7,
                28,
                19,
                4,
                14,
                tzinfo=timezone.utc,
            ),
        )
        awaiting = await coordinator.execute(
            selection,
            operation_id=OPERATION_ID,
        )
        assert awaiting.status == "awaiting_delivery"
        staged = await operations.find_one({"id": OPERATION_ID}, {"_id": 0})
        for ordinal, target in enumerate(staged["targets"], 1):
            outcome = await record_provider_delivery_event(
                client=client,
                operations_collection=operations,
                event=VerifiedDeliveryEvent(
                    event_id=f"evt_synthetic_mongo_{ordinal:04d}",
                    provider_message_id=target["provider_message_id"],
                    provider_status=ProviderStatus.DELIVERED,
                    occurred_at=datetime.now(timezone.utc).isoformat(),
                ),
            )
            assert outcome == "delivered"
        report = await coordinator.execute(
            selection,
            operation_id=OPERATION_ID,
        )
        final_events = await events.find({}, {"_id": 0}).sort("id", 1).to_list(None)
        operation = await operations.find_one({"id": OPERATION_ID}, {"_id": 0})
        client.close()
        return report, final_events, operation, originals

    caplog.set_level(logging.DEBUG)
    report, final_events, operation, originals = asyncio.run(campaign())

    assert report.status == "completed"
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
    assert {
        final_events[0]["event_invites"][0]["id"],
        final_events[1]["event_invites"][0]["id"],
    }.isdisjoint({"synthetic-old-mongo-one", "synthetic-old-mongo-two"})
    for before, after in zip(originals, final_events):
        before_invite = before["event_invites"][0]
        after_invite = after["event_invites"][0]
        assert {key: value for key, value in before_invite.items() if key != "id"} == {
            key: value
            for key, value in after_invite.items()
            if key not in {"id", "credential_rotation"}
        }
        assert after_invite["credential_rotation"]["operation_id"] == OPERATION_ID
        assert (
            after_invite["credential_rotation"]["selection_fingerprint"]
            == operation["selection_fingerprint"]
        )
    for target in operation["targets"]:
        assert "recipient_ciphertext" not in target
        assert "old_credential_ciphertext" not in target
        assert "new_credential_ciphertext" not in target
    rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
    for needle in SENSITIVE_NEEDLES:
        assert needle not in rendered_logs


def test_real_incident_claims_and_validation_transitions_are_monotonic():
    class ValidationGate:
        def __init__(self):
            self.count = 0
            self.ready = asyncio.Event()

        async def wait(self):
            self.count += 1
            if self.count >= 2:
                self.ready.set()
            await self.ready.wait()

    class DivergentValidator(DatabaseValidator):
        def __init__(self, events, *, succeeds, gate):
            super().__init__(events)
            self._succeeds = succeeds
            self._gate = gate
            self._first_check = True

        async def old_credential_rejected(self, credential):
            if self._first_check:
                self._first_check = False
                await self._gate.wait()
            if not self._succeeds:
                return False
            return await super().old_credential_rejected(credential)

        async def new_credential_valid(self, credential):
            if not self._succeeds:
                await asyncio.sleep(0.05)
                return False
            return await super().new_credential_valid(credential)

    async def campaign():
        client = AsyncIOMotorClient(DISPOSABLE_URL)
        database = client[DB_NAME]
        selection = InvitationSelection(
            invite_source="guest",
            expected_count=2,
            created_before=datetime(
                2026,
                7,
                28,
                19,
                4,
                14,
                tzinfo=timezone.utc,
            ),
        )

        async def reset():
            await database.drop_collection("events")
            await database.drop_collection("invitation_redelivery_operations")
            events = database.events
            operations = database.invitation_redelivery_operations
            await events.create_index("event_invites.id", unique=True, sparse=True)
            await operations.create_index("id", unique=True)
            await operations.create_index(
                "targets.old_credential_digest",
                unique=True,
                sparse=True,
            )
            await operations.create_index(
                "selection_fingerprint",
                unique=True,
                sparse=True,
            )
            await events.insert_many(
                [
                    {
                        "id": f"synthetic-event-{ordinal}",
                        "created_at": "2026-07-27T00:00:00+00:00",
                        "rsvp_revision": 0,
                        "event_invites": [
                            {
                                "id": f"synthetic-old-{ordinal}",
                                "email": f"guest.{ordinal}@example.com",
                                "invite_source": "guest",
                                "created_at": "2026-07-27T00:00:00+00:00",
                                "rsvp_status": "pending",
                            }
                        ],
                    }
                    for ordinal in (1, 2)
                ]
            )
            store = MongoInvitationRedeliveryStore(
                client=client,
                events_collection=events,
                operations_collection=operations,
                vault=CredentialVault(Fernet.generate_key().decode("ascii")),
            )
            return events, operations, store

        async def activate_without_validation(operation_id):
            events, operations, store = await reset()
            replacements = iter(("synthetic-new-one", "synthetic-new-two"))
            await store.prepare(
                operation_id,
                selection,
                lambda: next(replacements),
            )
            for target in await store.delivery_targets(operation_id):
                claimed = await store.claim_provider_submission(
                    operation_id,
                    target.target_id,
                )
                assert claimed is not None
                await store.record_provider_receipt(
                    operation_id,
                    target.target_id,
                    ProviderReceipt(
                        status=ProviderStatus.DELIVERED,
                        provider_message_id=f"provider_{target.target_id}_0001",
                    ),
                )
            activation = await store.activate_if_ready(operation_id)
            assert activation is not None
            return events, operations, store, activation

        events, operations, store = await reset()
        provider = FakeProvider()
        first_flow = InvitationRedeliveryCoordinator(
            store=store,
            provider=provider,
            validator=DatabaseValidator(events),
            app_url="https://synthetic.example",
        )
        distinct_reports = await asyncio.gather(
            first_flow.execute(
                selection,
                operation_id="11111111111111111111111111111111",
            ),
            first_flow.execute(
                selection,
                operation_id="22222222222222222222222222222222",
            ),
        )
        assert sorted(report.status for report in distinct_reports) == [
            "blocked",
            "completed",
        ]
        assert provider.send_calls == 2
        assert len(set(provider.idempotency_keys)) == 2
        assert await operations.count_documents({}) == 1

        completed_operation = next(
            report.operation_id
            for report in distinct_reports
            if report.status == "completed"
        )
        active_before_retry = {
            item["event_invites"][0]["id"]
            for item in await events.find({}, {"_id": 0}).to_list(None)
        }
        different_retry = await first_flow.execute(
            selection,
            operation_id="33333333333333333333333333333333",
        )
        same_retry = await first_flow.execute(
            selection,
            operation_id=completed_operation,
        )
        active_after_retry = {
            item["event_invites"][0]["id"]
            for item in await events.find({}, {"_id": 0}).to_list(None)
        }
        assert different_retry.status == "blocked"
        assert (
            different_retry.error_code == SafeErrorCode.INCIDENT_ALREADY_CLAIMED.value
        )
        assert same_retry.status == "completed"
        assert provider.send_calls == 2
        assert active_after_retry == active_before_retry

        operation_id = "44444444444444444444444444444444"
        events, operations, store, activation = await activate_without_validation(
            operation_id
        )
        before_completion = await operations.find_one(
            {"id": operation_id},
            {"_id": 0},
        )
        assert before_completion["status"] == "activated"
        assert (
            sum(
                "old_credential_ciphertext" in target
                and "new_credential_ciphertext" in target
                for target in before_completion["targets"]
            )
            == 2
        )

        gate = ValidationGate()
        provider = FakeProvider()
        success_flow = InvitationRedeliveryCoordinator(
            store=store,
            provider=provider,
            validator=DivergentValidator(
                events,
                succeeds=True,
                gate=gate,
            ),
            app_url="https://synthetic.example",
        )
        failure_flow = InvitationRedeliveryCoordinator(
            store=store,
            provider=provider,
            validator=DivergentValidator(
                events,
                succeeds=False,
                gate=gate,
            ),
            app_url="https://synthetic.example",
        )
        divergent = await asyncio.gather(
            success_flow.execute(selection, operation_id=operation_id),
            failure_flow.execute(selection, operation_id=operation_id),
        )
        assert all(report.status == "completed" for report in divergent)
        completed_document = await operations.find_one(
            {"id": operation_id},
            {"_id": 0},
        )
        assert completed_document["status"] == "completed"
        assert (
            sum(
                "old_credential_ciphertext" in target
                or "new_credential_ciphertext" in target
                for target in completed_document["targets"]
            )
            == 0
        )
        immutable = await store.record_validation(
            operation_id,
            old_credentials_rejected=0,
            new_credentials_validated=0,
            failures=2,
            expected_validation_revision=activation.validation_revision,
        )
        assert immutable.status == "completed"
        assert immutable.failures == 0

        operation_id = "55555555555555555555555555555555"
        events, operations, store, activation = await activate_without_validation(
            operation_id
        )
        gate = ValidationGate()
        provider = FakeProvider()
        failures = await asyncio.gather(
            *[
                InvitationRedeliveryCoordinator(
                    store=store,
                    provider=provider,
                    validator=DivergentValidator(
                        events,
                        succeeds=False,
                        gate=gate,
                    ),
                    app_url="https://synthetic.example",
                ).execute(selection, operation_id=operation_id)
                for _ in range(2)
            ]
        )
        assert all(report.status == "activated" for report in failures)
        failed_document = await operations.find_one(
            {"id": operation_id},
            {"_id": 0},
        )
        assert failed_document["status"] == "activated"
        assert (
            sum(
                "old_credential_ciphertext" in target
                and "new_credential_ciphertext" in target
                for target in failed_document["targets"]
            )
            == 2
        )
        recovered = await InvitationRedeliveryCoordinator(
            store=store,
            provider=provider,
            validator=DatabaseValidator(events),
            app_url="https://synthetic.example",
        ).execute(selection, operation_id=operation_id)
        assert recovered.status == "completed"
        recovered_document = await operations.find_one(
            {"id": operation_id},
            {"_id": 0},
        )
        assert (
            sum(
                "old_credential_ciphertext" in target
                or "new_credential_ciphertext" in target
                for target in recovered_document["targets"]
            )
            == 0
        )

        operation_id = "66666666666666666666666666666666"
        events, operations, store, _ = await activate_without_validation(operation_id)
        gate = ValidationGate()
        provider = FakeProvider()
        successes = await asyncio.gather(
            *[
                InvitationRedeliveryCoordinator(
                    store=store,
                    provider=provider,
                    validator=DivergentValidator(
                        events,
                        succeeds=True,
                        gate=gate,
                    ),
                    app_url="https://synthetic.example",
                ).execute(selection, operation_id=operation_id)
                for _ in range(2)
            ]
        )
        assert all(report.status == "completed" for report in successes)
        assert provider.send_calls == 0

        client.close()

    asyncio.run(campaign())


def test_real_preflight_failures_leave_zero_outbox_documents():
    class ConfigurableProvider(FakeProvider):
        def __init__(self, *, ready):
            super().__init__()
            self._ready = ready

        async def preflight(self):
            return PreflightResult(
                ready=self._ready,
                error_code=(
                    SafeErrorCode.NONE
                    if self._ready
                    else SafeErrorCode.PROVIDER_UNAVAILABLE
                ),
            )

    class ConfigurableValidator(DatabaseValidator):
        def __init__(self, events, *, ready):
            super().__init__(events)
            self._ready = ready

        async def preflight(self):
            return PreflightResult(
                ready=self._ready,
                error_code=(
                    SafeErrorCode.NONE
                    if self._ready
                    else SafeErrorCode.VALIDATION_UNAVAILABLE
                ),
            )

    async def campaign():
        client = AsyncIOMotorClient(DISPOSABLE_URL)
        database = client[DB_NAME]
        await database.drop_collection("events")
        await database.drop_collection("invitation_redelivery_operations")
        events = database.events
        operations = database.invitation_redelivery_operations
        await operations.create_index("id", unique=True)
        await operations.create_index(
            "selection_fingerprint",
            unique=True,
            sparse=True,
        )
        original_event = {
            "id": "synthetic-preflight-event",
            "created_at": "2026-07-27T00:00:00+00:00",
            "rsvp_revision": 0,
            "event_invites": [
                {
                    "id": "synthetic-preflight-old",
                    "email": "preflight.guest@example.com",
                    "invite_source": "guest",
                    "created_at": "2026-07-27T00:00:00+00:00",
                }
            ],
        }
        await events.insert_one(deepcopy(original_event))
        selection = InvitationSelection(
            invite_source="guest",
            expected_count=1,
            created_before=datetime(
                2026,
                7,
                28,
                19,
                4,
                14,
                tzinfo=timezone.utc,
            ),
        )

        for ordinal, (provider_ready, validator_ready) in enumerate(
            ((False, True), (True, False)),
            1,
        ):
            store = MongoInvitationRedeliveryStore(
                client=client,
                events_collection=events,
                operations_collection=operations,
                vault=CredentialVault(Fernet.generate_key().decode("ascii")),
            )
            provider = ConfigurableProvider(ready=provider_ready)
            report = await InvitationRedeliveryCoordinator(
                store=store,
                provider=provider,
                validator=ConfigurableValidator(
                    events,
                    ready=validator_ready,
                ),
                app_url="https://synthetic.example",
            ).execute(
                selection,
                operation_id=f"{ordinal}" * 32,
            )
            assert report.status == "preflight_failed"
            assert provider.send_calls == 0
            assert await operations.count_documents({}) == 0
            current_event = await events.find_one(
                {"id": original_event["id"]},
                {"_id": 0},
            )
            assert current_event == original_event

        store = MongoInvitationRedeliveryStore(
            client=client,
            events_collection=events,
            operations_collection=operations,
            vault=CredentialVault(Fernet.generate_key().decode("ascii")),
        )

        async def failed_database_preflight():
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.TRANSACTION_REQUIRED,
            )

        store.preflight = failed_database_preflight
        provider = ConfigurableProvider(ready=True)
        report = await InvitationRedeliveryCoordinator(
            store=store,
            provider=provider,
            validator=ConfigurableValidator(events, ready=True),
            app_url="https://synthetic.example",
        ).execute(
            selection,
            operation_id="3" * 32,
        )
        assert report.status == "preflight_failed"
        assert provider.send_calls == 0
        assert await operations.count_documents({}) == 0

        provider = ConfigurableProvider(ready=True)
        with pytest.raises(RedeliveryFailure) as captured:
            InvitationRedeliveryCoordinator(
                store=store,
                provider=provider,
                validator=ConfigurableValidator(events, ready=True),
                app_url="http://unsafe.example",
            )
        assert captured.value.code == SafeErrorCode.CONFIGURATION_UNAVAILABLE
        assert provider.send_calls == 0
        assert await operations.count_documents({}) == 0
        current_event = await events.find_one(
            {"id": original_event["id"]},
            {"_id": 0},
        )
        assert current_event == original_event
        client.close()

    asyncio.run(campaign())
