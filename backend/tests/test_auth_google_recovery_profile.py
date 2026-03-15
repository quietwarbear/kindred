import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv


# Run tests against the public preview URL used by frontend users.
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
    # Auth seed fixture for login, password recovery, profile, and session tests.
    suffix = uuid.uuid4().hex[:8]
    host_email = f"test_auth_host_{suffix}@example.com"
    host_password = "SecurePass123!"

    bootstrap_payload = {
        "full_name": "TEST Auth Host",
        "email": host_email,
        "password": host_password,
        "community_name": f"TEST Auth Community {suffix}",
        "community_type": "family reunion",
        "location": "Nashville, TN",
        "description": "TEST auth profile recovery coverage",
        "motto": "TEST together",
    }
    bootstrap_response = api_client.post(f"{BASE_URL}/api/auth/bootstrap", json=bootstrap_payload, timeout=30)
    assert bootstrap_response.status_code == 200
    bootstrap_data = bootstrap_response.json()

    return {
        "email": host_email,
        "password": host_password,
        "token": bootstrap_data["token"],
        "user": bootstrap_data["user"],
        "community": bootstrap_data["community"],
    }


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_login_still_works_after_google_path_added(api_client, host_context):
    # Email/password regression coverage.
    login_response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": host_context["email"], "password": host_context["password"]},
        timeout=20,
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data["user"]["email"] == host_context["email"]
    assert login_data["community"]["id"] == host_context["community"]["id"]


def test_auth_me_accepts_bearer_token(api_client, host_context):
    # Session API coverage using Authorization header.
    me_response = api_client.get(
        f"{BASE_URL}/api/auth/me",
        headers=_auth_headers(host_context["token"]),
        timeout=20,
    )
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["user"]["id"] == host_context["user"]["id"]
    assert me_data["community"]["id"] == host_context["community"]["id"]


def test_google_session_invalid_id_returns_error_without_crashing(api_client):
    # Google callback/session exchange error-path coverage.
    response = api_client.post(
        f"{BASE_URL}/api/auth/google/session",
        json={"session_id": "invalid-session-id-for-test"},
        timeout=30,
    )
    assert response.status_code in [400, 401]
    detail = response.json().get("detail", "")
    assert "Google session" in detail or "validate Google session" in detail


def test_password_recovery_request_returns_connection_ready_for_existing_user(api_client, host_context):
    # Password recovery request flow in connection-ready mode.
    response = api_client.post(
        f"{BASE_URL}/api/auth/password-recovery/request",
        json={"email": host_context["email"]},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["delivery_status"] in ["connection-ready", "email-sent"]


def test_password_recovery_request_is_silent_for_unknown_email(api_client):
    # Password recovery privacy behavior for unknown email addresses.
    response = api_client.post(
        f"{BASE_URL}/api/auth/password-recovery/request",
        json={"email": f"unknown_{uuid.uuid4().hex[:8]}@example.com"},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["delivery_status"] == "silent"


def test_password_recovery_verify_requires_prior_request(api_client):
    # Password recovery verify error handling for missing reset request.
    email = f"norequest_{uuid.uuid4().hex[:8]}@example.com"
    response = api_client.post(
        f"{BASE_URL}/api/auth/password-recovery/verify",
        json={"email": email, "code": "123456", "new_password": "AnotherPass123!"},
        timeout=20,
    )
    assert response.status_code == 404
    assert "No recovery request found" in response.json().get("detail", "")


def test_profile_update_persists_name_nickname_phone_and_avatar(api_client, host_context):
    # Profile update persistence coverage for settings profile section.
    update_payload = {
        "full_name": "TEST Auth Host Updated",
        "nickname": "Hosty",
        "phone_number": "+1-555-1200",
        "profile_image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
    }
    update_response = api_client.put(
        f"{BASE_URL}/api/auth/profile",
        headers=_auth_headers(host_context["token"]),
        json=update_payload,
        timeout=20,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["full_name"] == update_payload["full_name"]
    assert updated["nickname"] == update_payload["nickname"]
    assert updated["phone_number"] == update_payload["phone_number"]
    assert updated["profile_image_url"] == update_payload["profile_image_url"]

    me_response = api_client.get(
        f"{BASE_URL}/api/auth/me",
        headers=_auth_headers(host_context["token"]),
        timeout=20,
    )
    assert me_response.status_code == 200
    me_user = me_response.json()["user"]
    assert me_user["full_name"] == update_payload["full_name"]
    assert me_user["nickname"] == update_payload["nickname"]
    assert me_user["phone_number"] == update_payload["phone_number"]
