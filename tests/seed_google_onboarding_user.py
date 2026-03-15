import json
import os
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "frontend" / ".env")
load_dotenv(ROOT / "backend" / ".env")

base_url = os.environ.get("REACT_APP_BACKEND_URL")
mongo_url = os.environ.get("MONGO_URL")
db_name = os.environ.get("DB_NAME")

if not base_url or not mongo_url or not db_name:
    raise RuntimeError("REACT_APP_BACKEND_URL, MONGO_URL and DB_NAME are required")

base_url = base_url.rstrip("/")
suffix = uuid.uuid4().hex[:8]
email = f"ui_google_onboarding_{suffix}@example.com"
password = "SecurePass123!"

bootstrap_payload = {
    "full_name": "UI Google Pending Host",
    "email": email,
    "password": password,
    "community_name": f"UI Circle {suffix}",
    "community_type": "family reunion",
    "location": "Denver, CO",
    "description": "UI onboarding e2e setup",
    "motto": "UI Together",
}

bootstrap_res = requests.post(f"{base_url}/api/auth/bootstrap", json=bootstrap_payload, timeout=30)
bootstrap_res.raise_for_status()
bootstrap = bootstrap_res.json()

mongo_client = MongoClient(mongo_url)
db = mongo_client[db_name]
db.users.update_one(
    {"id": bootstrap["user"]["id"]},
    {"$set": {"auth_provider": "google", "onboarding_completed": False}},
)
mongo_client.close()

output = {
    "email": email,
    "password": password,
    "community_name": bootstrap["community"]["name"],
}

print(json.dumps(output))
