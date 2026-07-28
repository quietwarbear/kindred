"""Public, unauthenticated RSVP-by-link routes (the elder-friendly path).

An invited person can RSVP to a gathering from a shared link without an account
or the app. New links carry the invite's uuid4 `id` in the browser fragment and
send it to this API in an Authorization header. Holding a valid token lets the
bearer view MINIMAL gathering details and set the RSVP for that ONE invite —
nothing else is exposed or mutable.

SECURITY (do not relax without review):
- No account-session dependency here on purpose. Invitation authorization is
  bearer-token based.
- The token is a uuid4 (122 bits random); it is only ever shown to the
  authenticated organizer/members who send the invite. Treat it like a
  shared calendar link (Evite-style).
- The GET returns only the gathering basics + this invite's name/status. Never
  add member lists, contact info, or other invites here.
- The POST can only change this single invite's rsvp_status. It creates no
  account and grants no access.
- Legacy web links are rewritten client-side to fragment URLs. The API never
  accepts invitation credentials in a path or query string.
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from db import communities_collection, events_collection, users_collection
from dependencies import now_iso
from itinerary import (
    ACTIVITY_RESPONSES,
    activity_summaries,
    parse_local_datetime,
    published_activities,
    replace_respondent_activity_responses,
)
from rsvp_integrity import (
    RSVPWriteConflict,
    compare_and_swap_event,
    find_community_member_by_email,
    public_respondent_identity,
)

router = APIRouter(prefix="/api/public")


class PublicRSVPRequest(BaseModel):
    status: Literal["going", "some", "maybe", "not-going"]
    guests: int = Field(default=0, ge=0, le=50)
    activity_responses: dict[str, Literal["coming", "not-coming", "maybe"]] = Field(default_factory=dict)


async def _find_event_and_invite(token: str):
    event = await events_collection.find_one({"event_invites.id": token}, {"_id": 0})
    if not event:
        return None, None
    invite = next((i for i in event.get("event_invites", []) if i.get("id") == token), None)
    return event, invite


def _invitation_token(authorization: str | None) -> str:
    scheme, _, token = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This invitation requires a private link.",
        )
    return token.strip()


def _public_view(event: dict, invite: dict) -> dict:
    fmt = event.get("gathering_format", "in-person")
    summaries = activity_summaries(event)
    invite_respondent_id, respondent_aliases = public_respondent_identity(invite)
    own_activity_responses = {
        response.get("activity_id", ""): response.get("status", "")
        for response in event.get("activity_rsvps", [])
        if response.get("respondent_id") in respondent_aliases
    }
    activities = []
    for activity in published_activities(event):
        activity_id = activity.get("id", "")
        deadline = parse_local_datetime(
            activity.get("rsvp_deadline", ""),
            activity.get("timezone") or event.get("timezone", "UTC"),
        )
        deadline_value = activity.get("rsvp_deadline", "")
        response_open = (
            not deadline_value
            or bool(deadline and datetime.now(timezone.utc) <= deadline)
        )
        activities.append({
            "id": activity_id,
            "title": activity.get("title", ""),
            "description": activity.get("description", ""),
            "start_at": activity.get("start_at", ""),
            "end_at": activity.get("end_at", ""),
            "timezone": activity.get("timezone") or event.get("timezone", "UTC"),
            "venue_name": activity.get("venue_name", ""),
            "venue_address": activity.get("venue_address", ""),
            "venue_detail": activity.get("venue_detail", ""),
            "map_url": activity.get("map_url", ""),
            "virtual_link": activity.get("virtual_link", ""),
            "location_tba": bool(activity.get("location_tba", False)),
            "capacity": activity.get("capacity"),
            "rsvp_deadline": activity.get("rsvp_deadline", ""),
            "response_open": response_open,
            "attendance_requested": bool(activity.get("attendance_requested", True)),
            "notes": activity.get("notes", ""),
            "featured": bool(activity.get("featured", False)),
            "attendance": summaries.get(activity_id, {}),
            "my_response": own_activity_responses.get(activity_id, "no-response"),
        })
    return {
        "invitee_name": invite.get("invitee_name", ""),
        "rsvp_status": invite.get("rsvp_status", "pending"),
        "gathering": {
            "title": event.get("title", ""),
            "start_at": event.get("start_at", ""),
            "end_at": event.get("end_at", ""),
            "timezone": event.get("timezone", "UTC"),
            "location": event.get("location", ""),
            "gathering_format": fmt,
            "zoom_link": event.get("zoom_link", "") if fmt in {"online", "hybrid"} else "",
            "description": event.get("description", ""),
            "event_template": event.get("event_template", "custom"),
            "activity_count": len(activities),
            "activities": activities,
        },
    }


async def _public_rsvp_view(token: str):
    """Minimal gathering + invite info for a held invitation token."""
    event, invite = await _find_event_and_invite(token)
    if not event or not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invitation link is not valid.")
    community = await communities_collection.find_one(
        {"id": event.get("community_id")}, {"_id": 0, "name": 1}
    )
    view = _public_view(event, invite)
    view["community_name"] = community.get("name", "") if community else ""
    organizer = await users_collection.find_one(
        {"id": event.get("created_by"), "community_id": event.get("community_id")},
        {"_id": 0, "full_name": 1},
    )
    view["invited_by_name"] = (
        event.get("created_by_name")
        or (organizer or {}).get("full_name", "")
    )
    return view


async def _public_rsvp_submit(token: str, payload: PublicRSVPRequest):
    """Set the RSVP for this one invitation token."""
    event, invite = await _find_event_and_invite(token)
    if not event or not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invitation link is not valid.")
    resolved_member_id = invite.get("member_id", "")
    if (
        not resolved_member_id
        and invite.get("invite_source") == "member"
        and invite.get("email")
    ):
        member = await find_community_member_by_email(
            users_collection,
            event.get("community_id", ""),
            invite.get("email", ""),
        )
        resolved_member_id = (member or {}).get("id", "")

    def mutate(current_event: dict) -> dict:
        current_invite = next(
            (
                item for item in current_event.get("event_invites", [])
                if item.get("id") == token
            ),
            None,
        )
        if not current_invite:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invitation link is not valid.")
        if resolved_member_id and current_invite.get("invite_source") == "member":
            current_invite["member_id"] = resolved_member_id
        rsvp_uid, respondent_aliases = public_respondent_identity(current_invite)

        next_records = [
            record for record in current_event.get("rsvp_records", [])
            if record.get("user_id") not in respondent_aliases
        ]
        next_records.append({
            "user_id": rsvp_uid,
            "user_name": current_invite.get("invitee_name", "Guest"),
            "status": payload.status,
            "guests": max(0, payload.guests),
            "updated_at": now_iso(),
            "via": "public-link",
        })
        current_invite["rsvp_status"] = payload.status

        published_by_id = {
            item.get("id"): item for item in published_activities(current_event)
            if item.get("attendance_requested", True)
        }
        invalid_activity_ids = [
            activity_id for activity_id, response in payload.activity_responses.items()
            if activity_id not in published_by_id or response not in ACTIVITY_RESPONSES
        ]
        if invalid_activity_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "invalid_activity_response",
                    "message": "One or more activity responses are unavailable.",
                },
            )

        existing_own_responses = {
            response.get("activity_id"): response.get("status")
            for response in current_event.get("activity_rsvps", [])
            if response.get("respondent_id") in respondent_aliases
        }
        for activity_id, response in payload.activity_responses.items():
            activity = published_by_id[activity_id]
            deadline_value = activity.get("rsvp_deadline", "")
            deadline = parse_local_datetime(
                deadline_value,
                activity.get("timezone") or current_event.get("timezone", "UTC"),
            )
            if deadline_value and (
                not deadline
                or (
                    datetime.now(timezone.utc) > deadline
                    and existing_own_responses.get(activity_id) != response
                )
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "activity_rsvp_closed",
                        "message": "One or more activities are not accepting RSVP changes.",
                    },
                )

        replacement_activity_responses = [
            {
                "activity_id": activity_id,
                "respondent_id": rsvp_uid,
                "respondent_type": "member" if resolved_member_id else "public-invite",
                "display_name": current_invite.get("invitee_name", "Invited guest"),
                "status": response_status,
                "party_size": max(1, payload.guests + 1),
                "updated_at": now_iso(),
                "via": "public-link",
            }
            for activity_id, response_status in payload.activity_responses.items()
        ]
        activity_responses = replace_respondent_activity_responses(
            current_event.get("activity_rsvps", []),
            rsvp_uid,
            replacement_activity_responses,
            respondent_aliases,
        )
        current_event["rsvp_records"] = next_records
        current_event["activity_rsvps"] = activity_responses
        summaries = activity_summaries(current_event)
        return {
            "rsvp_records": next_records,
            "event_invites": current_event.get("event_invites", []),
            "activity_rsvps": activity_responses,
            "activity_rsvp_summaries": summaries,
        }

    try:
        event = await compare_and_swap_event(
            events_collection,
            {"id": event["id"], "event_invites.id": token},
            mutate,
        )
    except RSVPWriteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "rsvp_write_conflict", "message": str(exc)},
        ) from exc
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invitation link is not valid.")
    invite = next(
        item for item in event.get("event_invites", []) if item.get("id") == token
    )

    community = await communities_collection.find_one(
        {"id": event.get("community_id")}, {"_id": 0, "name": 1}
    )
    view = _public_view(event, {**invite, "rsvp_status": payload.status})
    view["community_name"] = community.get("name", "") if community else ""
    organizer = await users_collection.find_one(
        {"id": event.get("created_by"), "community_id": event.get("community_id")},
        {"_id": 0, "full_name": 1},
    )
    view["invited_by_name"] = (
        event.get("created_by_name")
        or (organizer or {}).get("full_name", "")
    )
    view["saved"] = True
    return view


@router.get("/rsvp")
async def secure_public_rsvp_view(authorization: str | None = Header(default=None)):
    """Read an invitation using an Authorization header, never a request URL."""
    return await _public_rsvp_view(_invitation_token(authorization))


@router.post("/rsvp")
async def secure_public_rsvp_submit(
    payload: PublicRSVPRequest,
    authorization: str | None = Header(default=None),
):
    """Update an invitation using an Authorization header, never a request URL."""
    return await _public_rsvp_submit(_invitation_token(authorization), payload)


async def public_rsvp_view(token: str):
    """Internal compatibility helper; intentionally not exposed as an API route."""
    return await _public_rsvp_view(token)


async def public_rsvp_submit(token: str, payload: PublicRSVPRequest):
    """Internal compatibility helper; intentionally not exposed as an API route."""
    return await _public_rsvp_submit(token, payload)


# ---------------------------------------------------------------------------
# Weekly digest one-click unsubscribe / resubscribe (no auth; token-based).
# Linked from the digest email footer. The token is a per-user opaque value.
# ---------------------------------------------------------------------------

def _digest_pref_page(title: str, message: str, action_label: str, action_href: str, *, post_action: str = "") -> str:
    # If post_action is set, render a real POST form button (the action MUTATES state and
    # must not run on a bare GET — email clients and security scanners prefetch GET links).
    # Otherwise render a plain link (navigation only, safe to prefetch).
    if post_action:
        action_html = (
            f'<form method="post" action="{post_action}" style="margin:0;">'
            f'<button type="submit" style="cursor:pointer;border:0;border-radius:999px;'
            f'background:#9A3412;color:#fff;font-size:15px;font-weight:600;padding:12px 28px;">'
            f'{action_label}</button></form>'
        )
    else:
        action_html = f'<a href="{action_href}" style="display:inline-block;font-size:14px;color:#9A3412;text-decoration:underline;">{action_label}</a>'
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Kindred</title></head>
<body style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9f5f0;">
<div style="max-width:480px;margin:64px auto;background:#fff;border:1px solid #e8e0d8;border-radius:16px;padding:40px 32px;text-align:center;">
<p style="font-size:13px;letter-spacing:.2em;text-transform:uppercase;color:#9A3412;margin:0 0 12px;">Kindred</p>
<h1 style="font-size:24px;color:#2d1810;margin:0 0 12px;">{title}</h1>
<p style="font-size:16px;line-height:1.6;color:#5a4a3a;margin:0 0 24px;">{message}</p>
{action_html}
</div></body></html>"""


