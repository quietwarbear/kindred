"""Release 7 continuity policy and source-boundary tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from guest_family_access import (
    find_relationship_invite,
    invitation_relationship_fingerprint,
    is_expired,
    safe_organizer_projection,
    safe_status_projection,
)

ROOT = Path(__file__).resolve().parents[2]


def _invite(**overrides):
    return {
        "id": "synthetic-private-credential",
        "created_at": "2027-08-01T00:00:00+00:00",
        "invite_source": "guest",
        "email": "Guest@Example.invalid",
        "status": "invited",
        "rsvp_status": "going",
        **overrides,
    }


def test_relationship_survives_credential_replacement_without_email_authority():
    original = _invite()
    replacement = _invite(
        id="synthetic-replacement-credential",
        credential_rotation={"operation_id": "internal-only"},
    )
    original_fingerprint = invitation_relationship_fingerprint("event-one", original)
    assert original_fingerprint == invitation_relationship_fingerprint("event-one", replacement)
    assert find_relationship_invite(
        {"id": "event-one", "event_invites": [replacement]}, original_fingerprint
    ) == replacement
    assert "Guest@Example.invalid" not in original_fingerprint
    assert "synthetic-private-credential" not in original_fingerprint


def test_relationship_fails_closed_for_ambiguous_revoked_or_cross_event_claims():
    active = _invite()
    fingerprint = invitation_relationship_fingerprint("event-one", active)
    assert find_relationship_invite(
        {"id": "event-one", "event_invites": [active, dict(active)]}, fingerprint
    ) is None
    assert find_relationship_invite(
        {"id": "event-one", "event_invites": [_invite(revoked_at="2027-08-02T00:00:00+00:00")]},
        fingerprint,
    ) is None
    assert find_relationship_invite(
        {"id": "event-two", "event_invites": [active]}, fingerprint
    ) is None


def test_expiration_and_state_projections_are_content_free():
    now = datetime.now(timezone.utc)
    assert is_expired((now - timedelta(seconds=1)).isoformat(), now=now)
    assert not is_expired((now + timedelta(seconds=1)).isoformat(), now=now)
    assert is_expired("malformed", now=now)

    private = {
        "id": "internal-database-id",
        "public_reference": "safe-action-reference",
        "community_id": "private-community",
        "event_id": "private-event",
        "applicant_user_id": "private-user",
        "applicant_name": "Synthetic Applicant",
        "email": "private@example.invalid",
        "relationship_fingerprint": "internal-fingerprint",
        "status": "pending",
        "revision": 2,
        "created_at": "2027-08-02T00:00:00+00:00",
    }
    applicant = safe_status_projection(private)
    organizer = safe_organizer_projection(private)
    assert applicant == {
        "status": "pending",
        "revision": 2,
        "next_action_codes": ["wait_for_organizer", "cancel_request"],
    }
    assert organizer == {
        "request_reference": "safe-action-reference",
        "applicant_name": "Synthetic Applicant",
        "status": "pending",
        "revision": 2,
        "requested_at": "2027-08-02T00:00:00+00:00",
    }
    rendered = repr((applicant, organizer))
    for forbidden in ("private@example.invalid", "private-community", "private-event", "private-user", "internal-fingerprint"):
        assert forbidden not in rendered


def test_routes_keep_credentials_out_of_urls_and_decisions_transactional():
    public_routes = (ROOT / "backend/routes/public.py").read_text()
    access_routes = (ROOT / "backend/routes/guest_family_access.py").read_text()
    frontend = (ROOT / "frontend/src/components/PublicRSVPPage.jsx").read_text()
    service_worker = (ROOT / "frontend/public/sw.js").read_text()

    assert '@router.post("/family-access-claim")' in public_routes
    assert 'Header(default=None, alias="X-Kindred-Guest-Claim")' in access_routes
    assert "with_transaction" in access_routes
    assert '"$addToSet": {"community_ids"' in access_routes
    assert "email" not in access_routes.split("async def submit_family_access_request", 1)[1].split("@router.get", 1)[0]
    assert 'window.history.replaceState({}, "", "/rsvp")' in frontend
    assert 'window.location.assign("/login?intent=family-access")' in frontend
    assert "guest-family-access-claim" not in service_worker
    assert "/family-access-claim/" not in public_routes


def test_auth_continuity_intent_disables_legacy_email_invite_autojoin():
    auth = (ROOT / "backend/routes/auth.py").read_text()
    assert "allow_email_invite=not payload.family_access_intent" in auth
    assert "if allow_email_invite" in auth
    assert '@router.post("/auth/guest-account"' in auth
    guest_account = auth.split('@router.post("/auth/guest-account"', 1)[1].split("@router", 1)[0]
    assert '"community_id": ""' in guest_account
    assert '"community_ids": []' in guest_account
    assert '"role": "member"' in guest_account
