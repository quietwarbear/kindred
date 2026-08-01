"""Real replica-set concurrency campaign for Stage 12B transfer operations."""

import asyncio
import os

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from legacy_table_transfer import (
    TRANSFER_ORIGIN,
    TransferFailure,
    acknowledge_transfer,
    activate_grant,
    ensure_transfer_indexes,
    operation_for_grant,
    prepare_operation,
    retrieve_payload,
    revoke_grant,
    verify_transfer_indexes,
)

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


def configure():
    os.environ["LEGACY_TABLE_TRANSFER_ENABLED"] = "true"
    os.environ["LEGACY_TABLE_TRANSFER_HASH_KEY"] = (
        "synthetic-stage12b-hash-key-at-least-32-bytes"
    )
    os.environ["LEGACY_TABLE_API_ORIGIN"] = "https://api.legacytable.app"
    os.environ["LEGACY_TABLE_WEB_ORIGIN"] = "https://legacytable.app"
    os.environ["UBUNTU_SSO_SECRET"] = "synthetic-only"


@pytest.mark.asyncio
async def test_concurrent_operation_grant_payload_acknowledgement_and_replay_guards():
    configure()
    client = AsyncIOMotorClient(DISPOSABLE_URL)
    database = client[DB_NAME]
    await database.drop_collection("legacy_table_transfer_operations")
    await database.drop_collection("threads")
    await ensure_transfer_indexes(database)
    await verify_transfer_indexes(database)
    thread = {
        "id": "synthetic-stage12b-thread",
        "community_id": "synthetic-stage12b-community",
        "created_by": "synthetic-stage12b-author",
        "category": "recipe-tradition",
        "title": "Synthetic holiday dish",
        "body": "Synthetic preparation notes only.",
        "revision": 1,
    }
    user = {"id": "synthetic-stage12b-author", "role": "member"}
    await database.threads.insert_one(dict(thread))

    operations = await asyncio.gather(
        *(prepare_operation(database, client, thread, user) for _ in range(8))
    )
    assert len({item["operation_id"] for item in operations}) == 1
    assert await database.legacy_table_transfer_operations.count_documents({}) == 1

    grants = await asyncio.gather(
        *(activate_grant(database, operations[0]) for _ in range(2)),
        return_exceptions=True,
    )
    winners = [item for item in grants if not isinstance(item, Exception)]
    assert len(winners) == 1
    grant, operation = winners[0]
    stored = await database.legacy_table_transfer_operations.find_one(
        {"operation_id": operation["operation_id"]}
    )
    assert grant not in repr(stored)
    assert thread["id"] not in repr(stored)
    assert user["id"] not in repr(stored)
    assert "grant_digest" in stored

    with pytest.raises(TransferFailure, match="transfer_not_found"):
        await operation_for_grant(database, grant, "https://unapproved.invalid")
    retrieved = await asyncio.gather(
        *(retrieve_payload(database, grant, TRANSFER_ORIGIN) for _ in range(5))
    )
    assert len({item[1]["operation_id"] for item in retrieved}) == 1
    payload = retrieved[0][1]
    assert set(payload) == {
        "source",
        "operation_id",
        "source_subject_reference",
        "source_revision_digest",
        "consent_version",
        "title",
        "instructions_or_story",
        "category",
    }

    current = await database.legacy_table_transfer_operations.find_one(
        {"operation_id": payload["operation_id"]}
    )
    recovery_grant, recovered = await activate_grant(database, current)
    assert recovered["state"] == "payload_retrieved"
    with pytest.raises(TransferFailure, match="transfer_not_found"):
        await operation_for_grant(database, grant, TRANSFER_ORIGIN)
    recovered, recovered_payload = await retrieve_payload(
        database, recovery_grant, TRANSFER_ORIGIN
    )
    assert recovered_payload["operation_id"] == payload["operation_id"]

    receipt = "ltr_synthetic_stage12b_receipt"
    acknowledgement = {
        "operation_id": payload["operation_id"],
        "source_revision_digest": payload["source_revision_digest"],
        "status": "accepted",
        "receipt_reference": receipt,
        "error_code": None,
    }
    acknowledged = await asyncio.gather(
        *(
            acknowledge_transfer(database, client, recovered, acknowledgement)
            for _ in range(4)
        )
    )
    assert {item["state"] for item in acknowledged} == {"completed"}
    assert {item["receipt_reference"] for item in acknowledged} == {receipt}
    assert (await database.threads.find_one({"id": thread["id"]}))[
        "legacy_table_transfer_state"
    ] == "completed"

    with pytest.raises(TransferFailure, match="transfer_already_completed"):
        await activate_grant(database, acknowledged[0])
    divergent = dict(
        acknowledgement, receipt_reference="ltr_divergent_stage12b_receipt"
    )
    with pytest.raises(TransferFailure, match="transfer_conflict"):
        await acknowledge_transfer(database, client, acknowledged[0], divergent)

    changed = dict(thread, title="Changed after consent", revision=2)
    with pytest.raises(TransferFailure, match="source_revision_conflict"):
        await prepare_operation(database, client, changed, user)

    second = dict(
        thread, id="synthetic-stage12b-second-thread", title="Second synthetic dish"
    )
    await database.threads.insert_one(dict(second))
    second_operation = await prepare_operation(database, client, second, user)
    second_grant, second_operation = await activate_grant(database, second_operation)
    revoked = await revoke_grant(database, second_operation)
    assert revoked["state"] == "revoked"
    with pytest.raises(TransferFailure, match="transfer_not_found"):
        await operation_for_grant(database, second_grant, TRANSFER_ORIGIN)

    client.close()
