"""Synthetic regressions for provider-neutral consumer activation."""

from __future__ import annotations

import os
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_consumer_activation_unit")
os.environ.setdefault("JWT_SECRET", "synthetic-consumer-activation-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import GoogleOnboardingRequest  # noqa: E402
from routes import auth  # noqa: E402


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, branch) for branch in expected):
                return False
            continue
        if isinstance(expected, dict) and "$exists" in expected:
            if (key in document) is not expected["$exists"]:
                return False
            continue
        if document.get(key) != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, documents=()):
        self.documents = [deepcopy(document) for document in documents]

    async def find_one(self, query, _projection=None):
        return next(
            (
                deepcopy(document)
                for document in self.documents
                if _matches(document, query)
            ),
            None,
        )

    async def insert_one(self, document):
        self.documents.append(deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("id"))

    async def insert_many(self, documents):
        self.documents.extend(deepcopy(list(documents)))
        return SimpleNamespace(inserted_ids=[item.get("id") for item in documents])

    async def update_one(self, query, update, upsert=False):
        document = next(
            (item for item in self.documents if _matches(item, query)),
            None,
        )
        if document is None and upsert:
            document = {}
            self.documents.append(document)
        if document is None:
            return SimpleNamespace(matched_count=0, modified_count=0)
        for key, value in update.get("$set", {}).items():
            document[key] = deepcopy(value)
        for key, value in update.get("$addToSet", {}).items():
            values = document.setdefault(key, [])
            if value not in values:
                values.append(deepcopy(value))
        return SimpleNamespace(matched_count=1, modified_count=1)

    async def delete_one(self, query):
        before = len(self.documents)
        self.documents = [
            document for document in self.documents if not _matches(document, query)
        ]
        return SimpleNamespace(deleted_count=before - len(self.documents))


@pytest.fixture
def synthetic_store(monkeypatch):
    users = FakeCollection()
    communities = FakeCollection()
    invites = FakeCollection()
    sessions = FakeCollection()

    monkeypatch.setattr(auth, "users_collection", users)
    monkeypatch.setattr(auth, "communities_collection", communities)
    monkeypatch.setattr(auth, "invites_collection", invites)
    monkeypatch.setattr(auth, "user_sessions_collection", sessions)
    monkeypatch.setattr(auth, "apply_session_cookie", lambda *_args: None)

    async def no_op(*_args, **_kwargs):
        return None

    async def get_community_for_user(user):
        community = await communities.find_one(
            {"id": user.get("community_id", "")}, {"_id": 0}
        )
        if not community:
            raise HTTPException(status_code=404, detail="Community not found.")
        return community

    monkeypatch.setattr(auth, "ensure_chat_rooms_for_community", no_op)
    monkeypatch.setattr(auth, "enforce_member_limit", no_op)
    monkeypatch.setattr(auth, "get_community_for_user", get_community_for_user)
    return SimpleNamespace(
        users=users,
        communities=communities,
        invites=invites,
        sessions=sessions,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "apple"])
async def test_social_sign_in_does_not_create_an_empty_community(
    synthetic_store,
    provider,
):
    payload = await auth._build_google_auth_response(
        {
            "email": f"new-{provider}@example.invalid",
            "name": "Synthetic Organizer",
            "picture": "",
        },
        Response(),
        provider=provider,
    )

    assert payload["community"] is None
    assert payload["user"]["community_id"] == ""
    assert payload["user"]["community_ids"] == []
    assert payload["user"]["role"] == "member"
    assert payload["user"]["onboarding_completed"] is False
    assert len(synthetic_store.users.documents) == 1
    assert synthetic_store.communities.documents == []


@pytest.mark.asyncio
async def test_pending_invitation_joins_without_organizer_setup(synthetic_store):
    synthetic_store.communities.documents.append(
        {
            "id": "synthetic-community",
            "name": "Synthetic Family",
            "owner_user_id": "synthetic-owner",
        }
    )
    synthetic_store.invites.documents.append(
        {
            "id": "synthetic-invite",
            "email": "invited@example.invalid",
            "role": "member",
            "community_id": "synthetic-community",
            "status": "pending",
        }
    )

    payload = await auth._build_google_auth_response(
        {
            "email": "Invited@Example.Invalid",
            "name": "Synthetic Invitee",
            "picture": "",
        },
        Response(),
        provider="apple",
    )

    assert payload["community"]["id"] == "synthetic-community"
    assert payload["user"]["community_id"] == "synthetic-community"
    assert payload["user"]["community_ids"] == ["synthetic-community"]
    assert payload["user"]["role"] == "member"
    assert payload["user"]["onboarding_completed"] is True
    assert synthetic_store.invites.documents[0]["status"] == "accepted"


