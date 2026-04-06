"""Authentication routes."""

import os
import secrets
import urllib.parse
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from courtyard_helpers import ROLE_TOOLING, build_default_subyards, build_planning_checklist, build_role_suggestions
from db import (
    communities_collection,
    events_collection,
    invites_collection,
    notification_events_collection,
    notification_preferences_collection,
    password_resets_collection,
    polls_collection,
    announcements_collection,
    budget_plans_collection,
    chat_rooms_collection,
    kinships_collection,
    memories_collection,
    payments_collection,
    subyards_collection,
    threads_collection,
    travel_plans_collection,
    user_sessions_collection,
    users_collection,
)
from dependencies import (
    apply_session_cookie,
    build_auth_response,
    enforce_member_limit,
    ensure_chat_rooms_for_community,
    get_community_for_user,
    get_current_user,
    normalize_community_type,
    normalize_email,
    now_iso,
)
from models import (
    AccountDeleteRequest,
    AuthResponse,
    CommunityBootstrapRequest,
    GoogleOnboardingRequest,
    GoogleSessionRequest,
    InviteRegistrationRequest,
    LoginRequest,
    OwnershipTransferRequest,
    PasswordRecoveryRequest,
    PasswordRecoveryVerifyRequest,
    ProfileUpdateRequest,
    UserPublic,
)
from security import hash_password, verify_password

router = APIRouter(prefix="/api")
DEFAULT_MOBILE_GOOGLE_REDIRECT = os.environ.get(
    "GOOGLE_MOBILE_REDIRECT_URI",
    "kindred://auth/google/callback",
)
ALLOWED_MOBILE_GOOGLE_SCHEMES = {
    scheme.strip()
    for scheme in os.environ.get(
        "GOOGLE_MOBILE_REDIRECT_SCHEMES",
        "kindred,com.ubuntumarket.kindred",
    ).split(",")
    if scheme.strip()
}


def _append_query_value(url: str, key: str, value: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query.append((key, value))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _validate_mobile_redirect_uri(redirect_uri: str) -> str:
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.scheme not in ALLOWED_MOBILE_GOOGLE_SCHEMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported mobile redirect URI.")
    if not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mobile redirect URI must include a host.")
    return redirect_uri


def _external_base_url(request: Request) -> str:
    """
    Build the public-facing base URL behind a proxy like Railway.
    """
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()

    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}"

    public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base_url:
        return public_base_url

    return str(request.base_url).rstrip("/")


