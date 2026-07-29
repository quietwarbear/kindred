"""Dedicated invitation delivery provider with privacy-safe logging.

This adapter deliberately does not import or call ``email_service._send_email``.
The generic helper logs recipient information and is therefore not suitable
for invitation credentials.
"""

from __future__ import annotations

import logging
import re
from email.utils import parseaddr

import httpx

from invitation_redelivery import (
    DeliveryEnvelope,
    InvitationDeliveryProvider,
    PreflightResult,
    ProviderReceipt,
    ProviderStatus,
    SafeErrorCode,
)


logger = logging.getLogger(__name__)

RESEND_API_BASE = "https://api.resend.com"
SAFE_PROVIDER_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


class ResendInvitationDeliveryProvider(InvitationDeliveryProvider):
    """Resend adapter that emits only sanitized operational metadata."""

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        client: httpx.AsyncClient | None = None,
    ):
        self._api_key = str(api_key or "").strip()
        self._from_address = str(from_address or "").strip()
        self._client = client

    def _headers(self, *, idempotency_key: str = "") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, path, **kwargs)
        async with httpx.AsyncClient(
            base_url=RESEND_API_BASE,
            timeout=httpx.Timeout(15.0),
        ) as client:
            return await client.request(method, path, **kwargs)

    async def preflight(self) -> PreflightResult:
        _, parsed_from = parseaddr(self._from_address)
        if not self._api_key or "@" not in parsed_from:
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.CONFIGURATION_UNAVAILABLE,
            )
        from_domain = parsed_from.rsplit("@", 1)[-1].lower()
        try:
            response = await self._request(
                "GET",
                "/domains",
                headers=self._headers(),
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )
        except Exception:
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )
        if response.status_code != 200:
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )
        try:
            domains = response.json().get("data", [])
            verified = any(
                str(item.get("name") or "").lower() == from_domain
                and str(item.get("status") or "").lower() == "verified"
                for item in domains
                if isinstance(item, dict)
            )
        except Exception:
            verified = False
        return PreflightResult(
            ready=verified,
            error_code=(
                SafeErrorCode.NONE
                if verified
                else SafeErrorCode.CONFIGURATION_UNAVAILABLE
            ),
        )

    async def send(self, envelope: DeliveryEnvelope) -> ProviderReceipt:
        try:
            response = await self._request(
                "POST",
                "/emails",
                headers=self._headers(
                    idempotency_key=envelope.idempotency_key,
                ),
                json={
                    "from": self._from_address,
                    "to": [envelope.recipient],
                    "subject": envelope.subject,
                    "html": envelope.html_body,
                },
            )
        except httpx.TimeoutException:
            logger.warning(
                "invitation_delivery status=ambiguous operation_id=%s target_id=%s code=%s",
                envelope.operation_id,
                envelope.target_id,
                SafeErrorCode.PROVIDER_TIMEOUT.value,
            )
            return ProviderReceipt(
                status=ProviderStatus.AMBIGUOUS,
                error_code=SafeErrorCode.PROVIDER_TIMEOUT,
            )
        except httpx.NetworkError:
            logger.warning(
                "invitation_delivery status=failed operation_id=%s target_id=%s code=%s",
                envelope.operation_id,
                envelope.target_id,
                SafeErrorCode.PROVIDER_UNAVAILABLE.value,
            )
            return ProviderReceipt(
                status=ProviderStatus.FAILED,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )
        except Exception:
            logger.warning(
                "invitation_delivery status=failed operation_id=%s target_id=%s code=%s",
                envelope.operation_id,
                envelope.target_id,
                SafeErrorCode.INTERNAL_FAILURE.value,
            )
            return ProviderReceipt(
                status=ProviderStatus.FAILED,
                error_code=SafeErrorCode.INTERNAL_FAILURE,
            )

        if response.status_code not in (200, 201):
            logger.warning(
                "invitation_delivery status=rejected operation_id=%s target_id=%s code=%s",
                envelope.operation_id,
                envelope.target_id,
                SafeErrorCode.PROVIDER_REJECTED.value,
            )
            return ProviderReceipt(
                status=ProviderStatus.REJECTED,
                error_code=SafeErrorCode.PROVIDER_REJECTED,
            )
        try:
            provider_message_id = str(response.json().get("id") or "")
        except Exception:
            provider_message_id = ""
        if not SAFE_PROVIDER_ID.fullmatch(provider_message_id):
            return ProviderReceipt(
                status=ProviderStatus.AMBIGUOUS,
                error_code=SafeErrorCode.PROVIDER_AMBIGUOUS,
            )
        logger.info(
            "invitation_delivery status=accepted operation_id=%s target_id=%s",
            envelope.operation_id,
            envelope.target_id,
        )
        return ProviderReceipt(
            status=ProviderStatus.ACCEPTED,
            provider_message_id=provider_message_id,
        )

    async def delivery_status(
        self,
        provider_message_id: str,
        *,
        operation_id: str,
        target_id: str,
    ) -> ProviderReceipt:
        if not SAFE_PROVIDER_ID.fullmatch(provider_message_id):
            return ProviderReceipt(
                status=ProviderStatus.AMBIGUOUS,
                error_code=SafeErrorCode.PROVIDER_AMBIGUOUS,
            )
        try:
            response = await self._request(
                "GET",
                f"/emails/{provider_message_id}",
                headers=self._headers(),
            )
        except httpx.TimeoutException:
            return ProviderReceipt(
                status=ProviderStatus.AMBIGUOUS,
                provider_message_id=provider_message_id,
                error_code=SafeErrorCode.PROVIDER_TIMEOUT,
            )
        except Exception:
            return ProviderReceipt(
                status=ProviderStatus.AMBIGUOUS,
                provider_message_id=provider_message_id,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )
        if response.status_code != 200:
            return ProviderReceipt(
                status=ProviderStatus.AMBIGUOUS,
                provider_message_id=provider_message_id,
                error_code=SafeErrorCode.PROVIDER_AMBIGUOUS,
            )
        try:
            last_event = str(response.json().get("last_event") or "").lower()
        except Exception:
            last_event = ""
        if last_event == "delivered":
            status = ProviderStatus.DELIVERED
            error_code = SafeErrorCode.NONE
        elif last_event in {"bounced", "failed", "complained", "canceled"}:
            status = ProviderStatus.FAILED
            error_code = SafeErrorCode.DELIVERY_FAILED
        elif last_event in {"queued", "sent", "delivery_delayed", "scheduled"}:
            status = ProviderStatus.ACCEPTED
            error_code = SafeErrorCode.NONE
        else:
            status = ProviderStatus.AMBIGUOUS
            error_code = SafeErrorCode.PROVIDER_AMBIGUOUS
        logger.info(
            "invitation_delivery status=%s operation_id=%s target_id=%s",
            status.value,
            operation_id,
            target_id,
        )
        return ProviderReceipt(
            status=status,
            provider_message_id=provider_message_id,
            error_code=error_code,
        )
