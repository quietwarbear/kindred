import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient


# Run API tests against the same public backend URL used by frontend users.
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required for onboarding API tests")
if not MONGO_URL or not DB_NAME:
    raise RuntimeError("MONGO_URL and DB_NAME are required for onboarding API tests")

BASE_URL = BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_host(api_client, suffix: str):
    payload = {
        "full_name": "TEST Onboarding Host",
        "email": f"test_onboarding_host_{suffix}@example.com",
        "password": "SecurePass123!",
        "community_name": f"TEST Onboarding Circle {suffix}",
        "community_type": "family reunion",
        "location": "Austin, TX",
        "description": "TEST onboarding verification",
        "motto": "TEST together",
    }
    response = api_client.post(f"{BASE_URL}/api/auth/bootstrap", json=payload, timeout=30)
    assert response.status_code == 200
    return response.json()


def _force_google_pending(mongo_db, user_id: str):
    mongo_db.users.update_one(
        {"id": user_id},
        {"$set": {"auth_provider": "google", "onboarding_completed": False}},
    )


def test_google_pending_user_login_returns_expected_onboarding_flags(api_client, mongo_db):
    # Auth regression: login still works and returns Google onboarding flags.
    suffix = uuid.uuid4().hex[:8]
    seeded = _bootstrap_host(api_client, suffix)
    _force_google_pending(mongo_db, seeded["user"]["id"])

    login_response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": seeded["user"]["email"], "password": "SecurePass123!"},
        timeout=20,
    )
    assert login_response.status_code == 200
    login_data = login_response.json()

    assert login_data["user"]["auth_provider"] == "google"
    assert login_data["user"]["onboarding_completed"] is False


def test_onboarding_complete_updates_host_profile_circle_and_starter_resources(api_client, mongo_db):
    # Google onboarding endpoint: host flow updates profile/community/subyard/gathering/invites.
    suffix = uuid.uuid4().hex[:8]
    seeded = _bootstrap_host(api_client, suffix)
    _force_google_pending(mongo_db, seeded["user"]["id"])

    onboarding_payload = {
        "full_name": "TEST Host Finished",
        "nickname": "THF",
        "phone_number": "+1-555-2000",
        "profile_image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
        "community_name": f"TEST Polished Circle {suffix}",
        "community_type": "diaspora",
        "location": "Seattle, WA",
        "motto": "TEST we gather",
        "first_subyard_name": f"TEST Starter Subyard {suffix}",
        "first_subyard_description": "TEST first subyard from onboarding",
        "first_gathering_title": f"TEST Starter Gathering {suffix}",
        "first_gathering_template": "reunion",
        "first_gathering_start_at": "2026-11-12T18:00:00.000Z",
        "first_gathering_location": "TEST Community Hall",
        "invite_emails": [
            f"invite_a_{suffix}@example.com",
            f"invite_b_{suffix}@example.com",
        ],
    }

    complete_response = api_client.post(
        f"{BASE_URL}/api/auth/onboarding/complete",
        headers=_auth_headers(seeded["token"]),
        json=onboarding_payload,
        timeout=40,
    )
    assert complete_response.status_code == 200
    complete_data = complete_response.json()

    assert complete_data["user"]["onboarding_completed"] is True
    assert complete_data["user"]["full_name"] == onboarding_payload["full_name"]
    assert complete_data["community"]["name"] == onboarding_payload["community_name"]
    assert complete_data["community"]["community_type"] == onboarding_payload["community_type"]
    assert complete_data["community"]["location"] == onboarding_payload["location"]
    assert complete_data["community"]["motto"] == onboarding_payload["motto"]

    subyards_response = api_client.get(
        f"{BASE_URL}/api/subyards",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    )
    assert subyards_response.status_code == 200
    subyards = subyards_response.json()["subyards"]
    assert any(item["name"] == onboarding_payload["first_subyard_name"] for item in subyards)

    events_response = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    )
    assert events_response.status_code == 200
    events = events_response.json()
    matching_event = next(item for item in events if item["title"] == onboarding_payload["first_gathering_title"])
    assert matching_event["event_template"] == onboarding_payload["first_gathering_template"]
    assert matching_event["location"] == onboarding_payload["first_gathering_location"]

    invites_response = api_client.get(
        f"{BASE_URL}/api/invites",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    )
    assert invites_response.status_code == 200
    invite_emails = {item["email"] for item in invites_response.json()["invites"]}
    assert onboarding_payload["invite_emails"][0] in invite_emails
    assert onboarding_payload["invite_emails"][1] in invite_emails


