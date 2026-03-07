import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv


# Load frontend env so tests run against public URL used by end users
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
def test_context(api_client):
    # Auth + seed context for cross-feature integration tests
    suffix = uuid.uuid4().hex[:8]
    host_email = f"test_host_{suffix}@example.com"
    host_password = "SecurePass123!"

    bootstrap_payload = {
        "full_name": "TEST Host",
        "email": host_email,
        "password": host_password,
        "community_name": f"TEST Community {suffix}",
        "community_type": "family reunion",
        "location": "Atlanta, GA",
        "description": "TEST private community for integration testing",
        "motto": "TEST together",
    }
    bootstrap_response = api_client.post(f"{BASE_URL}/api/auth/bootstrap", json=bootstrap_payload, timeout=30)
    assert bootstrap_response.status_code == 200
    bootstrap_data = bootstrap_response.json()

    return {
        "host_email": host_email,
        "host_password": host_password,
        "host_token": bootstrap_data["token"],
        "host_user": bootstrap_data["user"],
        "community": bootstrap_data["community"],
    }


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_api_root_health(api_client):
    # Health check endpoint
    response = api_client.get(f"{BASE_URL}/api/", timeout=20)
    assert response.status_code == 200
    assert response.json()["message"] == "Gathering Cypher API is ready."


def test_auth_bootstrap_context(test_context):
    # Bootstrap response data assertions
    assert isinstance(test_context["host_token"], str)
    assert len(test_context["host_token"]) > 20
    assert test_context["host_user"]["role"] == "host"
    assert test_context["community"]["owner_user_id"] == test_context["host_user"]["id"]


def test_auth_login_and_me(api_client, test_context):
    # Login + auth/me persistence verification
    login_response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": test_context["host_email"], "password": test_context["host_password"]},
        timeout=20,
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data["user"]["email"] == test_context["host_email"]

    me_response = api_client.get(
        f"{BASE_URL}/api/auth/me",
        headers=_auth_headers(login_data["token"]),
        timeout=20,
    )
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["community"]["id"] == test_context["community"]["id"]
    assert me_data["user"]["id"] == test_context["host_user"]["id"]


