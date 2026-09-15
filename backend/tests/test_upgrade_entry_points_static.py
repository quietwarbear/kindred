"""Static guarantees that families can find the subscription page."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_hosts_reach_subscription_from_today_and_settings():
    card = read("frontend/src/components/PlanUpgradeCard.jsx")
    home = read("frontend/src/components/HomePage.jsx")
    settings = read("frontend/src/components/SettingsPage.jsx")

    assert 'apiRequest("/subscriptions/current", { token })' in card
    assert card.count('<Link to="/subscription">') == 2
    assert (
        '<PlanUpgradeCard isHost={todayData.viewer_role === "host"} token={token} variant="today" />'
        in home
    )
    assert (
        '{user?.role === "host" ? <PlanUpgradeCard token={token} variant="settings" /> : null}'
        in settings
    )


def test_keep_the_record_prompts_hosts_and_tells_everyone_else_to_ask_the_host():
    card = read("frontend/src/components/PlanUpgradeCard.jsx")
    plan_usage = read("frontend/src/lib/planUsage.js")

    assert 'startsAt: Date.parse("2026-09-07T00:00:00-07:00")' in plan_usage
    assert 'endsAt: Date.parse("2026-12-06T00:00:00-08:00")' in plan_usage
    assert "const contestPrompt = contestOpen && !usage.isPaid && usage.canUpgrade;" in card
    assert "Ask your family host to upgrade so everyone can enter." in card
    # Non-hosts cannot buy, so their card must not link to checkout.
    ask_host = card.split('data-testid="today-contest-ask-host-card"', 1)[1].split("</section>", 1)[0]
    assert "/subscription" not in ask_host


def test_member_limit_error_points_joiners_to_the_host():
    dependencies = read("backend/dependencies.py")
    assert "Please upgrade to add more." not in dependencies
    assert "The family host can upgrade the plan to make room." in dependencies
