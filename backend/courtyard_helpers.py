import calendar
import uuid
from datetime import datetime, timedelta, timezone


ROLE_TOOLING = {
    "organizer": ["Gathering planner", "RSVP oversight", "Checklist ownership"],
    "treasurer": ["Budget tracking", "Contribution visibility", "Travel payment coordination"],
    "historian": ["Timeline archive", "Story preservation", "Memory curation"],
    "communications lead": ["Announcements", "Invite reminders", "Cross-subyard updates"],
    "elder": ["Guidance prompts", "Kinship visibility", "Reflection threads"],
    "contributor": ["Volunteer signups", "Potluck claims", "Upload privileges"],
}


# ── Community Operating System: composable modules ──────────────────────────
# Each community type gets a tuned default shape. Stewards can toggle from there.
# Home, Activity, Courtyards, Members, Subscription, Settings, and Community Setup
# are always on (the spine) and are NOT in this catalog.
MODULE_CATALOG = [
    {"key": "gatherings", "label": "Gatherings", "blurb": "Plan events with agendas, volunteers, potluck, travel."},
    {"key": "care", "label": "Circle of Care", "blurb": "Meal trains, check-ins, milestones."},
    {"key": "legacy_threads", "label": "Legacy Threads", "blurb": "Oral histories, sermons, family lore."},
    {"key": "kinship", "label": "Kinship Map", "blurb": "Map relationships across generations."},
    {"key": "memory", "label": "Timeline & Memory", "blurb": "The living archive of photos and stories."},
    {"key": "polls", "label": "Polls", "blurb": "Gather the community's voice."},
    {"key": "funds", "label": "Funds & Travel", "blurb": "Dues, contributions, travel coordination."},
    {"key": "health", "label": "Community Health", "blurb": "Belonging and participation signals."},
    {"key": "steward", "label": "Ubuntu Guide", "blurb": "The AI community steward."},
]
ALL_MODULE_KEYS = [m["key"] for m in MODULE_CATALOG]

_DEFAULT_MODULES_BY_TYPE = {
    "family": ["gatherings", "care", "legacy_threads", "kinship", "memory", "funds", "polls", "steward", "health"],
    "reunion": ["gatherings", "care", "legacy_threads", "kinship", "memory", "funds", "polls", "steward", "health"],
    "church": ["gatherings", "care", "legacy_threads", "memory", "polls", "funds", "steward", "health"],
    "ministry": ["gatherings", "care", "legacy_threads", "memory", "polls", "funds", "steward", "health"],
    "greek": ["gatherings", "funds", "polls", "kinship", "memory", "steward", "health", "care"],
    "fraternity": ["gatherings", "funds", "polls", "kinship", "memory", "steward", "health", "care"],
    "sorority": ["gatherings", "funds", "polls", "kinship", "memory", "steward", "health", "care"],
}


def default_modules_for_type(community_type: str) -> list[str]:
    """The recommended module shape for a community type. Unknown types → everything on."""
    t = (community_type or "").lower()
    for key, mods in _DEFAULT_MODULES_BY_TYPE.items():
        if key in t:
            return list(mods)
    return list(ALL_MODULE_KEYS)


def resolve_modules(community: dict) -> list[str]:
    """A community's enabled modules: its saved config, else the type default."""
    mods = community.get("modules")
    if isinstance(mods, list) and mods:
        return [m for m in mods if m in ALL_MODULE_KEYS]
    return default_modules_for_type(community.get("community_type", ""))


def build_default_subyards(community_type: str) -> list[dict]:
    normalized = (community_type or "").lower()
    if "church" in normalized:
        return [
            {
                "name": "Ministry Leaders",
                "description": "Planning and communications for ministry-wide gatherings.",
                "role_focus": ["organizer", "communications lead"],
            },
            {
                "name": "Elders Council",
                "description": "Prayer, care, and intergenerational guidance.",
                "role_focus": ["elder", "historian"],
            },
            {
                "name": "Youth Circle",
                "description": "Youth reflections, support, and program flow.",
                "role_focus": ["contributor", "communications lead"],
            },
        ]

    if "family" in normalized or "reunion" in normalized:
        return [
            {
                "name": "Cousins Circle",
                "description": "Social planning, games, and shared memory moments.",
                "role_focus": ["organizer", "contributor"],
            },
            {
                "name": "Elders Council",
                "description": "Ancestral storytelling, blessings, and oral history care.",
                "role_focus": ["elder", "historian"],
            },
            {
                "name": "Reunion Planning Team",
                "description": "Travel, budget, and logistics for the main gathering.",
                "role_focus": ["organizer", "treasurer", "communications lead"],
            },
        ]

    return [
        {
            "name": "Core Organizers",
            "description": "Main logistics and planning group for the courtyard.",
            "role_focus": ["organizer", "communications lead"],
        },
        {
            "name": "Memory Keepers",
            "description": "Stories, archives, and documentation for the group.",
            "role_focus": ["historian", "elder"],
        },
        {
            "name": "Travel Circle",
            "description": "Shared travel, stay planning, and pooled coordination.",
            "role_focus": ["treasurer", "contributor"],
        },
    ]


