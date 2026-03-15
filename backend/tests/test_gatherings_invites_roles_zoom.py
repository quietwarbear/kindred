import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv


# Run against the public preview backend URL used by frontend users.
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
def host_and_member_context(api_client):
    # Auth + seed member used across gatherings invite/role/zoom scenarios.
    suffix = uuid.uuid4().hex[:8]
    host_email = f"test_gath_host_{suffix}@example.com"
    host_password = "SecurePass123!"

    bootstrap_payload = {
        "full_name": "TEST Gatherings Host",
        "email": host_email,
        "password": host_password,
        "community_name": f"TEST Gatherings Community {suffix}",
        "community_type": "family reunion",
        "location": "Chicago, IL",
        "description": "TEST coverage for gatherings invite and roles",
        "motto": "TEST together",
    }
    bootstrap_response = api_client.post(f"{BASE_URL}/api/auth/bootstrap", json=bootstrap_payload, timeout=30)
    assert bootstrap_response.status_code == 200
    bootstrap = bootstrap_response.json()

    member_email = f"test_gath_member_{suffix}@example.com"
    invite_response = api_client.post(
        f"{BASE_URL}/api/invites",
        headers=_auth_headers(bootstrap["token"]),
        json={"email": member_email, "role": "member"},
        timeout=20,
    )
    assert invite_response.status_code == 200
    invite_data = invite_response.json()

    register_response = api_client.post(
        f"{BASE_URL}/api/auth/register-with-invite",
        json={
            "full_name": "TEST Gatherings Member",
            "email": member_email,
            "password": "SecurePass123!",
            "invite_code": invite_data["code"],
        },
        timeout=30,
    )
    assert register_response.status_code == 200
    member_auth = register_response.json()

    return {
        "host_token": bootstrap["token"],
        "host_user": bootstrap["user"],
        "member_token": member_auth["token"],
        "member_user": member_auth["user"],
    }


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_create_hybrid_event_persists_zoom_link(api_client, host_and_member_context):
    # Gatherings create flow: hybrid/online event supports zoom_link.
    create_payload = {
        "title": "TEST Hybrid Prayer Gathering",
        "description": "TEST hybrid gathering with meeting link",
        "start_at": "2026-11-08T18:30:00.000Z",
        "location": "TEST Fellowship Hall",
        "event_template": "reunion",
        "gathering_format": "hybrid",
        "zoom_link": "https://zoom.us/j/987654321",
        "recurrence_frequency": "none",
    }
    create_response = api_client.post(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_and_member_context["host_token"]),
        json=create_payload,
        timeout=30,
    )
    assert create_response.status_code == 200
    created_event = create_response.json()
    assert created_event["gathering_format"] == "hybrid"
    assert created_event["zoom_link"] == create_payload["zoom_link"]

    list_response = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_and_member_context["host_token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    fetched = next(item for item in list_response.json() if item["id"] == created_event["id"])
    assert fetched["zoom_link"] == create_payload["zoom_link"]


def test_event_invites_include_member_guest_zoom_and_share_message(api_client, host_and_member_context):
    # Event invites: existing member + manual guest email with share-ready invite text.
    event_response = api_client.post(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_and_member_context["host_token"]),
        json={
            "title": "TEST Online Bible Study",
            "description": "TEST event invites coverage",
            "start_at": "2026-12-02T01:00:00.000Z",
            "location": "Online",
            "event_template": "custom",
            "gathering_format": "online",
            "zoom_link": "https://zoom.us/j/123123123",
            "recurrence_frequency": "none",
        },
        timeout=30,
    )
    assert event_response.status_code == 200
    event = event_response.json()

    invites_response = api_client.post(
        f"{BASE_URL}/api/events/{event['id']}/invites",
        headers=_auth_headers(host_and_member_context["host_token"]),
        json={
            "member_ids": [host_and_member_context["member_user"]["id"]],
            "guest_emails": [f"guest_{uuid.uuid4().hex[:6]}@example.com"],
            "note": "TEST bring your notes",
        },
        timeout=30,
    )
    assert invites_response.status_code == 200
    updated_event = invites_response.json()
    invites = updated_event["event_invites"]

    assert len(invites) == 2
    assert sorted([item["invite_source"] for item in invites]) == ["guest", "member"]
    assert all(item["delivery_status"] == "ready-for-email" for item in invites)
    assert all(item["zoom_link"] == event["zoom_link"] for item in invites)
    assert all("Join via Zoom:" in item["share_message"] for item in invites)
    assert all(event["zoom_link"] in item["share_message"] for item in invites)

    list_response = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_and_member_context["host_token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    persisted = next(item for item in list_response.json() if item["id"] == event["id"])
    assert len(persisted["event_invites"]) == 2


def test_role_assignment_supports_custom_role_and_multiple_assignees(api_client, host_and_member_context):
    # Event role assignment: existing role + custom role and multiple assignees.
    create_event_response = api_client.post(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_and_member_context["host_token"]),
        json={
            "title": "TEST Role Assignment Event",
            "description": "TEST role assignment flow",
            "start_at": "2026-12-15T16:00:00.000Z",
            "location": "TEST Campus",
            "event_template": "reunion",
            "recurrence_frequency": "none",
        },
        timeout=30,
    )
    assert create_event_response.status_code == 200
    event = create_event_response.json()

    update_existing_role = api_client.post(
        f"{BASE_URL}/api/events/{event['id']}/role-assignments",
        headers=_auth_headers(host_and_member_context["host_token"]),
        json={"role_name": "organizer", "assignees": ["Ava", "Noah"]},
        timeout=20,
    )
    assert update_existing_role.status_code == 200
    existing_payload = update_existing_role.json()
    organizer_assignment = next(
        item for item in existing_payload["event_role_assignments"] if item["role_name"].lower() == "organizer"
    )
    assert organizer_assignment["assignees"] == ["Ava", "Noah"]

    add_custom_role = api_client.post(
        f"{BASE_URL}/api/events/{event['id']}/role-assignments",
        headers=_auth_headers(host_and_member_context["host_token"]),
        json={"role_name": "Zoom Host", "assignees": ["Ava", "Noah", "Mia"]},
        timeout=20,
    )
    assert add_custom_role.status_code == 200
    custom_payload = add_custom_role.json()
    custom_assignment = next(
        item for item in custom_payload["event_role_assignments"] if item["role_name"].lower() == "zoom host"
    )
    assert custom_assignment["assignees"] == ["Ava", "Noah", "Mia"]

    list_response = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_and_member_context["host_token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    fetched = next(item for item in list_response.json() if item["id"] == event["id"])
    persisted_custom = next(
        item for item in fetched["event_role_assignments"] if item["role_name"].lower() == "zoom host"
    )
    assert persisted_custom["assignees"] == ["Ava", "Noah", "Mia"]


def test_recurring_event_still_generates_instances_after_invite_role_changes(api_client, host_and_member_context):
    # Regression: recurring event generation should still create child instances.
    create_response = api_client.post(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_and_member_context["host_token"]),
        json={
            "title": "TEST Weekly Choir Practice",
            "description": "TEST recurrence regression",
            "start_at": "2026-09-03T19:00:00.000Z",
            "location": "TEST Sanctuary",
            "event_template": "custom",
            "gathering_format": "in-person",
            "recurrence_frequency": "weekly",
        },
        timeout=30,
    )
    assert create_response.status_code == 200
    parent = create_response.json()
    assert parent["is_recurring_instance"] is False

    list_response = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(host_and_member_context["host_token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    same_series = [item for item in list_response.json() if item.get("series_id") == parent["series_id"]]
    children = [item for item in same_series if item.get("is_recurring_instance") is True]
    assert len(same_series) == 6
    assert len(children) == 5
