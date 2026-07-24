"""Provider-neutral subscription lifecycle invariants."""

from datetime import datetime, timezone
from typing import Optional

from pricing import resolve_revenuecat_product


PAID_ACCESS_STATUSES = frozenset({"active", "canceling", "past_due"})


def _future_timestamp(value: object, now: datetime) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed > now


def subscription_has_paid_access(
    subscription: Optional[dict],
    now: Optional[datetime] = None,
) -> bool:
    if not subscription or subscription.get("status") not in PAID_ACCESS_STATUSES:
        return False
    current_time = now or datetime.now(timezone.utc)
    access_until = (
        subscription.get("grace_period_expires_at")
        or subscription.get("current_period_end")
        or subscription.get("expires_at")
    )
    if subscription.get("status") == "active":
        # Provider-backed access must have a provider-authoritative end date.
        # Administrative overrides are not purchases and remain non-recurring.
        if subscription.get("provider") in {"stripe", "revenuecat"}:
            return _future_timestamp(access_until, current_time)
        return True
    return _future_timestamp(access_until, current_time)


def should_apply_provider_event(current_timestamp: object, incoming_timestamp: object) -> bool:
    """Accept a provider event only when it is not older than stored state."""
    if not isinstance(incoming_timestamp, int):
        return False
    if current_timestamp is None:
        return True
    return isinstance(current_timestamp, int) and incoming_timestamp >= current_timestamp


def revenuecat_period_is_active(data: dict, now: Optional[datetime] = None) -> bool:
    expires_at = data.get("expires_date")
    if not expires_at:
        return True
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return False
    return parsed > (now or datetime.now(timezone.utc))


def resolve_revenuecat_subscriber(
    subscriber: dict,
    now: Optional[datetime] = None,
) -> Optional[tuple[str, str, str, str, str]]:
    """Resolve active subscriber state to one canonical native purchase."""
    entitlements = subscriber.get("entitlements", {})
    subscriptions = subscriber.get("subscriptions", {})
    known = []
    unknown_products = []

    for product_id, subscription in subscriptions.items():
        try:
            tier_id, interval, entitlement_id = resolve_revenuecat_product(product_id)
        except ValueError:
            if revenuecat_period_is_active(subscription, now):
                unknown_products.append(product_id)
            continue
        entitlement = entitlements.get(entitlement_id)
        if not entitlement or not revenuecat_period_is_active(entitlement, now):
            continue
        expires_at = entitlement.get("expires_date") or subscription.get("expires_date") or ""
        known.append((tier_id, interval, entitlement_id, product_id, expires_at))

    active_entitlements = {
        entitlement_id: entitlement
        for entitlement_id, entitlement in entitlements.items()
        if revenuecat_period_is_active(entitlement, now)
    }
    if len(known) > 1:
        raise ValueError("RevenueCat returned multiple active canonical subscriptions.")
    if known:
        expected_entitlement = known[0][2]
        unexpected_entitlements = set(active_entitlements) - {expected_entitlement}
        if unknown_products or unexpected_entitlements:
            raise ValueError("RevenueCat returned an unmapped or contradictory paid subscription.")
        return known[0]
    if active_entitlements or unknown_products:
        raise ValueError("RevenueCat returned an unmapped or contradictory paid subscription.")
    return None


def resolve_revenuecat_webhook_purchase(event: dict) -> tuple[str, str, str, str]:
    """Resolve and cross-check the product, entitlement, and expiration."""
    tier_id, interval, entitlement_id = resolve_revenuecat_product(event.get("product_id", ""))
    entitlement_ids = event.get("entitlement_ids") or []
    if not entitlement_ids and event.get("entitlement_id"):
        entitlement_ids = [event["entitlement_id"]]
    if entitlement_id not in entitlement_ids:
        raise ValueError("RevenueCat product and entitlement do not agree.")
    expiration_at_ms = event.get("expiration_at_ms")
    if not isinstance(expiration_at_ms, (int, float)):
        raise ValueError("RevenueCat subscription event is missing its expiration.")
    expires_at = datetime.fromtimestamp(expiration_at_ms / 1000, tz=timezone.utc).isoformat()
    return tier_id, interval, entitlement_id, expires_at
