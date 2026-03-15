"""Database connection and collection references."""

import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

users_collection = db.users
communities_collection = db.communities
invites_collection = db.invites
user_sessions_collection = db.user_sessions
password_resets_collection = db.password_resets
subyards_collection = db.subyards
kinships_collection = db.kinship_relationships
events_collection = db.events
memories_collection = db.memories
threads_collection = db.threads
payments_collection = db.payment_transactions
travel_plans_collection = db.travel_plans
budget_plans_collection = db.budget_plans
legacy_table_collection = db.legacy_table_configs
announcements_collection = db.announcements
chat_rooms_collection = db.chat_rooms
notification_events_collection = db.notification_events
notification_preferences_collection = db.notification_preferences
polls_collection = db.polls