def test_member_onboarding_only_updates_profile_not_circle_resources(api_client, mongo_db):
    # Permission behavior: member onboarding should not create circle-level resources.
    suffix = uuid.uuid4().hex[:8]
    seeded = _bootstrap_host(api_client, suffix)

    invite_email = f"member_{suffix}@example.com"
    invite_response = api_client.post(
        f"{BASE_URL}/api/invites",
        headers=_auth_headers(seeded["token"]),
        json={"email": invite_email, "role": "member"},
        timeout=20,
    )
    assert invite_response.status_code == 200
    invite_code = invite_response.json()["code"]

    register_response = api_client.post(
        f"{BASE_URL}/api/auth/register-with-invite",
        json={
            "full_name": "TEST Onboarding Member",
            "email": invite_email,
            "password": "SecurePass123!",
            "invite_code": invite_code,
        },
        timeout=30,
    )
    assert register_response.status_code == 200
    member_auth = register_response.json()

    _force_google_pending(mongo_db, member_auth["user"]["id"])

    before_subyards = api_client.get(
        f"{BASE_URL}/api/subyards",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    ).json()["subyards"]
    before_events = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    ).json()
    before_invites = api_client.get(
        f"{BASE_URL}/api/invites",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    ).json()["invites"]

    onboarding_response = api_client.post(
        f"{BASE_URL}/api/auth/onboarding/complete",
        headers=_auth_headers(member_auth["token"]),
        json={
            "full_name": "TEST Member Onboarded",
            "community_name": f"TEST should-not-change {suffix}",
            "first_subyard_name": f"TEST forbidden subyard {suffix}",
            "first_gathering_title": f"TEST forbidden gathering {suffix}",
            "first_gathering_template": "reunion",
            "first_gathering_start_at": "2026-11-24T18:00:00.000Z",
            "first_gathering_location": "TEST Blocked",
            "invite_emails": [f"should_not_invite_{suffix}@example.com"],
        },
        timeout=30,
    )
    assert onboarding_response.status_code == 200
    onboarding_data = onboarding_response.json()
    assert onboarding_data["user"]["onboarding_completed"] is True
    assert onboarding_data["user"]["full_name"] == "TEST Member Onboarded"

    after_subyards = api_client.get(
        f"{BASE_URL}/api/subyards",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    ).json()["subyards"]
    after_events = api_client.get(
        f"{BASE_URL}/api/events",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    ).json()
    after_invites = api_client.get(
        f"{BASE_URL}/api/invites",
        headers=_auth_headers(seeded["token"]),
        timeout=20,
    ).json()["invites"]

    assert len(after_subyards) == len(before_subyards)
    assert len(after_events) == len(before_events)
    assert len(after_invites) == len(before_invites)


def test_profile_update_still_works_after_onboarding_completion(api_client, mongo_db):
    # Settings regression: profile endpoint remains functional after onboarding completion.
    suffix = uuid.uuid4().hex[:8]
    seeded = _bootstrap_host(api_client, suffix)
    _force_google_pending(mongo_db, seeded["user"]["id"])

    complete_response = api_client.post(
        f"{BASE_URL}/api/auth/onboarding/complete",
        headers=_auth_headers(seeded["token"]),
        json={"full_name": "TEST Host Onboarded"},
        timeout=20,
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["user"]["onboarding_completed"] is True

    update_payload = {
        "full_name": "TEST Host Final",
        "nickname": "Final",
        "phone_number": "+1-555-3333",
        "profile_image_url": "",
    }
    profile_response = api_client.put(
        f"{BASE_URL}/api/auth/profile",
        headers=_auth_headers(seeded["token"]),
        json=update_payload,
        timeout=20,
    )
    assert profile_response.status_code == 200
    profile_data = profile_response.json()
    assert profile_data["full_name"] == update_payload["full_name"]
    assert profile_data["nickname"] == update_payload["nickname"]
    assert profile_data["phone_number"] == update_payload["phone_number"]
