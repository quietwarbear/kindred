"""The sign-in page must not front-load family setup on a first visit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_signin_page_has_no_community_setup_form():
    auth = read("frontend/src/components/AuthPage.jsx")
    for removed in (
        "launch-community-name-input",
        "launch-community-type-input",
        "launch-location-input",
        "launch-motto-input",
        "launch-description-input",
        "What brings your people together?",
        "Launch Kindred",
    ):
        assert removed not in auth, removed


def test_new_visitors_are_sent_to_the_reunion_first_path():
    auth = read("frontend/src/components/AuthPage.jsx")
    assert '<Link to="/reunion/start">' in auth
    assert "New to Kindred?" in auth
    # Create account only exists once a reunion draft or family-access request exists.
    assert "{hasLightweightIntent ? (\n          <TabsContent value=\"launch\">" in auth
    assert 'hasReunionIntent ? "launch" : "login"' in auth


def test_signin_copy_does_not_turn_away_new_families():
    auth = read("frontend/src/components/AuthPage.jsx")
    assert "Invitation-only access" not in auth
    assert "after starting a reunion plan" not in auth
    assert "Email your invite was sent to" in auth
