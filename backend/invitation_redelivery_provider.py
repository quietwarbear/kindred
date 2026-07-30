"""Dedicated invitation delivery provider with privacy-safe logging.

This adapter deliberately does not import or call ``email_service._send_email``.
The generic helper logs recipient information and is therefore not suitable
for invitation credentials.
"""

from __future__ import annotations

import logging
import re
from email.utils import parseaddr

import dns.asyncresolver
import dns.exception
import dns.resolver
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
SAFE_DOMAIN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+" r"[a-z]{2,63}$"
)
SAFE_DKIM_PUBLIC_KEY = re.compile(r"^p=[A-Za-z0-9+/]{128,}={0,2}$")
RESEND_RESTRICTED_KEY_ERROR = "restricted_api_key"
RESEND_DKIM_SELECTOR = "resend._domainkey"
RESEND_MAIL_FROM_SUBDOMAIN = "send"
RESEND_EXPECTED_MX = "feedback-smtp.us-east-1.amazonses.com"
RESEND_EXPECTED_MX_PRIORITY = 10
RESEND_EXPECTED_SPF = "v=spf1 include:amazonses.com ~all"
DNS_TIMEOUT_SECONDS = 5.0


class ResendInvitationDeliveryProvider(InvitationDeliveryProvider):
    """Resend adapter that emits only sanitized operational metadata."""

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        verified_domain: str,
        client: httpx.AsyncClient | None = None,
        resolver=None,
    ):
        self._api_key = str(api_key or "").strip()
        self._from_address = str(from_address or "").strip()
        self._verified_domain = str(verified_domain or "").strip().lower()
        self._client = client
        self._resolver = resolver or dns.asyncresolver.Resolver()

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

    @staticmethod
    def _txt_value(record) -> str:
        strings = getattr(record, "strings", None)
        if strings is not None:
            try:
                return b"".join(strings).decode("utf-8")
            except (AttributeError, UnicodeDecodeError):
                return ""
        return str(record).strip().strip('"')

    @staticmethod
    def _mx_value(record) -> tuple[int, str] | None:
        priority = getattr(record, "preference", None)
        exchange = getattr(record, "exchange", None)
        if priority is not None and exchange is not None:
            try:
                return int(priority), str(exchange).rstrip(".").lower()
            except (TypeError, ValueError):
                return None
        parts = str(record).strip().split(maxsplit=1)
        if len(parts) != 2:
            return None
        try:
            return int(parts[0]), parts[1].rstrip(".").lower()
        except ValueError:
            return None

    async def _dns_preflight(self, from_domain: str) -> PreflightResult:
        dkim_name = f"{RESEND_DKIM_SELECTOR}.{from_domain}"
        mail_from_name = f"{RESEND_MAIL_FROM_SUBDOMAIN}.{from_domain}"
        try:
            dkim_records = await self._resolver.resolve(
                dkim_name,
                "TXT",
                lifetime=DNS_TIMEOUT_SECONDS,
            )
            spf_records = await self._resolver.resolve(
                mail_from_name,
                "TXT",
                lifetime=DNS_TIMEOUT_SECONDS,
            )
            mx_records = await self._resolver.resolve(
                mail_from_name,
                "MX",
                lifetime=DNS_TIMEOUT_SECONDS,
            )
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.CONFIGURATION_UNAVAILABLE,
            )
        except (
            dns.exception.Timeout,
            dns.resolver.NoNameservers,
            OSError,
        ):
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )
        except Exception:
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )

        dkim_ready = any(
            SAFE_DKIM_PUBLIC_KEY.fullmatch(self._txt_value(record))
            for record in dkim_records
        )
        spf_ready = any(
            self._txt_value(record) == RESEND_EXPECTED_SPF for record in spf_records
        )
        mx_ready = any(
            self._mx_value(record) == (RESEND_EXPECTED_MX_PRIORITY, RESEND_EXPECTED_MX)
            for record in mx_records
        )
        ready = dkim_ready and spf_ready and mx_ready
        return PreflightResult(
            ready=ready,
            error_code=(
                SafeErrorCode.NONE if ready else SafeErrorCode.CONFIGURATION_UNAVAILABLE
            ),
        )

    async def preflight(self) -> PreflightResult:
        _, parsed_from = parseaddr(self._from_address)
        if (
            not self._api_key
            or "\r" in self._from_address
            or "\n" in self._from_address
            or parsed_from.count("@") != 1
        ):
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.CONFIGURATION_UNAVAILABLE,
            )
        from_domain = parsed_from.rsplit("@", 1)[-1].lower()
        if (
            not SAFE_DOMAIN.fullmatch(from_domain)
            or not SAFE_DOMAIN.fullmatch(self._verified_domain)
            or from_domain != self._verified_domain
        ):
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.CONFIGURATION_UNAVAILABLE,
            )
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
        provider_ready = False
        if response.status_code == 200:
            try:
                domains = response.json().get("data", [])
                provider_ready = any(
                    str(item.get("name") or "").lower() == from_domain
                    and str(item.get("status") or "").lower() == "verified"
                    for item in domains
                    if isinstance(item, dict)
                )
            except Exception:
                provider_ready = False
        elif response.status_code == 401:
            try:
                provider_ready = (
                    str(response.json().get("name") or "")
                    == RESEND_RESTRICTED_KEY_ERROR
                )
            except Exception:
                provider_ready = False
        else:
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.PROVIDER_UNAVAILABLE,
            )
        if not provider_ready:
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.CONFIGURATION_UNAVAILABLE,
            )
        return await self._dns_preflight(from_domain)

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
