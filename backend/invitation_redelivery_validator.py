"""Header-only validation for rotated invitation credentials."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from invitation_redelivery import (
    HeaderOnlyInvitationValidator,
    PreflightResult,
    SafeErrorCode,
)


class PublicRSVPHeaderValidator(HeaderOnlyInvitationValidator):
    """Validate credentials without ever placing them in a request URL."""

    def __init__(
        self,
        *,
        api_base_url: str,
        client: httpx.AsyncClient | None = None,
    ):
        clean = str(api_base_url or "").strip().rstrip("/")
        parsed = urlsplit(clean)
        self._configured = (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
        )
        self._endpoint = (
            f"{parsed.scheme}://{parsed.netloc}/api/public/rsvp"
            if self._configured
            else ""
        )
        self._client = client

    async def _get(self, *, authorization: str = "") -> httpx.Response:
        headers = {"Authorization": authorization} if authorization else {}
        if self._client is not None:
            return await self._client.get(self._endpoint, headers=headers)
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            return await client.get(self._endpoint, headers=headers)

    async def preflight(self) -> PreflightResult:
        if not self._configured:
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.CONFIGURATION_UNAVAILABLE,
            )
        try:
            response = await self._get()
        except Exception:
            return PreflightResult(
                ready=False,
                error_code=SafeErrorCode.VALIDATION_UNAVAILABLE,
            )
        return PreflightResult(
            ready=response.status_code == 401,
            error_code=(
                SafeErrorCode.NONE
                if response.status_code == 401
                else SafeErrorCode.VALIDATION_UNAVAILABLE
            ),
        )

    async def old_credential_rejected(self, credential: str) -> bool:
        try:
            response = await self._get(
                authorization=f"Bearer {credential}",
            )
        except Exception:
            return False
        return response.status_code == 404

    async def new_credential_valid(self, credential: str) -> bool:
        try:
            response = await self._get(
                authorization=f"Bearer {credential}",
            )
        except Exception:
            return False
        return response.status_code == 200
