"""Offline regression tests for the emergency web-subscription kill switch."""

import ast
import asyncio
from copy import deepcopy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBSCRIPTIONS_PATH = REPO_ROOT / "backend" / "routes" / "subscriptions.py"
SUBSCRIPTIONS_SOURCE = SUBSCRIPTIONS_PATH.read_text()
SUBSCRIPTIONS_TREE = ast.parse(SUBSCRIPTIONS_SOURCE)
PAID_PLAN_INTERVALS = (
    ("sapling", "monthly"),
    ("sapling", "annual"),
    ("oak", "monthly"),
    ("oak", "annual"),
    ("redwood", "monthly"),
    ("redwood", "annual"),
)
EXPECTED_CODE = "subscription_checkout_migrating"
EXPECTED_MESSAGE = (
    "New web subscription purchases are temporarily unavailable while billing is being updated."
)


class StubHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


class StubStatus:
    HTTP_410_GONE = 410


class SubscriptionCheckoutRequest:
    def __init__(self, plan_id, billing_cycle):
        self.plan_id = plan_id
        self.billing_cycle = billing_cycle
        self.origin_url = "https://example.invalid"


def checkout_handler_node() -> ast.AsyncFunctionDef:
    return next(
        node
        for node in SUBSCRIPTIONS_TREE.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "create_subscription_checkout"
    )


def isolated_checkout_handler():
    """Compile the committed handler itself without importing provider dependencies."""
    node = deepcopy(checkout_handler_node())
    node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    namespace = {
        "HTTPException": StubHTTPException,
        "SubscriptionCheckoutRequest": SubscriptionCheckoutRequest,
        "status": StubStatus,
    }
    exec(compile(module, str(SUBSCRIPTIONS_PATH), "exec"), namespace)
    return namespace["create_subscription_checkout"]


@pytest.mark.parametrize(("plan_id", "billing_cycle"), PAID_PLAN_INTERVALS)
def test_every_paid_plan_and_interval_returns_stable_410(plan_id, billing_cycle):
    handler = isolated_checkout_handler()
    payload = SubscriptionCheckoutRequest(plan_id, billing_cycle)

    with pytest.raises(StubHTTPException) as raised:
        asyncio.run(handler(payload))

    assert raised.value.status_code == 410
    assert raised.value.detail == {
        "code": EXPECTED_CODE,
        "message": EXPECTED_MESSAGE,
    }


def test_checkout_handler_cannot_reach_stripe_or_write_subscription_state():
    node = checkout_handler_node()
    source = ast.get_source_segment(SUBSCRIPTIONS_SOURCE, node)
    prohibited = (
        "stripe",
        "_configure_stripe",
        "_get_or_create_stripe_customer",
        "Price.retrieve",
        "Customer.create",
        "Session.create",
        "subscriptions_collection",
        "insert_one",
        "update_one",
        "Depends",
        "get_current_user",
    )

    assert all(token not in source for token in prohibited)
    assert len(node.body) == 1
    assert isinstance(node.body[0], ast.Raise)


def test_unrelated_payment_and_existing_subscriber_routes_remain_present():
    finance = (REPO_ROOT / "backend" / "routes" / "finance.py").read_text()
    subscriptions = SUBSCRIPTIONS_SOURCE

    assert '@router.post("/payments/checkout/session")' in finance
    assert "stripe.checkout.Session.create(" in finance
    assert '@router.post("/addons/checkout")' in subscriptions
    for route in (
        '@router.get("/subscriptions/current")',
        '@router.post("/subscriptions/cancel")',
        '@router.post("/subscriptions/reactivate")',
        '@router.post("/subscriptions/portal")',
        '@router.get("/subscriptions/checkout/status/{session_id}")',
    ):
        assert route in subscriptions


def test_web_ui_disables_subscription_purchase_without_disabling_addons():
    subscription_page = (
        REPO_ROOT / "frontend" / "src" / "components" / "SubscriptionPage.jsx"
    ).read_text()
    pricing_page = (
        REPO_ROOT / "frontend" / "src" / "components" / "PricingPage.jsx"
    ).read_text()
    expected_ui_message = (
        "Web subscriptions are temporarily unavailable while billing is being updated."
    )

    assert expected_ui_message in subscription_page
    assert expected_ui_message in pricing_page
    # Web purchase is disabled until the deployment sets the RevenueCat Billing
    # web key. Both surfaces must read the same flag, or the buttons and the
    # "unavailable" notice disagree with each other.
    assert "webPurchaseDisabled={!isIOS() && !WEB_PURCHASES_ENABLED}" in subscription_page
    assert "!displayedBillingOption || webPurchaseDisabled" in subscription_page
    for page in (subscription_page, pricing_page):
        assert (
            "const WEB_PURCHASES_ENABLED = Boolean(process.env.REACT_APP_REVENUECAT_WEB_KEY);"
            in page
        )
    assert "{!WEB_PURCHASES_ENABLED && (" in pricing_page
    assert 'apiRequest("/subscriptions/checkout"' not in subscription_page
    assert 'apiRequest("/addons/checkout"' in subscription_page
    assert 'data-testid={`addon-buy-${addon.id}`}' in subscription_page
