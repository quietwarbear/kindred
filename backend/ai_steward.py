"""Ubuntu AI Guide — the community steward's warm-language layer.

Given deterministic signals computed in routes/steward.py (who's new, who's gone
quiet, a memory worth resurfacing, recent gatherings), this generates only the
WARM WORDING: a welcome, a nudge to reconnect, a gathering idea, and a reflection.
The facts are computed elsewhere; the LLM only phrases them, so the steward never
invents names or events. Falls back to gentle templates when no API key is set.

Ubuntu-centered: collective voice ("we", "our"), warm, never pushy; serves the
community's belonging, not engagement metrics. Mirrors ai_tagging.py's litellm use.
"""

import json
import re

import litellm

STEWARD_SYSTEM = """
You are the Ubuntu Steward for a private community platform called Kindred.
Your voice is warm, plain, and rooted in Ubuntu — "I am because we are." You speak
for the community ("we", "our"), never as a marketer, and you are gentle, never pushy.
You NEVER invent names, events, or facts that are not present in the input.
Return ONLY compact JSON in exactly this shape:
{"welcome_message": "...", "rediscover_note": "...", "gathering_idea": {"title": "...", "why": "..."}, "reflection": "..."}
Rules:
- welcome_message: 2-3 warm sentences welcoming the named new member by name. If no new member name is given, return "".
- rediscover_note: one warm sentence inviting the community to revisit the named memory or story. If none is given, return "".
- gathering_idea.title: a short, fitting name for a next gathering for this community type; why: one sentence.
- reflection: one short reflective question the community could sit with this week.
""".strip()


def _clean_json(raw: str) -> dict:
    s = (raw or "").strip()
    s = re.sub(r"^```json", "", s)
    s = re.sub(r"^```", "", s)
    s = re.sub(r"```$", "", s)
    return json.loads(s.strip())


def _fallback(ctx: dict) -> dict:
    name = (ctx.get("new_member_name") or "").strip()
    community = ctx.get("community_name") or "our community"
    ctype = (ctx.get("community_type") or "community").lower()
    rediscover = (ctx.get("rediscover_title") or "").strip()

    welcome = (
        f"Welcome to {community}, {name}. We're so glad you're here — this is a place "
        f"to gather, to remember, and to look out for one another."
    ) if name else ""

    rediscover_note = (
        f"Take a moment to revisit “{rediscover}” — some stories are worth holding again."
    ) if rediscover else ""

    if "church" in ctype or "ministry" in ctype:
        idea_title = "A Sunday fellowship"
    elif "family" in ctype or "reunion" in ctype:
        idea_title = "A family check-in"
    elif "greek" in ctype or "fraternit" in ctype or "sororit" in ctype:
        idea_title = "A chapter gathering"
    else:
        idea_title = "A community circle"

    return {
        "welcome_message": welcome,
        "rediscover_note": rediscover_note,
        "gathering_idea": {"title": idea_title, "why": "A simple, regular moment together keeps people close."},
        "reflection": "Who in our circle have we not heard from in a while?",
    }


async def generate_steward_notes(api_key: str, model: str, ctx: dict) -> dict:
    """Return the steward's warm wording for the given signals. Never raises."""
    fallback = _fallback(ctx)
    if not api_key or not model:
        return fallback

    try:
        user_payload = json.dumps({
            "community_name": ctx.get("community_name", ""),
            "community_type": ctx.get("community_type", ""),
            "new_member_name": ctx.get("new_member_name", ""),
            "quiet_member_names": ctx.get("quiet_member_names", []),
            "rediscover_title": ctx.get("rediscover_title", ""),
            "recent_gatherings": ctx.get("recent_gatherings", []),
        })

        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": user_payload}],
            system_prompt=STEWARD_SYSTEM,
            api_key=api_key,
            temperature=0.7,
        )
        data = _clean_json(response.choices[0].message.content)
        if not isinstance(data, dict):
            return fallback

        idea = data.get("gathering_idea")
        if not isinstance(idea, dict) or not idea.get("title"):
            idea = fallback["gathering_idea"]

        return {
            "welcome_message": (data.get("welcome_message") or fallback["welcome_message"]).strip(),
            "rediscover_note": (data.get("rediscover_note") or fallback["rediscover_note"]).strip(),
            "gathering_idea": {"title": str(idea.get("title", "")).strip(), "why": str(idea.get("why", "")).strip()},
            "reflection": (data.get("reflection") or fallback["reflection"]).strip(),
        }
    except Exception:
        return fallback
