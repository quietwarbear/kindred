from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_reunion_flow_preserves_the_existing_security_boundary():
    app = read("frontend/src/App.js")
    start = read("frontend/src/components/ReunionStartPage.jsx")
    auth = read("frontend/src/components/AuthPage.jsx")
    assert 'path="/reunion/start"' in app
    assert 'path="/reunion/activate/:eventId"' in app
    assert "this draft stays only in this browser" in start
    assert "provisionalCommunityName" in auth
    assert 'apiRequest("/events"' in auth


def test_public_rsvp_remains_minimal_and_identifies_the_organizer():
    public = read("backend/routes/public.py")
    events = read("backend/routes/events.py")
    public_view = public.split("def _public_view", 1)[1].split("@router.get", 1)[0]
    assert '"created_by_name": current_user["full_name"]' in events
    assert '"event_template": event.get("event_template", "custom")' in public_view
    assert 'view["invited_by_name"]' in public
    for forbidden in ["member_count", "event_invites", "rsvp_records", "community_id"]:
        assert forbidden not in public_view


def test_reunion_analytics_have_an_explicit_privacy_allowlist():
    analytics = read("frontend/src/lib/analytics.js")
    for event_name in [
        "reunion_start_clicked",
        "reunion_draft_created",
        "reunion_preview_viewed",
        "invite_created",
        "invite_link_copied",
        "invite_opened",
        "rsvp_completed",
        "guest_account_started",
        "community_activated",
        "memory_prompt_completed",
    ]:
        assert f'"{event_name}"' in analytics
    allowlist = analytics.split("SAFE_REUNION_PROPERTY_KEYS", 1)[1].split("]);", 1)[0]
    for sensitive_key in ["email", "token", "gathering_name", "community_id"]:
        assert f'"{sensitive_key}"' not in allowlist


def test_activation_requires_evidence_stronger_than_invite_creation_or_copying():
    activation = read("frontend/src/components/ReunionActivationPage.jsx")
    assert '(invite.rsvp_status || "pending") !== "pending"' in activation
    assert "invite.opened_at" in activation
    assert "invite.delivery_verified_at" in activation
    assert "evidencedInvites >= 3" in activation
    assert "invites.length >= 3" not in activation
    assert "invite_link_copied" not in activation
