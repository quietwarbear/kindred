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
from pydantic import BaseModel

from db import communities_collection, events_collection
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
