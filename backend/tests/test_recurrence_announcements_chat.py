import os
import uuid
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


@pytest.fixture(scope="session")
def host_context(api_client):
    # Auth + base seed for recurrence/announcement/chat feature tests
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "full_name": "TEST Host Recurrence",
        "email": f"test_recur_host_{suffix}@example.com",
        "password": "SecurePass123!",
        "community_name": f"TEST Recurrence Courtyard {suffix}",
        "community_type": "family reunion",
        "location": "Houston, TX",
        "description": "TEST community for recurrence and chat coverage",
        "motto": "TEST together",
    }
    bootstrap = api_client.post(f"{BASE_URL}/api/auth/bootstrap", json=payload, timeout=30)
    assert bootstrap.status_code == 200
    auth = bootstrap.json()
    return {
        "token": auth["token"],
        "user": auth["user"],
    }


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_create_weekly_recurring_event_generates_instances(api_client, host_context):
    # Recurring event creation + generated child instances
    create_payload = {
        "title": "TEST Weekly Prayer Circle",
        "description": "TEST recurring event",
        "start_at": "2026-08-01T14:30:00.000Z",
        "location": "TEST Hall A",
        "event_template": "reunion",
        "recurrence_frequency": "weekly",
    }
    create_response = api_client.post(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_context["token"]),
        json=create_payload,
        timeout=30,
    )
    assert create_response.status_code == 200
    parent_event = create_response.json()
    assert parent_event["is_recurring_instance"] is False
    assert parent_event["recurrence_frequency"] == "weekly"
    assert isinstance(parent_event.get("series_id"), str) and len(parent_event["series_id"]) > 0

    list_response = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_context["token"]),
        timeout=30,
    )
    assert list_response.status_code == 200
    events = list_response.json()
    same_series = [event for event in events if event.get("series_id") == parent_event["series_id"]]
    children = [event for event in same_series if event.get("is_recurring_instance") is True]

    assert len(same_series) == 6
    assert len(children) == 5
    assert all(child.get("parent_event_id") == parent_event["id"] for child in children)


def test_announcement_with_attachment_and_comment(api_client, host_context):
    # Announcement create with attachment + comment flow
    structure = api_client.get(
        f"{BASE_URL}/api/courtyard/structure",
        headers=_auth_headers(host_context["token"]),
        timeout=20,
    )
    assert structure.status_code == 200
    subyards = structure.json().get("subyards", [])
    assert len(subyards) >= 1

    create_payload = {
        "title": "TEST Subyard Bulletin",
        "body": "TEST bulletin body",
        "scope": "subyard",
        "subyard_id": subyards[0]["id"],
        "attachments": [
            {
                "name": "bulletin.txt",
                "mime_type": "text/plain",
                "data_url": "data:text/plain;base64,VEVTVCBhbm5vdW5jZW1lbnQ=",
            }
        ],
    }
    create_response = api_client.post(
        f"{BASE_URL}/api/announcements",
        headers=_auth_headers(host_context["token"]),
        json=create_payload,
        timeout=20,
    )
    assert create_response.status_code == 200
    announcement = create_response.json()
    assert announcement["scope"] == "subyard"
    assert announcement["subyard_id"] == subyards[0]["id"]
    assert announcement["attachments"][0]["name"] == "bulletin.txt"

    comment_response = api_client.post(
        f"{BASE_URL}/api/announcements/{announcement['id']}/comments",
        headers=_auth_headers(host_context["token"]),
        json={"text": "TEST announcement comment"},
        timeout=20,
    )
    assert comment_response.status_code == 200
    commented = comment_response.json()
    assert any(comment["text"] == "TEST announcement comment" for comment in commented["comments"])


def test_chat_room_send_attachment_pin_and_comment(api_client, host_context):
    # Internal chat: list rooms + send + pin/unpin + comment
    rooms_response = api_client.get(
        f"{BASE_URL}/api/chat/rooms",
        headers=_auth_headers(host_context["token"]),
        timeout=20,
    )
    assert rooms_response.status_code == 200
    rooms = rooms_response.json().get("rooms", [])
    assert len(rooms) >= 2

    room = rooms[0]
    message_payload = {
        "text": "TEST chat message",
        "attachments": [
            {
                "name": "chat-note.txt",
                "mime_type": "text/plain",
                "data_url": "data:text/plain;base64,VEVTVCBjaGF0IGZpbGU=",
            }
        ],
    }
    message_response = api_client.post(
        f"{BASE_URL}/api/chat/rooms/{room['id']}/messages",
        headers=_auth_headers(host_context["token"]),
        json=message_payload,
        timeout=20,
    )
    assert message_response.status_code == 200
    updated_room = message_response.json()
    created_message = next(msg for msg in updated_room["messages"] if msg["text"] == "TEST chat message")
    assert created_message["attachments"][0]["name"] == "chat-note.txt"

    pin_response = api_client.post(
        f"{BASE_URL}/api/chat/rooms/{room['id']}/messages/{created_message['id']}/pin",
        headers=_auth_headers(host_context["token"]),
        timeout=20,
    )
    assert pin_response.status_code == 200
    pinned_room = pin_response.json()
    pinned_message = next(msg for msg in pinned_room["messages"] if msg["id"] == created_message["id"])
    assert pinned_message["is_pinned"] is True

    unpin_response = api_client.post(
        f"{BASE_URL}/api/chat/rooms/{room['id']}/messages/{created_message['id']}/pin",
        headers=_auth_headers(host_context["token"]),
        timeout=20,
    )
    assert unpin_response.status_code == 200
    unpinned_room = unpin_response.json()
    unpinned_message = next(msg for msg in unpinned_room["messages"] if msg["id"] == created_message["id"])
    assert unpinned_message["is_pinned"] is False

    comment_response = api_client.post(
        f"{BASE_URL}/api/chat/rooms/{room['id']}/messages/{created_message['id']}/comments",
        headers=_auth_headers(host_context["token"]),
        json={"text": "TEST chat reply"},
        timeout=20,
    )
    assert comment_response.status_code == 200
    commented_room = comment_response.json()
    commented_message = next(msg for msg in commented_room["messages"] if msg["id"] == created_message["id"])
    assert any(comment["text"] == "TEST chat reply" for comment in commented_message["comments"])
