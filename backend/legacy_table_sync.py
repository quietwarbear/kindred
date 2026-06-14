"""Kindred → Legacy Table recipe sync via Ubuntu Markets single-identity SSO.

No passwords are stored or exchanged. Because the signed-in Kindred user is already
trusted, Kindred presents that user's email + a shared server-side secret
(UBUNTU_SSO_SECRET, set identically in both products' environments) to Legacy Table's
POST /auth/exchange, which find-or-creates the same-email user and returns a normal
Legacy Table session. Kindred then POSTs the recipe — authored by the user in Legacy
Table automatically.

The shared secret is powerful (it mints a Legacy Table session for any email), so it
lives ONLY in server environments and Legacy Table must trust only products you control.
"""

import os

import httpx

DEFAULT_BASE_URL = "https://api.legacytable.app/api"


def sso_secret() -> str:
    return os.environ.get("UBUNTU_SSO_SECRET", "")


async def _exchange_token(base_url: str, email: str, name: str = "") -> str | None:
    secret = sso_secret()
    if not secret:
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{base_url}/auth/exchange",
                json={"email": email, "secret": secret, "name": name},
            )
        if resp.status_code == 200:
            return resp.json().get("token")
    except Exception:
        return None
    return None


async def push_recipe(base_url: str, email: str, recipe: dict, name: str = "") -> dict:
    """Sideways-sign-in to Legacy Table as `email` and create one recipe.

    Returns {"ok": True, "recipe_id": ...} or {"ok": False, "error": ...}.
    """
    base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if not sso_secret():
        return {"ok": False, "error": "Cross-product sign-in isn't configured yet (UBUNTU_SSO_SECRET is not set)."}
    if not email:
        return {"ok": False, "error": "Your Kindred account has no email to carry into Legacy Table."}

    token = await _exchange_token(base_url, email, name)
    if not token:
        return {"ok": False, "error": "Couldn't establish your Legacy Table session — check the shared SSO secret on both apps."}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/recipes",
                headers={"Authorization": f"Bearer {token}"},
                json=recipe,
            )
    except Exception as exc:
        return {"ok": False, "error": f"Could not reach Legacy Table: {exc}"}

    if resp.status_code == 200:
        data = resp.json()
        return {"ok": True, "recipe_id": data.get("id", ""), "recipe": data}
    return {"ok": False, "error": f"Legacy Table rejected the recipe (HTTP {resp.status_code}).", "detail": resp.text[:300]}
