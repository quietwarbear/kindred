"""Kindred → Legacy Table recipe sync.

Legacy Table ("Where family recipes live forever") exposes JWT-only auth — there is
no API key / service account. So Kindred authenticates as a real Legacy Table account
(the community's connected account) via POST /auth/login, then POST /recipes.

SECURITY NOTE: the connected account's password is stored in the community's
legacy_table config to allow auto-login per sync. Use a DEDICATED Legacy Table
account for this, not a personal one. The clean long-term fix is an API-key/service
account on Legacy Table's side (it doesn't have one yet) — until then this is the
only path. The password is never logged or returned to clients.
"""

import httpx

DEFAULT_BASE_URL = "https://api.legacytable.app/api"


async def _login(base_url: str, email: str, password: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{base_url}/auth/login", json={"email": email, "password": password})
        if resp.status_code == 200:
            return resp.json().get("token")
    except Exception:
        return None
    return None


async def push_recipe(config: dict, recipe: dict) -> dict:
    """Log into the community's Legacy Table account and create one recipe.

    Returns {"ok": True, "recipe_id": ...} or {"ok": False, "error": ...}.
    """
    base_url = (config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    email = (config.get("account_email") or "").strip()
    password = config.get("account_password") or ""
    if not email or not password:
        return {"ok": False, "error": "No Legacy Table account is connected for this community."}

    token = await _login(base_url, email, password)
    if not token:
        return {"ok": False, "error": "Could not sign in to Legacy Table — check the connected account's email and password."}

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
