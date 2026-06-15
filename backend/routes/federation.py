"""Cross-product federation jumps — Ubuntu Markets single sign-on handoff.

Kindred mints a single-use code at a trusted sibling product (server-to-server, via the
shared UBUNTU_SSO_SECRET) and returns a jump URL. The browser opens it; the sibling's
/sso page redeems the code ONCE for a session. No session token ever rides in the URL —
only a short-lived, single-use code (OAuth-authorization-code style).
"""

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dependencies import get_current_user

router = APIRouter(prefix="/api")

# Each target: API base (where /auth/sso-code lives) + web base (where /sso lives).
TARGETS = {
    "legacy_table": {
        "api": os.environ.get("LEGACY_TABLE_API_URL", "https://api.legacytable.app/api").rstrip("/"),
        "web": os.environ.get("LEGACY_TABLE_WEB_URL", "https://legacytable.app").rstrip("/"),
        "label": "Legacy Table",
    },
}


class JumpRequest(BaseModel):
    target: str


@router.post("/federation/jump")
async def federation_jump(payload: JumpRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    cfg = TARGETS.get(payload.target)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown destination.")
    secret = os.environ.get("UBUNTU_SSO_SECRET", "")
    if not secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Cross-product sign-in isn't configured.")
    email = current_user.get("email", "")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your account has no email to carry over.")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{cfg['api']}/auth/sso-code",
                json={"email": email, "secret": secret, "name": current_user.get("full_name", "")},
            )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Couldn't reach {cfg['label']} ({exc}).")
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{cfg['label']} declined the handoff (HTTP {resp.status_code}).")
    code = resp.json().get("code")
    if not code:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{cfg['label']} returned no code.")
    return {"url": f"{cfg['web']}/sso?code={code}", "label": cfg["label"]}
