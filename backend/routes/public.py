"""Public, unauthenticated RSVP-by-link routes (the elder-friendly path).

An invited person can RSVP to a gathering from a shared link without an account
or the app. The link carries the invite's own uuid4 `id` as an unguessable token.
Holding a valid token lets the bearer view MINIMAL gathering details and set the
RSVP for that ONE invite — nothing else is exposed or mutable.

SECURITY (do not relax without review):
- No auth dependency here on purpose. Keep these endpoints dependency-free.
- The token is a uuid4 (122 bits random); it is only ever shown to the
  authenticated organizer/members who send the invite. Treat it like a
  shared calendar link (Evite-style).
- The GET returns only the gathering basics + this invite's name/status. Never
  add member lists, contact info, or other invites here.
- The POST can only change this single invite's rsvp_status. It creates no
  account and grants no access.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from db import communities_collection, events_collection, users_collection
from dependencies import now_iso

router = APIRouter(prefix="/api/public")


class PublicRSVPRequest(BaseModel):
    status: Literal["going", "maybe", "not-going"]
    guests: int = 0


async def _find_event_and_invite(token: str):
    event = await events_collection.find_one({"event_invites.id": token}, {"_id": 0})
    if not event:
        return None, None
    invite = next((i for i in event.get("event_invites", []) if i.get("id") == token), None)
    return event, invite


def _public_view(event: dict, invite: dict) -> dict:
    fmt = event.get("gathering_format", "in-person")
    return {
        "invite_id": invite.get("id", ""),
        "invitee_name": invite.get("invitee_name", ""),
        "rsvp_status": invite.get("rsvp_status", "pending"),
        "gathering": {
            "title": event.get("title", ""),
            "start_at": event.get("start_at", ""),
            "location": event.get("location", ""),
            "gathering_format": fmt,
            "zoom_link": event.get("zoom_link", "") if fmt in {"online", "hybrid"} else "",
            "description": event.get("description", ""),
        },
    }


@router.get("/rsvp/{token}")
async def public_rsvp_view(token: str):
    """Minimal gathering + invite info for a held token. No auth."""
    event, invite = await _find_event_and_invite(token)
    if not event or not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invitation link is not valid.")
    community = await communities_collection.find_one(
        {"id": event.get("community_id")}, {"_id": 0, "name": 1}
    )
    view = _public_view(event, invite)
    view["community_name"] = community.get("name", "") if community else ""
    return view


@router.post("/rsvp/{token}")
async def public_rsvp_submit(token: str, payload: PublicRSVPRequest):
    """Set the RSVP for this one invite. No auth, no account creation."""
    event, invite = await _find_event_and_invite(token)
    if not event or not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invitation link is not valid.")

    rsvp_uid = f"invite:{invite['id']}"
    next_records = [r for r in event.get("rsvp_records", []) if r.get("user_id") != rsvp_uid]
    next_records.append({
        "user_id": rsvp_uid,
        "user_name": invite.get("invitee_name", "Guest"),
        "status": payload.status,
        "guests": max(0, payload.guests),
        "updated_at": now_iso(),
        "via": "public-link",
    })

    invites = event.get("event_invites", [])
    for i in invites:
        if i.get("id") == invite["id"]:
            i["rsvp_status"] = payload.status

    await events_collection.update_one(
        {"id": event["id"]},
        {"$set": {"rsvp_records": next_records, "event_invites": invites}},
    )

    community = await communities_collection.find_one(
        {"id": event.get("community_id")}, {"_id": 0, "name": 1}
    )
    view = _public_view(event, {**invite, "rsvp_status": payload.status})
    view["community_name"] = community.get("name", "") if community else ""
    view["saved"] = True
    return view


# ---------------------------------------------------------------------------
# Weekly digest one-click unsubscribe / resubscribe (no auth; token-based).
# Linked from the digest email footer. The token is a per-user opaque value.
# ---------------------------------------------------------------------------

def _digest_pref_page(title: str, message: str, action_label: str, action_href: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Kindred</title></head>
<body style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9f5f0;">
<div style="max-width:480px;margin:64px auto;background:#fff;border:1px solid #e8e0d8;border-radius:16px;padding:40px 32px;text-align:center;">
<p style="font-size:13px;letter-spacing:.2em;text-transform:uppercase;color:#9A3412;margin:0 0 12px;">Kindred</p>
<h1 style="font-size:24px;color:#2d1810;margin:0 0 12px;">{title}</h1>
<p style="font-size:16px;line-height:1.6;color:#5a4a3a;margin:0 0 24px;">{message}</p>
<a href="{action_href}" style="display:inline-block;font-size:14px;color:#9A3412;text-decoration:underline;">{action_label}</a>
</div></body></html>"""


@router.get("/digest/unsubscribe/{token}", response_class=HTMLResponse)
async def digest_unsubscribe(token: str):
    """Opt this user out of weekly digests. One click, no login."""
    user = await users_collection.find_one({"digest_unsubscribe_token": token}, {"_id": 0, "id": 1})
    if not user:
        return HTMLResponse(_digest_pref_page(
            "Link not recognized",
            "This unsubscribe link is no longer valid. You can manage notifications inside the app.",
            "Open Kindred", "https://www.heykindred.org",
        ), status_code=404)
    await users_collection.update_one(
        {"id": user["id"]}, {"$set": {"digest_opt_out": True, "digest_opt_out_at": now_iso()}}
    )
    return HTMLResponse(_digest_pref_page(
        "You're unsubscribed",
        "You won't receive the weekly community digest anymore. Changed your mind?",
        "Re-subscribe", f"/api/public/digest/resubscribe/{token}",
    ))


@router.get("/digest/resubscribe/{token}", response_class=HTMLResponse)
async def digest_resubscribe(token: str):
    """Re-enable weekly digests for this user."""
    user = await users_collection.find_one({"digest_unsubscribe_token": token}, {"_id": 0, "id": 1})
    if not user:
        return HTMLResponse(_digest_pref_page(
            "Link not recognized",
            "This link is no longer valid. You can manage notifications inside the app.",
            "Open Kindred", "https://www.heykindred.org",
        ), status_code=404)
    await users_collection.update_one(
        {"id": user["id"]}, {"$set": {"digest_opt_out": False}, "$unset": {"digest_opt_out_at": ""}}
    )
    return HTMLResponse(_digest_pref_page(
        "Welcome back",
        "You're subscribed to the weekly community digest again.",
        "Open Kindred", "https://www.heykindred.org",
    ))
