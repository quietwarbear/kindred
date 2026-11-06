"""Cross-app jumps only carry an email the person has proven they own.

A sibling app (Legacy Table, Ile Ubuntu) signs the person into whichever
account holds the email Kindred sends. If Kindred sent an unverified address,
anyone could sign up here with someone else's email and land in that person's
account in the other app.
"""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_sso_unit")

from routes import federation  # noqa: E402


def user(**fields):
    return {"id": "u-1", "email": "person@example.invalid", "full_name": "Person", **fields}


@pytest.mark.parametrize(
    "fields, proven",
    [
        ({"email_verified": True, "auth_provider": "password"}, True),
        ({"email_verified": False, "auth_provider": "password"}, False),
        ({"auth_provider": "password"}, False),  # older accounts with no flag
        ({"auth_provider": "google"}, True),
        ({"auth_provider": "apple"}, True),
        ({"auth_provider": "ubuntu-sso"}, False),  # arrived from a sibling; must verify here
        ({"email_verified": "yes", "auth_provider": "password"}, False),
    ],
)
def test_email_proven(fields, proven):
    assert federation.email_proven(user(**fields)) is proven


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("UBUNTU_SSO_SECRET", "synthetic-only")
    monkeypatch.setenv("ILE_UBUNTU_API_ORIGIN", "https://ileubuntu-production.up.railway.app")
    monkeypatch.setenv("ILE_UBUNTU_WEB_ORIGIN", "https://www.ile-ubuntu.org")


@pytest.fixture
def sibling(monkeypatch):
    """Record whether Kindred contacted the sibling at all."""
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(200, json={"code": "c" * 40})

    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(federation.httpx, "AsyncClient", client)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["ile_ubuntu", "legacy_table"])
async def test_unverified_account_cannot_jump_and_nothing_is_sent(configured, sibling, target):
    with pytest.raises(HTTPException) as exc:
        await federation.mint_sso_code(target, user(email_verified=False, auth_provider="password"))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "email_not_verified"
    assert sibling == []  # the email never left Kindred


@pytest.mark.asyncio
async def test_verified_account_jumps(configured, sibling):
    reply = await federation.federation_jump(
        federation.JumpRequest(target="ile_ubuntu"), user(email_verified=True, auth_provider="password")
    )
    assert reply["url"].startswith("https://www.ile-ubuntu.org/sso?code=")
    assert len(sibling) == 1


@pytest.mark.asyncio
async def test_google_account_jumps(configured, sibling):
    code, origin = await federation.mint_sso_code("ile_ubuntu", user(auth_provider="google"))
    assert origin == "https://www.ile-ubuntu.org" and len(code) == 40


@pytest.mark.asyncio
async def test_sso_code_refuses_a_wrong_secret(monkeypatch):
    """The shared secret is compared in constant time; a wrong one is still refused."""
    from models import SSOCodeRequest
    from routes import auth

    monkeypatch.setenv("UBUNTU_SSO_SECRET", "synthetic-only")
    for secret in ("wrong", "synthetic-onlyX", "synthetic-onl"):
        with pytest.raises(HTTPException) as exc:
            await auth.sso_mint_code(
                SSOCodeRequest(
                    email="person@example.invalid", secret=secret, name="Person",
                    audience="kindred", origin="https://www.ile-ubuntu.org",
                )
            )
        assert exc.value.status_code == 403