def build_role_suggestions(event_template: str) -> list[str]:
    template = (event_template or "general").lower()
    mapping = {
        "reunion": ["organizer", "historian", "treasurer", "communications lead"],
        "family-reunion": ["organizer", "historian", "elder", "treasurer"],
        "church-gathering": ["organizer", "communications lead", "elder", "historian"],
        "holiday": ["organizer", "contributor", "historian"],
        "holiday_meal": ["organizer", "contributor", "historian"],
        "wedding": ["organizer", "treasurer", "communications lead"],
        "birthday": ["organizer", "historian", "contributor"],
    }
    return mapping.get(template, ["organizer", "historian", "contributor"])


def build_planning_checklist(event_template: str, gathering_format: str) -> list[dict]:
    template = (event_template or "general").lower()
    format_label = (gathering_format or "in-person").lower()

    administrative = [
        "Confirm RSVP flow and attendance target",
        "Finalize liability, waivers, or host approvals",
        "Confirm contribution or dues expectations",
    ]
    experience = [
        "Lock venue, food, decorations, and supplies",
        "Assign historian and memory capture roles",
        "Confirm welcome flow, opening remarks, or blessings",
    ]
    technology = [
        "Test livestream, hybrid setup, and recording plan",
        "Confirm map links and travel coordination info",
    ]
    promotion = [
        "Send invitations and reminders",
        "Share subyard-specific updates and assignments",
    ]
    post_event = [
        "Collect photos, reflections, and survey notes",
        "Archive highlights to the timeline",
    ]

    if template in {"reunion", "family-reunion"}:
        experience.append("Prepare family roll call or branch recognition moment")
        post_event.append("Publish reunion recap and memory highlights")
    if template == "church-gathering":
        experience.append("Assign ministry duties, speakers, and prayer leads")
        technology.append("Confirm sermon or testimony capture setup")
    if template == "wedding":
        administrative.append("Confirm seating, vendors, and ceremony timeline")
    if template == "birthday":
        experience.append("Confirm gifts, cake, and tribute moment")
    if template == "holiday_meal":
        experience.append("Review the editable meal schedule and contribution list")
        post_event.append("Invite optional recipe or food-tradition contributions")

    if format_label == "online":
        technology.append("Share access links and moderator responsibilities")
    if format_label == "hybrid":
        technology.append("Coordinate on-site and remote guest experience")

    items = []
    for category, titles in [
        ("administrative", administrative),
        ("experience", experience),
        ("technology", technology),
        ("promotion", promotion),
        ("post-event", post_event),
    ]:
        for title in titles:
            items.append(
                {
                    "id": str(uuid.uuid4()),
                    "category": category,
                    "title": title,
                    "completed": False,
                }
            )
    return items


def years_since(iso_value: str | None) -> int | None:
    if not iso_value:
        return None
    try:
        normalized = iso_value.replace("Z", "+00:00")
        then = datetime.fromisoformat(normalized)
        delta_days = (datetime.now(timezone.utc) - then).days
        return max(delta_days // 365, 0)
    except Exception:
        return None


def countdown_days(iso_value: str | None) -> int | None:
    if not iso_value:
        return None
    try:
        normalized = iso_value.replace("Z", "+00:00")
        then = datetime.fromisoformat(normalized)
        return (then - datetime.now(timezone.utc)).days
    except Exception:
        return None


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _add_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def build_recurring_dates(start_at: str, frequency: str, occurrence_count: int = 5) -> list[str]:
    try:
        base = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    except Exception:
        return []

    results: list[str] = []
    for step in range(occurrence_count):
        if frequency == "daily":
            computed = base + timedelta(days=step + 1)
        elif frequency == "weekly":
            computed = base + timedelta(weeks=step + 1)
        elif frequency == "monthly":
            computed = _add_months(base, step + 1)
        elif frequency == "yearly":
            computed = _add_years(base, step + 1)
        else:
            break
        results.append(computed.isoformat())
    return results
