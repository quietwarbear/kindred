from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_organizer_command_unit")

from event_privacy import serialize_event_for_guest  # noqa: E402
from organizer_command_center import (  # noqa: E402
    build_command_center,
    canonical_response_summary,
    deadline_summary,
    next_best_action,
    planning_progress,
)
from organizer_reminders import (  # noqa: E402
    classify_provider_attempt,
    reminder_preflight,
    validate_idempotency_key,
)
from routes import organizer as organizer_routes  # noqa: E402

NOW = datetime(2027, 7, 1, 12, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


def reunion(**overrides):
    event = {
        "id": "synthetic-event",
        "community_id": "synthetic-community",
        "event_template": "reunion",
        "title": "Synthetic Reunion",
        "description": "Synthetic public description",
        "start_at": "2027-07-20T12:00:00-04:00",
        "end_at": "2027-07-21T12:00:00-04:00",
        "timezone": "America/New_York",
        "location": "Example Hall",
        "agenda": [
            {
                "id": "activity-1",
                "title": "Welcome",
                "description": "Synthetic welcome",
                "start_at": "2027-07-20T12:00:00-04:00",
                "end_at": "2027-07-20T13:00:00-04:00",
                "timezone": "America/New_York",
                "visibility": "published",
                "attendance_requested": True,
            }
        ],
        "event_invites": [],
        "rsvp_records": [],
        "activity_rsvps": [],
        "planning_checklist": [],
        "event_role_assignments": [],
        "potluck_items": [],
        "volunteer_slots": [],
    }
    event.update(overrides)
    return event


def progress(event):
    return planning_progress(
        event,
        travel_plans=[],
        budgets=[],
        planning_team_assigned=0,
        planning_team_pending=0,
    )


def test_response_counts_reconcile_members_and_keep_guests_separate():
    event = reunion(
        event_invites=[
            {
                "id": "member-old",
                "invite_source": "member",
                "email": "Family@Example.Invalid",
                "created_at": "2027-01-01T00:00:00Z",
                "rsvp_status": "pending",
            },
            {
                "id": "member-new",
                "member_id": "member-1",
                "invite_source": "member",
                "email": "family@example.invalid",
                "created_at": "2027-01-02T00:00:00Z",
                "rsvp_status": "going",
            },
            {
                "id": "guest-a",
                "invite_source": "guest",
                "email": "same@example.invalid",
                "rsvp_status": "maybe",
            },
            {
                "id": "guest-b",
                "invite_source": "guest",
                "email": "SAME@example.invalid",
                "rsvp_status": "pending",
            },
            {
                "id": "revoked",
                "invite_source": "guest",
                "status": "revoked",
                "rsvp_status": "pending",
            },
        ],
        rsvp_records=[
            {
                "user_id": "invite:member-old",
                "status": "maybe",
                "updated_at": "2027-01-01T00:00:00Z",
            },
            {
                "user_id": "member-1",
                "status": "going",
                "updated_at": "2027-01-03T00:00:00Z",
            },
        ],
    )
    summary = canonical_response_summary(
        event,
        member_ids_by_email={"family@example.invalid": "member-1"},
        now=NOW,
    )
    assert summary == {
        "total": 3,
        "responded": 2,
        "missing": 1,
        "counts": {
            "going": 1,
            "some": 0,
            "maybe": 1,
            "not-going": 0,
            "pending": 1,
        },
        "reconciles": True,
    }


def test_expired_and_superseded_credentials_do_not_create_response_gaps():
    event = reunion(
        event_invites=[
            {
                "id": "expired",
                "invite_source": "guest",
                "expires_at": "2027-06-30T00:00:00Z",
            },
            {
                "id": "superseded",
                "invite_source": "guest",
                "credential_state": "superseded",
            },
            {"id": "active", "invite_source": "guest"},
        ]
    )
    assert canonical_response_summary(event, now=NOW)["missing"] == 1


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda event: event.update(location=""), "complete_reunion_details"),
        (lambda event: event.update(agenda=[]), "confirm_itinerary"),
        (lambda event: None, "create_first_invitation"),
        (
            lambda event: event.update(event_invites=[{"id": "a"}]),
            "share_invitations",
        ),
        (
            lambda event: event.update(
                event_invites=[
                    {
                        "id": "a",
                        "opened_at": "2027-01-01T00:00:00Z",
                        "rsvp_status": "pending",
                    }
                ],
                agenda=[
                    {
                        **event["agenda"][0],
                        "rsvp_deadline": "2027-07-03T12:00:00Z",
                    }
                ],
            ),
            "resolve_approaching_deadline",
        ),
    ],
)
def test_deterministic_priority_order(mutate, expected):
    event = reunion()
    mutate(event)
    responses = canonical_response_summary(event, now=NOW)
    deadlines = deadline_summary(event, now=NOW)
    assert (
        next_best_action(
            event,
            responses=responses,
            deadlines=deadlines,
            progress=progress(event),
            now=NOW,
        )["code"]
        == expected
    )


