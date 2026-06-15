"""Gathering Intelligence Layer — the Ubuntu Guide that plans and remembers.

Two capabilities, both built on litellm (Gemini via OPENAI_API_KEY/GEMINI_MODEL) with
graceful heuristic fallbacks so they degrade rather than fail when no key is set:

- generate_gathering_plan: turn a one-sentence ask ("plan our August reunion") into a
  structured, ready-to-create gathering (agenda, volunteer slots, potluck, focus).
- generate_community_history: weave the community's memories, stories, and gatherings into
  a warm, narrated chronicle.

It only ever phrases/structures what it's given — it never invents real people or events.
"""

import json
import re

import litellm

PLAN_SYSTEM = """
You are the Ubuntu Steward planning a gathering for a private community on Kindred.
Warm, practical, rooted in Ubuntu ("I am because we are"). Return ONLY compact JSON:
{"title": "...", "description": "...", "special_focus": "...", "when_hint": "...",
 "agenda": [{"time_label": "...", "title": "...", "notes": "..."}],
 "volunteer_slots": [{"title": "...", "needed_count": 3}],
 "potluck_items": ["..."]}
Rules:
- title: short and warm. description: 1-2 sentences. special_focus: a few words.
- when_hint: a human note about timing if the ask implies one, else "".
- 3-6 agenda items in a sensible order; 2-5 volunteer slots with realistic needed_count;
  4-8 potluck items fitting the community type. Keep everything concrete and doable.
- Never invent specific real names. Tailor to the community type (family, church, etc.).
""".strip()

HISTORY_SYSTEM = """
You are the Ubuntu Steward, the keeper of a community's story on Kindred. From the memories,
stories, and gatherings provided, write a warm, flowing chronicle the community could read
aloud at a gathering. 2-4 short paragraphs. Honor elders and milestones. Use ONLY what is
provided — never invent names, dates, or events. Plain, heartfelt prose. Return plain text.
""".strip()


def _clean_json(raw: str) -> dict:
    s = (raw or "").strip()
    s = re.sub(r"^```json", "", s)
    s = re.sub(r"^```", "", s)
    s = re.sub(r"```$", "", s)
    return json.loads(s.strip())


def _plan_fallback(ctx: dict) -> dict:
    ctype = (ctx.get("community_type") or "community").lower()
    prompt = (ctx.get("prompt") or "a gathering").strip()
    is_church = "church" in ctype or "ministry" in ctype
    is_family = "family" in ctype or "reunion" in ctype
    return {
        "title": prompt[:60].strip().title() or "Our Next Gathering",
        "description": f"A gathering for {ctx.get('community_name', 'our community')}: {prompt}.",
        "special_focus": "togetherness",
        "when_hint": "",
        "agenda": [
            {"time_label": "Arrival", "title": "Welcome & gathering in", "notes": "Greet everyone as they arrive."},
            {"time_label": "Opening", "title": "Opening words" + (" & prayer" if is_church else ""), "notes": "Set the tone together."},
            {"time_label": "Main", "title": "Shared meal" if is_family else "Main program", "notes": "The heart of the gathering."},
            {"time_label": "Closing", "title": "Reflections & farewell", "notes": "Close with gratitude."},
        ],
        "volunteer_slots": [
            {"title": "Setup crew", "needed_count": 3},
            {"title": "Food coordination", "needed_count": 2},
            {"title": "Cleanup crew", "needed_count": 3},
        ],
        "potluck_items": (
            ["Main dish", "Side dish", "Salad", "Dessert", "Drinks", "Bread"] if is_family
            else ["Refreshments", "Snacks", "Desserts", "Drinks"]
        ),
    }


async def generate_gathering_plan(api_key: str, model: str, ctx: dict) -> dict:
    """Return a structured gathering plan for the ask in ctx['prompt']. Never raises."""
    fallback = _plan_fallback(ctx)
    if not api_key or not model:
        return fallback
    try:
        user_payload = json.dumps({
            "ask": ctx.get("prompt", ""),
            "community_name": ctx.get("community_name", ""),
            "community_type": ctx.get("community_type", ""),
            "recent_gatherings": ctx.get("recent_gatherings", []),
        })
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": user_payload}],
            system_prompt=PLAN_SYSTEM,
            api_key=api_key,
            temperature=0.6,
        )
        data = _clean_json(resp.choices[0].message.content)
        if not isinstance(data, dict) or not data.get("title"):
            return fallback
        # Sanitize shapes so the caller can trust them.
        agenda = [
            {"time_label": str(a.get("time_label", "")), "title": str(a.get("title", "")), "notes": str(a.get("notes", ""))}
            for a in (data.get("agenda") or []) if isinstance(a, dict) and a.get("title")
        ][:8]
        slots = [
            {"title": str(s.get("title", "")), "needed_count": int(s.get("needed_count", 1) or 1)}
            for s in (data.get("volunteer_slots") or []) if isinstance(s, dict) and s.get("title")
        ][:8]
        potluck = [str(p) for p in (data.get("potluck_items") or []) if str(p).strip()][:12]
        return {
            "title": str(data.get("title", "")).strip()[:120] or fallback["title"],
            "description": str(data.get("description", "")).strip(),
            "special_focus": str(data.get("special_focus", "")).strip()[:80],
            "when_hint": str(data.get("when_hint", "")).strip(),
            "agenda": agenda or fallback["agenda"],
            "volunteer_slots": slots or fallback["volunteer_slots"],
            "potluck_items": potluck or fallback["potluck_items"],
        }
    except Exception:
        return fallback


def _history_fallback(ctx: dict) -> str:
    name = ctx.get("community_name", "our community")
    mems = ctx.get("memories", [])
    stories = ctx.get("stories", [])
    gatherings = ctx.get("gatherings", [])
    bits = [f"The story of {name} is still being written, and it is already rich."]
    if gatherings:
        bits.append("We have gathered for " + ", ".join(g for g in gatherings[:5] if g) + " — each one a thread in our shared cloth.")
    if mems:
        bits.append("We hold memories like " + ", ".join(m for m in mems[:5] if m) + ".")
    if stories:
        bits.append("And our elders and members have preserved stories: " + ", ".join(s for s in stories[:5] if s) + ".")
    bits.append("I am because we are.")
    return " ".join(bits)


async def generate_community_history(api_key: str, model: str, ctx: dict) -> str:
    """Return a narrated chronicle from the community's archive. Never raises."""
    fallback = _history_fallback(ctx)
    if not api_key or not model:
        return fallback
    try:
        user_payload = json.dumps({
            "community_name": ctx.get("community_name", ""),
            "community_type": ctx.get("community_type", ""),
            "gatherings": ctx.get("gatherings", []),
            "memories": ctx.get("memories", []),
            "stories": ctx.get("stories", []),
        })
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": user_payload}],
            system_prompt=HISTORY_SYSTEM,
            api_key=api_key,
            temperature=0.7,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or fallback
    except Exception:
        return fallback
