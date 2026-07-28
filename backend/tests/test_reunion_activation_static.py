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
    public_view = public.split("def _public_view", 1)[1].split(
        "async def _public_rsvp_view", 1
    )[0]
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


def test_invitation_credentials_stay_out_of_new_request_urls_and_worker_caches():
    app = read("frontend/src/App.js")
    page = read("frontend/src/components/PublicRSVPPage.jsx")
    transport = read("frontend/src/lib/invitationTransport.js")
    worker = read("frontend/public/sw.js")
    backend = read("backend/routes/public.py")
    assert 'path="/rsvp"' in app
    assert 'fetch(`${API_URL}/public/rsvp`' in page
    assert "/public/rsvp/${token}" not in page
    assert "/rsvp#${encodeURIComponent(invitationId)}" in transport
    assert "Authorization: `Bearer ${token}`" in transport
    assert 'const CACHE_NAME = "kindred-v2"' in worker
    assert 'url.pathname.startsWith("/rsvp/")' in worker
    assert "cache.delete(request)" in worker
    assert '@router.get("/rsvp")' in backend
    assert '@router.post("/rsvp")' in backend
    assert '@router.get("/rsvp/{token}")' not in backend
    assert '@router.post("/rsvp/{token}")' not in backend


def test_fragment_invitation_blocks_pre_react_third_party_scripts():
    html = read("frontend/public/index.html")
    css = read("frontend/src/index.css")
    landing = read("frontend/src/components/LandingPage.jsx")
    assert "window.__kindredSensitiveInvitationRoute" in html
    assert r'^\/rsvp\/?$' in html
    assert "Boolean(window.location.hash)" in html
    assert html.count("!window.__kindredSensitiveInvitationRoute") >= 3
    for third_party in [
        "www.googletagmanager.com/gtm.js",
        "www.googletagmanager.com/gtag/js",
        "accounts.google.com/gsi/client",
    ]:
        assert third_party in html
    assert "fonts.googleapis.com" not in html
    assert "fonts.googleapis.com" not in css
    assert "images.unsplash.com" not in css
    assert "developer.apple.com/assets" not in landing
    assert "badges/static/images" not in landing


def test_committed_browser_campaign_uses_fragment_and_header_transport():
    campaign = read("frontend/scripts/verify-commercial-readiness.js")
    assert "/rsvp#demo-invite" in campaign
    assert "authorization !== 'Bearer demo-invite'" in campaign
    assert "requestUrl.pathname === '/api/public/rsvp'" in campaign
    assert "/api/public/rsvp/demo-invite" not in campaign
    assert "allowedSensitiveOrigins" in campaign
    assert "assertSensitivePageIsolation" in campaign
    assert "legacyPage = await browser.newPage()" in campaign
    assert "server.closeAllConnections" in campaign


def test_incident_qa_cannot_disable_identity_or_subscription_provider_startup():
    index = read("frontend/src/index.js")
    auth = read("frontend/src/components/AuthPage.jsx")
    railway = read("backend/railway.json")
    assert "REACT_APP_DISABLE_PROVIDER_INIT" not in index
    assert "REACT_APP_DISABLE_PROVIDER_INIT" not in auth
    assert "--no-access-log" not in railway
