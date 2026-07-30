"""Static boundaries for the reunion-first consumer activation path."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_authentication_never_routes_first_value_to_subscription():
    auth_page = read("frontend/src/components/AuthPage.jsx")
    assert (
        'navigate(payload.user?.community_id ? "/home" : "/reunion/start")' in auth_page
    )
    assert 'navigate(intent === "guest" ? "/home" : "/subscription")' not in auth_page


def test_onboarding_gate_is_provider_neutral():
    app = read("frontend/src/App.js")
    assert "needsGoogleOnboarding" not in app
    assert "const needsOrganizerActivation = !session?.user?.community_id;" in app
    assert 'return <Navigate replace to="/reunion/start" />;' in app
    assert "auth_provider ===" not in app


def test_social_sign_in_does_not_create_an_automatic_circle():
    auth = read("backend/routes/auth.py")
    social_auth = auth.split("async def _build_google_auth_response", 1)[1].split(
        "# ---- Apple Sign In helpers ----", 1
    )[0]
    assert '"community_id": ""' in social_auth
    assert '"community_ids": []' in social_auth
    assert '"role": "member"' in social_auth
    assert "A new Kindred courtyard created through social sign up." not in social_auth
    assert "build_default_subyards" not in social_auth


def test_community_creation_requires_confirmed_organizer_intent():
    auth = read("backend/routes/auth.py")
    helper = auth.split("async def _ensure_confirmed_organizer_community", 1)[1].split(
        '@router.post("/auth/onboarding/complete"', 1
    )[0]
    assert 'if current_user.get("community_id")' in helper
    assert "if not community_name" in helper
    assert "uuid.uuid5" in helper
    assert '"_id": community_id' in helper
    assert "DuplicateKeyError" in helper
    assert 'community_doc.get("owner_user_id") != current_user["id"]' in helper
    assert '"community_id": ""' in helper
    assert '"community_id": {"$exists": False}' in helper
    assert "status.HTTP_409_CONFLICT" in helper


def test_reunion_save_activates_then_uses_idempotent_event_creation():
    start = read("frontend/src/components/ReunionStartPage.jsx")
    auth_page = read("frontend/src/components/AuthPage.jsx")
    for source in (start, auth_page):
        assert 'apiRequest("/auth/onboarding/complete"' in source
        assert 'apiRequest("/events"' in source
        assert "reunionDraftToEventPayload" in source
        assert '"reunion_saved"' in source
    assert "clearReunionDraft()" in start


def test_activation_analytics_remain_allowlisted_and_credential_free():
    analytics = read("frontend/src/lib/analytics.js")
    assert '"organizer_intent_confirmed"' in analytics
    assert '"reunion_saved"' in analytics
    allowlist = analytics.split("SAFE_REUNION_PROPERTY_KEYS", 1)[1].split("]);", 1)[0]
    for sensitive_key in [
        "email",
        "token",
        "event_id",
        "community_id",
        "gathering_name",
        "organizer_name",
    ]:
        assert f'"{sensitive_key}"' not in allowlist