def test_deadlines_fail_closed_for_nonexistent_and_ambiguous_local_times():
    event = reunion(
        agenda=[
            {
                **reunion()["agenda"][0],
                "rsvp_deadline": "2027-03-14T02:30:00",
            },
            {
                **reunion()["agenda"][0],
                "id": "activity-2",
                "rsvp_deadline": "2027-11-07T01:30:00",
            },
            {
                **reunion()["agenda"][0],
                "id": "activity-3",
                "rsvp_deadline": "2027-07-03T12:00:00-04:00",
            },
        ]
    )
    summary = deadline_summary(event, now=NOW)
    assert summary["invalid"] == 2
    assert summary["valid"] == 1
    assert summary["approaching"] == 1


def test_absent_budget_is_omitted_and_empty_areas_are_not_started():
    event = reunion(agenda=[], potluck_items=[], volunteer_slots=[])
    status = planning_progress(
        event,
        travel_plans=[],
        budgets=[],
        planning_team_assigned=0,
        planning_team_pending=0,
    )
    assert status["budget"] is None
    assert status["itinerary"]["status"] == "not_started"
    assert status["potluck"]["status"] == "not_started"
    assert status["travel"]["status"] == "not_started"


def test_guest_preview_reuses_minimal_serializer_and_excludes_organizer_fields():
    event = reunion(
        event_invites=[
            {
                "id": "secret-credential",
                "email": "guest@example.invalid",
                "note": "private note",
            }
        ],
        rsvp_records=[{"user_id": "invite:secret-credential", "status": "going"}],
        planning_team_member_ids=["organizer-2"],
        event_role_assignments=[
            {"role_name": "treasurer", "assignees": ["Private Name"]}
        ],
    )
    preview = serialize_event_for_guest(
        event,
        {"id": "preview-only", "invitee_name": "Invited guest"},
    )
    encoded = json.dumps(preview)
    for marker in [
        "secret-credential",
        "guest@example.invalid",
        "private note",
        "planning_team_member_ids",
        "event_role_assignments",
        "Private Name",
    ]:
        assert marker not in encoded


def test_command_center_report_is_aggregate_only():
    event = reunion(
        event_invites=[
            {
                "id": "secret",
                "email": "guest@example.invalid",
                "invitee_name": "Synthetic Guest",
            }
        ]
    )
    report = build_command_center(
        event,
        member_ids_by_email={},
        travel_plans=[],
        budgets=[],
        planning_team_assigned=0,
        planning_team_pending=0,
        recent_changes=[{"kind": "event-invite", "at": "2027-01-01T00:00:00Z"}],
        reminder_preflight={
            "available": False,
            "code": "delivery_unavailable",
            "recipient_count": 1,
        },
        now=NOW,
    )
    encoded = json.dumps(report)
    assert "guest@example.invalid" not in encoded
    assert "Synthetic Guest" not in encoded
    assert "secret" not in encoded


