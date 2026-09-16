"""The "web subscriptions unavailable" notice must never be hardcoded.

Web purchases went live on 2026-09-05 (#50 gated the pricing page), but the
landing page kept an ungated copy of the notice and told every visitor that
buying was unavailable — for ten days, while the campaign pointed traffic there.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTICE = "Web subscriptions are temporarily unavailable while billing is being updated."
GATE = "WEB_PURCHASES_ENABLED"
PAGES = (
    "frontend/src/components/LandingPage.jsx",
    "frontend/src/components/PricingPage.jsx",
    "frontend/src/components/SubscriptionPage.jsx",
)


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_the_switch_comes_from_the_deployment_not_a_literal():
    for page in PAGES:
        source = read(page)
        assert GATE in source, page
        if "const WEB_PURCHASES_ENABLED" in source:
            assert "Boolean(process.env.REACT_APP_REVENUECAT_WEB_KEY)" in source, page


def test_any_page_carrying_the_notice_also_gates_on_the_switch():
    for page in PAGES:
        source = read(page)
        if NOTICE in source or "WEB_SUBSCRIPTION_MESSAGE" in source:
            assert f"!{GATE}" in source, page


def test_the_landing_notice_renders_only_when_purchases_are_off():
    source = read("frontend/src/components/LandingPage.jsx")
    assert f"{{!{GATE} && (" in source
    block = source.split(f"{{!{GATE} && (", 1)[1].split(")}", 1)[0]
    assert NOTICE in block
    assert 'data-testid="landing-billing-notice"' in block