def test_members_and_invites_flow(api_client, test_context):
    # Members + invites CRUD-lite
    invite_email = f"test_member_{uuid.uuid4().hex[:8]}@example.com"
    invite_response = api_client.post(
        f"{BASE_URL}/api/invites",
        headers=_auth_headers(test_context["host_token"]),
        json={"email": invite_email, "role": "member"},
        timeout=20,
    )
    assert invite_response.status_code == 200
    invite_data = invite_response.json()
    assert invite_data["email"] == invite_email
    assert invite_data["status"] == "pending"

    list_response = api_client.get(
        f"{BASE_URL}/api/invites",
        headers=_auth_headers(test_context["host_token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    list_data = list_response.json()["invites"]
    assert any(invite["id"] == invite_data["id"] for invite in list_data)

    register_payload = {
        "full_name": "TEST Member",
        "email": invite_email,
        "password": "SecurePass123!",
        "invite_code": invite_data["code"],
    }
    register_response = api_client.post(
        f"{BASE_URL}/api/auth/register-with-invite",
        json=register_payload,
        timeout=20,
    )
    assert register_response.status_code == 200
    register_data = register_response.json()
    assert register_data["user"]["role"] == "member"

    test_context["member_token"] = register_data["token"]
    test_context["member_user"] = register_data["user"]

    members_response = api_client.get(
        f"{BASE_URL}/api/community/members",
        headers=_auth_headers(test_context["host_token"]),
        timeout=20,
    )
    assert members_response.status_code == 200
    members = members_response.json()["members"]
    assert any(member["email"] == invite_email for member in members)


def test_events_hub_end_to_end(api_client, test_context):
    # Events Hub: create + RSVP + agenda + volunteer + potluck
    create_event_payload = {
        "title": "TEST Reunion Service",
        "description": "TEST event description",
        "start_at": "2026-12-24T15:00:00.000Z",
        "location": "TEST Hall",
        "map_url": "",
        "event_template": "family-reunion",
        "special_focus": "TEST ancestral roll call",
    }
    create_response = api_client.post(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(test_context["host_token"]),
        json=create_event_payload,
        timeout=20,
    )
    assert create_response.status_code == 200
    event_data = create_response.json()
    assert event_data["title"] == create_event_payload["title"]
    test_context["event_id"] = event_data["id"]

    list_response = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(test_context["host_token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    events = list_response.json()
    assert any(event["id"] == event_data["id"] for event in events)

    rsvp_response = api_client.post(
        f"{BASE_URL}/api/events/{event_data['id']}/rsvp",
        headers=_auth_headers(test_context["member_token"]),
        json={"status": "going", "guests": 2},
        timeout=20,
    )
    assert rsvp_response.status_code == 200
    rsvp_data = rsvp_response.json()
    assert any(record["user_id"] == test_context["member_user"]["id"] for record in rsvp_data["rsvp_records"])

    agenda_response = api_client.post(
        f"{BASE_URL}/api/events/{event_data['id']}/agenda",
        headers=_auth_headers(test_context["host_token"]),
        json={"time_label": "3:30 PM", "title": "TEST Welcome", "notes": "TEST Notes"},
        timeout=20,
    )
    assert agenda_response.status_code == 200
    agenda_data = agenda_response.json()
    assert any(item["title"] == "TEST Welcome" for item in agenda_data["agenda"])

    slot_response = api_client.post(
        f"{BASE_URL}/api/events/{event_data['id']}/volunteer-slots",
        headers=_auth_headers(test_context["host_token"]),
        json={"title": "TEST Greeters", "needed_count": 2},
        timeout=20,
    )
    assert slot_response.status_code == 200
    slot_data = slot_response.json()
    created_slot = next(slot for slot in slot_data["volunteer_slots"] if slot["title"] == "TEST Greeters")

    signup_response = api_client.post(
        f"{BASE_URL}/api/events/{event_data['id']}/volunteer-signup",
        headers=_auth_headers(test_context["member_token"]),
        json={"slot_id": created_slot["id"]},
        timeout=20,
    )
    assert signup_response.status_code == 200
    signup_data = signup_response.json()
    updated_slot = next(slot for slot in signup_data["volunteer_slots"] if slot["id"] == created_slot["id"])
    assert test_context["member_user"]["full_name"] in updated_slot["assigned_members"]

    potluck_response = api_client.post(
        f"{BASE_URL}/api/events/{event_data['id']}/potluck-items",
        headers=_auth_headers(test_context["host_token"]),
        json={"item_name": "TEST Peach Cobbler"},
        timeout=20,
    )
    assert potluck_response.status_code == 200
    potluck_data = potluck_response.json()
    created_item = next(item for item in potluck_data["potluck_items"] if item["item_name"] == "TEST Peach Cobbler")

    claim_response = api_client.post(
        f"{BASE_URL}/api/events/{event_data['id']}/potluck-claim",
        headers=_auth_headers(test_context["member_token"]),
        json={"item_id": created_item["id"]},
        timeout=20,
    )
    assert claim_response.status_code == 200
    claim_data = claim_response.json()
    claimed_item = next(item for item in claim_data["potluck_items"] if item["id"] == created_item["id"])
    assert claimed_item["assigned_to"] == test_context["member_user"]["full_name"]


def test_memory_vault_create_ai_tags_and_comment(api_client, test_context):
    # Memory Vault: create + list + comment
    create_memory_payload = {
        "event_id": test_context["event_id"],
        "title": "TEST Reunion Prayer Circle",
        "description": "TEST memory about prayer and family testimonies",
    }
    create_response = api_client.post(
        f"{BASE_URL}/api/memories",
        headers=_auth_headers(test_context["host_token"]),
        json=create_memory_payload,
        timeout=40,
    )
    assert create_response.status_code == 200
    memory_data = create_response.json()
    assert memory_data["title"] == create_memory_payload["title"]
    assert isinstance(memory_data["tags"], list)
    assert len(memory_data["tags"]) >= 1
    assert isinstance(memory_data["ai_summary"], str)
    test_context["memory_id"] = memory_data["id"]

    list_response = api_client.get(
        f"{BASE_URL}/api/memories",
        headers=_auth_headers(test_context["host_token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    memories = list_response.json()
    assert any(memory["id"] == memory_data["id"] for memory in memories)

    comment_response = api_client.post(
        f"{BASE_URL}/api/memories/{memory_data['id']}/comments",
        headers=_auth_headers(test_context["member_token"]),
        json={"text": "TEST memory comment"},
        timeout=20,
    )
    assert comment_response.status_code == 200
    comment_data = comment_response.json()
    assert any(comment["text"] == "TEST memory comment" for comment in comment_data["comments"])


def test_legacy_threads_create_and_comment(api_client, test_context):
    # Legacy Threads: create + list + comments
    create_thread_payload = {
        "title": "TEST Elder Reflection",
        "category": "oral-history",
        "body": "TEST oral history thread body",
        "elder_name": "TEST Elder",
    }
    create_response = api_client.post(
        f"{BASE_URL}/api/threads",
        headers=_auth_headers(test_context["host_token"]),
        json=create_thread_payload,
        timeout=20,
    )
    assert create_response.status_code == 200
    thread_data = create_response.json()
    assert thread_data["title"] == create_thread_payload["title"]

    list_response = api_client.get(
        f"{BASE_URL}/api/threads",
        headers=_auth_headers(test_context["host_token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    threads = list_response.json()
    assert any(thread["id"] == thread_data["id"] for thread in threads)

    comment_response = api_client.post(
        f"{BASE_URL}/api/threads/{thread_data['id']}/comments",
        headers=_auth_headers(test_context["member_token"]),
        json={"text": "TEST thread reply"},
        timeout=20,
    )
    assert comment_response.status_code == 200
    comment_data = comment_response.json()
    assert any(comment["text"] == "TEST thread reply" for comment in comment_data["comments"])


def test_contributions_summary_and_checkout_init(api_client, test_context):
    # Contributions: summary + checkout session creation
    summary_response = api_client.get(
        f"{BASE_URL}/api/payments/summary",
        headers=_auth_headers(test_context["host_token"]),
        timeout=20,
    )
    assert summary_response.status_code == 200
    summary_data = summary_response.json()
    assert len(summary_data["packages"]) >= 1

    checkout_response = api_client.post(
        f"{BASE_URL}/api/payments/checkout/session",
        headers=_auth_headers(test_context["host_token"]),
        json={"package_id": summary_data["packages"][0]["id"], "origin_url": BASE_URL},
        timeout=30,
    )
    assert checkout_response.status_code == 200
    checkout_data = checkout_response.json()
    assert isinstance(checkout_data["session_id"], str)
    assert checkout_data["url"].startswith("http")

    summary_after_response = api_client.get(
        f"{BASE_URL}/api/payments/summary",
        headers=_auth_headers(test_context["host_token"]),
        timeout=20,
    )
    assert summary_after_response.status_code == 200
    transactions = summary_after_response.json()["transactions"]
    assert any(txn["session_id"] == checkout_data["session_id"] for txn in transactions)
