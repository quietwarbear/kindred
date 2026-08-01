"""Fail-closed Legacy Table destination configuration.

Recipe delivery is deliberately disabled until the destination exposes both an
idempotency key and an acceptance-reconciliation endpoint.  This module keeps
origin validation centralized so no route can turn an operator value into an
SSRF primitive.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit

APPROVED_API_ORIGINS = frozenset({"https://api.legacytable.app"})
APPROVED_WEB_ORIGINS = frozenset({"https://legacytable.app"})


def validate_approved_origin(value: str, approved: frozenset[str]) -> str:
    candidate = (value or "").strip().rstrip("/")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid_origin") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port not in {None, 443}
    ):
        raise ValueError("invalid_origin")
    host = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError("prohibited_network")
    normalized = f"https://{host}"
    if normalized not in approved:
        raise ValueError("unapproved_origin")
    return normalized


def destination_configuration() -> dict[str, str | bool]:
    secret = os.environ.get("UBUNTU_SSO_SECRET", "")
    api_value = os.environ.get("LEGACY_TABLE_API_ORIGIN", "")
    web_value = os.environ.get("LEGACY_TABLE_WEB_ORIGIN", "")
    if not secret or not api_value or not web_value:
        return {"status": "configuration_required", "sso_ready": False, "transfer_ready": False}
    try:
        validate_approved_origin(api_value, APPROVED_API_ORIGINS)
        validate_approved_origin(web_value, APPROVED_WEB_ORIGINS)
    except ValueError:
        return {"status": "unavailable", "sso_ready": False, "transfer_ready": False}
    return {
        "status": "ready",
        "sso_ready": True,
        # The currently inspected sibling API has no safe idempotency/reconciliation contract.
        "transfer_ready": False,
    }
