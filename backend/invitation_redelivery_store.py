"""MongoDB outbox and transaction safeguards for invitation redelivery."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from email_validator import EmailNotValidError, validate_email
from pymongo.errors import (
    ConfigurationError,
    DuplicateKeyError,
    InvalidOperation,
    OperationFailure,
    PyMongoError,
)

from invitation_redelivery import (
    CredentialVault,
    InvitationRedeliveryStore,
    InvitationSelection,
    PreflightResult,
    ProviderReceipt,
    ProviderStatus,
    RedeliveryFailure,
    SafeErrorCode,
    SafeOperationReport,
    SensitiveActivationMaterial,
    SensitiveDeliveryTarget,
    credential_digest,
    selection_fingerprint,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _eligible_at_or_before(value: Any, boundary: datetime) -> bool:
    parsed = _parse_timestamp(value)
    return parsed is None or parsed <= boundary.astimezone(timezone.utc)


def _valid_recipient(value: Any) -> bool:
    try:
        validate_email(str(value or ""), check_deliverability=False)
    except EmailNotValidError:
        return False
    return True


def _guarded_event_query(event: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {"id": event["id"]}
    if "rsvp_revision" in event:
        query["rsvp_revision"] = int(event.get("rsvp_revision", 0) or 0)
    else:
        query["rsvp_revision"] = {"$exists": False}
    return query


class MongoInvitationRedeliveryStore(InvitationRedeliveryStore):
    """Store sensitive outbox state without exposing it in reports."""

    def __init__(
        self,
        *,
        client,
        events_collection,
        operations_collection,
        vault: CredentialVault,
    ):
        self._client = client
        self._events = events_collection
        self._operations = operations_collection
        self._vault = vault

    async def preflight(self) -> PreflightResult:
        """Verify transaction support without creating or changing a document."""
        try:
            async with await self._client.start_session() as session:
                async with session.start_transaction():
                    await self._operations.find_one(
                        {"id": "__privacy_safe_preflight__"},
                        {"_id": 0, "id": 1},
                        session=session,
                    )
        except (
            ConfigurationError,
            InvalidOperation,
            OperationFailure,
            PyMongoError,
        ):
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.TRANSACTION_REQUIRED,
            )
        return PreflightResult(ready=True)

    @staticmethod
    def _report(document: dict[str, Any]) -> SafeOperationReport:
        targets = list(document.get("targets") or [])
        selected = int(document.get("expected_count", len(targets)) or 0)
        delivered = sum(
            item.get("provider_status") == ProviderStatus.DELIVERED.value
            for item in targets
        )
        status = str(document.get("status") or "blocked")
        rotated = (
            selected
            if status
            in {
                "activated",
                "validation_failed",
                "completed",
            }
            else 0
        )
        target_failures = sum(
            item.get("provider_status")
            in {
                ProviderStatus.REJECTED.value,
                ProviderStatus.AMBIGUOUS.value,
                ProviderStatus.FAILED.value,
            }
            for item in targets
        )
        validation_failures = int(document.get("validation_failures", 0) or 0)
        return SafeOperationReport(
            operation_id=document["id"],
            status=status,
            credentials_selected=selected,
            credentials_rotated=rotated,
            replacements_delivered=delivered,
            old_credentials_rejected=int(
                document.get("old_credentials_rejected", 0) or 0
            ),
            new_credentials_validated=int(
                document.get("new_credentials_validated", 0) or 0
            ),
            failures=max(target_failures, validation_failures),
            error_code=str(document.get("error_code") or ""),
        )

    async def report(self, operation_id: str) -> SafeOperationReport:
        document = await self._operations.find_one(
            {"id": operation_id},
            {"_id": 0},
        )
        if not document:
            raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
        return self._report(document)

    async def prepare(
        self,
        operation_id: str,
        selection: InvitationSelection,
        credential_factory: Callable[[], str],
    ) -> SafeOperationReport:
        fingerprint = selection_fingerprint(selection)
        existing = await self._operations.find_one(
            {"id": operation_id},
            {"_id": 0},
        )
        if existing:
            if existing.get("selection") != selection.safe_document():
                raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
            return self._report(existing)

        claimed = await self._operations.find_one(
            {"selection_fingerprint": fingerprint},
            {"_id": 0, "id": 1},
        )
        if claimed:
            raise RedeliveryFailure(SafeErrorCode.INCIDENT_ALREADY_CLAIMED)

        try:
            async with await self._client.start_session() as session:
                async with session.start_transaction():
                    existing = await self._operations.find_one(
                        {"id": operation_id},
                        {"_id": 0},
                        session=session,
                    )
                    if existing:
                        if existing.get("selection") != selection.safe_document():
                            raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                        return self._report(existing)

                    claimed = await self._operations.find_one(
                        {"selection_fingerprint": fingerprint},
                        {"_id": 0, "id": 1},
                        session=session,
                    )
                    if claimed:
                        raise RedeliveryFailure(SafeErrorCode.INCIDENT_ALREADY_CLAIMED)

                    cursor = self._events.find(
                        {
                            "event_invites": {
                                "$elemMatch": {
                                    "invite_source": selection.invite_source,
                                }
                            }
                        },
                        {
                            "_id": 0,
                            "id": 1,
                            "created_at": 1,
                            "event_invites": 1,
                            "rsvp_revision": 1,
                        },
                        session=session,
                    )
                    events = await cursor.to_list(length=None)
                    boundary = selection.created_before.astimezone(timezone.utc)
                    selected: list[tuple[dict[str, Any], int, dict[str, Any]]] = []
                    for event in events:
                        if not _eligible_at_or_before(
                            event.get("created_at"),
                            boundary,
                        ):
                            continue
                        for invite_index, invite in enumerate(
                            event.get("event_invites") or []
                        ):
                            if invite.get("invite_source") != selection.invite_source:
                                continue
                            if not _eligible_at_or_before(
                                invite.get("created_at"),
                                boundary,
                            ):
                                continue
                            selected.append((event, invite_index, invite))

                    credentials = [
                        str(invite.get("id") or "") for _, _, invite in selected
                    ]
                    if (
                        len(selected) != selection.expected_count
                        or len(set(credentials)) != selection.expected_count
                        or any(not credential for credential in credentials)
                        or any(
                            not _valid_recipient(invite.get("email"))
                            for _, _, invite in selected
                        )
                        or any(
                            invite.get("credential_rotation")
                            for _, _, invite in selected
                        )
                    ):
                        raise RedeliveryFailure(SafeErrorCode.SELECTION_MISMATCH)

                    replacements: set[str] = set()
                    targets: list[dict[str, Any]] = []
                    for ordinal, (event, _invite_index, invite) in enumerate(selected):
                        replacement = credential_factory()
                        if (
                            not replacement
                            or replacement in replacements
                            or replacement in credentials
                        ):
                            raise RedeliveryFailure(SafeErrorCode.INTERNAL_FAILURE)
                        replacements.add(replacement)
                        target_id = f"target_{ordinal + 1}"
                        idempotency_key = (
                            f"kindred-invitation-redelivery/"
                            f"{operation_id}/{target_id}"
                        )
                        old_credential = credentials[ordinal]
                        target = {
                            "target_id": target_id,
                            "event_id": event["id"],
                            "old_credential_digest": credential_digest(old_credential),
                            "new_credential_digest": credential_digest(replacement),
                            "selection_fingerprint": fingerprint,
                            "old_credential_ciphertext": self._vault.seal(
                                old_credential
                            ),
                            "new_credential_ciphertext": self._vault.seal(replacement),
                            "recipient_ciphertext": self._vault.seal(
                                str(invite.get("email") or "")
                            ),
                            "idempotency_key": idempotency_key,
                            "provider_message_id": "",
                            "provider_status": ProviderStatus.PENDING.value,
                            "error_code": "",
                        }
                        targets.append(target)

                    now = _now_iso()
                    operation = {
                        "id": operation_id,
                        "status": "prepared",
                        "selection": selection.safe_document(),
                        "selection_fingerprint": fingerprint,
                        "expected_count": selection.expected_count,
                        "targets": targets,
                        "created_at": now,
                        "updated_at": now,
                        "validation_failures": 0,
                        "validation_revision": 0,
                        "old_credentials_rejected": 0,
                        "new_credentials_validated": 0,
                        "error_code": "",
                    }
                    await self._operations.insert_one(
                        operation,
                        session=session,
                    )
                    return self._report(operation)
        except RedeliveryFailure:
            raise
        except (
            ConfigurationError,
            InvalidOperation,
            OperationFailure,
        ) as exc:
            raise RedeliveryFailure(SafeErrorCode.TRANSACTION_REQUIRED) from exc
        except DuplicateKeyError as exc:
            raise RedeliveryFailure(SafeErrorCode.INCIDENT_ALREADY_CLAIMED) from exc
        except PyMongoError as exc:
            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT) from exc

    async def delivery_targets(
        self,
        operation_id: str,
    ) -> tuple[SensitiveDeliveryTarget, ...]:
        operation = await self._operations.find_one(
            {"id": operation_id},
            {"_id": 0},
        )
        if not operation:
            raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
        if operation.get("status") in {
            "activated",
            "validation_failed",
            "completed",
        }:
            return ()

        targets: list[SensitiveDeliveryTarget] = []
        for stored_target in operation.get("targets") or []:
            if stored_target.get("provider_status") == ProviderStatus.DELIVERED.value:
                continue
            try:
                recipient = self._vault.open(stored_target["recipient_ciphertext"])
                replacement = self._vault.open(
                    stored_target["new_credential_ciphertext"]
                )
            except KeyError:
                raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT)
            if not _valid_recipient(recipient) or not replacement:
                raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT)
            targets.append(
                SensitiveDeliveryTarget(
                    target_id=stored_target["target_id"],
                    recipient=recipient,
                    replacement_credential=replacement,
                    idempotency_key=stored_target["idempotency_key"],
                    provider_message_id=str(
                        stored_target.get("provider_message_id") or ""
                    ),
                    provider_status=ProviderStatus(
                        stored_target.get("provider_status")
                        or ProviderStatus.PENDING.value
                    ),
                )
            )
        return tuple(targets)

    async def claim_provider_submission(
        self,
        operation_id: str,
        target_id: str,
    ) -> SensitiveDeliveryTarget | None:
        try:
            async with await self._client.start_session() as session:
                async with session.start_transaction():
                    operation = await self._operations.find_one(
                        {"id": operation_id},
                        {"_id": 0},
                        session=session,
                    )
                    if not operation:
                        raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                    target = next(
                        (
                            item
                            for item in operation.get("targets") or []
                            if item.get("target_id") == target_id
                        ),
                        None,
                    )
                    if not target:
                        raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                    current_status = ProviderStatus(
                        target.get("provider_status") or ProviderStatus.PENDING.value
                    )
                    if current_status not in {
                        ProviderStatus.PENDING,
                        ProviderStatus.REJECTED,
                    }:
                        return None
                    target["provider_status"] = ProviderStatus.SUBMITTING.value
                    target["error_code"] = ""
                    operation["status"] = "awaiting_delivery"
                    operation["error_code"] = ""
                    operation["updated_at"] = _now_iso()
                    await self._operations.update_one(
                        {"id": operation_id},
                        {
                            "$set": {
                                "targets": operation["targets"],
                                "status": operation["status"],
                                "error_code": "",
                                "updated_at": operation["updated_at"],
                            }
                        },
                        session=session,
                    )
                    return SensitiveDeliveryTarget(
                        target_id=target_id,
                        recipient=self._vault.open(target["recipient_ciphertext"]),
                        replacement_credential=self._vault.open(
                            target["new_credential_ciphertext"]
                        ),
                        idempotency_key=target["idempotency_key"],
                        provider_status=ProviderStatus.SUBMITTING,
                    )
        except RedeliveryFailure:
            raise
        except (
            ConfigurationError,
            InvalidOperation,
            OperationFailure,
            PyMongoError,
        ) as exc:
            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT) from exc

    async def record_provider_receipt(
        self,
        operation_id: str,
        target_id: str,
        receipt: ProviderReceipt,
    ) -> SafeOperationReport:
        try:
            async with await self._client.start_session() as session:
                async with session.start_transaction():
                    operation = await self._operations.find_one(
                        {"id": operation_id},
                        {"_id": 0},
                        session=session,
                    )
                    if not operation:
                        raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                    if operation.get("status") in {
                        "activated",
                        "validation_failed",
                        "completed",
                    }:
                        return self._report(operation)
                    target = next(
                        (
                            item
                            for item in operation.get("targets") or []
                            if item.get("target_id") == target_id
                        ),
                        None,
                    )
                    if not target:
                        raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                    targets = [dict(item) for item in operation.get("targets") or []]
                    for item in targets:
                        if item.get("target_id") == target_id:
                            item["provider_status"] = receipt.status.value
                            item["provider_message_id"] = (
                                receipt.provider_message_id
                                or item.get("provider_message_id", "")
                            )
                            item["error_code"] = receipt.error_code.value
                    all_delivered = all(
                        item.get("provider_status") == ProviderStatus.DELIVERED.value
                        for item in targets
                    )
                    operation["targets"] = targets
                    operation["status"] = (
                        "activation_ready" if all_delivered else "awaiting_delivery"
                    )
                    operation["error_code"] = (
                        ""
                        if all_delivered
                        else next(
                            (
                                str(item.get("error_code") or "")
                                for item in targets
                                if item.get("error_code")
                            ),
                            "",
                        )
                    )
                    operation["updated_at"] = _now_iso()
                    await self._operations.update_one(
                        {"id": operation_id},
                        {
                            "$set": {
                                "targets": targets,
                                "status": operation["status"],
                                "error_code": operation["error_code"],
                                "updated_at": operation["updated_at"],
                            }
                        },
                        session=session,
                    )
                    return self._report(operation)
        except RedeliveryFailure:
            raise
        except (
            ConfigurationError,
            InvalidOperation,
            OperationFailure,
            PyMongoError,
        ) as exc:
            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT) from exc

    async def activate_if_ready(
        self,
        operation_id: str,
    ) -> SensitiveActivationMaterial | None:
        try:
            async with await self._client.start_session() as session:
                async with session.start_transaction():
                    operation = await self._operations.find_one(
                        {"id": operation_id},
                        {"_id": 0},
                        session=session,
                    )
                    if not operation:
                        raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                    if operation.get("status") == "completed":
                        return None
                    if operation.get("status") in {
                        "activated",
                        "validation_failed",
                    }:
                        return SensitiveActivationMaterial(
                            operation_id=operation_id,
                            validation_revision=int(
                                operation.get("validation_revision", 0) or 0
                            ),
                            credential_pairs=tuple(
                                (
                                    self._vault.open(item["old_credential_ciphertext"]),
                                    self._vault.open(item["new_credential_ciphertext"]),
                                )
                                for item in operation.get("targets") or []
                            ),
                        )
                    if not all(
                        item.get("provider_status") == ProviderStatus.DELIVERED.value
                        for item in operation.get("targets") or []
                    ):
                        return None

                    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
                    for target in operation.get("targets") or []:
                        by_event[target["event_id"]].append(target)

                    credential_pairs: list[tuple[str, str]] = []
                    for event_id, targets in by_event.items():
                        event = await self._events.find_one(
                            {"id": event_id},
                            {
                                "_id": 0,
                                "id": 1,
                                "event_invites": 1,
                                "rsvp_revision": 1,
                            },
                            session=session,
                        )
                        if not event:
                            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT)
                        invites = [
                            dict(item) for item in event.get("event_invites") or []
                        ]
                        for target in targets:
                            old_credential = self._vault.open(
                                target["old_credential_ciphertext"]
                            )
                            new_credential = self._vault.open(
                                target["new_credential_ciphertext"]
                            )
                            invite = next(
                                (
                                    item
                                    for item in invites
                                    if str(item.get("id") or "") == old_credential
                                ),
                                None,
                            )
                            if not invite:
                                raise RedeliveryFailure(
                                    SafeErrorCode.CONCURRENT_CONFLICT
                                )
                            if (
                                credential_digest(old_credential)
                                != target["old_credential_digest"]
                                or credential_digest(new_credential)
                                != target["new_credential_digest"]
                            ):
                                raise RedeliveryFailure(
                                    SafeErrorCode.CONCURRENT_CONFLICT
                                )
                            share_message = str(invite.get("share_message") or "")
                            if share_message:
                                invite["share_message"] = share_message.replace(
                                    f"/rsvp#{old_credential}",
                                    f"/rsvp#{new_credential}",
                                )
                            invite["id"] = new_credential
                            invite["credential_rotation"] = {
                                "operation_id": operation_id,
                                "selection_fingerprint": operation[
                                    "selection_fingerprint"
                                ],
                            }
                            credential_pairs.append((old_credential, new_credential))
                        result = await self._events.update_one(
                            _guarded_event_query(event),
                            {
                                "$set": {"event_invites": invites},
                                "$inc": {"rsvp_revision": 1},
                            },
                            session=session,
                        )
                        if result.matched_count != 1:
                            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT)

                    operation["status"] = "activated"
                    operation["validation_revision"] = int(
                        operation.get("validation_revision", 0) or 0
                    )
                    for target in operation.get("targets") or []:
                        target.pop("recipient_ciphertext", None)
                    operation["updated_at"] = _now_iso()
                    await self._operations.update_one(
                        {"id": operation_id},
                        {
                            "$set": {
                                "status": "activated",
                                "targets": operation["targets"],
                                "validation_revision": operation["validation_revision"],
                                "error_code": "",
                                "updated_at": operation["updated_at"],
                            }
                        },
                        session=session,
                    )
                    return SensitiveActivationMaterial(
                        operation_id=operation_id,
                        validation_revision=operation["validation_revision"],
                        credential_pairs=tuple(credential_pairs),
                    )
        except RedeliveryFailure:
            raise
        except (
            ConfigurationError,
            InvalidOperation,
            OperationFailure,
            PyMongoError,
        ) as exc:
            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT) from exc

    async def record_validation(
        self,
        operation_id: str,
        *,
        old_credentials_rejected: int,
        new_credentials_validated: int,
        failures: int,
        expected_validation_revision: int,
    ) -> SafeOperationReport:
        if expected_validation_revision < 0:
            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT)

        for attempt in range(5):
            try:
                async with await self._client.start_session() as session:
                    async with session.start_transaction():
                        operation = await self._operations.find_one(
                            {"id": operation_id},
                            {"_id": 0},
                            session=session,
                        )
                        if not operation:
                            raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
                        if operation.get("status") == "completed":
                            return self._report(operation)
                        if operation.get("status") != "activated":
                            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT)

                        current_revision = int(
                            operation.get("validation_revision", 0) or 0
                        )
                        if current_revision < expected_validation_revision:
                            raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT)

                        expected = int(operation.get("expected_count", 0) or 0)
                        complete = (
                            failures == 0
                            and old_credentials_rejected == expected
                            and new_credentials_validated == expected
                        )
                        if (
                            current_revision > expected_validation_revision
                            and not complete
                        ):
                            return self._report(operation)

                        targets = [
                            dict(item) for item in operation.get("targets") or []
                        ]
                        if complete:
                            for target in targets:
                                target.pop("old_credential_ciphertext", None)
                                target.pop("new_credential_ciphertext", None)
                                target.pop("recipient_ciphertext", None)

                        next_revision = current_revision + 1
                        update = {
                            "status": "completed" if complete else "activated",
                            "targets": targets,
                            "old_credentials_rejected": old_credentials_rejected,
                            "new_credentials_validated": new_credentials_validated,
                            "validation_failures": failures,
                            "validation_revision": next_revision,
                            "error_code": (
                                ""
                                if complete
                                else SafeErrorCode.VALIDATION_FAILED.value
                            ),
                            "updated_at": _now_iso(),
                        }
                        result = await self._operations.update_one(
                            {
                                "id": operation_id,
                                "status": "activated",
                                "validation_revision": current_revision,
                            },
                            {"$set": update},
                            session=session,
                        )
                        if result.matched_count == 1:
                            operation.update(update)
                            return self._report(operation)
            except RedeliveryFailure:
                raise
            except (
                ConfigurationError,
                InvalidOperation,
                OperationFailure,
                PyMongoError,
            ) as exc:
                if attempt == 4:
                    raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT) from exc

            latest = await self._operations.find_one(
                {"id": operation_id},
                {"_id": 0},
            )
            if not latest:
                raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
            if latest.get("status") == "completed":
                return self._report(latest)
            latest_expected = int(latest.get("expected_count", 0) or 0)
            validation_succeeded = (
                failures == 0
                and old_credentials_rejected == latest_expected
                and new_credentials_validated == latest_expected
            )
            if not validation_succeeded:
                return self._report(latest)

        raise RedeliveryFailure(SafeErrorCode.CONCURRENT_CONFLICT)
