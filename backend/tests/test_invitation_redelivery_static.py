"""Static deployment-boundary checks for invitation redelivery."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_redelivery_is_operator_only_and_bypasses_generic_email_helper():
    coordinator = read("backend/invitation_redelivery.py")
    provider = read("backend/invitation_redelivery_provider.py")
    cli = read("backend/scripts/run_invitation_redelivery.py")
    server = read("backend/server.py")

    assert "APIRouter" not in coordinator
    assert "FastAPI" not in coordinator
    assert "email_service" not in coordinator
    assert "does not import or call ``email_service._send_email``" in provider
    assert "from email_service import" not in provider
    assert "import email_service" not in provider
    assert "RAILWAY_GIT_COMMIT_SHA" in cli
    assert "--expected-commit" in cli
    assert "required=True" in cli
    assert "RESEND_VERIFIED_DOMAIN" in cli
    assert "restricted_api_key" in provider
    assert "resend._domainkey" in provider
    assert "feedback-smtp.us-east-1.amazonses.com" in provider
    assert "v=spf1 include:amazonses.com ~all" in provider
    assert "new_operation_id" not in cli
    assert "invitation_redelivery_operations_collection.create_index" in server
    assert "invitation_redelivery_incident_selection_once" in server
    assert "event_invitation_staged_token_lookup" not in server
    assert "credential_rotation" not in server


def test_links_and_validation_use_fragment_and_header_only_transport():
    coordinator = read("backend/invitation_redelivery.py")
    validator = read("backend/invitation_redelivery_validator.py")

    assert 'f"{stable_app_url}/rsvp#{replacement_credential}"' in coordinator
    assert '/api/public/rsvp"' in validator
    assert 'authorization=f"Bearer {credential}"' in validator
    assert "/api/public/rsvp/" not in validator
    assert "?token=" not in coordinator
    assert "?token=" not in validator


def test_sensitive_dataclasses_redact_their_representations():
    source = read("backend/invitation_redelivery.py")

    assert "@dataclass(frozen=True, repr=False)" in source
    for marker in (
        "recipient=<redacted>",
        "replacement_credential=<redacted>",
        "credential_pairs=<redacted>",
        "subject=<redacted>",
        "html_body=<redacted>",
    ):
        assert marker in source


def test_logs_and_reports_are_aggregate_only():
    source = read("backend/invitation_redelivery.py")
    provider = read("backend/invitation_redelivery_provider.py")
    report_fields = source.split(
        "class SafeOperationReport",
        1,
    )[1].split(
        "class RedeliveryFailure", 1
    )[0]

    for forbidden in (
        "recipient",
        "email",
        "event_title",
        "message_body",
        "provider_payload",
    ):
        assert forbidden not in report_fields

    log_lines = "\n".join(
        line
        for line in (source + "\n" + provider).splitlines()
        if "invitation_redelivery status=" in line
        or "invitation_delivery status=" in line
    )
    for forbidden in (
        "recipient",
        "email",
        "credential",
        "subject",
        "html_body",
        "response.text",
        "request.content",
    ):
        assert forbidden not in log_lines


def test_subscription_and_provider_systems_are_not_wired_to_redelivery():
    cli = read("backend/scripts/run_invitation_redelivery.py")
    coordinator = read("backend/invitation_redelivery.py")
    combined = cli + coordinator
    for forbidden in (
        "stripe",
        "revenuecat",
        "RevenueCat",
        "Apple",
        "Google",
        "subscriptions_collection",
    ):
        assert forbidden not in combined


def test_recovery_outbox_and_revision_guards_are_mandatory():
    store = read("backend/invitation_redelivery_store.py")
    cli = read("backend/scripts/run_invitation_redelivery.py")

    assert "INVITATION_REDELIVERY_RECOVERY_KEY" in cli
    assert "start_transaction()" in store
    assert "claim_provider_submission" in store
    assert "ProviderStatus.SUBMITTING" in store
    assert '"$inc": {"rsvp_revision": 1}' in store
    assert "_guarded_event_query(event)" in store
    assert "old_credential_ciphertext" in store
    assert "new_credential_ciphertext" in store
    assert "recipient_ciphertext" in store
    assert "replacement_credential" not in "\n".join(
        line for line in store.splitlines() if '"$set"' in line
    )
    assert 'target.pop("old_credential_ciphertext", None)' in store
    assert 'target.pop("new_credential_ciphertext", None)' in store
    assert 'target.pop("recipient_ciphertext", None)' in store
    assert '"selection_fingerprint": fingerprint' in store
    assert 'invite["credential_rotation"]' in store
    assert '"validation_revision": current_revision' in store
    assert 'operation.get("status") == "completed"' in store
    assert "async def preflight" in store
