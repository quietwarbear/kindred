"""Focused synthetic Release 11 privacy and fail-closed tests."""

import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_release11_unit")

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from dependencies import GATHERING_TEMPLATES
from legacy_table_sync import APPROVED_API_ORIGINS, destination_configuration, validate_approved_origin
from routes import legacy
from routes import auth
from models import LegacyTableRecipePreviewRequest, SSOCodeRequest, SSORedeemRequest
from today import build_today_projection


PROHIBITED_ORIGINS = [
    "http://api.legacytable.app",
    "https://user:pass@api.legacytable.app",
    "https://api.legacytable.app:444",
    "https://api.legacytable.app/path",
    "https://127.0.0.1",
    "https://169.254.169.254",
    "https://10.0.0.1",
    "https://[::1]",
    "https://example.invalid",
]


def test_holiday_template_is_private_editable_content_only():
    template = next(item for item in GATHERING_TEMPLATES if item["id"] == "holiday_meal")
    assert [item["title"] for item in template["defaults"]["agenda"]] == [
        "Welcome or arrival", "Meal time", "Cleanup"
    ]
    assert template["defaults"]["potluck_items"] == [
        "Main dish", "Side dish", "Dessert", "Drinks or supplies"
    ]
    serialized = repr(template).lower()
    assert "thanksgiving" not in serialized
    assert "email" not in serialized
    assert "invite" not in serialized


@pytest.mark.parametrize("origin", PROHIBITED_ORIGINS)
def test_legacy_origin_validation_rejects_ssrf_categories(origin):
    with pytest.raises(ValueError):
        validate_approved_origin(origin, APPROVED_API_ORIGINS)


def test_legacy_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("UBUNTU_SSO_SECRET", raising=False)
    monkeypatch.delenv("LEGACY_TABLE_API_ORIGIN", raising=False)
    monkeypatch.delenv("LEGACY_TABLE_WEB_ORIGIN", raising=False)
    assert destination_configuration() == {
        "status": "configuration_required", "sso_ready": False, "transfer_ready": False
    }


@pytest.mark.asyncio
async def test_recipe_preview_is_author_only_content_and_mutation_free(monkeypatch):
    calls = []
    thread = {
        "id": "synthetic-recipe",
        "community_id": "synthetic-family",
        "created_by": "pilot-author",
        "category": "recipe-tradition",
        "title": "Synthetic shared dish",
        "body": "Synthetic preparation notes.",
    }

    async def fake_get(thread_id, user):
        calls.append((thread_id, user["id"]))
        return dict(thread)

    monkeypatch.setattr(legacy, "get_thread_for_user", fake_get)
    before = dict(thread)
    result = await legacy.legacy_table_recipe_preview(
        LegacyTableRecipePreviewRequest(thread_id=thread["id"]),
        {"id": "pilot-author", "community_id": "synthetic-family", "role": "member"},
    )
    assert thread == before
    assert calls == [("synthetic-recipe", "pilot-author")]
    assert result["selected_content"] == {
        "title": "Synthetic shared dish", "instructions_or_story": "Synthetic preparation notes."
    }
    assert result["transfer_status"] == "unavailable"
    assert "community" not in repr(result).lower()


@pytest.mark.asyncio
async def test_organizer_cannot_preview_another_authors_recipe(monkeypatch):
    async def fake_get(_thread_id, _user):
        return {"created_by": "pilot-author", "category": "recipe-tradition"}

    monkeypatch.setattr(legacy, "get_thread_for_user", fake_get)
    with pytest.raises(HTTPException) as denied:
        await legacy.legacy_table_recipe_preview(
            LegacyTableRecipePreviewRequest(thread_id="synthetic-recipe"),
            {"id": "pilot-organizer", "community_id": "synthetic-family", "role": "organizer"},
        )
    assert denied.value.status_code == 404


def test_holiday_today_priorities_remain_content_free():
    projection = build_today_projection(
        viewer_role="organizer",
        lifecycle_state="active",
        candidates=[
            {"code": "preserve_holiday_recipe", "state": "available", "destination_category": "legacy_threads"},
            {"code": "finish_holiday_meal_setup", "state": "draft", "destination_category": "gatherings"},
        ],
        recent_changes=[],
    )
    assert projection["primary_action_code"] == "finish_holiday_meal_setup"
    assert "title" not in repr(projection).lower()
    assert "recipe" in projection["secondary_actions"][0]["code"]


