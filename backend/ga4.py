"""Server-side analytics via the GA4 Measurement Protocol.

Why server-side at all: the browser tag sees page views and clicks, but it
never sees the events that matter for spend decisions — a contribution that
actually cleared Stripe, a subscription that activated. Those happen in
webhooks, after the tab may already be closed. This module sends them from
the server, so revenue lands in the same GA4 property as the traffic that
produced it and paid campaigns can be judged on purchases instead of clicks.

Design constraints, mirroring email_service.py:
  - Graceful no-op when GA4_MEASUREMENT_ID / GA4_API_SECRET are unset (dev,
    or pre-setup prod): every send logs and returns False, nothing raises.
  - Fire-and-forget from request handlers via track() so signup, checkout and
    webhooks never wait on (or fail because of) Google.

Setup (already done in Railway):
    GA4_MEASUREMENT_ID=G-XXXXXXXXXX     # GA4 Admin -> Data streams -> Kindred
    GA4_API_SECRET=...                  # same panel -> Measurement Protocol API secrets
    APP_NAME=kindred                    # distinguishes apps in cross-property reports

Joining server events to web sessions:
  GA4 stitches on client_id. The browser tag's client_id lives in the `_ga`
  cookie; when the frontend forwards it we use it verbatim and the server
  event lands in the same session as the ad click that started it. When it
  does not, client_id_for() derives a stable synthetic id from the user id —
  the purchase still counts and still attaches to the user, but it starts its
  own session rather than joining the web one. Forwarding the cookie is what
  makes campaign attribution work, so it is worth doing on the frontend.
"""
import asyncio
import hashlib
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

GA4_MEASUREMENT_ID = os.environ.get("GA4_MEASUREMENT_ID", "")
GA4_API_SECRET = os.environ.get("GA4_API_SECRET", "")
APP_NAME = os.environ.get("APP_NAME", "kindred")

_MP_URL = "https://www.google-analytics.com/mp/collect"
_MP_DEBUG_URL = "https://www.google-analytics.com/debug/mp/collect"

# GA4 drops events whose params are not scalars, and silently. Keep the
# allowlist of types narrow rather than discovering this in a month of
# missing data.
_SCALARS = (str, int, float, bool)


def enabled() -> bool:
    return bool(GA4_MEASUREMENT_ID and GA4_API_SECRET)


def client_id_for(user_id: str = "", ga_client_id: str = "") -> str:
    """Resolve the GA4 client_id for an event.

    Prefers the real browser client_id (the `_ga` cookie value, minus its
    "GA1.1." prefix) when the caller has one. Otherwise derives a stable
    synthetic id from user_id, so the same user reports as the same GA4 user
    across events and processes without us storing anything new.
    """
    if ga_client_id:
        # Cookie form is GA1.1.1234567890.1699999999 — GA4 wants the tail.
        parts = ga_client_id.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 4 else ga_client_id
    if not user_id:
        return f"{int(time.time() * 1000) % 10**10}.{int(time.time())}"
    digest = hashlib.sha256(f"{APP_NAME}:{user_id}".encode()).hexdigest()
    return f"{int(digest[:9], 16) % 10**10}.{int(digest[9:18], 16) % 10**10}"


def _clean(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, list):  # `items` for ecommerce events
            out[key] = value
            continue
        if isinstance(value, _SCALARS):
            out[key] = value
        else:
            logger.warning("GA4 param %r dropped (unsupported type %s)", key, type(value).__name__)
    return out


async def send_event(
    name: str,
    *,
    client_id: str,
    user_id: str = "",
    params: Optional[Dict[str, Any]] = None,
    debug: bool = False,
) -> bool:
    """Send one event. Returns True on success; never raises."""
    if not enabled():
        logger.info("GA4 skipped (not configured): %s", name)
        return False

    event_params = _clean(params)
    event_params.setdefault("app_name", APP_NAME)
    # Without engagement_time_msec GA4 accepts the event but excludes it from
    # most standard reports. One millisecond is the documented minimum.
    event_params.setdefault("engagement_time_msec", 1)

    payload: Dict[str, Any] = {
        "client_id": client_id,
        "non_personalized_ads": False,
        "events": [{"name": name, "params": event_params}],
    }
    if user_id:
        payload["user_id"] = user_id

    url = _MP_DEBUG_URL if debug else _MP_URL
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                params={"measurement_id": GA4_MEASUREMENT_ID, "api_secret": GA4_API_SECRET},
                json=payload,
            )
        if debug:
            # The debug endpoint is the only one that reports validation
            # errors; /mp/collect answers 204 even for a malformed event.
            logger.info("GA4 debug %s -> %s %s", name, resp.status_code, resp.text[:500])
            return "validationMessages\": []" in resp.text or resp.json().get("validationMessages") == []
        if resp.status_code in (200, 204):
            logger.info("GA4 event sent: %s (client_id=%s)", name, client_id)
            return True
        logger.error("GA4 event failed (%s): %s", resp.status_code, resp.text[:300])
        return False
    except Exception as e:  # network, DNS, timeout — never break the caller
        logger.error("GA4 error sending %s: %s", name, e)
        return False


def track(
    name: str,
    *,
    client_id: str = "",
    user_id: str = "",
    ga_client_id: str = "",
    params: Optional[Dict[str, Any]] = None,
) -> None:
    """Fire-and-forget event for use inside request/webhook handlers."""
    if not enabled():
        return
    resolved = client_id or client_id_for(user_id, ga_client_id)
    asyncio.create_task(send_event(name, client_id=resolved, user_id=user_id, params=params))


# ---- Named events ---------------------------------------------------------
# GA4 reserves the meaning of sign_up, begin_checkout and purchase: using the
# reserved names is what makes them show up in the built-in reports and in
# Google Ads conversion imports, so do not rename them.


def track_sign_up(user_id: str, *, method: str = "email", ga_client_id: str = "") -> None:
    """method distinguishes Kindred's several front doors: a host creating a
    community, a relative accepting an invite, a guest claiming an identity."""
    track("sign_up", user_id=user_id, ga_client_id=ga_client_id, params={"method": method})


def _items(item_id: str, item_name: str, item_category: str, value_cents: int) -> list:
    return [{
        "item_id": item_id,
        "item_name": item_name,
        "item_category": item_category,
        "price": round(value_cents / 100, 2),
        "quantity": 1,
    }]


def track_begin_checkout(
    user_id: str,
    *,
    item_id: str,
    item_name: str,
    item_category: str,
    value_cents: int,
    ga_client_id: str = "",
) -> None:
    track(
        "begin_checkout",
        user_id=user_id,
        ga_client_id=ga_client_id,
        params={
            "currency": "USD",
            "value": round(value_cents / 100, 2),
            "items": _items(item_id, item_name, item_category, value_cents),
        },
    )


def track_purchase(
    *,
    transaction_id: str,
    value_cents: int,
    item_id: str,
    item_name: str,
    item_category: str = "subscription",
    user_id: str = "",
    ga_client_id: str = "",
) -> None:
    """A payment that actually cleared. Called from the Stripe webhook, not
    from the success page — a buyer who closes the tab still bought it."""
    track(
        "purchase",
        user_id=user_id,
        ga_client_id=ga_client_id,
        params={
            "transaction_id": transaction_id,
            "currency": "USD",
            "value": round(value_cents / 100, 2),
            "items": _items(item_id, item_name, item_category, value_cents),
        },
    )
