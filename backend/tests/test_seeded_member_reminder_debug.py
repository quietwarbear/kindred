import json
import os
from pathlib import Path

import requests
import pytest
from dotenv import load_dotenv


def test_seeded_member_reminder_debug():
    # Debug check for UI-seeded member reminder payload
    load_dotenv(Path("/app/frontend/.env"))
    seed_path = Path("/app/tests/ui_seed_unread.json")
    if not seed_path.exists():
        pytest.skip("ui_seed_unread.json not found; debug-only check skipped")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    base_url = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    assert base_url

    login_response = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": seed["member"]["email"], "password": seed["member"]["password"]},
        timeout=30,
    )
    assert login_response.status_code == 200
    token = login_response.json()["token"]

    reminders_response = requests.get(
        f"{base_url}/api/gatherings/reminders",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert reminders_response.status_code == 200
    payload = reminders_response.json()
    assert "reminders" in payload
    assert len(payload["reminders"]) >= 1
