"""Static guarantees that hosts can find the subscription page."""

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
        '{todayData.viewer_role === "host" ? <PlanUpgradeCard token={token} variant="today" /> : null}'
        in home
    )
    assert (
        '{user?.role === "host" ? <PlanUpgradeCard token={token} variant="settings" /> : null}'
        in settings
    )


def test_member_limit_error_points_joiners_to_the_host():
    dependencies = read("backend/dependencies.py")
    assert "Please upgrade to add more." not in dependencies
    assert "The family host can upgrade the plan to make room." in dependencies
