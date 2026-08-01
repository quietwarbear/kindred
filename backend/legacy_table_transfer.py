"""Purpose-bound, privacy-safe Kindred to Legacy Table recipe grants."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

from legacy_table_sync import (
    APPROVED_API_ORIGINS,
    APPROVED_WEB_ORIGINS,
    validate_approved_origin,
)

TRANSFER_AUDIENCE = "legacy_table"
TRANSFER_PURPOSE = "recipe_import"
TRANSFER_CONSENT_VERSION = "kindred_recipe_import_v1"
TRANSFER_SOURCE = "kindred"
TRANSFER_GRANT_TTL_MINUTES = 10
TRANSFER_OPERATION_RETENTION_DAYS = 400
TRANSFER_ORIGIN = "https://legacytable.app"
SAFE_STATES = {
    "previewed",
    "consented",
    "grant_ready",
    "payload_retrieved",
    "destination_pending",
    "destination_accepted",
    "completed",
    "conflict",
    "expired",
    "revoked",
    "unavailable",
}
SAFE_DESTINATION_CODES = {
    "database_unavailable",
    "family_choice_conflict",
    "family_creation_consent_required",
    "family_state_ambiguous",
    "family_state_changed",
    "idempotency_payload_conflict",
    "import_configuration_unavailable",
    "import_conflict",
    "reconciliation_unavailable",
    "recipe_deleted",
    "source_revision_conflict",
    "transaction_unavailable",
}
_OPERATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_GRANT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{40,160}$")


@dataclass(frozen=True)
class TransferFailure(Exception):
    code: str
    http_status: int
    safe_state: str = "unavailable"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _key() -> bytes:
    value = os.environ.get("LEGACY_TABLE_TRANSFER_HASH_KEY", "").encode("utf-8")
    if len(value) < 32:
        raise TransferFailure("transfer_configuration_unavailable", 503)
    return value


def _binding(key: bytes, category: str, value: str) -> str:
    return hmac.new(
        key, f"{category}\0{value}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


def revision_digest(thread: dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "category": thread.get("category", ""),
            "instructions_or_story": thread.get("body", ""),
            "revision": thread.get("revision", 0),
            "title": thread.get("title", ""),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def transfer_configuration() -> dict[str, Any]:
    """Validate every local prerequisite without mutating application state."""
    if os.environ.get("LEGACY_TABLE_TRANSFER_ENABLED", "").lower() != "true":
        return {"status": "configuration_required", "ready": False}
    try:
        _key()
        api_origin = validate_approved_origin(
            os.environ.get("LEGACY_TABLE_API_ORIGIN", ""), APPROVED_API_ORIGINS
        )
        web_origin = validate_approved_origin(
            os.environ.get("LEGACY_TABLE_WEB_ORIGIN", ""), APPROVED_WEB_ORIGINS
        )
    except (TransferFailure, ValueError):
        return {"status": "unavailable", "ready": False}
    if not os.environ.get("UBUNTU_SSO_SECRET", ""):
        return {"status": "configuration_required", "ready": False}
    return {
        "status": "ready",
        "ready": True,
        "api_origin": api_origin,
        "web_origin": web_origin,
    }


def require_transfer_configuration() -> dict[str, Any]:
    config = transfer_configuration()
    if not config["ready"]:
        raise TransferFailure("transfer_configuration_unavailable", 503)
    return config


async def ensure_transfer_indexes(database) -> None:
    await database.legacy_table_transfer_operations.create_index(
        "operation_id", unique=True, name="legacy_table_transfer_operation_unique"
    )
    await database.legacy_table_transfer_operations.create_index(
        [("author_binding", ASCENDING), ("source_subject_binding", ASCENDING)],
        unique=True,
        name="legacy_table_transfer_source_unique",
    )
    await database.legacy_table_transfer_operations.create_index(
        "grant_digest",
        unique=True,
        sparse=True,
        name="legacy_table_transfer_grant_unique",
    )
    await database.legacy_table_transfer_operations.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="legacy_table_transfer_operation_retention",
    )


def validate_owned_recipe(thread: dict[str, Any], user: dict[str, Any]) -> None:
    if (
        thread.get("category") != "recipe-tradition"
        or not thread.get("created_by")
        or thread.get("created_by") != user.get("id")
        or thread.get("withdrawn_at")
        or thread.get("deleted_at")
        or thread.get("hidden") is True
    ):
        raise TransferFailure("transfer_not_found", 404)


async def prepare_operation(
    database, mongo_client, thread: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """Create or recover the single durable operation for this author and source."""
    require_transfer_configuration()
    key = _key()
    user_id = user.get("id", "")
    thread_id = thread.get("id", "")
    if not user_id or not thread_id:
        raise TransferFailure("transfer_not_found", 404)
    validate_owned_recipe(thread, user)
    digest = revision_digest(thread)
    author_binding = _binding(key, "author", user_id)
    subject_binding = _binding(key, "subject", thread_id)

    async def body(session):
        existing = await database.legacy_table_transfer_operations.find_one(
            {
                "author_binding": author_binding,
                "source_subject_binding": subject_binding,
            },
            session=session,
        )
        if existing:
            if not hmac.compare_digest(
                existing.get("source_revision_digest", ""), digest
            ):
                raise TransferFailure("source_revision_conflict", 409, "conflict")
            return existing
        now = _now()
        operation = {
            "operation_id": f"ltop_{secrets.token_urlsafe(24)}",
            "author_binding": author_binding,
            "source_subject_binding": subject_binding,
            "source_subject_reference": f"krs_{secrets.token_urlsafe(24)}",
            "source_revision_digest": digest,
            "state": "consented",
            "revision": 1,
            "audience": TRANSFER_AUDIENCE,
            "purpose": TRANSFER_PURPOSE,
            "consent_version": TRANSFER_CONSENT_VERSION,
            "origin": TRANSFER_ORIGIN,
            "created_at": now,
            "updated_at": now,
            "expires_at": now + timedelta(days=TRANSFER_OPERATION_RETENTION_DAYS),
        }
        await database.legacy_table_transfer_operations.insert_one(
            operation, session=session
        )
        linked = await database.threads.update_one(
            {
                "id": thread_id,
                "created_by": user_id,
                "category": "recipe-tradition",
                "revision": thread.get("revision", 0),
            },
            {
                "$set": {
                    "legacy_table_transfer_operation_id": operation["operation_id"],
                    "legacy_table_source_reference": operation[
                        "source_subject_reference"
                    ],
                }
            },
            session=session,
        )
        if linked.modified_count != 1:
            raise TransferFailure("source_revision_conflict", 409, "conflict")
        return operation

    try:
        async with await mongo_client.start_session() as session:
            return await session.with_transaction(body)
    except TransferFailure:
        raise
    except DuplicateKeyError:
        operation = await database.legacy_table_transfer_operations.find_one(
            {
                "author_binding": author_binding,
                "source_subject_binding": subject_binding,
            }
        )
        if operation and hmac.compare_digest(
            operation.get("source_revision_digest", ""), digest
        ):
            return operation
        raise TransferFailure("source_revision_conflict", 409, "conflict")
    except (OperationFailure, PyMongoError) as exc:
        raise TransferFailure("transaction_unavailable", 503) from exc


async def activate_grant(
    database, operation: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    if operation.get("state") == "completed":
        raise TransferFailure("transfer_already_completed", 409, "completed")
    if operation.get("state") in {"conflict", "revoked"}:
        raise TransferFailure("transfer_unavailable", 409, operation["state"])
    credential = secrets.token_urlsafe(48)
    digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()
    now = _now()
    next_state = (
        operation.get("state")
        if operation.get("state")
        in {"payload_retrieved", "destination_pending", "destination_accepted"}
        else "grant_ready"
    )
    updated = await database.legacy_table_transfer_operations.find_one_and_update(
        {
            "operation_id": operation["operation_id"],
            "revision": operation["revision"],
            "state": {"$nin": ["completed", "conflict", "revoked"]},
        },
        {
            "$set": {
                "grant_digest": digest,
                "grant_expires_at": now + timedelta(minutes=TRANSFER_GRANT_TTL_MINUTES),
                "grant_status": "active",
                "state": next_state,
                "updated_at": now,
            },
            "$inc": {"revision": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise TransferFailure("transfer_start_conflict", 409, "conflict")
    return credential, updated


async def operation_for_grant(database, credential: str, origin: str) -> dict[str, Any]:
    if origin != TRANSFER_ORIGIN or not _GRANT_PATTERN.fullmatch(credential or ""):
        raise TransferFailure("transfer_not_found", 404)
    digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()
    operation = await database.legacy_table_transfer_operations.find_one(
        {
            "grant_digest": digest,
            "audience": TRANSFER_AUDIENCE,
            "purpose": TRANSFER_PURPOSE,
            "origin": TRANSFER_ORIGIN,
        }
    )
    if not operation:
        raise TransferFailure("transfer_not_found", 404)
    if _utc(operation.get("grant_expires_at", _now())) <= _now():
        await database.legacy_table_transfer_operations.update_one(
            {
                "operation_id": operation["operation_id"],
                "grant_digest": digest,
                "state": {"$nin": ["completed", "conflict", "revoked"]},
            },
            {
                "$set": {"grant_status": "expired", "updated_at": _now()},
                "$unset": {"grant_digest": ""},
                "$inc": {"revision": 1},
            },
        )
        raise TransferFailure("transfer_not_found", 404)
    if operation.get("state") in {"conflict", "expired", "revoked", "unavailable"}:
        raise TransferFailure("transfer_not_found", 404)
    return operation


async def retrieve_payload(
    database, credential: str, origin: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    operation = await operation_for_grant(database, credential, origin)
    thread = await database.threads.find_one(
        {"legacy_table_transfer_operation_id": operation["operation_id"]},
        {"_id": 0},
    )
    if not thread:
        raise TransferFailure("transfer_not_found", 404)
    if revision_digest(thread) != operation.get("source_revision_digest"):
        await database.legacy_table_transfer_operations.update_one(
            {"operation_id": operation["operation_id"], "state": {"$ne": "completed"}},
            {
                "$set": {"state": "conflict", "updated_at": _now()},
                "$inc": {"revision": 1},
            },
        )
        raise TransferFailure("transfer_not_found", 404)
    if (
        thread.get("withdrawn_at")
        or thread.get("deleted_at")
        or thread.get("hidden") is True
    ):
        raise TransferFailure("transfer_not_found", 404)
    if operation.get("state") == "grant_ready":
        operation = (
            await database.legacy_table_transfer_operations.find_one_and_update(
                {
                    "operation_id": operation["operation_id"],
                    "revision": operation["revision"],
                    "state": "grant_ready",
                },
                {
                    "$set": {"state": "payload_retrieved", "updated_at": _now()},
                    "$inc": {"revision": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
            or operation
        )
    payload = {
        "source": TRANSFER_SOURCE,
        "operation_id": operation["operation_id"],
        "source_subject_reference": operation["source_subject_reference"],
        "source_revision_digest": operation["source_revision_digest"],
        "consent_version": operation["consent_version"],
        "title": thread.get("title", ""),
        "instructions_or_story": thread.get("body", ""),
        "category": "Other",
    }
    return operation, payload


async def acknowledge_transfer(
    database,
    mongo_client,
    operation: dict[str, Any],
    acknowledgement: dict[str, Any],
) -> dict[str, Any]:
    if acknowledgement["operation_id"] != operation[
        "operation_id"
    ] or not hmac.compare_digest(
        acknowledgement["source_revision_digest"], operation["source_revision_digest"]
    ):
        raise TransferFailure("transfer_conflict", 409, "conflict")
    receipt = acknowledgement.get("receipt_reference")
    if acknowledgement["status"] in {"accepted", "already_accepted"} and not receipt:
        raise TransferFailure("receipt_required", 409, "conflict")

    async def body(session):
        current = await database.legacy_table_transfer_operations.find_one(
            {"operation_id": operation["operation_id"]}, session=session
        )
        if not current:
            raise TransferFailure("transfer_not_found", 404)
        if current.get("state") == "completed":
            if receipt and hmac.compare_digest(
                current.get("receipt_reference", ""), receipt
            ):
                return current
            raise TransferFailure("transfer_conflict", 409, "conflict")
        if acknowledgement["status"] in {"accepted", "already_accepted"}:
            updated = (
                await database.legacy_table_transfer_operations.find_one_and_update(
                    {
                        "operation_id": current["operation_id"],
                        "revision": current["revision"],
                        "state": {
                            "$in": [
                                "grant_ready",
                                "payload_retrieved",
                                "destination_pending",
                                "destination_accepted",
                            ]
                        },
                    },
                    {
                        "$set": {
                            "state": "completed",
                            "receipt_reference": receipt,
                            "completed_at": _now(),
                            "updated_at": _now(),
                        },
                        "$inc": {"revision": 1},
                    },
                    return_document=ReturnDocument.AFTER,
                    session=session,
                )
            )
            if not updated:
                raise TransferFailure("transfer_conflict", 409, "conflict")
            await database.threads.update_one(
                {"legacy_table_transfer_operation_id": current["operation_id"]},
                {"$set": {"legacy_table_transfer_state": "completed"}},
                session=session,
            )
            return updated
        if acknowledgement["status"] == "deleted":
            new_state, code = "conflict", "destination_deleted"
        elif acknowledgement["status"] == "conflict":
            requested_code = acknowledgement.get("error_code")
            new_state, code = (
                "conflict",
                (
                    requested_code
                    if requested_code in SAFE_DESTINATION_CODES
                    else "destination_conflict"
                ),
            )
        else:
            return current
        updated = await database.legacy_table_transfer_operations.find_one_and_update(
            {
                "operation_id": current["operation_id"],
                "revision": current["revision"],
                "state": {"$ne": "completed"},
            },
            {
                "$set": {"state": new_state, "error_code": code, "updated_at": _now()},
                "$inc": {"revision": 1},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if not updated:
            raise TransferFailure("transfer_conflict", 409, "conflict")
        return updated

    try:
        async with await mongo_client.start_session() as session:
            return await session.with_transaction(body)
    except TransferFailure:
        raise
    except (OperationFailure, PyMongoError) as exc:
        raise TransferFailure("transaction_unavailable", 503) from exc


async def revoke_grant(database, operation: dict[str, Any]) -> dict[str, Any]:
    if operation.get("state") == "completed":
        return operation
    updated = await database.legacy_table_transfer_operations.find_one_and_update(
        {
            "operation_id": operation["operation_id"],
            "revision": operation["revision"],
            "state": {"$ne": "completed"},
        },
        {
            "$set": {
                "state": "revoked",
                "grant_status": "revoked",
                "updated_at": _now(),
            },
            "$unset": {"grant_digest": ""},
            "$inc": {"revision": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    return updated or operation


def safe_projection(operation: dict[str, Any]) -> dict[str, Any]:
    state = operation.get("state", "unavailable")
    if state not in SAFE_STATES:
        state = "unavailable"
    result = {"operation_id": operation["operation_id"], "status": state}
    if operation.get("receipt_reference"):
        result["receipt_reference"] = operation["receipt_reference"]
    if operation.get("error_code"):
        result["error_code"] = operation["error_code"]
    return result


def valid_operation_id(value: str) -> bool:
    return bool(_OPERATION_PATTERN.fullmatch(value or ""))