def test_reminder_preflight_is_fail_closed_and_never_claims_configuration_is_enough():
    missing = reminder_preflight(invitation_count=2, environment={})
    configured = reminder_preflight(
        invitation_count=2,
        environment={
            "ORGANIZER_REMINDER_DELIVERY_ENABLED": "true",
            "APP_URL": "https://example.invalid",
            "FROM_EMAIL": "sender@example.invalid",
            "PUBLIC_API_BASE_URL": "https://api.example.invalid",
            "RESEND_API_KEY": "synthetic",
        },
    )
    assert missing == {
        "available": False,
        "code": "delivery_unavailable",
        "recipient_count": 2,
    }
    assert configured["available"] is False
    assert configured["code"] == "privacy_safe_sender_unavailable"


def test_provider_rejection_timeout_and_ambiguous_acceptance_are_sanitized():
    assert classify_provider_attempt(rejected=True).retry_allowed is True
    assert classify_provider_attempt(timed_out=True).status == "ambiguous"
    assert classify_provider_attempt(ambiguous=True).retry_allowed is False
    assert classify_provider_attempt(accepted=True, timed_out=True).safe_code == (
        "provider_acceptance_ambiguous"
    )


def test_stable_idempotency_keys_are_required():
    assert validate_idempotency_key("reminder:synthetic-operation-1")
    for invalid in ["", "short", "contains spaces and customer@example.invalid"]:
        with pytest.raises(ValueError):
            validate_idempotency_key(invalid)


def test_frontend_analytics_and_routes_are_allowlisted_and_credential_free():
    analytics = (ROOT / "frontend/src/lib/analytics.js").read_text()
    page = (ROOT / "frontend/src/components/OrganizerCommandCenterPage.jsx").read_text()
    app = (ROOT / "frontend/src/App.js").read_text()
    for event_name in [
        "command_center_viewed",
        "next_action_viewed",
        "next_action_completed",
        "invitation_share_initiated",
        "reminder_preflight_passed",
        "reminder_preflight_failed",
        "planning_team_setup_started",
        "planning_team_setup_completed",
        "organizer_returned_after_first_rsvp",
    ]:
        assert f'"{event_name}"' in analytics
    allowlist = analytics.split("SAFE_REUNION_PROPERTY_KEYS", 1)[1].split("]);", 1)[0]
    for forbidden in ["email", "event_id", "community_id", "title", "message", "token"]:
        assert f'"{forbidden}"' not in allowlist
    assert 'path="/reunion/command/:eventId"' in app
    assert "/rsvp?" not in page
    assert "/rsvp/" not in page
    assert "data-ph-no-capture" in page


def test_routes_use_canonical_authorization_and_do_not_reuse_generic_email():
    routes = (ROOT / "backend/routes/organizer.py").read_text()
    reminders = (ROOT / "backend/organizer_reminders.py").read_text()
    assert 'ensure_minimum_role(current_user, "organizer")' in routes
    assert "get_event_for_user(event_id, current_user)" in routes
    assert "is_platform_admin" not in routes
    assert "email_service" not in routes
    assert "_send_email" not in routes
    assert "privacy_safe_sender_unavailable" in reminders


@pytest.mark.asyncio
async def test_organizer_gate_rejects_members_and_does_not_honor_platform_admin(
    monkeypatch,
):
    async def event_for_user(_event_id, _user):
        return reunion()

    monkeypatch.setattr(organizer_routes, "get_event_for_user", event_for_user)
    for user in [
        {"id": "member", "community_id": "a", "role": "member"},
        {
            "id": "platform-admin",
            "community_id": "a",
            "role": "member",
            "is_platform_admin": True,
        },
    ]:
        with pytest.raises(HTTPException) as exc:
            await organizer_routes._organizer_reunion("synthetic-event", user)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_cross_community_and_hidden_event_lookup_remain_not_found(monkeypatch):
    async def not_found(_event_id, _user):
        raise HTTPException(status_code=404, detail="Event not found.")

    monkeypatch.setattr(organizer_routes, "get_event_for_user", not_found)
    with pytest.raises(HTTPException) as exc:
        await organizer_routes._organizer_reunion(
            "other-event",
            {"id": "organizer", "community_id": "a", "role": "organizer"},
        )
    assert exc.value.status_code == 404
