"""Strict, server-to-server cross-product SSO handoff."""

import os
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dependencies import get_current_user
from legacy_table_sync import (
    APPROVED_API_ORIGINS,
    APPROVED_WEB_ORIGINS,
    validate_approved_origin,
)

router = APIRouter(prefix="/api")

TARGETS = {
    "legacy_table": {
        "api_env": "LEGACY_TABLE_API_ORIGIN",
        "web_env": "LEGACY_TABLE_WEB_ORIGIN",
        "approved_api": APPROVED_API_ORIGINS,
        "approved_web": APPROVED_WEB_ORIGINS,
        "audience": "legacy_table",
    },
    "ile_ubuntu": {
        "api_env": "ILE_UBUNTU_API_ORIGIN",
        "web_env": "ILE_UBUNTU_WEB_ORIGIN",
        "approved_api": frozenset({"https://ileubuntu-production.up.railway.app"}),
        "approved_web": frozenset({"https://www.ile-ubuntu.org"}),
        "audience": "ile_ubuntu",
    },
}


class JumpRequest(BaseModel):
    target: str


def _target_config(target: str) -> tuple[dict[str, Any], str, str]:
    cfg = TARGETS.get(target)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown destination.")
    try:
        api_origin = validate_approved_origin(os.environ.get(cfg["api_env"], ""), cfg["approved_api"])
        web_origin = validate_approved_origin(os.environ.get(cfg["web_env"], ""), cfg["approved_web"])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "federation_configuration_invalid", "message": "Cross-product sign-in is unavailable."},
        ) from exc
    return cfg, api_origin, web_origin


@router.post("/federation/jump")
async def federation_jump(payload: JumpRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    cfg, api_origin, web_origin = _target_config(payload.target)
    secret = os.environ.get("UBUNTU_SSO_SECRET", "")
    email = current_user.get("email", "")
    if not secret or not email:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Cross-product sign-in is unavailable.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10), follow_redirects=False) as client:
            response = await client.post(
                f"{api_origin}/api/auth/sso-code",
                json={
                    "email": email,
                    "secret": secret,
                    "name": current_user.get("full_name", ""),
                    "audience": cfg["audience"],
                    "origin": "https://www.heykindred.org",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Cross-product sign-in is temporarily unavailable.") from exc
    if response.is_redirect or response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Cross-product sign-in was declined.")
    try:
        code = response.json().get("code")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Cross-product sign-in returned an invalid response.") from exc
    if not isinstance(code, str) or not (32 <= len(code) <= 128):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Cross-product sign-in returned an invalid response.")
    return {"url": f"{web_origin}/sso?{urlencode({'code': code})}", "destination": payload.target}
