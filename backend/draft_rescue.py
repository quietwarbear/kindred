"""Emailing a reunion draft to the person who wrote it.

A draft made on /reunion/start lives only in that browser until the organizer
signs in. That is a deliberate privacy promise, and it also means a closed tab
destroys the work and we never learn the draft existed. This module is the one
consented exception: the organizer types their own address and asks us to send
it, and only then does anything reach our servers.

SECURITY (do not relax without review):
- The endpoint is unauthenticated and sends mail, which is a spam relay unless
  it is bounded. Every request is counted against BOTH the caller's IP and the
  destination address, in Mongo rather than process memory, because Railway
  runs more than one replica and an in-process counter would multiply by the
  replica count.
- The IP is stored only as a salted hash. We need to count requests from an
  address; we do not need to know the address.
- Mail is only ever sent TO the address in the request, with content from the
  request. It cannot be aimed at a third party with attacker-chosen text: the
  draft fields are escaped and length-capped before they reach the template.
- No account is created and no session is granted.
"""

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from html import escape

# Deliberately permissive: this is a typo check, not an identity claim. The
# send either lands or it doesn't.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")

# Per IP, then per destination address. The per-address cap is what stops one
# mailbox being flooded from many IPs.
MAX_PER_IP_HOUR = 5
MAX_PER_IP_DAY = 20
MAX_PER_EMAIL_DAY = 3

# Salt so a stored hash can't be reversed with a list of IPv4 space. Falls back
# to a constant in dev; production sets it.
_IP_SALT = os.environ.get("DRAFT_RESCUE_IP_SALT", "kindred-draft-rescue")


def hash_ip(ip: str) -> str:
    return hashlib.sha256(f"{_IP_SALT}:{ip}".encode()).hexdigest()


def valid_email(value: str) -> bool:
    return bool(value) and len(value) <= 254 and bool(EMAIL_RE.match(value))


def clean_field(value: str | None, limit: int = 120) -> str:
    """Trim, cap and HTML-escape one draft field before it reaches an email."""
    if not value:
        return ""
    return escape(str(value).strip()[:limit])


async def rate_limit_reason(collection, ip_hash: str, email: str) -> str | None:
    """Return a human-readable reason to refuse, or None to allow.

    `collection` is injected rather than imported so these bounds can be tested
    without a live Mongo driver — the limits are the security boundary here.
    """
    now = datetime.now(timezone.utc)
    hour_ago = (now - timedelta(hours=1)).isoformat()
    day_ago = (now - timedelta(days=1)).isoformat()

    if await collection.count_documents(
        {"ip_hash": ip_hash, "created_at": {"$gte": hour_ago}}
    ) >= MAX_PER_IP_HOUR:
        return "Too many drafts emailed from here in the last hour. Try again shortly."

    if await collection.count_documents(
        {"ip_hash": ip_hash, "created_at": {"$gte": day_ago}}
    ) >= MAX_PER_IP_DAY:
        return "Too many drafts emailed from here today. Try again tomorrow."

    if await collection.count_documents(
        {"email": email, "created_at": {"$gte": day_ago}}
    ) >= MAX_PER_EMAIL_DAY:
        return "This address has already been sent today's drafts. Try again tomorrow."

    return None


def client_ip(request) -> str:
    """Best-effort caller IP behind Railway's proxy."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]
