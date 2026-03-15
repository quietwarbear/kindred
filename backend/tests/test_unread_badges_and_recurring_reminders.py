import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv


# Run tests against the public preview URL used by frontend users
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required for API tests")
BASE_URL = BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def seeded_context(api_client):
    # Seed host + invited member context for unread summary and recurring RSVP reminder coverage
    suffix = uuid.uuid4().hex[:8]
    host_email = f"test_unread_host_{suffix}@example.com"
    member_email = f"test_unread_member_{suffix}@example.com"
    password = "SecurePass123!"

    bootstrap_payload = {
        "full_name": "TEST Unread Host",
        "email": host_email,
        "password": password,
        "community_name": f"TEST Unread Courtyard {suffix}",
        "community_type": "family reunion",
        "location": "Austin, TX",
        "description": "TEST seed for unread badge and reminder coverage",
        "motto": "TEST together",
    }
    bootstrap_response = api_client.post(f"{BASE_URL}/api/auth/bootstrap", json=bootstrap_payload, timeout=30)
    assert bootstrap_response.status_code == 200
    host_auth = bootstrap_response.json()

    invite_response = api_client.post(
        f"{BASE_URL}/api/invites",
        headers=_auth_headers(host_auth["token"]),
        json={"email": member_email, "role": "member"},
        timeout=20,
    )
    assert invite_response.status_code == 200
    invite_doc = invite_response.json()

    register_response = api_client.post(
        f"{BASE_URL}/api/auth/register-with-invite",
        json={
            "full_name": "TEST Unread Member",
            "email": member_email,
            "password": password,
            "invite_code": invite_doc["code"],
        },
        timeout=30,
    )
    assert register_response.status_code == 200
    member_auth = register_response.json()

    return {
        "host": {
            "token": host_auth["token"],
            "user": host_auth["user"],
            "email": host_email,
            "password": password,
        },
        "member": {
            "token": member_auth["token"],
            "user": member_auth["user"],
            "email": member_email,
            "password": password,
        },
    }


def test_recurring_reminders_for_host_and_invited_member(api_client, seeded_context):
    # Create recurring event, invite member, and verify reminder visibility for both host and invitee
    now = datetime.now(timezone.utc)
    start_at = (now + timedelta(days=7)).replace(hour=18, minute=0, second=0, microsecond=0).isoformat()

    create_event_response = api_client.post(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(seeded_context["host"]["token"]),
        json={
            "title": "TEST Recurring RSVP Reminder Event",
            "description": "TEST recurring reminder event",
            "start_at": start_at,
            "location": "TEST Hall",
            "event_template": "reunion",
            "recurrence_frequency": "weekly",
        },
        timeout=30,
    )
    assert create_event_response.status_code == 200
    created_event = create_event_response.json()
    assert created_event["recurrence_frequency"] == "weekly"

    invite_member_response = api_client.post(
        f"{BASE_URL}/api/events/{created_event['id']}/invites",
        headers=_auth_headers(seeded_context["host"]["token"]),
        json={"member_ids": [seeded_context["member"]["user"]["id"]], "guest_emails": [], "note": "TEST reminder"},
        timeout=30,
    )
    assert invite_member_response.status_code == 200
    updated_event = invite_member_response.json()
    assert any(
        invite.get("email", "").lower() == seeded_context["member"]["email"].lower() and invite.get("rsvp_status") == "pending"
        for invite in updated_event.get("event_invites", [])
    )

    host_reminders_response = api_client.get(
        f"{BASE_URL}/api/gatherings/reminders",
        headers=_auth_headers(seeded_context["host"]["token"]),
        timeout=20,
    )
    assert host_reminders_response.status_code == 200
    host_reminders = host_reminders_response.json().get("reminders", [])
    assert any(
        reminder.get("event_id") == created_event["id"] and reminder.get("type") == "invite-reminder"
        for reminder in host_reminders
    )

    member_reminders_response = api_client.get(
        f"{BASE_URL}/api/gatherings/reminders",
        headers=_auth_headers(seeded_context["member"]["token"]),
        timeout=20,
    )
    assert member_reminders_response.status_code == 200
    member_reminders = member_reminders_response.json().get("reminders", [])
    assert any(
        reminder.get("event_id") == created_event["id"] and reminder.get("type") == "invite-reminder"
        for reminder in member_reminders
    )


