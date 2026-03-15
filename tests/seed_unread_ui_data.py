import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / "frontend" / ".env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required")


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def main():
    suffix = uuid.uuid4().hex[:8]
    host_email = f"test_ui_host_{suffix}@example.com"
    member_email = f"test_ui_member_{suffix}@example.com"
    password = "SecurePass123!"

    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})

    bootstrap = s.post(
        f"{BASE_URL}/api/auth/bootstrap",
        json={
            "full_name": "TEST UI Host",
            "email": host_email,
            "password": password,
            "community_name": f"TEST UI Courtyard {suffix}",
            "community_type": "family reunion",
            "location": "Atlanta, GA",
            "description": "TEST seed for UI unread badge validation",
            "motto": "TEST all together",
        },
        timeout=30,
    )
    bootstrap.raise_for_status()
    host_auth = bootstrap.json()

    invite_resp = s.post(
        f"{BASE_URL}/api/invites",
        headers=auth_headers(host_auth["token"]),
        json={"email": member_email, "role": "member"},
        timeout=20,
    )
    invite_resp.raise_for_status()
    invite_code = invite_resp.json()["code"]

    register_resp = s.post(
        f"{BASE_URL}/api/auth/register-with-invite",
        json={
            "full_name": "TEST UI Member",
            "email": member_email,
            "password": password,
            "invite_code": invite_code,
        },
        timeout=30,
    )
    register_resp.raise_for_status()
    member_auth = register_resp.json()

    now = datetime.now(timezone.utc)
    start_at = (now + timedelta(days=5)).replace(hour=17, minute=30, second=0, microsecond=0).isoformat()

    event_resp = s.post(
        f"{BASE_URL}/api/events",
        headers=auth_headers(host_auth["token"]),
        json={
            "title": "TEST UI Recurring Reminder Event",
            "description": "TEST reminder visibility",
            "start_at": start_at,
            "location": "Community Hall",
            "event_template": "reunion",
            "recurrence_frequency": "weekly",
            "gathering_format": "in-person",
        },
        timeout=30,
    )
    event_resp.raise_for_status()
    event_doc = event_resp.json()

    invites_resp = s.post(
        f"{BASE_URL}/api/events/{event_doc['id']}/invites",
        headers=auth_headers(host_auth["token"]),
        json={"member_ids": [member_auth["user"]["id"]], "guest_emails": [], "note": "Please RSVP"},
        timeout=20,
    )
    invites_resp.raise_for_status()

    announce_resp = s.post(
        f"{BASE_URL}/api/announcements",
        headers=auth_headers(host_auth["token"]),
        json={
            "title": "TEST UI Announcement",
            "body": "Unread announcement for member",
            "scope": "courtyard",
            "subyard_id": "",
            "attachments": [],
        },
        timeout=20,
    )
    announce_resp.raise_for_status()

    rooms_resp = s.get(f"{BASE_URL}/api/chat/rooms", headers=auth_headers(host_auth["token"]), timeout=20)
    rooms_resp.raise_for_status()
    room_id = rooms_resp.json()["rooms"][0]["id"]

    message_resp = s.post(
        f"{BASE_URL}/api/chat/rooms/{room_id}/messages",
        headers=auth_headers(host_auth["token"]),
        json={"text": "TEST UI unread chat message", "attachments": []},
        timeout=20,
    )
    message_resp.raise_for_status()

    output = {
        "host": {"email": host_email, "password": password},
        "member": {"email": member_email, "password": password},
        "event_id": event_doc["id"],
        "room_id": room_id,
    }

    out_path = Path(__file__).resolve().parent / "ui_seed_unread.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output))


if __name__ == "__main__":
    main()