async def _build_google_auth_response(google_user: dict[str, str], response: Response):
    email = normalize_email(google_user.get("email", ""))
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account did not return a usable email.")

    user_doc = await users_collection.find_one({"email": email}, {"_id": 0})
    if user_doc:
        update_payload = {
            "full_name": google_user.get("name") or user_doc.get("full_name"),
            "google_picture": google_user.get("picture", ""),
            "auth_provider": "google",
        }
        if user_doc.get("auth_provider") != "google" or "onboarding_completed" not in user_doc:
            update_payload["onboarding_completed"] = False
        await users_collection.update_one(
            {"id": user_doc["id"]},
            {"$set": update_payload},
        )
        user_doc = await users_collection.find_one({"id": user_doc["id"]}, {"_id": 0})
    else:
        invite_doc = await invites_collection.find_one({"email": email, "status": "pending"}, {"_id": 0})
        created_at = now_iso()
        user_id = str(uuid.uuid4())

        if invite_doc:
            await enforce_member_limit(invite_doc["community_id"])
            user_doc = {
                "id": user_id,
                "full_name": google_user.get("name") or email.split("@")[0],
                "nickname": "",
                "email": email,
                "phone_number": "",
                "profile_image_url": "",
                "google_picture": google_user.get("picture", ""),
                "password_hash": "",
                "role": invite_doc["role"],
                "community_id": invite_doc["community_id"],
                "auth_provider": "google",
                "onboarding_completed": False,
                "created_at": created_at,
            }
            await users_collection.insert_one(user_doc.copy())
            await invites_collection.update_one({"id": invite_doc["id"]}, {"$set": {"status": "accepted", "accepted_at": created_at}})
        else:
            community_id = str(uuid.uuid4())
            display_name = (google_user.get("name") or email.split("@")[0]).split(" ")[0]
            community_doc = {
                "id": community_id,
                "name": f"{display_name}'s Circle",
                "community_type": "community",
                "location": "",
                "description": "A new Kindred courtyard created through Google sign up.",
                "motto": "",
                "owner_user_id": user_id,
                "created_at": created_at,
            }
            user_doc = {
                "id": user_id,
                "full_name": google_user.get("name") or display_name,
                "nickname": "",
                "email": email,
                "phone_number": "",
                "profile_image_url": "",
                "google_picture": google_user.get("picture", ""),
                "password_hash": "",
                "role": "host",
                "community_id": community_id,
                "auth_provider": "google",
                "onboarding_completed": False,
                "created_at": created_at,
            }
            await communities_collection.insert_one(community_doc.copy())
            await users_collection.insert_one(user_doc.copy())

            default_subyards = []
            for template in build_default_subyards(community_doc["community_type"]):
                default_subyards.append(
                    {
                        "id": str(uuid.uuid4()),
                        "community_id": community_id,
                        "name": template["name"],
                        "description": template["description"],
                        "inherited_roles": True,
                        "role_focus": template["role_focus"],
                        "assigned_tools": sorted({tool for role in template["role_focus"] for tool in ROLE_TOOLING.get(role, [])}),
                        "visibility": "shared",
                        "created_by": user_id,
                        "created_at": created_at,
                    }
                )
            if default_subyards:
                await subyards_collection.insert_many([item.copy() for item in default_subyards])
                await ensure_chat_rooms_for_community(community_id, community_doc["name"], default_subyards)
            else:
                await ensure_chat_rooms_for_community(community_id, community_doc["name"], [])

    session_token = secrets.token_urlsafe(32)
    await user_sessions_collection.update_one(
        {"session_token": session_token},
        {
            "$set": {
                "session_token": session_token,
                "user_id": user_doc["id"],
                "email": email,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "created_at": now_iso(),
            }
        },
        upsert=True,
    )
    apply_session_cookie(response, session_token)

    community_doc = await get_community_for_user(user_doc)
    return build_auth_response(user_doc, community_doc)


