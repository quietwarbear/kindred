"""Privacy-safe invitation credential rotation and redelivery coordination.

This module is intentionally not exposed through an HTTP route. An authorized
operator runs the dedicated command in ``scripts/run_invitation_redelivery.py``.
The command reports aggregate counts and sanitized status codes only.

Sensitive values are kept in redacted dataclasses and are never passed to the
generic email helper. Provider implementations must honor idempotency keys and
must not log envelopes, responses, exception text, or request bodies.
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import logging
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Literal, Protocol
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

OPAQUE_OPERATION_ID = re.compile(r"^[0-9a-f]{32}$")
SAFE_STATUS = re.compile(r"^[a-z0-9_]{2,64}$")
SAFE_APPLICATION_HOST = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


class SafeErrorCode(str, Enum):
    NONE = ""
    CONFIGURATION_UNAVAILABLE = "configuration_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_REJECTED = "provider_rejected"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_AMBIGUOUS = "provider_ambiguous"
    DELIVERY_FAILED = "delivery_failed"
    SELECTION_MISMATCH = "selection_mismatch"
    CONCURRENT_CONFLICT = "concurrent_conflict"
    TRANSACTION_REQUIRED = "transaction_required"
    OPERATION_MISMATCH = "operation_mismatch"
    VALIDATION_UNAVAILABLE = "validation_unavailable"
    VALIDATION_FAILED = "validation_failed"
    INCIDENT_ALREADY_CLAIMED = "incident_already_claimed"
    INTERNAL_FAILURE = "internal_failure"


class ProviderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTING = "submitting"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


@dataclass(frozen=True)
class InvitationSelection:
    invite_source: Literal["guest", "member"]
    expected_count: int
    created_before: datetime

    def __post_init__(self) -> None:
        if self.expected_count <= 0:
            raise ValueError("expected_count must be positive")
        if self.created_before.tzinfo is None:
            raise ValueError("created_before must include a timezone")

    def safe_document(self) -> dict[str, str | int]:
        return {
            "invite_source": self.invite_source,
            "expected_count": self.expected_count,
            "created_before": self.created_before.astimezone(timezone.utc).isoformat(),
        }


@dataclass(frozen=True, repr=False)
class SensitiveDeliveryTarget:
    target_id: str
    recipient: str
    replacement_credential: str
    idempotency_key: str
    provider_message_id: str = ""
    provider_status: ProviderStatus = ProviderStatus.PENDING

    def __repr__(self) -> str:
        return (
            "SensitiveDeliveryTarget("
            f"target_id={self.target_id!r}, provider_status={self.provider_status.value!r}, "
            "recipient=<redacted>, replacement_credential=<redacted>)"
        )


@dataclass(frozen=True, repr=False)
class SensitiveActivationMaterial:
    operation_id: str
    validation_revision: int
    credential_pairs: tuple[tuple[str, str], ...]

    def __repr__(self) -> str:
        return (
            "SensitiveActivationMaterial("
            f"operation_id={self.operation_id!r}, credential_pairs=<redacted>)"
        )


@dataclass(frozen=True, repr=False)
class DeliveryEnvelope:
    recipient: str
    subject: str
    html_body: str
    idempotency_key: str
    operation_id: str
    target_id: str

    def __repr__(self) -> str:
        return (
            "DeliveryEnvelope("
            f"operation_id={self.operation_id!r}, target_id={self.target_id!r}, "
            "recipient=<redacted>, subject=<redacted>, html_body=<redacted>)"
        )


@dataclass(frozen=True)
class ProviderReceipt:
    status: ProviderStatus
    provider_message_id: str = ""
    error_code: SafeErrorCode = SafeErrorCode.NONE


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    error_code: SafeErrorCode = SafeErrorCode.NONE


@dataclass(frozen=True)
class SafeOperationReport:
    operation_id: str
    status: str
    credentials_selected: int = 0
    credentials_rotated: int = 0
    replacements_delivered: int = 0
    old_credentials_rejected: int = 0
    new_credentials_validated: int = 0
    failures: int = 0
    error_code: str = ""

    def __post_init__(self) -> None:
        if not OPAQUE_OPERATION_ID.fullmatch(self.operation_id):
            raise ValueError("operation_id must be opaque")
        if not SAFE_STATUS.fullmatch(self.status):
            raise ValueError("status must be a safe category")
        for field_name in (
            "credentials_selected",
            "credentials_rotated",
            "replacements_delivered",
            "old_credentials_rejected",
            "new_credentials_validated",
            "failures",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if self.error_code and not SAFE_STATUS.fullmatch(self.error_code):
            raise ValueError("error_code must be sanitized")

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


class RedeliveryFailure(RuntimeError):
    """A deliberately sanitized operational failure."""

    def __init__(self, code: SafeErrorCode):
        super().__init__(code.value)
        self.code = code


class CredentialVault:
    """Encrypt recoverable credentials stored in an operation outbox."""

    def __init__(self, key: str):
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise RedeliveryFailure(SafeErrorCode.CONFIGURATION_UNAVAILABLE) from exc

    def seal(self, credential: str) -> str:
        return self._fernet.encrypt(credential.encode("utf-8")).decode("ascii")

    def open(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise RedeliveryFailure(SafeErrorCode.CONFIGURATION_UNAVAILABLE) from exc


class InvitationDeliveryProvider(Protocol):
    async def preflight(self) -> PreflightResult: ...

    async def send(self, envelope: DeliveryEnvelope) -> ProviderReceipt: ...

    async def delivery_status(
        self,
        provider_message_id: str,
        *,
        operation_id: str,
        target_id: str,
    ) -> ProviderReceipt: ...


class HeaderOnlyInvitationValidator(Protocol):
    async def preflight(self) -> PreflightResult: ...

    async def old_credential_rejected(self, credential: str) -> bool: ...

    async def new_credential_valid(self, credential: str) -> bool: ...


class InvitationRedeliveryStore(Protocol):
    async def preflight(self) -> PreflightResult: ...

    async def prepare(
        self,
        operation_id: str,
        selection: InvitationSelection,
        credential_factory: Callable[[], str],
    ) -> SafeOperationReport: ...

    async def delivery_targets(
        self,
        operation_id: str,
    ) -> tuple[SensitiveDeliveryTarget, ...]: ...

    async def claim_provider_submission(
        self,
        operation_id: str,
        target_id: str,
    ) -> SensitiveDeliveryTarget | None: ...

    async def record_provider_receipt(
        self,
        operation_id: str,
        target_id: str,
        receipt: ProviderReceipt,
    ) -> SafeOperationReport: ...

    async def activate_if_ready(
        self,
        operation_id: str,
    ) -> SensitiveActivationMaterial | None: ...

    async def record_validation(
        self,
        operation_id: str,
        *,
        old_credentials_rejected: int,
        new_credentials_validated: int,
        failures: int,
        expected_validation_revision: int,
    ) -> SafeOperationReport: ...

    async def report(self, operation_id: str) -> SafeOperationReport: ...


def new_invitation_credential() -> str:
    return secrets.token_urlsafe(32)


def credential_digest(credential: str) -> str:
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


def selection_fingerprint(selection: InvitationSelection) -> str:
    canonical = json.dumps(
        selection.safe_document(),
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_operation_id(operation_id: str) -> str:
    clean = str(operation_id or "").strip()
    if not OPAQUE_OPERATION_ID.fullmatch(clean):
        raise RedeliveryFailure(SafeErrorCode.OPERATION_MISMATCH)
    return clean


def normalize_application_url(app_url: str) -> str:
    stable_app_url = str(app_url or "").strip().rstrip("/")
    parsed_app_url = urlsplit(stable_app_url)
    try:
        hostname = parsed_app_url.hostname
        port = parsed_app_url.port
        ascii_hostname = (
            hostname.encode("idna").decode("ascii").lower() if hostname else ""
        )
    except (UnicodeError, ValueError) as exc:
        raise RedeliveryFailure(SafeErrorCode.CONFIGURATION_UNAVAILABLE) from exc
    try:
        ipaddress.ip_address(ascii_hostname)
    except ValueError:
        is_ip_address = False
    else:
        is_ip_address = True
    if (
        parsed_app_url.scheme != "https"
        or not parsed_app_url.netloc
        or not hostname
        or is_ip_address
        or ascii_hostname == "localhost"
        or ascii_hostname.endswith(".localhost")
        or not SAFE_APPLICATION_HOST.fullmatch(ascii_hostname)
        or parsed_app_url.username is not None
        or parsed_app_url.password is not None
        or parsed_app_url.path not in ("", "/")
        or parsed_app_url.query
        or parsed_app_url.fragment
        or "\\" in parsed_app_url.netloc
        or any(ord(character) <= 32 for character in stable_app_url)
    ):
        raise RedeliveryFailure(SafeErrorCode.CONFIGURATION_UNAVAILABLE)
    authority = ascii_hostname if port is None else f"{ascii_hostname}:{port}"
    return f"{parsed_app_url.scheme}://{authority}"


def invitation_redelivery_envelope(
    *,
    app_url: str,
    recipient: str,
    replacement_credential: str,
    idempotency_key: str,
    operation_id: str,
    target_id: str,
) -> DeliveryEnvelope:
    """Build a generic message without names, event details, or URL credentials."""
    stable_app_url = normalize_application_url(app_url)
    invitation_url = f"{stable_app_url}/rsvp#{replacement_credential}"
    escaped_url = html.escape(invitation_url, quote=True)
    body = (
        "<p>Your private Kindred invitation link has been refreshed.</p>"
        f'<p><a href="{escaped_url}">Open your invitation</a></p>'
        "<p>If you did not expect this message, you can ignore it.</p>"
    )
    return DeliveryEnvelope(
        recipient=recipient,
        subject="Your private Kindred invitation link has been refreshed",
        html_body=body,
        idempotency_key=idempotency_key,
        operation_id=operation_id,
        target_id=target_id,
    )


class InvitationRedeliveryCoordinator:
    """Run a recoverable, idempotent redelivery operation."""

    def __init__(
        self,
        *,
        store: InvitationRedeliveryStore,
        provider: InvitationDeliveryProvider,
        validator: HeaderOnlyInvitationValidator,
        app_url: str,
    ):
        self._store = store
        self._provider = provider
        self._validator = validator
        self._app_url = normalize_application_url(app_url)

    @staticmethod
    def _preflight_failure(
        operation_id: str,
        code: SafeErrorCode,
    ) -> SafeOperationReport:
        return SafeOperationReport(
            operation_id=operation_id,
            status="preflight_failed",
            failures=1,
            error_code=code.value,
        )

    async def execute(
        self,
        selection: InvitationSelection,
        *,
        operation_id: str,
    ) -> SafeOperationReport:
        operation_id = validate_operation_id(operation_id)

        try:
            provider_preflight = await self._provider.preflight()
        except Exception:
            provider_preflight = PreflightResult(
                ready=False,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )
        if not provider_preflight.ready:
            provider_code = (
                provider_preflight.error_code
                if provider_preflight.error_code != SafeErrorCode.NONE
                else SafeErrorCode.PROVIDER_UNAVAILABLE
            )
            logger.warning(
                "invitation_redelivery status=preflight_failed operation_id=%s code=%s",
                operation_id,
                provider_code.value,
            )
            return self._preflight_failure(
                operation_id,
                provider_code,
            )

        try:
            validation_preflight = await self._validator.preflight()
        except Exception:
            validation_preflight = PreflightResult(
                ready=False,
                error_code=SafeErrorCode.VALIDATION_UNAVAILABLE,
            )
        if not validation_preflight.ready:
            validation_code = (
                validation_preflight.error_code
                if validation_preflight.error_code != SafeErrorCode.NONE
                else SafeErrorCode.VALIDATION_UNAVAILABLE
            )
            logger.warning(
                "invitation_redelivery status=preflight_failed operation_id=%s code=%s",
                operation_id,
                validation_code.value,
            )
            return self._preflight_failure(
                operation_id,
                validation_code,
            )

        try:
            store_preflight = await self._store.preflight()
        except Exception:
            store_preflight = PreflightResult(
                ready=False,
                error_code=SafeErrorCode.TRANSACTION_REQUIRED,
            )
        if not store_preflight.ready:
            store_code = (
                store_preflight.error_code
                if store_preflight.error_code != SafeErrorCode.NONE
                else SafeErrorCode.TRANSACTION_REQUIRED
            )
            logger.warning(
                "invitation_redelivery status=preflight_failed operation_id=%s code=%s",
                operation_id,
                store_code.value,
            )
            return self._preflight_failure(
                operation_id,
                store_code,
            )

        try:
            report = await self._store.prepare(
                operation_id,
                selection,
                new_invitation_credential,
            )
            if report.status == "completed":
                return report

            if report.credentials_rotated == 0:
                targets = await self._store.delivery_targets(operation_id)
                for target in targets:
                    receipt = await self._next_receipt(operation_id, target)
                    if receipt is None:
                        continue
                    await self._store.record_provider_receipt(
                        operation_id,
                        target.target_id,
                        receipt,
                    )

                report = await self._store.report(operation_id)
                if report.replacements_delivered != report.credentials_selected:
                    logger.warning(
                        "invitation_redelivery status=%s operation_id=%s "
                        "selected=%d delivered=%d failures=%d",
                        report.status,
                        operation_id,
                        report.credentials_selected,
                        report.replacements_delivered,
                        report.failures,
                    )
                    return report

            activation = await self._store.activate_if_ready(operation_id)
            if activation is None:
                return await self._store.report(operation_id)

            old_rejected = 0
            new_validated = 0
            validation_failures = 0
            for old_credential, new_credential in activation.credential_pairs:
                if await self._validator.old_credential_rejected(old_credential):
                    old_rejected += 1
                else:
                    validation_failures += 1
                if await self._validator.new_credential_valid(new_credential):
                    new_validated += 1
                else:
                    validation_failures += 1

            report = await self._store.record_validation(
                operation_id,
                old_credentials_rejected=old_rejected,
                new_credentials_validated=new_validated,
                failures=validation_failures,
                expected_validation_revision=activation.validation_revision,
            )
            logger.info(
                "invitation_redelivery status=%s operation_id=%s "
                "selected=%d rotated=%d delivered=%d old_rejected=%d "
                "new_validated=%d failures=%d",
                report.status,
                operation_id,
                report.credentials_selected,
                report.credentials_rotated,
                report.replacements_delivered,
                report.old_credentials_rejected,
                report.new_credentials_validated,
                report.failures,
            )
            return report
        except RedeliveryFailure as exc:
            logger.warning(
                "invitation_redelivery status=blocked operation_id=%s code=%s",
                operation_id,
                exc.code.value,
            )
            try:
                existing = await self._store.report(operation_id)
            except Exception:
                existing = SafeOperationReport(
                    operation_id=operation_id,
                    status="blocked",
                )
            return SafeOperationReport(
                operation_id=operation_id,
                status="blocked",
                credentials_selected=existing.credentials_selected,
                credentials_rotated=existing.credentials_rotated,
                replacements_delivered=existing.replacements_delivered,
                old_credentials_rejected=existing.old_credentials_rejected,
                new_credentials_validated=existing.new_credentials_validated,
                failures=max(1, existing.failures),
                error_code=exc.code.value,
            )
        except Exception:
            logger.error(
                "invitation_redelivery status=blocked operation_id=%s code=%s",
                operation_id,
                SafeErrorCode.INTERNAL_FAILURE.value,
            )
            return SafeOperationReport(
                operation_id=operation_id,
                status="blocked",
                failures=1,
                error_code=SafeErrorCode.INTERNAL_FAILURE.value,
            )

    async def _next_receipt(
        self,
        operation_id: str,
        target: SensitiveDeliveryTarget,
    ) -> ProviderReceipt | None:
        if target.provider_message_id and target.provider_status in {
            ProviderStatus.ACCEPTED,
        }:
            return await self._provider.delivery_status(
                target.provider_message_id,
                operation_id=operation_id,
                target_id=target.target_id,
            )

        if target.provider_status not in {
            ProviderStatus.PENDING,
            ProviderStatus.REJECTED,
        }:
            return None
        claimed = await self._store.claim_provider_submission(
            operation_id,
            target.target_id,
        )
        if claimed is None:
            return None

        envelope = invitation_redelivery_envelope(
            app_url=self._app_url,
            recipient=claimed.recipient,
            replacement_credential=claimed.replacement_credential,
            idempotency_key=claimed.idempotency_key,
            operation_id=operation_id,
            target_id=claimed.target_id,
        )
        receipt = await self._provider.send(envelope)
        if receipt.status == ProviderStatus.ACCEPTED and receipt.provider_message_id:
            return await self._provider.delivery_status(
                receipt.provider_message_id,
                operation_id=operation_id,
                target_id=claimed.target_id,
            )
        return receipt