@router.get("/digest/unsubscribe/{token}", response_class=HTMLResponse)
async def digest_unsubscribe_confirm(token: str):
    """Show a confirmation page. Does NOT change anything — a bare GET (prefetched by mail
    clients and link scanners) must never silently unsubscribe someone."""
    user = await users_collection.find_one({"digest_unsubscribe_token": token}, {"_id": 0, "id": 1})
    if not user:
        return HTMLResponse(_digest_pref_page(
            "Link not recognized",
            "This unsubscribe link is no longer valid. You can manage notifications inside the app.",
            "Open Kindred", "https://www.heykindred.org",
        ), status_code=404)
    return HTMLResponse(_digest_pref_page(
        "Unsubscribe from the weekly digest?",
        "Confirm below and you'll stop receiving the weekly community digest.",
        "Unsubscribe me", "", post_action=f"/api/public/digest/unsubscribe/{token}",
    ))


@router.post("/digest/unsubscribe/{token}", response_class=HTMLResponse)
async def digest_unsubscribe(token: str):
    """Opt this user out of weekly digests. Triggered by the confirm-page button (POST)."""
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
        "Re-subscribe", "", post_action=f"/api/public/digest/resubscribe/{token}",
    ))


@router.post("/digest/resubscribe/{token}", response_class=HTMLResponse)
async def digest_resubscribe(token: str):
    """Re-enable weekly digests for this user (POST from the unsubscribe-success page)."""
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
