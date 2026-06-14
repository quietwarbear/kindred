"""Kindred → Legacy Table recipe sync via Ubuntu Markets single-identity SSO.

No passwords are stored or exchanged. Because the signed-in Kindred user is already
trusted, Kindred presents that user's email + a shared server-side secret
(UBUNTU_SSO_SECRET, set identically in both products' environments) to Legacy Table's
POST /auth/exchange, which find-or-creates the same-email user and returns a normal
Legacy Table session.

Legacy Table is family-scoped: a recipe with no family has no visible home. So before
posting the recipe, if the user has no Legacy Table family we create one named after the
Kindred community (mapping the community → a Legacy Table family cookbook). Then the
recipe lands in that family and shows up in the Family Cookbook.

The shared secret is powerful (it mints a Legacy Table session for any email), so it
lives ONLY in server environments and Legacy Table must trust only products you control.
"""

import os

import httpx

DEFAULT_BASE_URL = "https://api.legacytable.app/api"


def sso_secret() -> str:
    return os.environ.get("UBUNTU_SSO_SECRET", "")


async def push_recipe(base_url: str, email: str, recipe: dict, name: str = "", family_name: str = "") -> dict:
    """Sideways-sign-in to Legacy Table as `email`, ensure a family, and create one recipe.

    Returns {"ok": True, "recipe_id": ..., "family_id": ..., "family_created": bool}
    or {"ok": False, "error": ...}.
    """
    base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if not sso_secret():
        return {"ok": False, "error": "Cross-product sign-in isn't configured yet (UBUNTU_SSO_SECRET is not set)."}
    if not email:
        return {"ok": False, "error": "Your Kindred account has no email to carry into Legacy Table."}

    # 1) Exchange identity for a Legacy Table session — surface precise failures.
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            ex = await client.post(
                f"{base_url}/auth/exchange",
                json={"email": email, "secret": sso_secret(), "name": name},
            )
    except Exception as exc:
        return {"ok": False, "error": f"Couldn't reach Legacy Table at {base_url} ({exc}). The backend URL may be wrong."}

    if ex.status_code == 403:
        return {"ok": False, "error": "Legacy Table rejected the shared secret (403) — UBUNTU_SSO_SECRET doesn't match on both apps."}
    if ex.status_code == 404:
        return {"ok": False, "error": f"No /auth/exchange at {base_url} (404) — deploy the Legacy Table change, or the backend URL is wrong."}
    if ex.status_code != 200:
        return {"ok": False, "error": f"Legacy Table exchange failed (HTTP {ex.status_code}): {ex.text[:200]}"}

    payload = ex.json()
    token = payload.get("token")
    if not token:
        return {"ok": False, "error": "Legacy Table exchange returned no token."}
    lt_user = payload.get("user") or {}
    headers = {"Authorization": f"Bearer {token}"}

    # 2) Ensure a family so the recipe has a visible home (community → family cookbook).
    family_created = False
    if not lt_user.get("family_id") and family_name:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                fam = await client.post(
                    f"{base_url}/families",
                    headers=headers,
                    json={"name": family_name, "description": f"Recipes preserved from {family_name} on Kindred."},
                )
            # 200 = created (user is now its keeper); 400 = already in a family (fine, proceed).
            family_created = fam.status_code == 200
        except Exception:
            pass  # Non-fatal: fall through and let the recipe post (family-less) rather than fail the sync.

    # 3) Create the recipe (Legacy Table stamps it with the user's family, now set).
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/recipes",
                headers=headers,
                json=recipe,
            )
    except Exception as exc:
        return {"ok": False, "error": f"Could not reach Legacy Table: {exc}"}

    if resp.status_code == 200:
        data = resp.json()
        return {
            "ok": True,
            "recipe_id": data.get("id", ""),
            "family_id": data.get("family_id"),
            "family_created": family_created,
            "recipe": data,
        }
    return {"ok": False, "error": f"Legacy Table rejected the recipe (HTTP {resp.status_code}).", "detail": resp.text[:300]}