@pytest.mark.asyncio
async def test_confirmed_organizer_activation_is_idempotent(synthetic_store):
    user = {
        "id": "synthetic-user",
        "email": "organizer@example.invalid",
        "full_name": "Synthetic Organizer",
        "role": "member",
        "community_id": "",
        "community_ids": [],
        "auth_provider": "google",
        "onboarding_completed": False,
    }
    synthetic_store.users.documents.append(deepcopy(user))
    request = GoogleOnboardingRequest(
        full_name="Synthetic Organizer",
        community_name="Synthetic Reunion Family",
        community_type="family reunion",
        location="Example City",
    )

    claimed_user, first_community = await auth._ensure_confirmed_organizer_community(
        request,
        user,
    )
    retry_user, retry_community = await auth._ensure_confirmed_organizer_community(
        request,
        claimed_user,
    )

    assert claimed_user["role"] == "host"
    assert claimed_user["community_id"] == first_community["id"]
    assert claimed_user["community_ids"] == [first_community["id"]]
    assert retry_user["community_id"] == first_community["id"]
    assert retry_community["id"] == first_community["id"]
    assert len(synthetic_store.communities.documents) == 1
    assert (
        synthetic_store.communities.documents[0]["_id"]
        == synthetic_store.communities.documents[0]["id"]
    )


@pytest.mark.asyncio
async def test_missing_organizer_intent_leaves_zero_communities(synthetic_store):
    user = {
        "id": "synthetic-user",
        "email": "organizer@example.invalid",
        "full_name": "Synthetic Organizer",
        "role": "member",
        "community_id": "",
        "community_ids": [],
        "auth_provider": "google",
        "onboarding_completed": False,
    }
    synthetic_store.users.documents.append(deepcopy(user))

    with pytest.raises(HTTPException) as raised:
        await auth._ensure_confirmed_organizer_community(
            GoogleOnboardingRequest(community_name=""),
            user,
        )

    assert raised.value.status_code == 400
    assert synthetic_store.communities.documents == []
    assert synthetic_store.users.documents[0]["community_id"] == ""


@pytest.mark.asyncio
async def test_existing_deterministic_community_must_belong_to_same_account(
    synthetic_store,
):
    user = {
        "id": "synthetic-user",
        "email": "organizer@example.invalid",
        "full_name": "Synthetic Organizer",
        "role": "member",
        "community_id": "",
        "community_ids": [],
        "auth_provider": "apple",
        "onboarding_completed": False,
    }
    community_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"kindred-organizer:{user['id']}")
    )
    synthetic_store.users.documents.append(deepcopy(user))
    synthetic_store.communities.documents.append(
        {
            "_id": community_id,
            "id": community_id,
            "name": "Unrelated synthetic community",
            "owner_user_id": "different-synthetic-owner",
        }
    )

    with pytest.raises(HTTPException) as raised:
        await auth._ensure_confirmed_organizer_community(
            GoogleOnboardingRequest(community_name="Synthetic Reunion Family"),
            user,
        )

    assert raised.value.status_code == 409
    assert synthetic_store.users.documents[0]["community_id"] == ""
    assert len(synthetic_store.communities.documents) == 1


@pytest.mark.asyncio
async def test_concurrent_community_claim_fails_closed_and_removes_orphan(
    synthetic_store,
):
    stale_user = {
        "id": "synthetic-user",
        "email": "organizer@example.invalid",
        "full_name": "Synthetic Organizer",
        "role": "member",
        "community_id": "",
        "community_ids": [],
        "auth_provider": "google",
        "onboarding_completed": False,
    }
    synthetic_store.users.documents.append(
        {
            **deepcopy(stale_user),
            "community_id": "concurrently-joined-community",
            "community_ids": ["concurrently-joined-community"],
        }
    )

    with pytest.raises(HTTPException) as raised:
        await auth._ensure_confirmed_organizer_community(
            GoogleOnboardingRequest(
                community_name="Synthetic Reunion Family",
                community_type="family reunion",
            ),
            stale_user,
        )

    assert raised.value.status_code == 409
    assert synthetic_store.communities.documents == []
    assert (
        synthetic_store.users.documents[0]["community_id"]
        == "concurrently-joined-community"
    )