class _InsertResult:
    pass


class FakeSSOCodes:
    def __init__(self):
        self.rows = []

    async def insert_one(self, row):
        self.rows.append(dict(row))
        return _InsertResult()

    async def find_one_and_update(self, query, update, **_kwargs):
        for row in self.rows:
            if (
                row.get("code_digest") == query.get("code_digest")
                and row.get("audience") == query.get("audience")
                and row.get("used") is False
                and row.get("expires_at", "") > query["expires_at"]["$gt"]
            ):
                before = dict(row)
                row.update(update.get("$set", {}))
                for key in update.get("$unset", {}):
                    row.pop(key, None)
                return before
        return None


class FakeUsers:
    async def find_one(self, query, _projection):
        if query == {"id": "pilot-sso-user"}:
            return {
                "id": "pilot-sso-user",
                "email": "pilot.user@example.invalid",
                "email_normalized": "pilot.user@example.invalid",
                "full_name": "Pilot Guest",
                "community_id": "",
                "community_ids": [],
                "role": "member",
                "auth_provider": "ubuntu-sso",
                "onboarding_completed": False,
            }
        return None


def kindred_request(origin="https://www.heykindred.org"):
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/sso-redeem",
        "headers": [(b"origin", origin.encode("ascii"))],
    })


@pytest.mark.asyncio
async def test_sso_code_is_digest_only_audience_bound_and_single_use(monkeypatch):
    codes = FakeSSOCodes()
    monkeypatch.setenv("UBUNTU_SSO_SECRET", "synthetic-server-secret")
    monkeypatch.setenv("JWT_SECRET", "synthetic-jwt-secret-for-unit-tests")
    monkeypatch.setattr(auth, "sso_codes_collection", codes)
    monkeypatch.setattr(auth, "users_collection", FakeUsers())

    async def synthetic_user(_email, _name):
        return {"id": "pilot-sso-user"}

    monkeypatch.setattr(auth, "_find_or_create_sso_user", synthetic_user)
    minted = await auth.sso_mint_code(SSOCodeRequest(
        email="pilot.user@example.invalid",
        name="Pilot Guest",
        secret="synthetic-server-secret",
        audience="kindred",
        origin="https://legacytable.app",
    ))
    assert minted["code"] not in repr(codes.rows)
    assert "code" not in codes.rows[0]
    assert len(codes.rows[0]["code_digest"]) == 64

    redeemed = await auth.sso_redeem_code(
        SSORedeemRequest(code=minted["code"], audience="kindred", origin="https://www.heykindred.org"),
        kindred_request(),
    )
    assert redeemed["user"]["id"] == "pilot-sso-user"
    assert "code_digest" not in codes.rows[0]

    with pytest.raises(HTTPException):
        await auth.sso_redeem_code(
            SSORedeemRequest(code=minted["code"], audience="kindred", origin="https://www.heykindred.org"),
            kindred_request(),
        )
    with pytest.raises(HTTPException):
        await auth.sso_redeem_code(
            SSORedeemRequest(code="synthetic-wrong-code-value-that-is-long-enough", audience="wrong", origin="https://www.heykindred.org"),
            kindred_request(),
        )
    with pytest.raises(HTTPException):
        await auth.sso_redeem_code(
            SSORedeemRequest(code="synthetic-wrong-origin-code-value", audience="kindred", origin="https://www.heykindred.org"),
            kindred_request("https://unapproved.invalid"),
        )


@pytest.mark.asyncio
async def test_token_returning_sso_exchange_is_retired():
    from models import SSOExchangeRequest

    with pytest.raises(HTTPException) as retired:
        await auth.auth_exchange(SSOExchangeRequest(
            email="pilot.user@example.invalid", name="Pilot Guest", secret="synthetic"
        ))
    assert retired.value.status_code == 410
    assert retired.value.detail["code"] == "sso_exchange_retired"
