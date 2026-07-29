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
)
from invitation_redelivery_store import MongoInvitationRedeliveryStore

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
    async def preflight(self):
        return PreflightResult(ready=True)

    async def send(self, envelope):
        return ProviderReceipt(
            status=ProviderStatus.ACCEPTED,
            provider_message_id=f"provider_{envelope.target_id}_0001",
        )

    async def delivery_status(
        self,
        provider_message_id,
        *,
        operation_id,
        target_id,
    ):
        return ProviderReceipt(
            status=ProviderStatus.DELIVERED,
            provider_message_id=provider_message_id,
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
            provider=FakeProvider(),
            validator=DatabaseValidator(events),
            app_url="https://synthetic.example",
        )
        report = await coordinator.execute(
            InvitationSelection(
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
            ),
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
            key: value for key, value in after_invite.items() if key != "id"
        }
        assert "credential_rotation" not in after_invite
    for target in operation["targets"]:
        assert "recipient_ciphertext" not in target
        assert "old_credential_ciphertext" not in target
        assert "new_credential_ciphertext" not in target
    rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
    for needle in SENSITIVE_NEEDLES:
        assert needle not in rendered_logs