@router.post("/auth/bootstrap", response_model=AuthResponse)
async def bootstrap_community(payload: CommunityBootstrapRequest):
    email = normalize_email(payload.email)
    existing_user = await users_collection.find_one({"email": email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    community_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    created_at = now_iso()
    community_doc = {
        "id": community_id,
        "name": payload.community_name.strip(),
        "community_type": normalize_community_type(payload.community_type),
        "location": payload.location.strip(),
        "description": payload.description.strip(),
        "motto": (payload.motto or "").strip(),
        "owner_user_id": user_id,
        "created_at": created_at,
    }
    user_doc = {
        "id": user_id,
        "full_name": payload.full_name.strip(),
        "nickname": "",
        "email": email,
        "phone_number": "",
        "profile_image_url": "",
        "google_picture": "",
        "password_hash": hash_password(payload.password),
        "role": "host",
        "community_id": community_id,
        "community_ids": [community_id],
        "auth_provider": "password",
        "onboarding_completed": True,
        "created_at": created_at,
    }

    await communities_collection.insert_one(community_doc.copy())
    await users_collection.insert_one(user_doc.copy())

    default_subyards = []
    for template in build_default_subyards(community_doc["community_type"]):
        default_subyards.append(
            {
                "id": str(uuid.uuid4()),
                "community_id": community_id,
                "name": template["name"],
                "description": template["description"],
                "inherited_roles": True,
                "role_focus": template["role_focus"],
                "assigned_tools": sorted({tool for role in template["role_focus"] for tool in ROLE_TOOLING.get(role, [])}),
                "visibility": "shared",
                "created_by": user_id,
                "created_at": created_at,
            }
        )
    if default_subyards:
        await subyards_collection.insert_many([item.copy() for item in default_subyards])
        await ensure_chat_rooms_for_community(community_id, community_doc["name"], default_subyards)
    else:
        await ensure_chat_rooms_for_community(community_id, community_doc["name"], [])

    return build_auth_response(user_doc, community_doc)


@router.post("/auth/register-with-invite", response_model=AuthResponse)
async def register_with_invite(payload: InviteRegistrationRequest):
    email = normalize_email(payload.email)
    invite_doc = await invites_collection.find_one({"code": payload.invite_code.strip().upper()}, {"_id": 0})
    if not invite_doc or invite_doc["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code is invalid or already used.")
    if normalize_email(invite_doc["email"]) != email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite code does not match this email address.")

    existing_user = await users_collection.find_one({"email": email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    await enforce_member_limit(invite_doc["community_id"])

    created_at = now_iso()
    user_doc = {
        "id": str(uuid.uuid4()),
        "full_name": payload.full_name.strip(),
        "nickname": "",
        "email": email,
        "phone_number": "",
        "profile_image_url": "",
        "google_picture": "",
        "password_hash": hash_password(payload.password),
        "role": invite_doc["role"],
        "community_id": invite_doc["community_id"],
        "community_ids": [invite_doc["community_id"]],
        "auth_provider": "password",
        "onboarding_completed": True,
        "created_at": created_at,
    }
    await users_collection.insert_one(user_doc.copy())
    await invites_collection.update_one({"id": invite_doc["id"]}, {"$set": {"status": "accepted", "accepted_at": created_at}})

    community_doc = await communities_collection.find_one({"id": invite_doc["community_id"]}, {"_id": 0})
    return build_auth_response(user_doc, community_doc)


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest):
    email = normalize_email(payload.email)
    user_doc = await users_collection.find_one({"email": email}, {"_id": 0})
    if not user_doc or not verify_password(payload.password, user_doc["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    community_doc = await communities_collection.find_one({"id": user_doc["community_id"]}, {"_id": 0})
    return build_auth_response(user_doc, community_doc)


@router.get("/auth/me", response_model=AuthResponse)
async def me(current_user: dict[str, Any] = Depends(get_current_user)):
    community_doc = await get_community_for_user(current_user)
    return build_auth_response(current_user, community_doc)


@router.post("/auth/google/session")
async def google_session_login(payload: GoogleSessionRequest, response: Response):
    """
    Validate Google OAuth ID token and log the user in.
    Requires GOOGLE_CLIENT_ID environment variable.
    """
    try:
        google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        if not google_client_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID environment variable.",
            )

        # Verify the ID token
        idinfo = id_token.verify_oauth2_token(
            payload.credential,
            GoogleRequest(),
            google_client_id,
        )

        # Extract user information from the verified token
        google_user = {
            "email": idinfo.get("email", ""),
            "name": idinfo.get("name", ""),
            "picture": idinfo.get("picture", ""),
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to validate Google session.") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google session validation failed.") from exc

    return await _build_google_auth_response(google_user, response)


@router.get("/auth/google/start")
async def google_login_start(request: Request, redirect_uri: str = DEFAULT_MOBILE_GOOGLE_REDIRECT):
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not google_client_id or not google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth is not configured.",
        )

    app_redirect_uri = _validate_mobile_redirect_uri(redirect_uri)
    oauth_callback_uri = _external_base_url(request) + "/api/auth/google/callback"
    params = {
        "client_id": google_client_id,
        "redirect_uri": oauth_callback_uri,
        "scope": "openid email profile",
        "response_type": "code",
        "access_type": "online",
        "prompt": "select_account",
        "state": app_redirect_uri,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/auth/google/callback")
async def google_login_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    app_redirect_uri = _validate_mobile_redirect_uri(state or DEFAULT_MOBILE_GOOGLE_REDIRECT)

    if error:
        return RedirectResponse(url=_append_query_value(app_redirect_uri, "google_error", error))

    if not code:
        return RedirectResponse(url=_append_query_value(app_redirect_uri, "google_error", "no_code"))

    oauth_callback_uri = _external_base_url(request) + "/api/auth/google/callback"
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": google_client_id,
            "client_secret": google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": oauth_callback_uri,
        },
        timeout=20,
    )

    if token_response.status_code != 200:
        try:
            error_detail = token_response.json().get("error_description", "token_exchange_failed")
        except Exception:
            error_detail = "token_exchange_failed"
        return RedirectResponse(url=_append_query_value(app_redirect_uri, "google_error", error_detail))

    tokens = token_response.json()
    id_token_value = tokens.get("id_token")
    if not id_token_value:
        return RedirectResponse(url=_append_query_value(app_redirect_uri, "google_error", "missing_id_token"))

    response = Response()
    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_value,
            GoogleRequest(),
            google_client_id,
        )
        auth_payload = await _build_google_auth_response(
            {
                "email": idinfo.get("email", ""),
                "name": idinfo.get("name", ""),
                "picture": idinfo.get("picture", ""),
            },
            response,
        )
    except Exception:
        return RedirectResponse(url=_append_query_value(app_redirect_uri, "google_error", "google_validation_failed"))

    redirect_url = _append_query_value(app_redirect_uri, "google_success", "1")
    redirect_url = _append_query_value(redirect_url, "token", auth_payload["token"])
    if auth_payload.get("user", {}).get("onboarding_completed") is False:
        redirect_url = _append_query_value(redirect_url, "needs_onboarding", "1")

    redirect = RedirectResponse(url=redirect_url)
    for header_name, header_value in response.headers.items():
        if header_name.lower() == "set-cookie":
            redirect.headers.append("set-cookie", header_value)
    return redirect


@router.post("/auth/password-recovery/request")
async def request_password_recovery(payload: PasswordRecoveryRequest):
    email = normalize_email(payload.email)
    user_doc = await users_collection.find_one({"email": email}, {"_id": 0})
    if not user_doc:
        return {"ok": True, "delivery_status": "silent"}

    code = f"{secrets.randbelow(1000000):06d}"
    await password_resets_collection.update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "code": code,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                "created_at": now_iso(),
            }
        },
        upsert=True,
    )

    if os.environ.get("RESEND_API_KEY"):
        delivery_status = "email-sent"
    else:
        delivery_status = "connection-ready"

    return {"ok": True, "delivery_status": delivery_status}