def test_unread_summary_announcements_and_chat_clear_on_view(api_client, seeded_context):
    # Validate unread counters increase from announcement/chat and clear after viewing list + room detail
    create_announcement_response = api_client.post(
        f"{BASE_URL}/api/announcements",
        headers=_auth_headers(seeded_context["host"]["token"]),
        json={
            "title": "TEST Unread Announcement",
            "body": "TEST unread announcement body",
            "scope": "courtyard",
            "subyard_id": "",
            "attachments": [],
        },
        timeout=20,
    )
    assert create_announcement_response.status_code == 200
    created_announcement = create_announcement_response.json()
    assert created_announcement["title"] == "TEST Unread Announcement"

    rooms_response = api_client.get(
        f"{BASE_URL}/api/chat/rooms",
        headers=_auth_headers(seeded_context["host"]["token"]),
        timeout=20,
    )
    assert rooms_response.status_code == 200
    rooms = rooms_response.json().get("rooms", [])
    assert len(rooms) >= 1
    room_id = rooms[0]["id"]

    create_message_response = api_client.post(
        f"{BASE_URL}/api/chat/rooms/{room_id}/messages",
        headers=_auth_headers(seeded_context["host"]["token"]),
        json={"text": "TEST unread chat message", "attachments": []},
        timeout=20,
    )
    assert create_message_response.status_code == 200
    room_after_message = create_message_response.json()
    assert any(message.get("text") == "TEST unread chat message" for message in room_after_message.get("messages", []))

    member_unread_response = api_client.get(
        f"{BASE_URL}/api/communications/unread-summary",
        headers=_auth_headers(seeded_context["member"]["token"]),
        timeout=20,
    )
    assert member_unread_response.status_code == 200
    unread_before = member_unread_response.json()
    assert unread_before["announcements_unread"] >= 1
    assert unread_before["chat_unread"] >= 1
    assert unread_before["total_unread"] == unread_before["announcements_unread"] + unread_before["chat_unread"]

    view_announcements_response = api_client.get(
        f"{BASE_URL}/api/announcements",
        headers=_auth_headers(seeded_context["member"]["token"]),
        timeout=20,
    )
    assert view_announcements_response.status_code == 200
    announcements_payload = view_announcements_response.json()
    assert announcements_payload["unread_before_view"] >= 1

    unread_after_announcements_response = api_client.get(
        f"{BASE_URL}/api/communications/unread-summary",
        headers=_auth_headers(seeded_context["member"]["token"]),
        timeout=20,
    )
    assert unread_after_announcements_response.status_code == 200
    unread_after_announcements = unread_after_announcements_response.json()
    assert unread_after_announcements["announcements_unread"] == 0
    assert unread_after_announcements["chat_unread"] >= 1

    member_rooms_response = api_client.get(
        f"{BASE_URL}/api/chat/rooms",
        headers=_auth_headers(seeded_context["member"]["token"]),
        timeout=20,
    )
    assert member_rooms_response.status_code == 200
    member_rooms = member_rooms_response.json().get("rooms", [])
    target_room = next((room for room in member_rooms if room.get("unread_count", 0) > 0), None)
    assert target_room is not None

    view_room_response = api_client.get(
        f"{BASE_URL}/api/chat/rooms/{target_room['id']}",
        headers=_auth_headers(seeded_context["member"]["token"]),
        timeout=20,
    )
    assert view_room_response.status_code == 200
    viewed_room = view_room_response.json()
    assert viewed_room["unread_count"] == 0

    unread_after_chat_response = api_client.get(
        f"{BASE_URL}/api/communications/unread-summary",
        headers=_auth_headers(seeded_context["member"]["token"]),
        timeout=20,
    )
    assert unread_after_chat_response.status_code == 200
    unread_after_chat = unread_after_chat_response.json()
    assert unread_after_chat["announcements_unread"] == 0
    assert unread_after_chat["chat_unread"] == 0
    assert unread_after_chat["total_unread"] == 0