@router.post("/auth/password-recovery/verify")
async def verify_password_recovery(payload: PasswordRecoveryVerifyRequest):
    email = normalize_email(payload.email)
    reset_doc = await password_resets_collection.find_one({"email": email}, {"_id": 0})
    if not reset_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No recovery request found for this email.")
    if reset_doc.get("code") != payload.code.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recovery code is invalid.")
    expires_at = datetime.fromisoformat(reset_doc["expires_at"].replace("Z", "+00:00"))
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recovery code has expired.")

    await users_collection.update_one({"email": email}, {"$set": {"password_hash": hash_password(payload.new_password)}})
    await password_resets_collection.delete_one({"email": email})
    return {"ok": True}


@router.put("/auth/profile", response_model=UserPublic)
async def update_profile(payload: ProfileUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    update_payload = {
        "full_name": payload.full_name.strip(),
        "nickname": (payload.nickname or "").strip(),
        "phone_number": (payload.phone_number or "").strip(),
        "profile_image_url": (payload.profile_image_url or "").strip(),
    }
    await users_collection.update_one({"id": current_user["id"]}, {"$set": update_payload})
    updated_user = await users_collection.find_one({"id": current_user["id"]}, {"_id": 0})
    updated_user.pop("password_hash", None)
    return updated_user


@router.delete("/auth/account")
async def delete_account(payload: AccountDeleteRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = current_user["id"]
    community_id = current_user["community_id"]

    if current_user.get("auth_provider") != "google":
        if not payload.password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is required to delete your account.")
        full_user = await users_collection.find_one({"id": user_id}, {"_id": 0})
        if not full_user or not verify_password(payload.password, full_user.get("password_hash", "")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect password.")

    community_doc = await communities_collection.find_one({"id": community_id}, {"_id": 0})
    is_owner = community_doc and community_doc.get("owner_user_id") == user_id
    member_count = await users_collection.count_documents({"community_id": community_id})

    if is_owner and member_count > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are the community owner. Transfer ownership to another member before deleting your account.",
        )

    await notification_preferences_collection.delete_many({"user_id": user_id})
    await password_resets_collection.delete_many({"email": current_user.get("email", "")})
    await user_sessions_collection.delete_many({"user_id": user_id})
    await polls_collection.update_many(
        {"community_id": community_id},
        {"$pull": {"options.$[].voter_ids": user_id}},
    )

    if is_owner and member_count <= 1:
        await events_collection.delete_many({"community_id": community_id})
        await announcements_collection.delete_many({"community_id": community_id})
        await chat_rooms_collection.delete_many({"community_id": community_id})
        await subyards_collection.delete_many({"community_id": community_id})
        await kinships_collection.delete_many({"community_id": community_id})
        await memories_collection.delete_many({"community_id": community_id})
        await threads_collection.delete_many({"community_id": community_id})
        await payments_collection.delete_many({"community_id": community_id})
        await travel_plans_collection.delete_many({"community_id": community_id})
        await budget_plans_collection.delete_many({"community_id": community_id})
        await invites_collection.delete_many({"community_id": community_id})
        await notification_events_collection.delete_many({"community_id": community_id})
        await polls_collection.delete_many({"community_id": community_id})
        await communities_collection.delete_one({"id": community_id})

    await users_collection.delete_one({"id": user_id})
    return {"ok": True, "message": "Account deleted permanently."}


@router.post("/community/transfer-ownership")
async def transfer_ownership(payload: OwnershipTransferRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    from dependencies import ensure_minimum_role, log_notification_event

    ensure_minimum_role(current_user, "host")
    community_id = current_user["community_id"]

    new_owner = await users_collection.find_one(
        {"id": payload.new_owner_user_id, "community_id": community_id}, {"_id": 0}
    )
    if not new_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this community.")
    if new_owner["id"] == current_user["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already the owner.")

    await users_collection.update_one({"id": new_owner["id"]}, {"$set": {"role": "host"}})
    await users_collection.update_one({"id": current_user["id"]}, {"$set": {"role": "organizer"}})
    await communities_collection.update_one({"id": community_id}, {"$set": {"owner_user_id": new_owner["id"]}})

    await log_notification_event(
        community_id=community_id,
        actor_name=current_user["full_name"],
        event_type="ownership-transfer",
        title=f"Ownership transferred to {new_owner['full_name']}",
        description=f"{current_user['full_name']} transferred community ownership to {new_owner['full_name']}.",
        related_id=new_owner["id"],
        audience_scope="community",
    )
    return {"ok": True, "new_owner_name": new_owner["full_name"]}


@router.post("/auth/onboarding/complete", response_model=AuthResponse)
async def complete_google_onboarding(payload: GoogleOnboardingRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    profile_updates = {
        "full_name": payload.full_name.strip() or current_user.get("full_name", ""),
        "nickname": (payload.nickname or "").strip(),
        "phone_number": (payload.phone_number or "").strip(),
        "profile_image_url": (payload.profile_image_url or "").strip(),
        "onboarding_completed": True,
    }
    await users_collection.update_one({"id": current_user["id"]}, {"$set": profile_updates})

    refreshed_user = await users_collection.find_one({"id": current_user["id"]}, {"_id": 0})
    community_doc = await get_community_for_user(refreshed_user)

    if refreshed_user["role"] in {"host", "organizer"}:
        community_updates = {
            "name": (payload.community_name or community_doc.get("name", "")).strip() or community_doc.get("name", ""),
            "community_type": normalize_community_type(payload.community_type or community_doc.get("community_type", "community")),
            "location": (payload.location or community_doc.get("location", "")).strip(),
            "motto": (payload.motto or community_doc.get("motto", "")).strip(),
        }
        await communities_collection.update_one({"id": community_doc["id"]}, {"$set": community_updates})
        community_doc = await communities_collection.find_one({"id": community_doc["id"]}, {"_id": 0})

        if (payload.first_subyard_name or "").strip():
            existing_subyard = await subyards_collection.find_one(
                {"community_id": community_doc["id"], "name": payload.first_subyard_name.strip()},
                {"_id": 0},
            )
            if not existing_subyard:
                subyard_doc = {
                    "id": str(uuid.uuid4()),
                    "community_id": community_doc["id"],
                    "name": payload.first_subyard_name.strip(),
                    "description": (payload.first_subyard_description or "").strip() or "Starter subyard created during onboarding.",
                    "inherited_roles": True,
                    "role_focus": ["organizer", "historian"],
                    "assigned_tools": sorted({tool for role in ["organizer", "historian"] for tool in ROLE_TOOLING.get(role, [])}),
                    "visibility": "shared",
                    "created_by": refreshed_user["id"],
                    "created_at": now_iso(),
                }
                await subyards_collection.insert_one(subyard_doc.copy())
                await ensure_chat_rooms_for_community(community_doc["id"], community_doc["name"], [subyard_doc])

        if (
            (payload.first_gathering_title or "").strip()
            and payload.first_gathering_start_at
            and (payload.first_gathering_location or "").strip()
        ):
            existing_event = await events_collection.find_one(
                {
                    "community_id": community_doc["id"],
                    "title": payload.first_gathering_title.strip(),
                    "start_at": payload.first_gathering_start_at,
                },
                {"_id": 0},
            )
            if not existing_event:
                template = payload.first_gathering_template or "reunion"
                event_doc = {
                    "id": str(uuid.uuid4()),
                    "community_id": community_doc["id"],
                    "created_by": refreshed_user["id"],
                    "title": payload.first_gathering_title.strip(),
                    "description": "Starter gathering created during Google onboarding.",
                    "start_at": payload.first_gathering_start_at,
                    "location": payload.first_gathering_location.strip(),
                    "map_url": "",
                    "event_template": template,
                    "special_focus": "",
                    "gathering_format": "in-person",
                    "max_attendees": None,
                    "subyard_id": "",
                    "subyard_name": "",
                    "assigned_roles": build_role_suggestions(template),
                    "planning_checklist": build_planning_checklist(template, "in-person"),
                    "travel_coordination_notes": "",
                    "suggested_contribution": 0.0,
                    "recurrence_frequency": "none",
                    "series_id": "",
                    "is_recurring_instance": False,
                    "parent_event_id": "",
                    "zoom_link": "",
                    "event_invites": [],
                    "event_role_assignments": [
                        {"id": str(uuid.uuid4()), "role_name": role, "assignees": []}
                        for role in build_role_suggestions(template)
                    ],
                    "agenda": [],
                    "volunteer_slots": [],
                    "potluck_items": [],
                    "rsvp_records": [],
                    "created_at": now_iso(),
                }
                await events_collection.insert_one(event_doc.copy())

        for invite_email in payload.invite_emails:
            email = normalize_email(invite_email)
            existing_member = await users_collection.find_one({"community_id": community_doc["id"], "email": email}, {"_id": 0})
            existing_invite = await invites_collection.find_one({"community_id": community_doc["id"], "email": email, "status": "pending"}, {"_id": 0})
            if existing_member or existing_invite:
                continue
            invite_doc = {
                "id": str(uuid.uuid4()),
                "code": uuid.uuid4().hex[:8].upper(),
                "email": email,
                "role": "member",
                "status": "pending",
                "community_id": community_doc["id"],
                "created_by": refreshed_user["id"],
                "created_at": now_iso(),
            }
            await invites_collection.insert_one(invite_doc.copy())

    refreshed_user = await users_collection.find_one({"id": current_user["id"]}, {"_id": 0})
    community_doc = await get_community_for_user(refreshed_user)
    return build_auth_response(refreshed_user, community_doc)



@router.post("/auth/push-token")
async def save_push_token(body: dict, current_user: dict[str, Any] = Depends(get_current_user)):
    """Store device push token for native push notifications."""
    push_token = body.get("push_token", "")
    if not push_token:
        return {"ok": False}
    await users_collection.update_one(
        {"id": current_user["id"]},
        {"$addToSet": {"push_tokens": push_token}},
    )
    return {"ok": True}
